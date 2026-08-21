import json
import os
import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional

app = FastAPI(
    title="CRM MVI - API de Auditoria",
    description="Motor de Auditoria Técnica e Comercial para Projetos de Marcenaria",
    version="1.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class PecaItem(BaseModel):
    descricao: str
    largura: float
    altura: float
    profundidade: float
    material: str
    fita_borda: Optional[str] = "Não especificada"
    ferragens: Optional[List[str]] = []

class AuditoriaRequest(BaseModel):
    nome_projeto: str
    ambiente: str
    valor_tabela_promob: float
    desconto_acrescimo_negociacao_pct: float = 0.0  # Ex: -5 para 5% desc, +10 para margem extra
    comissao_rt_porcentagem: float = 10.0  # Manual (0 a 10%)
    pecas: List[PecaItem]

@app.get("/")
def rota_status():
    return {"status": "online", "sistema": "CRM MVI Integrado"}

@app.post("/api/v1/auditor-promob", summary="Auditoria Técnica e Comercial MVI")
def auditar_projeto_promob(dados: AuditoriaRequest):
    gemini_key = os.getenv("GEMINI_API_KEY")
    if not gemini_key:
        raise HTTPException(
            status_code=500,
            detail="Chave GEMINI_API_KEY não configurada no Render."
        )

    # Cálculo financeiro do CRM antes de repassar à IA
    valor_venda_final = dados.valor_tabela_promob * (1 + (dados.desconto_acrescimo_negociacao_pct / 100))
    valor_rt = valor_venda_final * (dados.comissao_rt_porcentagem / 100)
    receita_liquida = valor_venda_final - valor_rt

    prompt_texto = f"""
    Você é o Auditor Técnico e Estrategista Comercial do sistema CRM MVI para marcenarias de alto padrão.

    DADOS DO PROJETO & NEGOCIAÇÃO COMERCIAL:
    - Projeto: {dados.nome_projeto}
    - Ambiente: {dados.ambiente}
    - Valor Base Tabela Promob (já inclui custos diretos, frete, montagem e comissão de vendedor): R$ {dados.valor_tabela_promob:.2f}
    - Ajuste Comercial de Negociação (%): {dados.desconto_acrescimo_negociacao_pct}%
    - Valor Final de Venda ao Cliente: R$ {valor_venda_final:.2f}
    - Comissão RT Arquiteto/Parceiro ({dados.comissao_rt_porcentagem}% inserido manual): R$ {valor_rt:.2f}
    - Receita Líquida do Projeto após RT: R$ {receita_liquida:.2f}

    LISTA TÉCNICA DE PEÇAS:
    {json.dumps([p.dict() for p in dados.pecas], indent=2, ensure_ascii=False)}

    Gere um parecer executivo contendo:
    1. **Parecer Comercial e RT:** Analise a saúde do fechamento considerando o ajuste percentual e o valor da RT inserido manualmente.
    2. **Auditoria Técnica de Produção:** Checagem rigorosa de espessuras de chapas vs vãos livres, ferragens críticas e proteção contra umidade.
    3. **Diretrizes para Produção e Fechamento:** Dicas de montagem, otimização de sobras e argumentos de alto padrão para venda.
    """

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent?key={gemini_key}"
    payload = {
        "contents": [
            {"parts": [{"text": prompt_texto}]}
        ]
    }
    
    try:
        response = requests.post(url, json=payload, timeout=40)
        
        if response.status_code != 200:
            raise HTTPException(status_code=500, detail=f"Erro na API Google: {response.text}")

        data = response.json()
        texto_ia = data["candidates"][0]["content"]["parts"][0]["text"]

        return {
            "status": "sucesso",
            "projeto": dados.nome_projeto,
            "ambiente": dados.ambiente,
            "resumo_financeiro": {
                "valor_tabela_promob": dados.valor_tabela_promob,
                "valor_venda_final": valor_venda_final,
                "valor_rt": valor_rt,
                "receita_liquida_projeto": receita_liquida
            },
            "analise_ia": texto_ia
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")

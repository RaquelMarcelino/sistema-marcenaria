import json
import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from google import genai

app = FastAPI(
    title="Sistema Marcenaria API",
    description="API para gestão de marcenarias com Auditoria Inteligente via Google Gemini",
    version="1.0.0"
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
    custo_total_estimado: float
    valor_venda_pretendido: float
    comissao_rt_porcentagem: float = 0.0
    pecas: List[PecaItem]

@app.get("/")
def rota_status():
    return {"status": "online", "motor_ia": "Google Gemini 2.5 Flash"}

@app.post("/api/v1/auditor-promob", summary="Auditar Projeto Promob")
def auditar_projeto_promob(dados: AuditoriaRequest):
    gemini_key = os.getenv("GEMINI_API_KEY")
    if not gemini_key:
        raise HTTPException(
            status_code=500,
            detail="Chave GEMINI_API_KEY não configurada nas variáveis de ambiente do Render."
        )

    prompt = f"""
    Você é um Auditor Especialista em Engenharia de Móveis Sob Medida, Marcenaria e Precificação Comercial.
    
    Analise tecnicamente o projeto a seguir:
    - Nome do Projeto: {dados.nome_projeto}
    - Ambiente: {dados.ambiente}
    - Custo Total Estimado: R$ {dados.custo_total_estimado:.2f}
    - Valor de Venda Pretendido: R$ {dados.valor_venda_pretendido:.2f}
    - Comissão RT/Parceiro: {dados.comissao_rt_porcentagem}%
    
    Lista de Peças e Engenharia:
    {json.dumps([p.dict() for p in dados.pecas], indent=2, ensure_ascii=False)}

    Forneça um parecer executivo e estruturado com:
    1. **Saúde Financeira e Margem:** Calcule o lucro bruto estimado em R$ e % descontando a RT e avalie se a margem está segura para o padrão de mercado sob medida.
    2. **Auditoria Técnica de Produção:** Aponte riscos em dimensões, proporções, ferragens ausentes ou fitas de borda não especificadas.
    3. **Recomendações Práticas:** Sugestões diretas para otimização de corte, montagem e fechamento de venda.
    """

    try:
        client = genai.Client(api_key=gemini_key)
        response = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=prompt,
        )
        return {
            "status": "sucesso",
            "projeto": dados.nome_projeto,
            "ambiente": dados.ambiente,
            "analise_ia": response.text
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao processar auditoria IA Gemini: {str(e)}"
        )

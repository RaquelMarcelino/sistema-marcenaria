import os
import json
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from openai import OpenAI

app = FastAPI(title="MVI Marcenaria AI Engine", version="2.0")

# Permite conexões do front-end
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Inicializa o cliente OpenAI
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Modelos de Dados
class PecaPromob(BaseModel):
    descricao: str
    largura: float
    altura: float
    profundidade: float
    material: str
    fita_borda: Optional[str] = "Não especificada"
    ferragens: Optional[List[str]] = []

class ProjetoAuditoriaRequest(BaseModel):
    nome_projeto: str
    ambiente: str
    custo_total_estimado: float
    valor_venda_pretendido: float
    comissao_rt_porcentagem: float
    pecas: List[PecaPromob]

@app.get("/")
def rota_status():
    return {"status": "online", "sistema": "MVI Marcenaria AI Engine v2.0"}

@app.post("/api/v1/auditor-promob")
async def auditar_projeto_promob(projeto: ProjetoAuditoriaRequest):
    """
    Inovação 1: Auditoria Inteligente de Engenharia, Margem e Inconsistências de Produção.
    """
    try:
        prompt_sistema = """
        Você é um Auditor Sênior de Engenharia Moveleira, Fábrica de Marcenaria e Finanças do Sistema MVI.
        Sua função é auditar a lista técnica de peças do Promob e os dados financeiros do projeto.
        
        Você DEVE retornar a resposta EXCLUSIVAMENTE em formato JSON com o seguinte schema:
        {
            "status_geral": "APROVADO" | "ALERTA" | "CRITICO",
            "pontuacao_conformidade": 0 a 100,
            "analise_financeira": {
                "markup_calculado": 0.0,
                "margem_liquida_estimada_porcentagem": 0.0,
                "status_margem": "SAUDAVEL" | "BAIXA" | "PREJUIZO",
                "parecer_rt": "string explicativa sobre a comissão do arquiteto"
            },
            "inconsistencias_engenharia": [
                "lista de itens com falta de fita de borda, ferragens incompatíveis ou usinagem incorreta"
            ],
            "sugestoes_otimizacao": [
                "dicas para reduzir desperdício de chapa MDF e agilizar montagem"
            ]
        }
        """

        dados_projeto_json = json.dumps(projeto.dict(), ensure_ascii=False)

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": prompt_sistema},
                {"role": "user", "content": f"Analise o seguinte projeto:\n{dados_projeto_json}"}
            ],
            temperature=0.2
        )

        resultado_ia = json.loads(response.choices[0].message.content)
        return {"sucesso": True, "resultado": resultado_ia}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao processar auditoria IA: {str(e)}")

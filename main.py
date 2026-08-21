import json
import os
import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import List, Optional

app = FastAPI(
    title="CRM MVI - Painel de Auditoria",
    description="Motor de Auditoria Técnica e Comercial para Projetos de Marcenaria",
    version="1.2.1"
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
    desconto_acrescimo_negociacao_pct: float = 0.0
    comissao_rt_porcentagem: float = 10.0
    pecas: List[PecaItem]

HTML_PAINEL = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CRM MVI - Auditoria Inteligente de Projetos</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap" rel="stylesheet">
    <style>
        * { box-sizing: border-box; font-family: 'Inter', sans-serif; margin: 0; padding: 0; }
        body { background: #0f172a; color: #f8fafc; padding: 30px 15px; }
        .container { max-width: 900px; margin: 0 auto; }
        .header { text-align: center; margin-bottom: 25px; }
        .header h1 { color: #38bdf8; font-size: 26px; font-weight: 700; margin-bottom: 6px; }
        .header p { color: #94a3b8; font-size: 14px; }
        .card { background: #1e293b; border-radius: 12px; padding: 24px; box-shadow: 0 10px 25px -5px rgba(0,0,0,0.3); margin-bottom: 20px; border: 1px solid #334155; }
        .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 15px; }
        .grid-3 { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 15px; }
        label { display: block; font-size: 13px; font-weight: 600; color: #cbd5e1; margin-bottom: 6px; }
        input, select, textarea { width: 100%; background: #0f172a; border: 1px solid #475569; color: #f8fafc; padding: 10px 12px; border-radius: 8px; font-size: 14px; outline: none; }
        input:focus, textarea:focus { border-color: #38bdf8; }
        .btn { background: #0284c7; color: #fff; border: none; padding: 14px 20px; border-radius: 8px; font-size: 15px; font-weight: 700; cursor: pointer; width: 100%; transition: 0.2s; margin-top: 10px; }
        .btn:hover { background: #0369a1; }
        .btn:disabled { background: #475569; cursor: not-allowed; }
        .finance-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-top: 15px; }
        .finance-card { background: #0f172a; padding: 14px; border-radius: 8px; text-align: center; border: 1px solid #334155; }
        .finance-card span { font-size: 12px; color: #94a3b8; display: block; margin-bottom: 4px; }
        .finance-card strong { font-size: 16px; color: #38bdf8; }
        .result-card { display: none; background: #1e293b; border-radius: 12px; padding: 24px; border: 1px solid #38bdf8; }
        .result-card h2 { font-size: 18px; color: #38bdf8; margin-bottom: 15px; display: flex; align-items: center; gap: 8px; }
        .result-content { background: #0f172a; padding: 20px; border-radius: 8px; font-size: 14px; line-height: 1.6; color: #e2e8f0; white-space: pre-wrap; max-height: 500px; overflow-y: auto; }
        @media (max-width: 768px) { .grid, .grid-3, .finance-row { grid-template-columns: 1fr; } }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Painel CRM MVI</h1>
            <p>Auditoria Técnica e Comercial de Marcenaria com IA</p>
        </div>

        <div class="card">
            <div class="grid" style="margin-bottom: 15px;">
                <div>
                    <label>Nome do Projeto</label>
                    <input type="text" id="nome_projeto" value="Cozinha Gourmet Studio">
                </div>
                <div>
                    <label>Ambiente</label>
                    <input type="text" id="ambiente" value="Cozinha">
                </div>
            </div>

            <div class="grid-3" style="margin-bottom: 15px;">
                <div>
                    <label>Tabela Promob (R$)</label>
                    <input type="number" id="valor_promob" value="28500" oninput="calcularPrevia()">
                </div>
                <div>
                    <label>Negociação / Desconto (%)</label>
                    <input type="number" id="desc_pct" value="-5" oninput="calcularPrevia()">
                </div>
                <div>
                    <label>RT Arquiteto / Parceiro (%)</label>
                    <input type="number" id="rt_pct" value="8" max="10" min="0" oninput="calcularPrevia()">
                </div>
            </div>

            <div class="finance-row">
                <div class="finance-card"><span>Tabela Promob</span><strong id="prev_promob">R$ 28.500,00</strong></div>
                <div class="finance-card"><span>Preço Final Fechado</span><strong id="prev_venda">R$ 27.075,00</strong></div>
                <div class="finance-card"><span>Comissão RT (R$)</span><strong id="prev_rt">R$ 2.166,00</strong></div>
                <div class="finance-card"><span>Receita Líquida Marcenaria</span><strong id="prev_liquido" style="color: #4ade80;">R$ 24.909,00</strong></div>
            </div>

            <div style="margin-top: 20px;">
                <label>Especificações das Peças / Móvel (Formato simplificado)</label>
                <textarea id="pecas_json" rows="6">{
  "descricao": "Armário Superior 2 Portas",
  "largura": 1200,
  "altura": 700,
  "profundidade": 350,
  "material": "MDF 18mm Louro Freijo",
  "fita_borda": "PVC 1mm",
  "ferragens": ["Pistao a gas 80N", "Dobradica amortecedor"]
}</textarea>
            </div>

            <button class="btn" id="btnAuditar" onclick="executarAuditoria()">⚡ Executar Auditoria Inteligente</button>
        </div>

        <div class="result-card" id="resultadoSecao">
            <h2>📋 Laudo da Auditoria Técnica & Comercial</h2>
            <div class="result-content" id="resultadoTexto"></div>
        </div>
    </div>

    <script>
        function calcularPrevia() {
            const promob = parseFloat(document.getElementById('valor_promob').value) || 0;
            const desc = parseFloat(document.getElementById('desc_pct').value) || 0;
            const rt = parseFloat(document.getElementById('rt_pct').value) || 0;

            const venda = promob * (1 + (desc / 100));
            const valorRt = venda * (rt / 100);
            const liquido = venda - valorRt;

            document.getElementById('prev_promob').innerText = 'R$ ' + promob.toLocaleString('pt-BR', {minimumFractionDigits: 2});
            document.getElementById('prev_venda').innerText = 'R$ ' + venda.toLocaleString('pt-BR', {minimumFractionDigits: 2});
            document.getElementById('prev_rt').innerText = 'R$ ' + valorRt.toLocaleString('pt-BR', {minimumFractionDigits: 2});
            document.getElementById('prev_liquido').innerText = 'R$ ' + liquido.toLocaleString('pt-BR', {minimumFractionDigits: 2});
        }

        async function executarAuditoria() {
            const btn = document.getElementById('btnAuditar');
            const resultadoSecao = document.getElementById('resultadoSecao');
            const resultadoTexto = document.getElementById('resultadoTexto');

            btn.disabled = true;
            btn.innerText = '⏳ Processando auditoria com IA...';
            resultadoSecao.style.display = 'none';

            let pecaObj;
            try {
                pecaObj = JSON.parse(document.getElementById('pecas_json').value);
            } catch(e) {
                alert('Por favor, revise o formato do texto das peças.');
                btn.disabled = false;
                btn.innerText = '⚡ Executar Auditoria Inteligente';
                return;
            }

            const pecasArray = Array.isArray(pecaObj) ? pecaObj : [pecaObj];

            const payload = {
                nome_projeto: document.getElementById('nome_projeto').value,
                ambiente: document.getElementById('ambiente').value,
                valor_tabela_promob: parseFloat(document.getElementById('valor_promob').value),
                desconto_acrescimo_negociacao_pct: parseFloat(document.getElementById('desc_pct').value),
                comissao_rt_porcentagem: parseFloat(document.getElementById('rt_pct').value),
                pecas: pecasArray
            };

            try {
                const response = await fetch('/api/v1/auditor-promob', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });

                const data = await response.json();
                if(response.ok) {
                    resultadoTexto.innerText = data.analise_ia;
                    resultadoSecao.style.display = 'block';
                } else {
                    alert('Erro: ' + (data.detail || 'Não foi possível auditar.'));
                }
            } catch(err) {
                alert('Erro de conexão: ' + err.message);
            } finally {
                btn.disabled = false;
                btn.innerText = '⚡ Executar Auditoria Inteligente';
            }
        }
    </script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
@app.get("/painel-get", response_class=HTMLResponse)
def painel_visual_mvi():
    return HTML_PAINEL

@app.post("/api/v1/auditor-promob", summary="Auditoria Técnica e Comercial MVI")
def auditar_projeto_promob(dados: AuditoriaRequest):
    gemini_key = os.getenv("GEMINI_API_KEY")
    if not gemini_key:
        raise HTTPException(
            status_code=500,
            detail="Chave GEMINI_API_KEY não configurada no Render."
        )

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
    1. Parecer Comercial e RT: Analise a saúde do fechamento considerando o ajuste percentual e o valor da RT inserido manualmente.
    2. Auditoria Técnica de Produção: Checagem rigorosa de espessuras de chapas vs vãos livres, ferragens críticas e proteção contra umidade.
    3. Diretrizes para Produção e Fechamento: Dicas de montagem, otimização de sobras e argumentos de alto padrão para venda.
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

from fastapi import FastAPI, Form, UploadFile, File, Response
from fastapi.responses import HTMLResponse, RedirectResponse
import xml.etree.ElementTree as ET
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
import io
import urllib.parse
import json
import sqlite3
from datetime import datetime, date

app = FastAPI(title="Sistema Marcenaria & Promob")
DB_PATH = "marcenaria.db"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS configuracoes (
                chave TEXT PRIMARY KEY,
                valor TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS orcamentos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                criado_em TEXT,
                cliente_nome TEXT,
                cliente_telefone TEXT,
                cliente_ambiente TEXT,
                prazo_entrega TEXT,
                total_custo REAL,
                markup REAL,
                preco_venda REAL,
                lucro REAL,
                items_json TEXT
            )
        """)
        cursor.execute("SELECT valor FROM configuracoes WHERE chave = 'precos'")
        if not cursor.fetchone():
            default_precos = {
                "mdf_m2": 65.0,
                "dobradica": 18.50,
                "corredica": 38.00,
                "fita_borda_m": 3.20,
                "puxador": 25.00,
                "outros_insumos": 15.00
            }
            cursor.execute("INSERT INTO configuracoes (chave, valor) VALUES ('precos', ?)", (json.dumps(default_precos),))
        conn.commit()

init_db()

def get_precos_config():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT valor FROM configuracoes WHERE chave = 'precos'")
        row = cursor.fetchone()
        if row:
            return json.loads(row["valor"])
    return {
        "mdf_m2": 65.0, "dobradica": 18.50, "corredica": 38.00,
        "fita_borda_m": 3.20, "puxador": 25.00, "outros_insumos": 15.00
    }

def set_precos_config(precos: dict):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO configuracoes (chave, valor) VALUES ('precos', ?)", (json.dumps(precos),))
        conn.commit()

# Sessão em memória para o rascunho de trabalho
CURRENT_DATA = {
    "user": "admin@marcenaria.com",
    "orcamento_id": None,
    "cliente_nome": "Cliente Exemplo",
    "cliente_telefone": "11999998888",
    "cliente_ambiente": "Cozinha Planejada",
    "prazo_entrega": "25 dias úteis",
    "total_custo": 0.0,
    "markup": 2.2,
    "items": []
}

LOGIN_HTML = """
<!DOCTYPE html>
<html lang="pt-br">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Marcenaria SaaS - Login</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-slate-900 text-slate-100 flex items-center justify-center min-h-screen p-4 font-sans">
    <div class="max-w-md w-full bg-slate-800 border border-slate-700 rounded-2xl p-8 shadow-2xl space-y-6">
        <div class="text-center space-y-2">
            <h1 class="text-2xl font-bold tracking-tight text-white">Marcenaria Pro SaaS</h1>
            <p class="text-xs text-slate-400">Gestão de Orçamentos Promob & Precificação DRE</p>
        </div>
        <form action="/painel" method="post" class="space-y-4">
            <div>
                <label class="block text-xs font-semibold text-slate-300 uppercase mb-1">E-mail</label>
                <input type="email" name="username" required value="admin@marcenaria.com" class="w-full px-4 py-2.5 bg-slate-900 border border-slate-700 rounded-lg text-sm focus:outline-none focus:border-sky-500 text-slate-200">
            </div>
            <div>
                <label class="block text-xs font-semibold text-slate-300 uppercase mb-1">Senha</label>
                <input type="password" name="password" required value="123456" class="w-full px-4 py-2.5 bg-slate-900 border border-slate-700 rounded-lg text-sm focus:outline-none focus:border-sky-500 text-slate-200">
            </div>
            <button type="submit" class="w-full py-3 bg-sky-600 hover:bg-sky-500 text-white font-semibold rounded-lg text-sm transition-colors shadow-lg shadow-sky-600/30">
                Acessar Painel de Controle
            </button>
        </form>
    </div>
</body>
</html>
"""

def calcular_custo_item(nome: str, largura_mm: float, altura_mm: float, qtd: int, precos: dict):
    n = nome.lower()
    if any(k in n for k in ["dobradiça", "dobradica", "hinge"]):
        custo_unit = precos.get("dobradica", 18.50)
        tipo = "Ferragem (Dobradiça)"
    elif any(k in n for k in ["corrediça", "corredica", "slide", "gaveta"]):
        custo_unit = precos.get("corredica", 38.00)
        tipo = "Ferragem (Corrediça)"
    elif any(k in n for k in ["puxador", "handle", "perfil alumínio"]):
        custo_unit = precos.get("puxador", 25.00)
        tipo = "Acessório (Puxador)"
    elif any(k in n for k in ["fita", "borda", "edge"]):
        custo_unit = precos.get("fita_borda_m", 3.20) * 2.0
        tipo = "Fita de Borda"
    elif largura_mm > 0 and altura_mm > 0:
        area_m2 = (largura_mm / 1000.0) * (altura_mm / 1000.0)
        custo_unit = max(area_m2 * precos.get("mdf_m2", 65.0), 12.0)
        tipo = "Chapa MDF / Painel"
    else:
        custo_unit = precos.get("outros_insumos", 15.00)
        tipo = "Insumo Geral"

    total = custo_unit * qtd
    return total, tipo

def render_dashboard(user: str, items=None, total_custo=0.0, markup=2.2, cliente_nome="Cliente Exemplo", cliente_telefone="11999998888", cliente_ambiente="Cozinha Planejada", prazo_entrega="25 dias úteis", precos=None, orcamento_id=None):
    items = items or []
    precos = precos or get_precos_config()
    
    # Listagem de Peças da Sessão Ativa
    rows_html = ""
    if items:
        for it in items:
            rows_html += f"""
            <tr class="border-b border-slate-800 hover:bg-slate-850">
                <td class="py-3 px-4 text-sm text-slate-200">
                    <span class="font-medium">{it.get('nome', 'Peça')}</span>
                    <span class="block text-[11px] text-sky-400">{it.get('tipo', 'Insumo')}</span>
                </td>
                <td class="py-3 px-4 text-sm text-center text-slate-400">{it.get('dimensoes', '-')}</td>
                <td class="py-3 px-4 text-sm text-center text-slate-300">{it.get('qtd', 1)}</td>
                <td class="py-3 px-4 text-sm text-right text-emerald-400 font-semibold">R$ {it.get('valor', 0.0):.2f}</td>
            </tr>
            """
    else:
        rows_html = """
        <tr>
            <td colspan="4" class="py-8 text-center text-sm text-slate-500">
                Nenhum arquivo importado ainda. Faça upload de um XML do Promob/Cutlist acima.
            </td>
        </tr>
        """

    pv_sugerido = total_custo * markup if total_custo > 0 else 0.0
    lucro = pv_sugerido - total_custo if total_custo > 0 else 0.0

    msg_zap = f"Olá {cliente_nome}! Segue o orçamento para o projeto {cliente_ambiente}: R$ {pv_sugerido:,.2f} com prazo de entrega de {prazo_entrega}."
    zap_url = f"https://api.whatsapp.com/send?phone=55{cliente_telefone}&text={urllib.parse.quote(msg_zap)}"

    # Histórico de Orçamentos do Banco de Dados
    historico_html = ""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, criado_em, cliente_nome, cliente_ambiente, preco_venda, total_custo, markup FROM orcamentos ORDER BY id DESC LIMIT 15")
        historico_rows = cursor.fetchall()
        
        if historico_rows:
            for h in historico_rows:
                historico_html += f"""
                <tr class="border-b border-slate-800 hover:bg-slate-800/40 text-xs">
                    <td class="py-3 px-4 text-slate-400 font-mono">#{h['id']}</td>
                    <td class="py-3 px-4 text-slate-300">{h['criado_em']}</td>
                    <td class="py-3 px-4 text-white font-medium">{h['cliente_nome']}</td>
                    <td class="py-3 px-4 text-slate-300">{h['cliente_ambiente']}</td>
                    <td class="py-3 px-4 text-right text-sky-400 font-bold">R$ {h['preco_venda']:,.2f}</td>
                    <td class="py-3 px-4 text-center">
                        <div class="flex items-center justify-center space-x-2">
                            <form action="/carregar-orcamento" method="post" class="inline">
                                <input type="hidden" name="orcamento_id" value="{h['id']}">
                                <button type="submit" class="px-2.5 py-1 bg-sky-600 hover:bg-sky-500 text-white rounded text-[11px] font-semibold">Abrir</button>
                            </form>
                            <a href="/gerar-pdf?id={h['id']}" class="px-2.5 py-1 bg-emerald-700 hover:bg-emerald-600 text-white rounded text-[11px] font-semibold">PDF</a>
                            <form action="/excluir-orcamento" method="post" class="inline" onsubmit="return confirm('Deseja excluir este orçamento?');">
                                <input type="hidden" name="orcamento_id" value="{h['id']}">
                                <button type="submit" class="px-2 py-1 bg-rose-700/60 hover:bg-rose-600 text-white rounded text-[11px]">✕</button>
                            </form>
                        </div>
                    </td>
                </tr>
                """
        else:
            historico_html = """
            <tr>
                <td colspan="6" class="py-6 text-center text-xs text-slate-500">
                    Nenhum orçamento salvo no histórico ainda. Salve o orçamento ativo abaixo.
                </td>
            </tr>
            """

    status_tag = f"<span class='text-xs bg-sky-950 border border-sky-700 text-sky-300 px-2.5 py-1 rounded-full'>Editando Orçamento #{orcamento_id}</span>" if orcamento_id else "<span class='text-xs bg-slate-800 border border-slate-700 text-slate-400 px-2.5 py-1 rounded-full'>Novo Orçamento em Rascunho</span>"

    return f"""
    <!DOCTYPE html>
    <html lang="pt-br">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Marcenaria SaaS - Painel</title>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-slate-950 text-slate-100 min-h-screen font-sans">
        <header class="bg-slate-900 border-b border-slate-800 px-6 py-4 flex items-center justify-between">
            <div class="flex items-center space-x-3">
                <div class="w-8 h-8 rounded-lg bg-sky-600 flex items-center justify-center font-bold text-white">M</div>
                <span class="font-bold text-lg text-white tracking-wide">Marcenaria Pro</span>
                {status_tag}
            </div>
            <div class="flex items-center space-x-4">
                <a href="/novo-orcamento" class="text-xs bg-sky-600 hover:bg-sky-500 text-white font-medium px-3 py-1.5 rounded-lg transition-colors">+ Novo Orçamento</a>
                <span class="text-xs text-slate-400">Usuário: <b class="text-sky-400">{user}</b></span>
                <a href="/" class="text-xs bg-slate-800 hover:bg-slate-700 px-3 py-1.5 rounded-lg text-slate-300 border border-slate-700">Sair</a>
            </div>
        </header>

        <main class="max-w-7xl mx-auto p-6 space-y-6">
            <!-- Cards de Resumo DRE -->
            <div class="grid grid-cols-1 md:grid-cols-3 gap-5">
                <div class="bg-slate-900 border border-slate-800 p-5 rounded-xl space-y-1 shadow-lg">
                    <p class="text-xs font-semibold text-slate-400 uppercase tracking-wider">Custo Insumos (XML Precificado)</p>
                    <p class="text-2xl font-bold text-white">R$ {total_custo:,.2f}</p>
                    <p class="text-xs text-slate-500">MDF, ferragens e fitas por valor unitário</p>
                </div>
                <div class="bg-slate-900 border border-slate-800 p-5 rounded-xl space-y-1 shadow-lg">
                    <p class="text-xs font-semibold text-slate-400 uppercase tracking-wider">Preço de Venda (Markup {markup:.1f}x)</p>
                    <p class="text-2xl font-bold text-sky-400">R$ {pv_sugerido:,.2f}</p>
                    <p class="text-xs text-slate-500">Valor orçado para a proposta</p>
                </div>
                <div class="bg-slate-900 border border-slate-800 p-5 rounded-xl space-y-1 shadow-lg">
                    <p class="text-xs font-semibold text-slate-400 uppercase tracking-wider">Margem Bruta Estimada</p>
                    <p class="text-2xl font-bold text-emerald-400">R$ {lucro:,.2f}</p>
                    <p class="text-xs text-slate-500">Lucro operacional projetado</p>
                </div>
            </div>

            <!-- Dados do Cliente -->
            <div class="bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-lg space-y-4">
                <div class="flex justify-between items-center border-b border-slate-800 pb-3">
                    <h2 class="text-base font-semibold text-white">👤 Dados do Cliente & Proposta</h2>
                    <span class="text-xs text-sky-400">Vinculado ao Banco, PDF e WhatsApp</span>
                </div>
                <form action="/salvar-cliente" method="post" class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                    <input type="hidden" name="user" value="{user}">
                    <div>
                        <label class="block text-xs font-medium text-slate-400 mb-1">Nome do Cliente</label>
                        <input type="text" name="cliente_nome" value="{cliente_nome}" required class="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-sm text-white focus:outline-none focus:border-sky-500">
                    </div>
                    <div>
                        <label class="block text-xs font-medium text-slate-400 mb-1">WhatsApp / Telefone</label>
                        <input type="text" name="cliente_telefone" value="{cliente_telefone}" required class="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-sm text-white focus:outline-none focus:border-sky-500">
                    </div>
                    <div>
                        <label class="block text-xs font-medium text-slate-400 mb-1">Ambiente / Projeto</label>
                        <input type="text" name="cliente_ambiente" value="{cliente_ambiente}" required class="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-sm text-white focus:outline-none focus:border-sky-500">
                    </div>
                    <div>
                        <label class="block text-xs font-medium text-slate-400 mb-1">Prazo de Entrega</label>
                        <div class="flex gap-2">
                            <input type="text" name="prazo_entrega" value="{prazo_entrega}" required class="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-sm text-white focus:outline-none focus:border-sky-500">
                            <button type="submit" class="px-4 py-2 bg-sky-600 hover:bg-sky-500 text-white rounded-lg text-xs font-semibold shrink-0">
                                Salvar
                            </button>
                        </div>
                    </div>
                </form>
            </div>

            <!-- Tabela de Precificação Individual de Insumos -->
            <div class="bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-lg space-y-4">
                <div class="flex justify-between items-center border-b border-slate-800 pb-3">
                    <h2 class="text-base font-semibold text-white">⚙️ Tabela de Custos Unitários por Insumo</h2>
                    <span class="text-xs text-slate-400">Gravado no Banco de Dados</span>
                </div>
                <form action="/salvar-precos" method="post" class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
                    <input type="hidden" name="user" value="{user}">
                    <div>
                        <label class="block text-[11px] font-medium text-slate-400 mb-1">MDF (m²)</label>
                        <input type="number" step="0.5" name="mdf_m2" value="{precos['mdf_m2']}" class="w-full px-2.5 py-1.5 bg-slate-950 border border-slate-700 rounded-lg text-xs text-white focus:outline-none focus:border-sky-500">
                    </div>
                    <div>
                        <label class="block text-[11px] font-medium text-slate-400 mb-1">Dobradiça (Un)</label>
                        <input type="number" step="0.5" name="dobradica" value="{precos['dobradica']}" class="w-full px-2.5 py-1.5 bg-slate-950 border border-slate-700 rounded-lg text-xs text-white focus:outline-none focus:border-sky-500">
                    </div>
                    <div>
                        <label class="block text-[11px] font-medium text-slate-400 mb-1">Corrediça (Par)</label>
                        <input type="number" step="0.5" name="corredica" value="{precos['corredica']}" class="w-full px-2.5 py-1.5 bg-slate-950 border border-slate-700 rounded-lg text-xs text-white focus:outline-none focus:border-sky-500">
                    </div>
                    <div>
                        <label class="block text-[11px] font-medium text-slate-400 mb-1">Fita Borda (m)</label>
                        <input type="number" step="0.1" name="fita_borda_m" value="{precos['fita_borda_m']}" class="w-full px-2.5 py-1.5 bg-slate-950 border border-slate-700 rounded-lg text-xs text-white focus:outline-none focus:border-sky-500">
                    </div>
                    <div>
                        <label class="block text-[11px] font-medium text-slate-400 mb-1">Puxador (Un)</label>
                        <input type="number" step="0.5" name="puxador" value="{precos['puxador']}" class="w-full px-2.5 py-1.5 bg-slate-950 border border-slate-700 rounded-lg text-xs text-white focus:outline-none focus:border-sky-500">
                    </div>
                    <div class="flex items-end">
                        <button type="submit" class="w-full py-2 bg-slate-800 hover:bg-slate-700 text-sky-400 border border-slate-700 rounded-lg text-xs font-semibold transition-colors">
                            Salvar Configuração
                        </button>
                    </div>
                </form>
            </div>

            <!-- Bloco de Upload + Markup + Salvar no Banco + PDF + WhatsApp -->
            <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <div class="lg:col-span-2 bg-slate-900 border border-slate-800 rounded-xl p-6 space-y-4 shadow-lg">
                    <h2 class="text-base font-semibold text-white">Importar Projeto (XML Promob / Cutlist)</h2>
                    <form action="/upload-xml" method="post" enctype="multipart/form-data" class="flex flex-col sm:flex-row items-center gap-4">
                        <input type="hidden" name="user" value="{user}">
                        <input type="file" name="file" accept=".xml,.txt" required class="block w-full text-xs text-slate-400 file:mr-4 file:py-2.5 file:px-4 file:rounded-lg file:border-0 file:text-xs file:font-semibold file:bg-slate-800 file:text-slate-200 hover:file:bg-slate-700 cursor-pointer">
                        <button type="submit" class="w-full sm:w-auto px-6 py-2.5 bg-sky-600 hover:bg-sky-500 text-white font-medium rounded-lg text-sm transition-colors shrink-0">
                            Processar e Orçar
                        </button>
                    </form>
                </div>

                <div class="bg-slate-900 border border-slate-800 rounded-xl p-6 flex flex-col justify-between space-y-4 shadow-lg">
                    <h2 class="text-base font-semibold text-white">Markup & Gravação</h2>
                    <form action="/recalcular" method="post" class="flex items-center gap-3">
                        <input type="hidden" name="user" value="{user}">
                        <label class="text-xs text-slate-400 font-medium">Markup:</label>
                        <input type="number" step="0.1" min="1.0" max="5.0" name="markup" value="{markup}" class="w-20 px-3 py-1.5 bg-slate-950 border border-slate-700 rounded-lg text-sm text-center text-white focus:outline-none focus:border-sky-500">
                        <button type="submit" class="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-lg text-xs font-semibold border border-slate-700">
                            Recalcular
                        </button>
                    </form>
                    
                    <div class="space-y-2">
                        <form action="/salvar-banco" method="post">
                            <button type="submit" class="w-full py-2 bg-blue-600 hover:bg-blue-500 text-white font-semibold text-center text-xs rounded-lg transition-colors flex items-center justify-center space-x-1 shadow-lg shadow-blue-600/20">
                                <span>💾 Salvar no Histórico (Banco)</span>
                            </button>
                        </form>
                        <a href="/gerar-pdf" class="w-full py-2 bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-center text-xs rounded-lg transition-colors flex items-center justify-center space-x-1 shadow-lg shadow-emerald-600/20">
                            <span>📄 Baixar Orçamento em PDF</span>
                        </a>
                        <a href="{zap_url}" target="_blank" class="w-full py-2 bg-green-600 hover:bg-green-500 text-white font-semibold text-center text-xs rounded-lg transition-colors flex items-center justify-center space-x-1 shadow-lg shadow-green-600/20">
                            <span>💬 Enviar pelo WhatsApp</span>
                        </a>
                    </div>
                </div>
            </div>

            <!-- Tabela de Histórico de Orçamentos Salvos -->
            <div class="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-lg">
                <div class="p-4 border-b border-slate-800 flex justify-between items-center bg-slate-850">
                    <h3 class="text-sm font-semibold text-white">📁 Histórico de Orçamentos Salvos (Banco de Dados)</h3>
                    <span class="text-xs text-slate-400">Clique em 'Abrir' para recarregar qualquer projeto</span>
                </div>
                <div class="overflow-x-auto">
                    <table class="w-full text-left border-collapse">
                        <thead>
                            <tr class="bg-slate-800/40 border-b border-slate-800 text-xs font-semibold text-slate-400 uppercase">
                                <th class="py-3 px-4"># ID</th>
                                <th class="py-3 px-4">Data/Hora</th>
                                <th class="py-3 px-4">Cliente</th>
                                <th class="py-3 px-4">Ambiente</th>
                                <th class="py-3 px-4 text-right">Valor Venda</th>
                                <th class="py-3 px-4 text-center">Ações</th>
                            </tr>
                        </thead>
                        <tbody>
                            {historico_html}
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- Listagem de Peças -->
            <div class="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-lg">
                <div class="p-4 border-b border-slate-800 flex justify-between items-center bg-slate-850">
                    <h3 class="text-sm font-semibold text-white">Listagem de Peças e Insumos ({cliente_ambiente})</h3>
                    <span class="text-xs text-slate-400">{len(items)} itens detectados</span>
                </div>
                <div class="overflow-x-auto">
                    <table class="w-full text-left border-collapse">
                        <thead>
                            <tr class="bg-slate-800/40 border-b border-slate-800 text-xs font-semibold text-slate-400 uppercase">
                                <th class="py-3 px-4">Descrição / Insumo</th>
                                <th class="py-3 px-4 text-center">Dimensões (mm)</th>
                                <th class="py-3 px-4 text-center">Quantidade</th>
                                <th class="py-3 px-4 text-right">Custo Est. (R$)</th>
                            </tr>
                        </thead>
                        <tbody>
                            {rows_html}
                        </tbody>
                    </table>
                </div>
            </div>
        </main>
    </body>
    </html>
    """

@app.get("/", response_class=HTMLResponse)
def home():
    return LOGIN_HTML

@app.post("/painel", response_class=HTMLResponse)
def login(username: str = Form(...), password: str = Form(...)):
    CURRENT_DATA["user"] = username
    return render_dashboard(
        user=username, 
        items=CURRENT_DATA["items"], 
        total_custo=CURRENT_DATA["total_custo"], 
        markup=CURRENT_DATA["markup"],
        cliente_nome=CURRENT_DATA["cliente_nome"],
        cliente_telefone=CURRENT_DATA["cliente_telefone"],
        cliente_ambiente=CURRENT_DATA["cliente_ambiente"],
        prazo_entrega=CURRENT_DATA["prazo_entrega"],
        orcamento_id=CURRENT_DATA["orcamento_id"]
    )

@app.get("/novo-orcamento", response_class=HTMLResponse)
def novo_orcamento():
    CURRENT_DATA["orcamento_id"] = None
    CURRENT_DATA["cliente_nome"] = "Novo Cliente"
    CURRENT_DATA["cliente_telefone"] = ""
    CURRENT_DATA["cliente_ambiente"] = "Ambiente Geral"
    CURRENT_DATA["prazo_entrega"] = "20 dias úteis"
    CURRENT_DATA["total_custo"] = 0.0
    CURRENT_DATA["markup"] = 2.2
    CURRENT_DATA["items"] = []
    return RedirectResponse(url="/painel-get", status_code=303)

@app.get("/painel-get", response_class=HTMLResponse)
def painel_get():
    return render_dashboard(
        user=CURRENT_DATA["user"],
        items=CURRENT_DATA["items"],
        total_custo=CURRENT_DATA["total_custo"],
        markup=CURRENT_DATA["markup"],
        cliente_nome=CURRENT_DATA["cliente_nome"],
        cliente_telefone=CURRENT_DATA["cliente_telefone"],
        cliente_ambiente=CURRENT_DATA["cliente_ambiente"],
        prazo_entrega=CURRENT_DATA["prazo_entrega"],
        orcamento_id=CURRENT_DATA["orcamento_id"]
    )

@app.post("/salvar-banco", response_class=HTMLResponse)
def salvar_banco():
    pv = CURRENT_DATA["total_custo"] * CURRENT_DATA["markup"]
    lucro = pv - CURRENT_DATA["total_custo"]
    agora = datetime.now().strftime("%d/%m/%Y %H:%M")
    
    with get_db() as conn:
        cursor = conn.cursor()
        if CURRENT_DATA["orcamento_id"]:
            cursor.execute("""
                UPDATE orcamentos SET
                    criado_em = ?,
                    cliente_nome = ?,
                    cliente_telefone = ?,
                    cliente_ambiente = ?,
                    prazo_entrega = ?,
                    total_custo = ?,
                    markup = ?,
                    preco_venda = ?,
                    lucro = ?,
                    items_json = ?
                WHERE id = ?
            """, (
                agora,
                CURRENT_DATA["cliente_nome"],
                CURRENT_DATA["cliente_telefone"],
                CURRENT_DATA["cliente_ambiente"],
                CURRENT_DATA["prazo_entrega"],
                CURRENT_DATA["total_custo"],
                CURRENT_DATA["markup"],
                pv,
                lucro,
                json.dumps(CURRENT_DATA["items"]),
                CURRENT_DATA["orcamento_id"]
            ))
        else:
            cursor.execute("""
                INSERT INTO orcamentos (criado_em, cliente_nome, cliente_telefone, cliente_ambiente, prazo_entrega, total_custo, markup, preco_venda, lucro, items_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                agora,
                CURRENT_DATA["cliente_nome"],
                CURRENT_DATA["cliente_telefone"],
                CURRENT_DATA["cliente_ambiente"],
                CURRENT_DATA["prazo_entrega"],
                CURRENT_DATA["total_custo"],
                CURRENT_DATA["markup"],
                pv,
                lucro,
                json.dumps(CURRENT_DATA["items"])
            ))
            CURRENT_DATA["orcamento_id"] = cursor.lastrowid
        conn.commit()

    return RedirectResponse(url="/painel-get", status_code=303)

@app.post("/carregar-orcamento", response_class=HTMLResponse)
def carregar_orcamento(orcamento_id: int = Form(...)):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM orcamentos WHERE id = ?", (orcamento_id,))
        row = cursor.fetchone()
        if row:
            CURRENT_DATA["orcamento_id"] = row["id"]
            CURRENT_DATA["cliente_nome"] = row["cliente_nome"]
            CURRENT_DATA["cliente_telefone"] = row["cliente_telefone"]
            CURRENT_DATA["cliente_ambiente"] = row["cliente_ambiente"]
            CURRENT_DATA["prazo_entrega"] = row["prazo_entrega"]
            CURRENT_DATA["total_custo"] = row["total_custo"]
            CURRENT_DATA["markup"] = row["markup"]
            CURRENT_DATA["items"] = json.loads(row["items_json"]) if row["items_json"] else []

    return RedirectResponse(url="/painel-get", status_code=303)

@app.post("/excluir-orcamento", response_class=HTMLResponse)
def excluir_orcamento(orcamento_id: int = Form(...)):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM orcamentos WHERE id = ?", (orcamento_id,))
        conn.commit()
    if CURRENT_DATA["orcamento_id"] == orcamento_id:
        CURRENT_DATA["orcamento_id"] = None
    return RedirectResponse(url="/painel-get", status_code=303)

@app.post("/salvar-cliente", response_class=HTMLResponse)
def salvar_cliente(
    user: str = Form("admin@marcenaria.com"),
    cliente_nome: str = Form(...),
    cliente_telefone: str = Form(...),
    cliente_ambiente: str = Form(...),
    prazo_entrega: str = Form(...)
):
    CURRENT_DATA["cliente_nome"] = cliente_nome
    CURRENT_DATA["cliente_telefone"] = cliente_telefone
    CURRENT_DATA["cliente_ambiente"] = cliente_ambiente
    CURRENT_DATA["prazo_entrega"] = prazo_entrega
    return RedirectResponse(url="/painel-get", status_code=303)

@app.post("/salvar-precos", response_class=HTMLResponse)
def salvar_precos(
    user: str = Form("admin@marcenaria.com"),
    mdf_m2: float = Form(65.0),
    dobradica: float = Form(18.50),
    corredica: float = Form(38.00),
    fita_borda_m: float = Form(3.20),
    puxador: float = Form(25.00)
):
    precos = {
        "mdf_m2": mdf_m2,
        "dobradica": dobradica,
        "corredica": corredica,
        "fita_borda_m": fita_borda_m,
        "puxador": puxador,
        "outros_insumos": 15.00
    }
    set_precos_config(precos)

    # Recalcular itens ativos
    novo_total = 0.0
    for it in CURRENT_DATA["items"]:
        valor_item, tipo = calcular_custo_item(it["nome"], it.get("largura", 0), it.get("altura", 0), it["qtd"], precos)
        it["valor"] = valor_item
        it["tipo"] = tipo
        novo_total += valor_item

    CURRENT_DATA["total_custo"] = novo_total
    return RedirectResponse(url="/painel-get", status_code=303)

@app.post("/recalcular", response_class=HTMLResponse)
def recalcular(user: str = Form("admin@marcenaria.com"), markup: float = Form(2.2)):
    CURRENT_DATA["markup"] = markup
    return RedirectResponse(url="/painel-get", status_code=303)

@app.post("/upload-xml", response_class=HTMLResponse)
async def upload_xml(user: str = Form("admin@marcenaria.com"), file: UploadFile = File(...)):
    contents = await file.read()
    items = []
    total_custo = 0.0
    precos = get_precos_config()

    try:
        root = ET.fromstring(contents)
        for elem in root.iter():
            if elem.tag.lower() in ["item", "piece", "peca", "component", "material"]:
                nome = str(elem.attrib.get("DESCRIPTION") or elem.attrib.get("nome") or elem.attrib.get("name") or elem.tag)
                try:
                    largura = float(elem.attrib.get("WIDTH") or elem.attrib.get("largura") or 0)
                    altura = float(elem.attrib.get("HEIGHT") or elem.attrib.get("altura") or 0)
                    prof = float(elem.attrib.get("DEPTH") or elem.attrib.get("profundidade") or 0)
                except Exception:
                    largura, altura, prof = 0, 0, 0

                qtd = int(elem.attrib.get("QUANTITY") or elem.attrib.get("quantidade") or 1)
                
                custo_total_item, tipo = calcular_custo_item(nome, largura, altura, qtd, precos)
                total_custo += custo_total_item

                items.append({
                    "nome": nome[:45],
                    "tipo": tipo,
                    "largura": largura,
                    "altura": altura,
                    "dimensoes": f"{int(largura)} x {int(altura)} x {int(prof)}" if largura > 0 else "-",
                    "qtd": qtd,
                    "valor": custo_total_item
                })

        if not items:
            items = [
                {"nome": "Dobradiça Ecco Ø35mm Slowmotion", "tipo": "Ferragem (Dobradiça)", "largura": 0, "altura": 0, "dimensoes": "-", "qtd": 22, "valor": 22 * precos["dobradica"]},
                {"nome": "Corrediça Telescópica 450mm", "tipo": "Ferragem (Corrediça)", "largura": 0, "altura": 0, "dimensoes": "450 mm", "qtd": 4, "valor": 4 * precos["corredica"]},
                {"nome": "Lateral MDF Branco TX 18mm", "tipo": "Chapa MDF / Painel", "largura": 2200, "altura": 600, "dimensoes": "2200 x 600 x 18", "qtd": 2, "valor": 2 * (2.2 * 0.6 * precos["mdf_m2"])},
                {"nome": "Fita de Borda PVC 22mm", "tipo": "Fita de Borda", "largura": 0, "altura": 0, "dimensoes": "-", "qtd": 15, "valor": 15 * precos["fita_borda_m"]}
            ]
            total_custo = sum(i["valor"] for i in items)

    except Exception:
        items = [
            {"nome": "Dobradiça Ø35mm Reta Slowmotion", "tipo": "Ferragem (Dobradiça)", "largura": 0, "altura": 0, "dimensoes": "-", "qtd": 10, "valor": 10 * precos["dobradica"]},
            {"nome": "Painel MDF Freijó 18mm", "tipo": "Chapa MDF / Painel", "largura": 1800, "altura": 800, "dimensoes": "1800 x 800 x 18", "qtd": 2, "valor": 2 * (1.8 * 0.8 * precos["mdf_m2"])}
        ]
        total_custo = sum(i["valor"] for i in items)

    CURRENT_DATA["items"] = items
    CURRENT_DATA["total_custo"] = total_custo
    return RedirectResponse(url="/painel-get", status_code=303)

@app.get("/gerar-pdf")
def gerar_pdf(id: int = None):
    # Se passou ID, busca o orçamento específico do banco; se não, usa a sessão atual
    if id:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM orcamentos WHERE id = ?", (id,))
            row = cursor.fetchone()
            if row:
                c_nome = row["cliente_nome"]
                c_tel = row["cliente_telefone"]
                c_amb = row["cliente_ambiente"]
                c_prazo = row["prazo_entrega"]
                custo = row["total_custo"]
                markup = row["markup"]
                pv = row["preco_venda"]
                lucro = row["lucro"]
                items = json.loads(row["items_json"]) if row["items_json"] else []
            else:
                return Response(content="Orçamento não encontrado", status_code=404)
    else:
        c_nome = CURRENT_DATA['cliente_nome']
        c_tel = CURRENT_DATA['cliente_telefone']
        c_amb = CURRENT_DATA['cliente_ambiente']
        c_prazo = CURRENT_DATA['prazo_entrega']
        custo = CURRENT_DATA["total_custo"]
        markup = CURRENT_DATA["markup"]
        pv = custo * markup
        lucro = pv - custo
        items = CURRENT_DATA["items"]

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    styles = getSampleStyleSheet()
    elements = []

    # Cabeçalho Principal
    title_style = ParagraphStyle(name='TitleStyle', parent=styles['Heading1'], fontSize=18, textColor=colors.HexColor('#0f172a'), spaceAfter=4)
    elements.append(Paragraph("Marcenaria Pro - Proposta Comercial & Orçamento", title_style))
    elements.append(Spacer(1, 8))

    # Dados do Cliente
    cliente_data = [
        ["Cliente:", c_nome, "Data da Proposta:", date.today().strftime("%d/%m/%Y")],
        ["WhatsApp/Tel:", c_tel, "Prazo de Entrega:", c_prazo],
        ["Ambiente/Projeto:", c_amb, "Validade da Proposta:", "15 dias"]
    ]
    cliente_table = Table(cliente_data, colWidths=[110, 160, 120, 150])
    cliente_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f1f5f9')),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#334155')),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
    ]))
    elements.append(cliente_table)
    elements.append(Spacer(1, 14))

    # Tabela DRE
    dre_data = [
        ["Custo Total de Materiais (XML Precificado)", f"R$ {custo:,.2f}"],
        ["Markup Aplicado", f"{markup:.1f}x"],
        ["VALOR TOTAL DA PROPOSTA", f"R$ {pv:,.2f}"],
        ["Margem Bruta Operacional Estimada", f"R$ {lucro:,.2f}"]
    ]
    dre_table = Table(dre_data, colWidths=[280, 260])
    dre_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
        ('BACKGROUND', (0, 2), (-1, 2), colors.HexColor('#dbeafe')),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#0f172a')),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
    ]))
    elements.append(dre_table)
    elements.append(Spacer(1, 14))

    # Tabela de Peças
    items = items or [{"nome": "Item Geral de Marcenaria", "dimensoes": "-", "qtd": 1, "valor": custo}]
    table_data = [["Item / Insumo Promob", "Dimensões (mm)", "Qtd", "Custo Total"]]
    for it in items:
        table_data.append([
            it.get("nome", "Peça"),
            it.get("dimensoes", "-"),
            str(it.get("qtd", 1)),
            f"R$ {it.get('valor', 0.0):,.2f}"
        ])

    items_table = Table(table_data, colWidths=[240, 140, 50, 110])
    items_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0284c7')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (2, 0), (2, -1), 'CENTER'),
        ('ALIGN', (3, 0), (3, -1), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
    ]))
    elements.append(items_table)

    doc.build(elements)
    buffer.seek(0)
    nome_arquivo = f"orcamento-{c_nome.replace(' ', '_')}.pdf"
    return Response(content=buffer.getvalue(), media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename={nome_arquivo}"})

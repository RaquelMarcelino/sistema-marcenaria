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
import math
from datetime import datetime, date, timedelta

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
            CREATE TABLE IF NOT EXISTS usuarios (
                email TEXT PRIMARY KEY,
                senha TEXT,
                nome TEXT,
                perfil TEXT
            )
        """)
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
                status TEXT DEFAULT 'Em Negociação',
                custo_materiais REAL,
                custo_mao_obra REAL,
                custo_frete_montagem REAL,
                imposto_pct REAL,
                comissao_pct REAL,
                markup REAL,
                preco_venda REAL,
                lucro_liquido REAL,
                entrada_valor REAL DEFAULT 0.0,
                num_parcelas INTEGER DEFAULT 1,
                forma_pagamento TEXT DEFAULT 'PIX / Transferência',
                items_json TEXT
            )
        """)
        
        # Migrações caso colunas não existam em bancos anteriores
        colunas = ["status", "entrada_valor", "num_parcelas", "forma_pagamento"]
        for col in colunas:
            try:
                cursor.execute(f"ALTER TABLE orcamentos ADD COLUMN {col} TEXT")
            except Exception:
                pass

        cursor.execute("SELECT email FROM usuarios WHERE email = 'admin@marcenaria.com'")
        if not cursor.fetchone():
            cursor.execute("INSERT INTO usuarios VALUES ('admin@marcenaria.com', '123456', 'Administrador', 'admin')")
            cursor.execute("INSERT INTO usuarios VALUES ('vendedor@marcenaria.com', '123456', 'Vendedor da Loja', 'vendedor')")

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

        cursor.execute("SELECT valor FROM configuracoes WHERE chave = 'dados_empresa'")
        if not cursor.fetchone():
            default_empresa = {
                "nome_empresa": "Marcenaria Pro Móveis Planejados",
                "cnpj": "00.000.000/0001-00",
                "telefone_empresa": "(11) 98888-7777",
                "pix": "contato@marcenaria.com"
            }
            cursor.execute("INSERT INTO configuracoes (chave, valor) VALUES ('dados_empresa', ?)", (json.dumps(default_empresa),))
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

def get_empresa_config():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT valor FROM configuracoes WHERE chave = 'dados_empresa'")
        row = cursor.fetchone()
        if row:
            return json.loads(row["valor"])
    return {
        "nome_empresa": "Marcenaria Pro Móveis Planejados",
        "cnpj": "00.000.000/0001-00",
        "telefone_empresa": "(11) 98888-7777",
        "pix": "contato@marcenaria.com"
    }

def set_empresa_config(dados: dict):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO configuracoes (chave, valor) VALUES ('dados_empresa', ?)", (json.dumps(dados),))
        conn.commit()

CURRENT_DATA = {
    "user": "admin@marcenaria.com",
    "user_perfil": "admin",
    "user_nome": "Administrador",
    "orcamento_id": None,
    "status": "Em Negociação",
    "cliente_nome": "Cliente Exemplo",
    "cliente_telefone": "11999998888",
    "cliente_ambiente": "Cozinha Planejada",
    "prazo_entrega": "25 dias úteis",
    "entrada_valor": 1000.0,
    "num_parcelas": 3,
    "forma_pagamento": "Entrada + Cartão de Crédito",
    "custo_materiais": 0.0,
    "dias_producao": 3,
    "valor_diaria": 180.0,
    "custo_frete": 250.0,
    "custo_montagem": 350.0,
    "imposto_pct": 6.0,
    "comissao_pct": 4.0,
    "markup": 2.2,
    "items": []
}

def render_login_page(msg_erro=""):
    erro_tag = f"<p class='text-rose-400 text-xs text-center bg-rose-950/60 border border-rose-800 p-2 rounded-lg'>{msg_erro}</p>" if msg_erro else ""
    return f"""
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
                <p class="text-xs text-slate-400">Gestão de Orçamentos Promob, Plano de Corte & Contratos</p>
            </div>
            {erro_tag}
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
            <div class="border-t border-slate-700/60 pt-4 text-center">
                <p class="text-[11px] text-slate-400">Contas de Acesso:</p>
                <p class="text-[11px] text-sky-400">Admin: <b>admin@marcenaria.com</b> | Senha: <b>123456</b></p>
                <p class="text-[11px] text-emerald-400">Vendedor: <b>vendedor@marcenaria.com</b> | Senha: <b>123456</b></p>
            </div>
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

def calcular_dre_completa(d: dict):
    custo_mat = d.get("custo_materiais", 0.0)
    custo_mo = d.get("dias_producao", 0) * d.get("valor_diaria", 0.0)
    custo_frete_mont = d.get("custo_frete", 0.0) + d.get("custo_montagem", 0.0)
    custo_direto_total = custo_mat + custo_mo + custo_frete_mont
    
    markup = d.get("markup", 2.2)
    pv = custo_direto_total * markup if custo_direto_total > 0 else 0.0
    
    imposto_val = (d.get("imposto_pct", 0.0) / 100.0) * pv
    comissao_val = (d.get("comissao_pct", 0.0) / 100.0) * pv
    
    lucro_liquido = pv - (custo_direto_total + imposto_val + comissao_val) if pv > 0 else 0.0
    margem_liq_pct = (lucro_liquido / pv * 100.0) if pv > 0 else 0.0
    
    # Cálculo do parcelamento
    entrada = min(float(d.get("entrada_valor", 0.0)), pv)
    saldo_restante = max(pv - entrada, 0.0)
    n_parc = max(int(d.get("num_parcelas", 1)), 1)
    valor_parcela = saldo_restante / n_parc if n_parc > 0 else 0.0

    return {
        "custo_mat": custo_mat,
        "custo_mo": custo_mo,
        "custo_frete_mont": custo_frete_mont,
        "custo_direto_total": custo_direto_total,
        "pv": pv,
        "imposto_val": imposto_val,
        "comissao_val": comissao_val,
        "lucro_liquido": lucro_liquido,
        "margem_liq_pct": margem_liq_pct,
        "entrada": entrada,
        "saldo_restante": saldo_restante,
        "n_parc": n_parc,
        "valor_parcela": valor_parcela
    }

def consolidar_compras_e_nesting(items: list):
    CHAPA_LARGURA = 2750.0
    CHAPA_ALTURA = 1830.0
    
    pecas_corte = []
    area_total_m2 = 0.0
    dobradicas = 0
    corredicas = 0
    puxadores = 0
    fita_metros = 0.0
    outros = 0

    for it in items:
        tipo = it.get("tipo", "")
        qtd = it.get("qtd", 1)
        largura = float(it.get("largura", 0.0))
        altura = float(it.get("altura", 0.0))

        if "MDF" in tipo and largura > 0 and altura > 0:
            area_item = (largura / 1000.0) * (altura / 1000.0) * qtd
            area_total_m2 += area_item
            fita_metros += (((largura + altura) * 2) / 1000.0) * qtd * 0.5
            for _ in range(qtd):
                pecas_corte.append({
                    "nome": it.get("nome", "Peça"),
                    "largura": largura,
                    "altura": altura
                })
        elif "Dobradiça" in tipo:
            dobradicas += qtd
        elif "Corrediça" in tipo:
            corredicas += qtd
        elif "Puxador" in tipo:
            puxadores += qtd
        elif "Fita" in tipo:
            fita_metros += qtd * 10.0
        else:
            outros += qtd

    chapas = []
    pecas_ordenadas = sorted(pecas_corte, key=lambda p: p["largura"] * p["altura"], reverse=True)
    
    for p in pecas_ordenadas:
        w = min(p["largura"], CHAPA_LARGURA)
        h = min(p["altura"], CHAPA_ALTURA)
        colocada = False
        
        for ch in chapas:
            if ch["cur_x"] + w <= CHAPA_LARGURA and ch["cur_y"] + h <= CHAPA_ALTURA:
                ch["pecas"].append({
                    "nome": p["nome"], "x": ch["cur_x"], "y": ch["cur_y"], "w": w, "h": h
                })
                ch["cur_x"] += w + 10
                ch["row_max_h"] = max(ch["row_max_h"], h)
                ch["area_utilizada"] += (w / 1000.0) * (h / 1000.0)
                colocada = True
                break
            elif ch["cur_y"] + ch["row_max_h"] + h <= CHAPA_ALTURA and w <= CHAPA_LARGURA:
                ch["cur_y"] += ch["row_max_h"] + 10
                ch["cur_x"] = 0.0
                ch["row_max_h"] = h
                ch["pecas"].append({
                    "nome": p["nome"], "x": ch["cur_x"], "y": ch["cur_y"], "w": w, "h": h
                })
                ch["cur_x"] += w + 10
                ch["area_utilizada"] += (w / 1000.0) * (h / 1000.0)
                colocada = True
                break
        
        if not colocada:
            nova_chapa = {
                "id": len(chapas) + 1,
                "cur_x": w + 10,
                "cur_y": 0.0,
                "row_max_h": h,
                "area_utilizada": (w / 1000.0) * (h / 1000.0),
                "pecas": [{
                    "nome": p["nome"], "x": 0.0, "y": 0.0, "w": w, "h": h
                }]
            }
            chapas.append(nova_chapa)

    total_chapas = max(len(chapas), 1 if items else 0)

    return {
        "area_m2": area_total_m2,
        "chapas_mdf": total_chapas,
        "fita_metros": round(fita_metros, 1),
        "dobradicas": dobradicas,
        "corredicas": corredicas,
        "puxadores": puxadores,
        "outros": outros,
        "chapas_nesting": chapas
    }

def render_dashboard(data: dict):
    is_admin = (data.get("user_perfil") == "admin")
    dre = calcular_dre_completa(data)
    items = data.get("items", [])
    precos = get_precos_config()
    empresa = get_empresa_config()
    compras = consolidar_compras_e_nesting(items)
    
    rows_html = ""
    if items:
        for it in items:
            valor_col = f"<td class='py-3 px-4 text-sm text-right text-emerald-400 font-semibold'>R$ {it.get('valor', 0.0):.2f}</td>" if is_admin else "<td class='py-3 px-4 text-sm text-right text-slate-500'>—</td>"
            rows_html += f"""
            <tr class="border-b border-slate-800 hover:bg-slate-850">
                <td class="py-3 px-4 text-sm text-slate-200">
                    <span class="font-medium">{it.get('nome', 'Peça')}</span>
                    <span class="block text-[11px] text-sky-400">{it.get('tipo', 'Insumo')}</span>
                </td>
                <td class="py-3 px-4 text-sm text-center text-slate-400">{it.get('dimensoes', '-')}</td>
                <td class="py-3 px-4 text-sm text-center text-slate-300">{it.get('qtd', 1)}</td>
                {valor_col}
            </tr>
            """
    else:
        rows_html = """
        <tr>
            <td colspan="4" class="py-8 text-center text-sm text-slate-500">
                Nenhum arquivo importado ainda. Faça upload de um XML do Promob/Cutlist abaixo.
            </td>
        </tr>
        """

    svg_chapas_html = ""
    if compras["chapas_nesting"]:
        for ch in compras["chapas_nesting"]:
            aproveitamento = min((ch["area_utilizada"] / 5.03) * 100.0, 100.0)
            rects_svg = ""
            for p in ch["pecas"]:
                sx = (p["x"] / 2750.0) * 550.0
                sy = (p["y"] / 1830.0) * 366.0
                sw = max((p["w"] / 2750.0) * 550.0, 4)
                sh = max((p["h"] / 1830.0) * 366.0, 4)
                rects_svg += f"""
                <rect x="{sx:.1f}" y="{sy:.1f}" width="{sw:.1f}" height="{sh:.1f}" fill="#0284c7" stroke="#0f172a" stroke-width="1" rx="2" opacity="0.9"/>
                <text x="{sx + 4:.1f}" y="{sy + 14:.1f}" fill="#ffffff" font-size="9" font-family="sans-serif" font-weight="bold">{p['nome'][:16]} ({int(p['w'])}x{int(p['h'])})</text>
                """

            svg_chapas_html += f"""
            <div class="bg-slate-950 p-4 rounded-xl border border-slate-800 space-y-2">
                <div class="flex justify-between items-center text-xs">
                    <span class="font-bold text-white">Chapa #{ch['id']} (2750 x 1830 mm)</span>
                    <span class="text-emerald-400 font-semibold">Aproveitamento: {aproveitamento:.1f}% ({ch['area_utilizada']:.2f} m²)</span>
                </div>
                <div class="w-full bg-slate-900 border border-dashed border-slate-700 rounded-lg p-2 overflow-x-auto flex justify-center">
                    <svg viewBox="0 0 550 366" class="w-full max-w-[550px] h-[220px] bg-slate-800/80 rounded border border-slate-700">
                        {rects_svg}
                    </svg>
                </div>
            </div>
            """
    else:
        svg_chapas_html = "<div class='py-8 text-center text-xs text-slate-500'>Importe um projeto XML para renderizar os diagramas de corte.</div>"

    condicoes_zap = f"Entrada de R$ {dre['entrada']:,.2f} + {dre['n_parc']}x de R$ {dre['valor_parcela']:,.2f}" if dre['n_parc'] > 1 else f"R$ {dre['pv']:,.2f} à vista"
    msg_zap = f"Olá {data['cliente_nome']}! Segue a proposta da {empresa['nome_empresa']} para o projeto {data['cliente_ambiente']}: Total de R$ {dre['pv']:,.2f} ({condicoes_zap}) com entrega em {data['prazo_entrega']}."
    zap_url = f"https://api.whatsapp.com/send?phone=55{data['cliente_telefone']}&text={urllib.parse.quote(msg_zap)}"

    msg_cotacao = f"*COTAÇÃO DE MATERIAIS - {empresa['nome_empresa']}*\n"
    msg_cotacao += f"Projeto: {data['cliente_ambiente']}\n"
    msg_cotacao += f"- Chapas MDF: {compras['chapas_mdf']} un ({compras['area_m2']:.1f} m²)\n"
    msg_cotacao += f"- Fita Borda: {compras['fita_metros']} metros\n"
    msg_cotacao += f"- Dobradiças c/ amortecedor: {compras['dobradicas']} un\n"
    msg_cotacao += f"- Corrediças Telescópicas: {compras['corredicas']} pares\n"
    msg_cotacao += f"- Puxadores: {compras['puxadores']} un\n"
    msg_cotacao += f"Favor enviar cotação e disponibilidade."
    zap_cotacao_url = f"https://api.whatsapp.com/send?text={urllib.parse.quote(msg_cotacao)}"

    historico_html = ""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, criado_em, cliente_nome, cliente_ambiente, preco_venda, lucro_liquido, status FROM orcamentos ORDER BY id DESC LIMIT 20")
        historico_rows = cursor.fetchall()
        
        if historico_rows:
            for h in historico_rows:
                lucro_col = f"<td class='py-3 px-4 text-right text-emerald-400 font-semibold'>R$ {h['lucro_liquido']:,.2f}</td>" if is_admin else "<td class='py-3 px-4 text-right text-slate-500'>—</td>"
                current_st = h['status'] or 'Em Negociação'
                
                historico_html += f"""
                <tr class="border-b border-slate-800 hover:bg-slate-800/40 text-xs">
                    <td class="py-3 px-4 text-slate-400 font-mono">#{h['id']}</td>
                    <td class="py-3 px-4 text-slate-300">{h['criado_em']}</td>
                    <td class="py-3 px-4 text-white font-medium">{h['cliente_nome']}</td>
                    <td class="py-3 px-4 text-slate-300">{h['cliente_ambiente']}</td>
                    <td class="py-3 px-4 text-right text-sky-400 font-bold">R$ {h['preco_venda']:,.2f}</td>
                    {lucro_col}
                    <td class="py-3 px-4 text-center">
                        <form action="/atualizar-status" method="post" class="inline">
                            <input type="hidden" name="orcamento_id" value="{h['id']}">
                            <select name="novo_status" onchange="this.form.submit()" class="bg-slate-950 border border-slate-700 text-[11px] text-slate-200 rounded px-2 py-1 focus:outline-none">
                                <option value="Em Negociação" {'selected' if current_st=='Em Negociação' else ''}>🟡 Em Negociação</option>
                                <option value="Aprovado" {'selected' if current_st=='Aprovado' else ''}>🟢 Aprovado</option>
                                <option value="Em Produção" {'selected' if current_st=='Em Produção' else ''}>🔵 Em Produção</option>
                                <option value="Entregue" {'selected' if current_st=='Entregue' else ''}>🟣 Entregue</option>
                                <option value="Cancelado" {'selected' if current_st=='Cancelado' else ''}>🔴 Cancelado</option>
                            </select>
                        </form>
                    </td>
                    <td class="py-3 px-4 text-center">
                        <div class="flex items-center justify-center space-x-1">
                            <form action="/carregar-orcamento" method="post" class="inline">
                                <input type="hidden" name="orcamento_id" value="{h['id']}">
                                <button type="submit" class="px-2 py-1 bg-sky-600 hover:bg-sky-500 text-white rounded text-[11px] font-semibold">Abrir</button>
                            </form>
                            <a href="/gerar-pdf?id={h['id']}" class="px-2 py-1 bg-emerald-700 hover:bg-emerald-600 text-white rounded text-[11px] font-semibold">Orçamento</a>
                            <a href="/gerar-contrato?id={h['id']}" class="px-2 py-1 bg-amber-700 hover:bg-amber-600 text-white rounded text-[11px] font-semibold">Contrato</a>
                            <a href="/gerar-pdf-compras?id={h['id']}" class="px-2 py-1 bg-indigo-700 hover:bg-indigo-600 text-white rounded text-[11px] font-semibold">Compras</a>
                            <form action="/excluir-orcamento" method="post" class="inline" onsubmit="return confirm('Deseja excluir este orçamento?');">
                                <input type="hidden" name="orcamento_id" value="{h['id']}">
                                <button type="submit" class="px-1.5 py-1 bg-rose-700/60 hover:bg-rose-600 text-white rounded text-[11px]">✕</button>
                            </form>
                        </div>
                    </td>
                </tr>
                """
        else:
            historico_html = """
            <tr>
                <td colspan="8" class="py-6 text-center text-xs text-slate-500">
                    Nenhum orçamento salvo no histórico ainda. Salve o orçamento ativo abaixo.
                </td>
            </tr>
            """

    usuarios_html = ""
    if is_admin:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT email, nome, perfil FROM usuarios")
            for u in cursor.fetchall():
                badge = "<span class='text-[10px] bg-sky-950 text-sky-300 border border-sky-800 px-2 py-0.5 rounded'>Admin</span>" if u['perfil'] == 'admin' else "<span class='text-[10px] bg-emerald-950 text-emerald-300 border border-emerald-800 px-2 py-0.5 rounded'>Vendedor</span>"
                usuarios_html += f"""
                <li class="flex items-center justify-between py-2 border-b border-slate-800/80 text-xs">
                    <div>
                        <span class="font-semibold text-white">{u['nome']}</span>
                        <span class="text-slate-400 block text-[11px]">{u['email']}</span>
                    </div>
                    {badge}
                </li>
                """

    status_tag = f"<span class='text-xs bg-sky-950 border border-sky-700 text-sky-300 px-2.5 py-1 rounded-full'>Editando Orçamento #{data['orcamento_id']} ({data.get('status', 'Em Negociação')})</span>" if data['orcamento_id'] else "<span class='text-xs bg-slate-800 border border-slate-700 text-slate-400 px-2.5 py-1 rounded-full'>Novo Orçamento em Rascunho</span>"
    perfil_badge = "<span class='text-[11px] bg-blue-900/60 border border-blue-600 text-blue-300 px-2 py-0.5 rounded-full font-medium'>👑 Administrador</span>" if is_admin else "<span class='text-[11px] bg-emerald-900/60 border border-emerald-600 text-emerald-300 px-2 py-0.5 rounded-full font-medium'>💼 Vendedor</span>"

    dre_cards = f"""
    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div class="bg-slate-900 border border-slate-800 p-5 rounded-xl space-y-1 shadow-lg">
            <p class="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">Custo Direto Total</p>
            <p class="text-xl font-bold text-white">R$ {dre['custo_direto_total']:,.2f}</p>
            <p class="text-[11px] text-slate-500">Mat: R$ {dre['custo_mat']:,.0f} | M.O: R$ {dre['custo_mo']:,.0f} | Frete/Mont: R$ {dre['custo_frete_mont']:,.0f}</p>
        </div>
        <div class="bg-slate-900 border border-slate-800 p-5 rounded-xl space-y-1 shadow-lg">
            <p class="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">Preço de Venda ({data['markup']:.1f}x)</p>
            <p class="text-xl font-bold text-sky-400">R$ {dre['pv']:,.2f}</p>
            <p class="text-[11px] text-slate-500">Proposta final para o cliente</p>
        </div>
        <div class="bg-slate-900 border border-slate-800 p-5 rounded-xl space-y-1 shadow-lg">
            <p class="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">Deduções (Imposto + Com.)</p>
            <p class="text-xl font-bold text-rose-400">R$ {(dre['imposto_val'] + dre['comissao_val']):,.2f}</p>
            <p class="text-[11px] text-slate-500">Imp. {data['imposto_pct']}% (R$ {dre['imposto_val']:,.0f}) | Com. {data['comissao_pct']}% (R$ {dre['comissao_val']:,.0f})</p>
        </div>
        <div class="bg-slate-900 border border-slate-800 p-5 rounded-xl space-y-1 shadow-lg">
            <p class="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">Margem Líquida Real</p>
            <p class="text-xl font-bold text-emerald-400">R$ {dre['lucro_liquido']:,.2f}</p>
            <p class="text-[11px] text-slate-500">Retorno limpo no caixa ({dre['margem_liq_pct']:.1f}%)</p>
        </div>
    </div>
    """ if is_admin else f"""
    <div class="bg-slate-900 border border-slate-800 p-6 rounded-xl shadow-lg flex justify-between items-center">
        <div>
            <p class="text-xs text-slate-400 uppercase font-semibold">Valor da Proposta Comercial</p>
            <p class="text-3xl font-bold text-sky-400 mt-1">R$ {dre['pv']:,.2f}</p>
            <p class="text-xs text-slate-500">Entrada: R$ {dre['entrada']:,.2f} + {dre['n_parc']}x de R$ {dre['valor_parcela']:,.2f}</p>
        </div>
        <div class="flex space-x-2">
            <a href="/gerar-pdf" class="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-xs rounded-lg transition-colors">
                📄 Orçamento
            </a>
            <a href="/gerar-contrato" class="px-4 py-2 bg-amber-600 hover:bg-amber-500 text-white font-semibold text-xs rounded-lg transition-colors">
                📑 Contrato
            </a>
        </div>
    </div>
    """

    admin_sections = f"""
    <!-- Personalização dos Dados da Sua Marcenaria -->
    <div class="bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-lg space-y-4">
        <div class="flex justify-between items-center border-b border-slate-800 pb-3">
            <h2 class="text-base font-semibold text-white">🏢 Dados da Sua Marcenaria (Contrato e Cabeçalho do PDF)</h2>
            <span class="text-xs text-slate-400">Configuração institucional da sua empresa</span>
        </div>
        <form action="/salvar-empresa" method="post" class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <div>
                <label class="block text-xs font-medium text-slate-400 mb-1">Nome Comercial / Razão Social</label>
                <input type="text" name="nome_empresa" value="{empresa['nome_empresa']}" required class="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-xs text-white">
            </div>
            <div>
                <label class="block text-xs font-medium text-slate-400 mb-1">CNPJ</label>
                <input type="text" name="cnpj" value="{empresa['cnpj']}" required class="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-xs text-white">
            </div>
            <div>
                <label class="block text-xs font-medium text-slate-400 mb-1">Telefone / WhatsApp da Loja</label>
                <input type="text" name="telefone_empresa" value="{empresa['telefone_empresa']}" required class="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-xs text-white">
            </div>
            <div>
                <label class="block text-xs font-medium text-slate-400 mb-1">Chave PIX p/ Pagamentos</label>
                <div class="flex gap-2">
                    <input type="text" name="pix" value="{empresa['pix']}" required class="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-xs text-white">
                    <button type="submit" class="px-4 py-2 bg-sky-600 hover:bg-sky-500 text-white rounded-lg text-xs font-semibold shrink-0">
                        Salvar
                    </button>
                </div>
            </div>
        </form>
    </div>

    <!-- Mão de Obra e Operacionais -->
    <div class="bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-lg space-y-4">
        <div class="flex justify-between items-center border-b border-slate-800 pb-3">
            <h2 class="text-base font-semibold text-white">🔨 Mão de Obra & Custos Operacionais</h2>
            <span class="text-xs text-slate-400">Visível apenas para Administrador</span>
        </div>
        <form action="/salvar-operacionais" method="post" class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
            <div>
                <label class="block text-[11px] font-medium text-slate-400 mb-1">Dias Fabricação</label>
                <input type="number" step="1" min="0" name="dias_producao" value="{data['dias_producao']}" class="w-full px-2.5 py-1.5 bg-slate-950 border border-slate-700 rounded-lg text-xs text-white focus:outline-none focus:border-sky-500">
            </div>
            <div>
                <label class="block text-[11px] font-medium text-slate-400 mb-1">Diária Marceneiro (R$)</label>
                <input type="number" step="10" name="valor_diaria" value="{data['valor_diaria']}" class="w-full px-2.5 py-1.5 bg-slate-950 border border-slate-700 rounded-lg text-xs text-white focus:outline-none focus:border-sky-500">
            </div>
            <div>
                <label class="block text-[11px] font-medium text-slate-400 mb-1">Custo Frete (R$)</label>
                <input type="number" step="10" name="custo_frete" value="{data['custo_frete']}" class="w-full px-2.5 py-1.5 bg-slate-950 border border-slate-700 rounded-lg text-xs text-white focus:outline-none focus:border-sky-500">
            </div>
            <div>
                <label class="block text-[11px] font-medium text-slate-400 mb-1">Montagem Cliente (R$)</label>
                <input type="number" step="10" name="custo_montagem" value="{data['custo_montagem']}" class="w-full px-2.5 py-1.5 bg-slate-950 border border-slate-700 rounded-lg text-xs text-white focus:outline-none focus:border-sky-500">
            </div>
            <div>
                <label class="block text-[11px] font-medium text-slate-400 mb-1">Impostos (%)</label>
                <input type="number" step="0.5" min="0" max="30" name="imposto_pct" value="{data['imposto_pct']}" class="w-full px-2.5 py-1.5 bg-slate-950 border border-slate-700 rounded-lg text-xs text-white focus:outline-none focus:border-sky-500">
            </div>
            <div class="flex items-end">
                <button type="submit" class="w-full py-2 bg-sky-600 hover:bg-sky-500 text-white rounded-lg text-xs font-semibold transition-colors">
                    Atualizar DRE
                </button>
            </div>
        </form>
    </div>

    <!-- Tabela de Custos Unitários de Insumos -->
    <div class="bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-lg space-y-4">
        <div class="flex justify-between items-center border-b border-slate-800 pb-3">
            <h2 class="text-base font-semibold text-white">⚙️ Tabela de Custos Unitários por Insumo</h2>
            <span class="text-xs text-slate-400">Tabela Geral da Marcenaria</span>
        </div>
        <form action="/salvar-precos" method="post" class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
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
                    Salvar Config
                </button>
            </div>
        </form>
    </div>

    <!-- Gestão de Usuários da Equipe -->
    <div class="bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-lg space-y-4">
        <div class="flex justify-between items-center border-b border-slate-800 pb-3">
            <h2 class="text-base font-semibold text-white">👥 Gestão de Equipe & Permissões</h2>
            <span class="text-xs text-sky-400">Cadastre novos vendedores ou administradores</span>
        </div>
        <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <form action="/criar-usuario" method="post" class="lg:col-span-2 space-y-3 bg-slate-950 p-4 rounded-lg border border-slate-800">
                <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div>
                        <label class="block text-[11px] text-slate-400 mb-1">Nome Completo</label>
                        <input type="text" name="nome" required placeholder="Ex: João Marceneiro" class="w-full px-3 py-1.5 bg-slate-900 border border-slate-700 rounded-lg text-xs text-white">
                    </div>
                    <div>
                        <label class="block text-[11px] text-slate-400 mb-1">E-mail de Acesso</label>
                        <input type="email" name="email" required placeholder="joao@marcenaria.com" class="w-full px-3 py-1.5 bg-slate-900 border border-slate-700 rounded-lg text-xs text-white">
                    </div>
                    <div>
                        <label class="block text-[11px] text-slate-400 mb-1">Senha</label>
                        <input type="password" name="senha" required placeholder="******" class="w-full px-3 py-1.5 bg-slate-900 border border-slate-700 rounded-lg text-xs text-white">
                    </div>
                    <div>
                        <label class="block text-[11px] text-slate-400 mb-1">Nível de Permissão</label>
                        <select name="perfil" class="w-full px-3 py-1.5 bg-slate-900 border border-slate-700 rounded-lg text-xs text-white">
                            <option value="vendedor">Vendedor (Sem visualização de DRE e lucros)</option>
                            <option value="admin">Administrador (Acesso completo)</option>
                        </select>
                    </div>
                </div>
                <button type="submit" class="px-4 py-2 bg-sky-600 hover:bg-sky-500 text-white rounded-lg text-xs font-semibold">
                    Adicionar Membro à Equipe
                </button>
            </form>
            <div class="bg-slate-950 p-4 rounded-lg border border-slate-800">
                <h3 class="text-xs font-semibold text-slate-300 uppercase mb-2">Usuários Cadastrados</h3>
                <ul class="divide-y divide-slate-800">
                    {usuarios_html}
                </ul>
            </div>
        </div>
    </div>
    """ if is_admin else ""

    markup_control = f"""
    <form action="/recalcular" method="post" class="flex items-center gap-3">
        <label class="text-xs text-slate-400 font-medium">Markup:</label>
        <input type="number" step="0.1" min="1.0" max="5.0" name="markup" value="{data['markup']}" class="w-20 px-3 py-1.5 bg-slate-950 border border-slate-700 rounded-lg text-sm text-center text-white focus:outline-none focus:border-sky-500">
        <button type="submit" class="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-lg text-xs font-semibold border border-slate-700">
            Recalcular
        </button>
    </form>
    """ if is_admin else "<p class='text-xs text-slate-400'>Margem e markup fixados pela diretoria.</p>"

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
                {perfil_badge}
                <a href="/novo-orcamento" class="text-xs bg-sky-600 hover:bg-sky-500 text-white font-medium px-3 py-1.5 rounded-lg transition-colors">+ Novo Orçamento</a>
                <span class="text-xs text-slate-400">Usuário: <b class="text-sky-400">{data['user_nome']}</b></span>
                <a href="/" class="text-xs bg-slate-800 hover:bg-slate-700 px-3 py-1.5 rounded-lg text-slate-300 border border-slate-700">Sair</a>
            </div>
        </header>

        <main class="max-w-7xl mx-auto p-6 space-y-6">
            {dre_cards}

            <!-- Simulador de Pagamento e Condições Comerciais -->
            <div class="bg-slate-900 border border-amber-900/50 rounded-xl p-6 shadow-lg space-y-4">
                <div class="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-2 border-b border-slate-800 pb-3">
                    <div>
                        <h2 class="text-base font-semibold text-white">💳 Condições de Pagamento & Financiamento</h2>
                        <p class="text-xs text-amber-400">Simule a entrada e o parcelamento para constar no Contrato e Proposta</p>
                    </div>
                    <div class="flex gap-2">
                        <a href="/gerar-contrato" class="px-3 py-1.5 bg-amber-600 hover:bg-amber-500 text-white font-medium text-xs rounded-lg transition-colors flex items-center space-x-1 shadow-md">
                            <span>📑 Emitir Contrato (PDF)</span>
                        </a>
                    </div>
                </div>
                <form action="/salvar-pagamento" method="post" class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                    <div>
                        <label class="block text-xs font-medium text-slate-400 mb-1">Valor de Entrada (R$)</label>
                        <input type="number" step="50" name="entrada_valor" value="{data['entrada_valor']}" class="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-sm text-white focus:outline-none focus:border-amber-500">
                    </div>
                    <div>
                        <label class="block text-xs font-medium text-slate-400 mb-1">Nº de Parcelas</label>
                        <select name="num_parcelas" class="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-sm text-white focus:outline-none">
                            <option value="1" {'selected' if data.get('num_parcelas')==1 else ''}>1x (À vista ou parcela única)</option>
                            <option value="2" {'selected' if data.get('num_parcelas')==2 else ''}>2x parcelas</option>
                            <option value="3" {'selected' if data.get('num_parcelas')==3 else ''}>3x parcelas</option>
                            <option value="4" {'selected' if data.get('num_parcelas')==4 else ''}>4x parcelas</option>
                            <option value="5" {'selected' if data.get('num_parcelas')==5 else ''}>5x parcelas</option>
                            <option value="6" {'selected' if data.get('num_parcelas')==6 else ''}>6x parcelas</option>
                            <option value="10" {'selected' if data.get('num_parcelas')==10 else ''}>10x parcelas</option>
                            <option value="12" {'selected' if data.get('num_parcelas')==12 else ''}>12x parcelas</option>
                        </select>
                    </div>
                    <div>
                        <label class="block text-xs font-medium text-slate-400 mb-1">Forma de Pagamento</label>
                        <input type="text" name="forma_pagamento" value="{data['forma_pagamento']}" placeholder="Ex: Entrada PIX + Cartão" class="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-sm text-white focus:outline-none focus:border-amber-500">
                    </div>
                    <div class="flex items-end">
                        <button type="submit" class="w-full py-2 bg-amber-600 hover:bg-amber-500 text-white rounded-lg text-xs font-semibold transition-colors">
                            Atualizar Condições
                        </button>
                    </div>
                </form>
                <div class="bg-slate-950 p-3 rounded-lg border border-slate-800 flex flex-wrap justify-between items-center text-xs">
                    <span class="text-slate-300">Resumo: <b>Entrada de R$ {dre['entrada']:,.2f}</b> + <b>{dre['n_parc']}x de R$ {dre['valor_parcela']:,.2f}</b></span>
                    <span class="text-amber-400 font-semibold">Total: R$ {dre['pv']:,.2f} ({data['forma_pagamento']})</span>
                </div>
            </div>

            <!-- Resumo de Compras para Fornecedores -->
            <div class="bg-slate-900 border border-indigo-900/50 rounded-xl p-6 shadow-lg space-y-4">
                <div class="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-2 border-b border-slate-800 pb-3">
                    <div>
                        <h2 class="text-base font-semibold text-white">📦 Resumo de Compras para Fornecedores / Madeireira</h2>
                        <p class="text-xs text-indigo-400">Totalizadores de materiais necessários para produzir o projeto</p>
                    </div>
                    <div class="flex gap-2">
                        <a href="/gerar-pdf-compras" class="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white font-medium text-xs rounded-lg transition-colors flex items-center space-x-1 shadow-md">
                            <span>📄 PDF p/ Madeireira</span>
                        </a>
                        <a href="{zap_cotacao_url}" target="_blank" class="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white font-medium text-xs rounded-lg transition-colors flex items-center space-x-1 shadow-md">
                            <span>💬 Cotar no Zap</span>
                        </a>
                    </div>
                </div>
                <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 text-center">
                    <div class="bg-slate-950 p-3 rounded-lg border border-slate-800">
                        <p class="text-[11px] text-slate-400 uppercase">Chapas MDF</p>
                        <p class="text-lg font-bold text-white">{compras['chapas_mdf']} <span class="text-xs font-normal text-slate-500">un</span></p>
                        <p class="text-[10px] text-slate-500">{compras['area_m2']:.1f} m²</p>
                    </div>
                    <div class="bg-slate-950 p-3 rounded-lg border border-slate-800">
                        <p class="text-[11px] text-slate-400 uppercase">Fita Borda</p>
                        <p class="text-lg font-bold text-white">{compras['fita_metros']} <span class="text-xs font-normal text-slate-500">m</span></p>
                        <p class="text-[10px] text-slate-500">PVC 22mm</p>
                    </div>
                    <div class="bg-slate-950 p-3 rounded-lg border border-slate-800">
                        <p class="text-[11px] text-slate-400 uppercase">Dobradiças</p>
                        <p class="text-lg font-bold text-sky-400">{compras['dobradicas']} <span class="text-xs font-normal text-slate-500">un</span></p>
                        <p class="text-[10px] text-slate-500">Amortecedor</p>
                    </div>
                    <div class="bg-slate-950 p-3 rounded-lg border border-slate-800">
                        <p class="text-[11px] text-slate-400 uppercase">Corrediças</p>
                        <p class="text-lg font-bold text-sky-400">{compras['corredicas']} <span class="text-xs font-normal text-slate-500">pares</span></p>
                        <p class="text-[10px] text-slate-500">Telescópicas</p>
                    </div>
                    <div class="bg-slate-950 p-3 rounded-lg border border-slate-800">
                        <p class="text-[11px] text-slate-400 uppercase">Puxadores</p>
                        <p class="text-lg font-bold text-white">{compras['puxadores']} <span class="text-xs font-normal text-slate-500">un</span></p>
                        <p class="text-[10px] text-slate-500">Perfis/Pontos</p>
                    </div>
                    <div class="bg-slate-950 p-3 rounded-lg border border-slate-800">
                        <p class="text-[11px] text-slate-400 uppercase">Outros Insumos</p>
                        <p class="text-lg font-bold text-slate-300">{compras['outros']} <span class="text-xs font-normal text-slate-500">itens</span></p>
                        <p class="text-[10px] text-slate-500">Parafusos/Tapas</p>
                    </div>
                </div>
            </div>

            <!-- Módulo Visual de Plano de Corte Gráfico (2D Nesting) -->
            <div class="bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-lg space-y-4">
                <div class="flex justify-between items-center border-b border-slate-800 pb-3">
                    <div>
                        <h2 class="text-base font-semibold text-white">📐 Diagrama Visual de Plano de Corte (Nesting)</h2>
                        <p class="text-xs text-slate-400">Distribuição automatizada das peças nas chapas padrão 2750 x 1830 mm</p>
                    </div>
                    <span class="text-xs text-sky-400 font-semibold">{compras['chapas_mdf']} chapa(s) necessária(s)</span>
                </div>
                <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
                    {svg_chapas_html}
                </div>
            </div>

            <!-- Dados do Cliente -->
            <div class="bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-lg space-y-4">
                <div class="flex justify-between items-center border-b border-slate-800 pb-3">
                    <h2 class="text-base font-semibold text-white">👤 Dados do Cliente & Proposta</h2>
                    <span class="text-xs text-sky-400">Vinculado ao Contrato, Banco, PDF e WhatsApp</span>
                </div>
                <form action="/salvar-cliente" method="post" class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
                    <div>
                        <label class="block text-xs font-medium text-slate-400 mb-1">Nome do Cliente</label>
                        <input type="text" name="cliente_nome" value="{data['cliente_nome']}" required class="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-sm text-white focus:outline-none focus:border-sky-500">
                    </div>
                    <div>
                        <label class="block text-xs font-medium text-slate-400 mb-1">WhatsApp / Telefone</label>
                        <input type="text" name="cliente_telefone" value="{data['cliente_telefone']}" required class="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-sm text-white focus:outline-none focus:border-sky-500">
                    </div>
                    <div>
                        <label class="block text-xs font-medium text-slate-400 mb-1">Ambiente / Projeto</label>
                        <input type="text" name="cliente_ambiente" value="{data['cliente_ambiente']}" required class="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-sm text-white focus:outline-none focus:border-sky-500">
                    </div>
                    <div>
                        <label class="block text-xs font-medium text-slate-400 mb-1">Status da Proposta</label>
                        <select name="status" class="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-sm text-white focus:outline-none">
                            <option value="Em Negociação" {'selected' if data.get('status')=='Em Negociação' else ''}>🟡 Em Negociação</option>
                            <option value="Aprovado" {'selected' if data.get('status')=='Aprovado' else ''}>🟢 Aprovado</option>
                            <option value="Em Produção" {'selected' if data.get('status')=='Em Produção' else ''}>🔵 Em Produção</option>
                            <option value="Entregue" {'selected' if data.get('status')=='Entregue' else ''}>🟣 Entregue</option>
                            <option value="Cancelado" {'selected' if data.get('status')=='Cancelado' else ''}>🔴 Cancelado</option>
                        </select>
                    </div>
                    <div>
                        <label class="block text-xs font-medium text-slate-400 mb-1">Prazo de Entrega</label>
                        <div class="flex gap-2">
                            <input type="text" name="prazo_entrega" value="{data['prazo_entrega']}" required class="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-sm text-white focus:outline-none focus:border-sky-500">
                            <button type="submit" class="px-4 py-2 bg-sky-600 hover:bg-sky-500 text-white rounded-lg text-xs font-semibold shrink-0">
                                Salvar
                            </button>
                        </div>
                    </div>
                </form>
            </div>

            {admin_sections}

            <!-- Upload + Markup + Salvar no Banco + PDF + WhatsApp -->
            <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <div class="lg:col-span-2 bg-slate-900 border border-slate-800 rounded-xl p-6 space-y-4 shadow-lg">
                    <h2 class="text-base font-semibold text-white">Importar Projeto (XML Promob / Cutlist)</h2>
                    <form action="/upload-xml" method="post" enctype="multipart/form-data" class="flex flex-col sm:flex-row items-center gap-4">
                        <input type="file" name="file" accept=".xml,.txt" required class="block w-full text-xs text-slate-400 file:mr-4 file:py-2.5 file:px-4 file:rounded-lg file:border-0 file:text-xs file:font-semibold file:bg-slate-800 file:text-slate-200 hover:file:bg-slate-700 cursor-pointer">
                        <button type="submit" class="w-full sm:w-auto px-6 py-2.5 bg-sky-600 hover:bg-sky-500 text-white font-medium rounded-lg text-sm transition-colors shrink-0">
                            Processar e Orçar
                        </button>
                    </form>
                </div>

                <div class="bg-slate-900 border border-slate-800 rounded-xl p-6 flex flex-col justify-between space-y-4 shadow-lg">
                    <h2 class="text-base font-semibold text-white">Ações da Proposta</h2>
                    {markup_control}
                    
                    <div class="space-y-2">
                        <form action="/salvar-banco" method="post">
                            <button type="submit" class="w-full py-2 bg-blue-600 hover:bg-blue-500 text-white font-semibold text-center text-xs rounded-lg transition-colors flex items-center justify-center space-x-1 shadow-lg shadow-blue-600/20">
                                <span>💾 Salvar no Histórico (Banco)</span>
                            </button>
                        </form>
                        <div class="grid grid-cols-2 gap-2">
                            <a href="/gerar-pdf" class="py-2 bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-center text-xs rounded-lg transition-colors flex items-center justify-center shadow-lg shadow-emerald-600/20">
                                <span>📄 Orçamento (PDF)</span>
                            </a>
                            <a href="/gerar-contrato" class="py-2 bg-amber-600 hover:bg-amber-500 text-white font-semibold text-center text-xs rounded-lg transition-colors flex items-center justify-center shadow-lg shadow-amber-600/20">
                                <span>📑 Contrato (PDF)</span>
                            </a>
                        </div>
                        <a href="{zap_url}" target="_blank" class="w-full py-2 bg-green-600 hover:bg-green-500 text-white font-semibold text-center text-xs rounded-lg transition-colors flex items-center justify-center space-x-1 shadow-lg shadow-green-600/20">
                            <span>💬 Enviar Proposta no WhatsApp</span>
                        </a>
                    </div>
                </div>
            </div>

            <!-- Histórico de Orçamentos com Status Dinâmico -->
            <div class="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-lg">
                <div class="p-4 border-b border-slate-800 flex justify-between items-center bg-slate-850">
                    <h3 class="text-sm font-semibold text-white">📁 Histórico & Funil de Pedidos (Banco de Dados)</h3>
                    <span class="text-xs text-slate-400">Altere o status para acompanhar a produção</span>
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
                                <th class="py-3 px-4 text-right">Lucro Líquido</th>
                                <th class="py-3 px-4 text-center">Status do Pedido</th>
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
                    <h3 class="text-sm font-semibold text-white">Listagem de Peças e Insumos ({data['cliente_ambiente']})</h3>
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
    return render_login_page()

@app.post("/painel", response_class=HTMLResponse)
def login(username: str = Form(...), password: str = Form(...)):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM usuarios WHERE email = ? AND senha = ?", (username, password))
        user_row = cursor.fetchone()
        
        if not user_row:
            return render_login_page("E-mail ou senha incorretos. Tente novamente.")

        CURRENT_DATA["user"] = user_row["email"]
        CURRENT_DATA["user_nome"] = user_row["nome"]
        CURRENT_DATA["user_perfil"] = user_row["perfil"]

    return render_dashboard(data=CURRENT_DATA)

@app.post("/salvar-empresa", response_class=HTMLResponse)
def salvar_empresa(nome_empresa: str = Form(...), cnpj: str = Form(...), telefone_empresa: str = Form(...), pix: str = Form(...)):
    if CURRENT_DATA.get("user_perfil") == "admin":
        dados = {
            "nome_empresa": nome_empresa,
            "cnpj": cnpj,
            "telefone_empresa": telefone_empresa,
            "pix": pix
        }
        set_empresa_config(dados)
    return RedirectResponse(url="/painel-get", status_code=303)

@app.post("/salvar-pagamento", response_class=HTMLResponse)
def salvar_pagamento(entrada_valor: float = Form(0.0), num_parcelas: int = Form(1), forma_pagamento: str = Form("PIX")):
    CURRENT_DATA["entrada_valor"] = entrada_valor
    CURRENT_DATA["num_parcelas"] = num_parcelas
    CURRENT_DATA["forma_pagamento"] = forma_pagamento
    return RedirectResponse(url="/painel-get", status_code=303)

@app.post("/atualizar-status", response_class=HTMLResponse)
def atualizar_status(orcamento_id: int = Form(...), novo_status: str = Form(...)):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE orcamentos SET status = ? WHERE id = ?", (novo_status, orcamento_id))
        conn.commit()
    if CURRENT_DATA.get("orcamento_id") == orcamento_id:
        CURRENT_DATA["status"] = novo_status
    return RedirectResponse(url="/painel-get", status_code=303)

@app.post("/criar-usuario", response_class=HTMLResponse)
def criar_usuario(nome: str = Form(...), email: str = Form(...), senha: str = Form(...), perfil: str = Form(...)):
    if CURRENT_DATA.get("user_perfil") == "admin":
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO usuarios (email, senha, nome, perfil) VALUES (?, ?, ?, ?)", (email, senha, nome, perfil))
            conn.commit()
    return RedirectResponse(url="/painel-get", status_code=303)

@app.get("/novo-orcamento", response_class=HTMLResponse)
def novo_orcamento():
    CURRENT_DATA["orcamento_id"] = None
    CURRENT_DATA["status"] = "Em Negociação"
    CURRENT_DATA["cliente_nome"] = "Novo Cliente"
    CURRENT_DATA["cliente_telefone"] = ""
    CURRENT_DATA["cliente_ambiente"] = "Ambiente Geral"
    CURRENT_DATA["prazo_entrega"] = "20 dias úteis"
    CURRENT_DATA["entrada_valor"] = 0.0
    CURRENT_DATA["num_parcelas"] = 1
    CURRENT_DATA["forma_pagamento"] = "PIX / Transferência"
    CURRENT_DATA["custo_materiais"] = 0.0
    CURRENT_DATA["dias_producao"] = 3
    CURRENT_DATA["valor_diaria"] = 180.0
    CURRENT_DATA["custo_frete"] = 250.0
    CURRENT_DATA["custo_montagem"] = 350.0
    CURRENT_DATA["imposto_pct"] = 6.0
    CURRENT_DATA["comissao_pct"] = 4.0
    CURRENT_DATA["markup"] = 2.2
    CURRENT_DATA["items"] = []
    return RedirectResponse(url="/painel-get", status_code=303)

@app.get("/painel-get", response_class=HTMLResponse)
def painel_get():
    return render_dashboard(data=CURRENT_DATA)

@app.post("/salvar-operacionais", response_class=HTMLResponse)
def salvar_operacionais(
    dias_producao: int = Form(3),
    valor_diaria: float = Form(180.0),
    custo_frete: float = Form(250.0),
    custo_montagem: float = Form(350.0),
    imposto_pct: float = Form(6.0)
):
    if CURRENT_DATA.get("user_perfil") == "admin":
        CURRENT_DATA["dias_producao"] = dias_producao
        CURRENT_DATA["valor_diaria"] = valor_diaria
        CURRENT_DATA["custo_frete"] = custo_frete
        CURRENT_DATA["custo_montagem"] = custo_montagem
        CURRENT_DATA["imposto_pct"] = imposto_pct
    return RedirectResponse(url="/painel-get", status_code=303)

@app.post("/salvar-banco", response_class=HTMLResponse)
def salvar_banco():
    dre = calcular_dre_completa(CURRENT_DATA)
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
                    status = ?,
                    custo_materiais = ?,
                    custo_mao_obra = ?,
                    custo_frete_montagem = ?,
                    imposto_pct = ?,
                    comissao_pct = ?,
                    markup = ?,
                    preco_venda = ?,
                    lucro_liquido = ?,
                    entrada_valor = ?,
                    num_parcelas = ?,
                    forma_pagamento = ?,
                    items_json = ?
                WHERE id = ?
            """, (
                agora,
                CURRENT_DATA["cliente_nome"],
                CURRENT_DATA["cliente_telefone"],
                CURRENT_DATA["cliente_ambiente"],
                CURRENT_DATA["prazo_entrega"],
                CURRENT_DATA.get("status", "Em Negociação"),
                dre["custo_mat"],
                dre["custo_mo"],
                dre["custo_frete_mont"],
                CURRENT_DATA["imposto_pct"],
                CURRENT_DATA["comissao_pct"],
                CURRENT_DATA["markup"],
                dre["pv"],
                dre["lucro_liquido"],
                CURRENT_DATA.get("entrada_valor", 0.0),
                CURRENT_DATA.get("num_parcelas", 1),
                CURRENT_DATA.get("forma_pagamento", "PIX"),
                json.dumps(CURRENT_DATA["items"]),
                CURRENT_DATA["orcamento_id"]
            ))
        else:
            cursor.execute("""
                INSERT INTO orcamentos (criado_em, cliente_nome, cliente_telefone, cliente_ambiente, prazo_entrega, status, custo_materiais, custo_mao_obra, custo_frete_montagem, imposto_pct, comissao_pct, markup, preco_venda, lucro_liquido, entrada_valor, num_parcelas, forma_pagamento, items_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                agora,
                CURRENT_DATA["cliente_nome"],
                CURRENT_DATA["cliente_telefone"],
                CURRENT_DATA["cliente_ambiente"],
                CURRENT_DATA["prazo_entrega"],
                CURRENT_DATA.get("status", "Em Negociação"),
                dre["custo_mat"],
                dre["custo_mo"],
                dre["custo_frete_mont"],
                CURRENT_DATA["imposto_pct"],
                CURRENT_DATA["comissao_pct"],
                CURRENT_DATA["markup"],
                dre["pv"],
                dre["lucro_liquido"],
                CURRENT_DATA.get("entrada_valor", 0.0),
                CURRENT_DATA.get("num_parcelas", 1),
                CURRENT_DATA.get("forma_pagamento", "PIX"),
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
            CURRENT_DATA["status"] = row["status"] or "Em Negociação"
            CURRENT_DATA["cliente_nome"] = row["cliente_nome"]
            CURRENT_DATA["cliente_telefone"] = row["cliente_telefone"]
            CURRENT_DATA["cliente_ambiente"] = row["cliente_ambiente"]
            CURRENT_DATA["prazo_entrega"] = row["prazo_entrega"]
            CURRENT_DATA["custo_materiais"] = row["custo_materiais"]
            CURRENT_DATA["imposto_pct"] = row["imposto_pct"] or 6.0
            CURRENT_DATA["comissao_pct"] = row["comissao_pct"] or 4.0
            CURRENT_DATA["markup"] = row["markup"] or 2.2
            try:
                CURRENT_DATA["entrada_valor"] = float(row["entrada_valor"] or 0.0)
                CURRENT_DATA["num_parcelas"] = int(row["num_parcelas"] or 1)
                CURRENT_DATA["forma_pagamento"] = row["forma_pagamento"] or "PIX"
            except Exception:
                pass
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
    cliente_nome: str = Form(...),
    cliente_telefone: str = Form(...),
    cliente_ambiente: str = Form(...),
    prazo_entrega: str = Form(...),
    status: str = Form("Em Negociação")
):
    CURRENT_DATA["cliente_nome"] = cliente_nome
    CURRENT_DATA["cliente_telefone"] = cliente_telefone
    CURRENT_DATA["cliente_ambiente"] = cliente_ambiente
    CURRENT_DATA["prazo_entrega"] = prazo_entrega
    CURRENT_DATA["status"] = status
    return RedirectResponse(url="/painel-get", status_code=303)

@app.post("/salvar-precos", response_class=HTMLResponse)
def salvar_precos(
    mdf_m2: float = Form(65.0),
    dobradica: float = Form(18.50),
    corredica: float = Form(38.00),
    fita_borda_m: float = Form(3.20),
    puxador: float = Form(25.00)
):
    if CURRENT_DATA.get("user_perfil") == "admin":
        precos = {
            "mdf_m2": mdf_m2,
            "dobradica": dobradica,
            "corredica": corredica,
            "fita_borda_m": fita_borda_m,
            "puxador": puxador,
            "outros_insumos": 15.00
        }
        set_precos_config(precos)

        novo_mat = 0.0
        for it in CURRENT_DATA["items"]:
            valor_item, tipo = calcular_custo_item(it["nome"], it.get("largura", 0), it.get("altura", 0), it["qtd"], precos)
            it["valor"] = valor_item
            it["tipo"] = tipo
            novo_mat += valor_item

        CURRENT_DATA["custo_materiais"] = novo_mat
    return RedirectResponse(url="/painel-get", status_code=303)

@app.post("/recalcular", response_class=HTMLResponse)
def recalcular(markup: float = Form(2.2)):
    if CURRENT_DATA.get("user_perfil") == "admin":
        CURRENT_DATA["markup"] = markup
    return RedirectResponse(url="/painel-get", status_code=303)

@app.post("/upload-xml", response_class=HTMLResponse)
async def upload_xml(file: UploadFile = File(...)):
    contents = await file.read()
    items = []
    total_mat = 0.0
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
                total_mat += custo_total_item

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
            total_mat = sum(i["valor"] for i in items)

    except Exception:
        items = [
            {"nome": "Dobradiça Ø35mm Reta Slowmotion", "tipo": "Ferragem (Dobradiça)", "largura": 0, "altura": 0, "dimensoes": "-", "qtd": 10, "valor": 10 * precos["dobradica"]},
            {"nome": "Painel MDF Freijó 18mm", "tipo": "Chapa MDF / Painel", "largura": 1800, "altura": 800, "dimensoes": "1800 x 800 x 18", "qtd": 2, "valor": 2 * (1.8 * 0.8 * precos["mdf_m2"])}
        ]
        total_mat = sum(i["valor"] for i in items)

    CURRENT_DATA["items"] = items
    CURRENT_DATA["custo_materiais"] = total_mat
    return RedirectResponse(url="/painel-get", status_code=303)

@app.get("/gerar-pdf")
def gerar_pdf(id: int = None):
    empresa = get_empresa_config()
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
                c_status = row["status"] or "Em Negociação"
                pv = row["preco_venda"]
                entrada = float(row["entrada_valor"] or 0.0)
                n_parc = int(row["num_parcelas"] or 1)
                forma_pgto = row["forma_pagamento"] or "PIX"
                items = json.loads(row["items_json"]) if row["items_json"] else []
            else:
                return Response(content="Orçamento não encontrado", status_code=404)
    else:
        dre = calcular_dre_completa(CURRENT_DATA)
        c_nome = CURRENT_DATA['cliente_nome']
        c_tel = CURRENT_DATA['cliente_telefone']
        c_amb = CURRENT_DATA['cliente_ambiente']
        c_prazo = CURRENT_DATA['prazo_entrega']
        c_status = CURRENT_DATA.get('status', 'Em Negociação')
        pv = dre["pv"]
        entrada = dre["entrada"]
        n_parc = dre["n_parc"]
        forma_pgto = CURRENT_DATA.get("forma_pagamento", "PIX")
        items = CURRENT_DATA["items"]

    v_parc = (pv - entrada) / n_parc if n_parc > 0 else 0.0

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    styles = getSampleStyleSheet()
    elements = []

    title_style = ParagraphStyle(name='TitleStyle', parent=styles['Heading1'], fontSize=18, textColor=colors.HexColor('#0f172a'), spaceAfter=2)
    sub_empresa = ParagraphStyle(name='SubEmpresa', parent=styles['Normal'], fontSize=9, textColor=colors.HexColor('#475569'), spaceAfter=10)
    
    elements.append(Paragraph(f"{empresa['nome_empresa']}", title_style))
    elements.append(Paragraph(f"CNPJ: {empresa['cnpj']} | Contato: {empresa['telefone_empresa']} | PIX: {empresa['pix']}", sub_empresa))
    elements.append(Spacer(1, 4))

    cliente_data = [
        ["Cliente:", c_nome, "Data da Proposta:", date.today().strftime("%d/%m/%Y")],
        ["WhatsApp/Tel:", c_tel, "Prazo de Entrega:", c_prazo],
        ["Ambiente/Projeto:", c_amb, "Status:", c_status]
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
    elements.append(Spacer(1, 12))

    cond_texto = f"Entrada de R$ {entrada:,.2f} + {n_parc}x de R$ {v_parc:,.2f} ({forma_pgto})" if n_parc > 1 else f"À vista: R$ {pv:,.2f} ({forma_pgto})"

    dre_data = [
        ["Ambiente / Projeto", f"{c_amb}"],
        ["Prazo de Fabricação e Instalação", f"{c_prazo}"],
        ["Condições de Pagamento", cond_texto],
        ["Garantia Estrutural e Ferragens", "12 meses contra defeitos de fabricação"],
        ["VALOR TOTAL DO INVESTIMENTO", f"R$ {pv:,.2f}"]
    ]
    dre_table = Table(dre_data, colWidths=[240, 300])
    dre_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 3), colors.HexColor('#f8fafc')),
        ('BACKGROUND', (0, 4), (-1, 4), colors.HexColor('#dbeafe')),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#0f172a')),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
    ]))
    elements.append(dre_table)
    elements.append(Spacer(1, 14))

    sum_title = ParagraphStyle(name='SumTitle', parent=styles['Heading2'], fontSize=12, textColor=colors.HexColor('#0284c7'), spaceAfter=6)
    elements.append(Paragraph("Especificação dos Módulos e Componentes", sum_title))

    items = items or [{"nome": "Módulo Planejado", "dimensoes": "-", "qtd": 1}]
    table_data = [["Descrição do Componente", "Dimensões Técnicas", "Qtd", "Tipo"]]
    for it in items:
        table_data.append([
            it.get("nome", "Peça"),
            it.get("dimensoes", "-"),
            str(it.get("qtd", 1)),
            it.get("tipo", "Módulo")
        ])

    items_table = Table(table_data, colWidths=[230, 130, 50, 130])
    items_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0284c7')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (2, 0), (2, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
    ]))
    elements.append(items_table)

    doc.build(elements)
    buffer.seek(0)
    nome_arquivo = f"proposta-{c_nome.replace(' ', '_')}.pdf"
    return Response(content=buffer.getvalue(), media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename={nome_arquivo}"})

@app.get("/gerar-contrato")
def gerar_contrato(id: int = None):
    empresa = get_empresa_config()
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
                pv = row["preco_venda"]
                entrada = float(row["entrada_valor"] or 0.0)
                n_parc = int(row["num_parcelas"] or 1)
                forma_pgto = row["forma_pagamento"] or "PIX"
            else:
                return Response(content="Orçamento não encontrado", status_code=404)
    else:
        dre = calcular_dre_completa(CURRENT_DATA)
        c_nome = CURRENT_DATA['cliente_nome']
        c_tel = CURRENT_DATA['cliente_telefone']
        c_amb = CURRENT_DATA['cliente_ambiente']
        c_prazo = CURRENT_DATA['prazo_entrega']
        pv = dre["pv"]
        entrada = dre["entrada"]
        n_parc = dre["n_parc"]
        forma_pgto = CURRENT_DATA.get("forma_pagamento", "PIX")

    v_parc = (pv - entrada) / n_parc if n_parc > 0 else 0.0

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    styles = getSampleStyleSheet()
    elements = []

    title_style = ParagraphStyle(name='TitleStyle', parent=styles['Heading1'], fontSize=15, alignment=1, textColor=colors.HexColor('#0f172a'), spaceAfter=10)
    body_style = ParagraphStyle(name='BodyStyle', parent=styles['Normal'], fontSize=9.5, leading=14, textColor=colors.HexColor('#1e293b'), spaceAfter=8)
    clause_title = ParagraphStyle(name='ClauseTitle', parent=styles['Heading2'], fontSize=11, textColor=colors.HexColor('#0369a1'), spaceBefore=8, spaceAfter=4)

    elements.append(Paragraph("<b>INSTRUMENTO PARTICULAR DE PRESTAÇÃO DE SERVIÇOS DE MARCENARIA</b>", title_style))
    elements.append(Spacer(1, 4))

    # Identificação das Partes
    elements.append(Paragraph("<b>1. IDENTIFICAÇÃO DAS PARTES CONTRATANTES</b>", clause_title))
    p_partes = f"""
    <b>CONTRATADA:</b> {empresa['nome_empresa']}, inscrita no CNPJ sob o nº {empresa['cnpj']}, contato {empresa['telefone_empresa']}.<br/>
    <b>CONTRATANTE:</b> {c_nome}, telefone/WhatsApp {c_tel}.
    """
    elements.append(Paragraph(p_partes, body_style))

    # Objeto do Contrato
    elements.append(Paragraph("<b>2. OBJETO DO CONTRATO</b>", clause_title))
    p_obj = f"O presente contrato tem por objeto a fabricação, acabamento e instalação de móveis sob medida destinados ao ambiente: <b>{c_amb}</b>, em conformidade com o projeto executivo e relação de insumos aprovados."
    elements.append(Paragraph(p_obj, body_style))

    # Preço e Pagamento
    elements.append(Paragraph("<b>3. VALOR E FORMA DE PAGAMENTO</b>", clause_title))
    cond_extenso = f"Entrada no valor de <b>R$ {entrada:,.2f}</b> mais <b>{n_parc} parcela(s)</b> de <b>R$ {v_parc:,.2f}</b> através de {forma_pgto}." if n_parc > 1 else f"Pagamento à vista no valor de <b>R$ {pv:,.2f}</b> via {forma_pgto}."
    p_preco = f"Pela execução integral dos serviços descritos, o CONTRATANTE pagará à CONTRATADA o valor total de <b>R$ {pv:,.2f}</b>, nas seguintes condições: {cond_extenso}"
    elements.append(Paragraph(p_preco, body_style))

    # Prazo de Entrega e Montagem
    elements.append(Paragraph("<b>4. PRAZO DE FABRICAÇÃO E INSTALAÇÃO</b>", clause_title))
    p_prazo = f"A CONTRATADA compromete-se a entregar e finalizar a montagem dos móveis no prazo estimado de <b>{c_prazo}</b>, contados a partir da aprovação final das medidas no local e confirmação do pagamento inicial."
    elements.append(Paragraph(p_prazo, body_style))

    # Garantia
    elements.append(Paragraph("<b>5. TERMO DE GARANTIA</b>", clause_title))
    p_garantia = "A CONTRATADA concede a garantia de <b>12 (doze) meses</b> a contar da data de entrega, cobrindo eventuais defeitos de fabricação e montagem de ferragens estruturais, não cobrindo danos ocasionados por umidade excessiva, mau uso ou intervenções de terceiros."
    elements.append(Paragraph(p_garantia, body_style))
    elements.append(Spacer(1, 16))

    # Data e Local
    data_extenso = date.today().strftime("%d de %B de %Y")
    elements.append(Paragraph(f"São Paulo, {data_extenso}.", body_style))
    elements.append(Spacer(1, 24))

    # Assinaturas
    sign_data = [
        ["_____________________________________________", "_____________________________________________"],
        [f"<b>{empresa['nome_empresa']}</b>\nCONTRATADA (CNPJ: {empresa['cnpj']})", f"<b>{c_nome}</b>\nCONTRATANTE"]
    ]
    sign_table = Table(sign_data, colWidths=[270, 270])
    sign_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#0f172a')),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    elements.append(sign_table)

    doc.build(elements)
    buffer.seek(0)
    nome_arquivo = f"contrato-{c_nome.replace(' ', '_')}.pdf"
    return Response(content=buffer.getvalue(), media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename={nome_arquivo}"})

@app.get("/gerar-pdf-compras")
def gerar_pdf_compras(id: int = None):
    empresa = get_empresa_config()
    if id:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM orcamentos WHERE id = ?", (id,))
            row = cursor.fetchone()
            if row:
                c_nome = row["cliente_nome"]
                c_amb = row["cliente_ambiente"]
                items = json.loads(row["items_json"]) if row["items_json"] else []
            else:
                return Response(content="Orçamento não encontrado", status_code=404)
    else:
        c_nome = CURRENT_DATA['cliente_nome']
        c_amb = CURRENT_DATA['cliente_ambiente']
        items = CURRENT_DATA["items"]

    compras = consolidar_compras_e_nesting(items)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    styles = getSampleStyleSheet()
    elements = []

    title_style = ParagraphStyle(name='TitleStyle', parent=styles['Heading1'], fontSize=18, textColor=colors.HexColor('#1e1b4b'), spaceAfter=4)
    elements.append(Paragraph(f"{empresa['nome_empresa']} - Cotação Fornecedor & Plano de Corte", title_style))
    elements.append(Spacer(1, 8))

    meta_data = [
        ["Projeto / Ambiente:", c_amb, "Data de Emissão:", date.today().strftime("%d/%m/%Y")],
        ["Identificação Interna:", f"Ref: {c_nome}", "Tipo:", "Cotação Direta / Madeireira"]
    ]
    meta_table = Table(meta_data, colWidths=[130, 160, 110, 140])
    meta_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#e0e7ff')),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#1e1b4b')),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#c7d2fe')),
    ]))
    elements.append(meta_table)
    elements.append(Spacer(1, 14))

    sum_title = ParagraphStyle(name='SumTitle', parent=styles['Heading2'], fontSize=13, textColor=colors.HexColor('#312e81'), spaceAfter=6)
    elements.append(Paragraph("1. Resumo de Insumos a Comprar", sum_title))

    sum_data = [
        ["Item / Insumo Requerido", "Quantidade Consolidada", "Observações Técnicas"],
        ["Chapas de MDF (Estimado)", f"{compras['chapas_mdf']} un", f"Área de corte aprox: {compras['area_m2']:.1f} m²"],
        ["Fita de Borda PVC", f"{compras['fita_metros']} metros", "Espessura padrão 22mm"],
        ["Dobradiças 35mm Slowmotion", f"{compras['dobradicas']} unidades", "Com amortecedor integrado"],
        ["Corrediças Telescópicas", f"{compras['corredicas']} pares", "Extração total / reforçada"],
        ["Puxadores / Perfis", f"{compras['puxadores']} unidades", "Conforme projeto aprovado"],
        ["Insumos Gerais / Ferragens", f"{compras['outros']} itens", "Parafusos, cantoneiras e acabamentos"]
    ]
    sum_table = Table(sum_data, colWidths=[200, 140, 200])
    sum_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4338ca')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f8fafc')),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
    ]))
    elements.append(sum_table)
    elements.append(Spacer(1, 14))

    elements.append(Paragraph("2. Detalhamento de Peças do Plano de Corte", sum_title))
    items_table_data = [["Descrição da Peça", "Dimensões (mm)", "Qtd", "Tipo"]]
    for it in (items or [{"nome": "Sem itens", "dimensoes": "-", "qtd": 1, "tipo": "-"}]):
        items_table_data.append([
            it.get("nome", "Peça"),
            it.get("dimensoes", "-"),
            str(it.get("qtd", 1)),
            it.get("tipo", "Insumo")
        ])

    items_doc_table = Table(items_table_data, colWidths=[220, 120, 50, 150])
    items_doc_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#64748b')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (2, 0), (2, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
    ]))
    elements.append(items_doc_table)

    doc.build(elements)
    buffer.seek(0)
    nome_arquivo = f"lista-compras-{c_amb.replace(' ', '_')}.pdf"
    return Response(content=buffer.getvalue(), media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename={nome_arquivo}"})

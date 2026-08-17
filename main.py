from fastapi import FastAPI, Form, UploadFile, File, Response
from fastapi.responses import HTMLResponse, RedirectResponse
import xml.etree.ElementTree as ET
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
import io
import csv
import urllib.parse
import json
import sqlite3
import math
import base64
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
            CREATE TABLE IF NOT EXISTS estoque (
                codigo TEXT PRIMARY KEY,
                descricao TEXT,
                quantidade REAL,
                qtd_minima REAL,
                unidade TEXT
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
                data_entrega_prevista TEXT,
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
                estoque_baixado INTEGER DEFAULT 0,
                valor_recebido REAL DEFAULT 0.0,
                imagens_json TEXT,
                ambientes_json TEXT,
                observacoes_tecnicas TEXT DEFAULT '',
                items_json TEXT
            )
        """)
        
        colunas = [
            ("status", "TEXT"),
            ("entrada_valor", "REAL"),
            ("num_parcelas", "INTEGER"),
            ("forma_pagamento", "TEXT"),
            ("estoque_baixado", "INTEGER"),
            ("data_entrega_prevista", "TEXT"),
            ("valor_recebido", "REAL"),
            ("imagens_json", "TEXT"),
            ("ambientes_json", "TEXT"),
            ("observacoes_tecnicas", "TEXT")
        ]
        for col, tipo in colunas:
            try:
                cursor.execute(f"ALTER TABLE orcamentos ADD COLUMN {col} {tipo}")
            except Exception:
                pass

        cursor.execute("SELECT codigo FROM estoque WHERE codigo = 'mdf'")
        if not cursor.fetchone():
            itens_padrao = [
                ('mdf', 'Chapas de MDF 18mm / 15mm', 15.0, 5.0, 'chapas'),
                ('fita', 'Fita de Borda PVC 22mm', 250.0, 50.0, 'metros'),
                ('dobradica', 'Dobradiças com Amortecedor 35mm', 80.0, 20.0, 'unidades'),
                ('corredica', 'Corrediças Telescópicas 450mm', 24.0, 6.0, 'pares'),
                ('puxador', 'Puxadores Perfil Alumínio / Pontos', 30.0, 10.0, 'unidades')
            ]
            cursor.executemany("INSERT INTO estoque VALUES (?, ?, ?, ?, ?)", itens_padrao)

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

def get_estoque_atual():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM estoque")
        return cursor.fetchall()

def get_metricas_financeiras():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT preco_venda, lucro_liquido, status, valor_recebido FROM orcamentos")
        rows = cursor.fetchall()
        
        total_orcamentos = len(rows)
        faturamento_total = 0.0
        lucro_acumulado = 0.0
        total_recebido = 0.0
        aprovados = 0
        
        for r in rows:
            st = r["status"] or "Em Negociação"
            pv = float(r["preco_venda"] or 0.0)
            lucro = float(r["lucro_liquido"] or 0.0)
            rec = float(r["valor_recebido"] or 0.0)
            
            if st in ["Aprovado", "Em Produção", "Entregue"]:
                faturamento_total += pv
                lucro_acumulado += lucro
                total_recebido += rec
                aprovados += 1

        taxa_conversao = (aprovados / total_orcamentos * 100.0) if total_orcamentos > 0 else 0.0
        ticket_medio = (faturamento_total / aprovados) if aprovados > 0 else 0.0
        saldo_a_receber = max(faturamento_total - total_recebido, 0.0)
        
        return {
            "total_orcamentos": total_orcamentos,
            "aprovados": aprovados,
            "faturamento_total": faturamento_total,
            "lucro_acumulado": lucro_acumulado,
            "total_recebido": total_recebido,
            "saldo_a_receber": saldo_a_receber,
            "ticket_medio": ticket_medio,
            "taxa_conversao": taxa_conversao
        }

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
    "data_entrega_prevista": (date.today() + timedelta(days=25)).strftime("%Y-%m-%d"),
    "entrada_valor": 1000.0,
    "num_parcelas": 3,
    "forma_pagamento": "Entrada + Cartão de Crédito",
    "estoque_baixado": 0,
    "valor_recebido": 1000.0,
    "imagens": [],
    "ambientes": ["Cozinha Planejada"],
    "observacoes_tecnicas": "Módulos com fita de borda dupla frontal. Gavetas com amortecimento slowmotion.",
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

def numero_extenso_reais(valor: float) -> str:
    inteiro = int(valor)
    centavos = int(round((valor - inteiro) * 100))
    unidades = ["", "um", "dois", "três", "quatro", "cinco", "seis", "sete", "oito", "nove"]
    de_10_a_19 = ["dez", "onze", "doze", "treze", "quatorze", "quinze", "dezesseis", "dezessete", "dezoito", "dezenove"]
    dezenas = ["", "", "vinte", "trinta", "quarenta", "cinquenta", "sessenta", "setenta", "oitenta", "noventa"]
    centenas = ["", "cento", "duzentos", "trezentos", "quatrocentos", "quinhentos", "seiscentos", "setecentos", "oitocentos", "novecentos"]

    def converter_grupo(n):
        if n == 100:
            return "cem"
        c = n // 100
        d = (n % 100) // 10
        u = n % 10
        partes = []
        if c > 0:
            partes.append(centenas[c])
        if d == 1:
            partes.append(de_10_a_19[u])
        else:
            if d > 1:
                partes.append(dezenas[d])
            if u > 0:
                partes.append(unidades[u])
        return " e ".join(partes)

    if inteiro == 0:
        texto = "zero reais"
    elif inteiro == 1:
        texto = "um real"
    else:
        milhares = inteiro // 1000
        resto = inteiro % 1000
        partes_mil = []
        if milhares > 0:
            partes_mil.append("mil" if milhares == 1 else f"{converter_grupo(milhares)} mil")
        if resto > 0:
            partes_mil.append(converter_grupo(resto))
        texto = " e ".join(partes_mil) + " reais"

    if centavos > 0:
        texto += f" e {centavos}/100 centavos"
    return texto.capitalize()

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
                <p class="text-xs text-slate-400">Gestão de Orçamentos Promob, Notificações & Produção DRE</p>
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
    
    entrada = min(float(d.get("entrada_valor", 0.0)), pv)
    saldo_restante = max(pv - entrada, 0.0)
    n_parc = max(int(d.get("num_parcelas", 1)), 1)
    valor_parcela = saldo_restante / n_parc if n_parc > 0 else 0.0
    
    valor_recebido = float(d.get("valor_recebido", 0.0))
    saldo_devedor = max(pv - valor_recebido, 0.0)

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
        "valor_parcela": valor_parcela,
        "valor_recebido": valor_recebido,
        "saldo_devedor": saldo_devedor
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
                    "ambiente": it.get("ambiente", "Geral"),
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
    estoque = get_estoque_atual()
    metricas = get_metricas_financeiras()
    imagens = data.get("imagens", [])
    ambientes = data.get("ambientes", ["Cozinha Planejada"])
    
    rows_html = ""
    if items:
        for it in items:
            valor_col = f"<td class='py-3 px-4 text-sm text-right text-emerald-400 font-semibold'>R$ {it.get('valor', 0.0):.2f}</td>" if is_admin else "<td class='py-3 px-4 text-sm text-right text-slate-500'>—</td>"
            rows_html += f"""
            <tr class="border-b border-slate-800 hover:bg-slate-850">
                <td class="py-3 px-4 text-sm text-slate-200">
                    <span class="font-medium">{it.get('nome', 'Peça')}</span>
                    <span class="block text-[11px] text-sky-400">{it.get('tipo', 'Insumo')} - {it.get('ambiente', 'Geral')}</span>
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

    galeria_html = ""
    if imagens:
        for idx, img_b64 in enumerate(imagens):
            galeria_html += f"""
            <div class="relative group rounded-lg overflow-hidden border border-slate-700 aspect-video bg-slate-950 flex items-center justify-center">
                <img src="data:image/jpeg;base64,{img_b64}" class="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300">
                <form action="/remover-imagem" method="post" class="absolute top-1.5 right-1.5 opacity-0 group-hover:opacity-100 transition-opacity">
                    <input type="hidden" name="img_index" value="{idx}">
                    <button type="submit" class="bg-rose-600 hover:bg-rose-500 text-white rounded p-1 text-[10px] shadow">✕</button>
                </form>
            </div>
            """
    else:
        galeria_html = "<div class='py-6 text-center text-xs text-slate-500 col-span-full'>Nenhum render 3D ou foto anexada. Faça upload abaixo para enriquecer a proposta comercial em PDF.</div>"

    ambientes_tags_html = ""
    for amb_nome in ambientes:
        ambientes_tags_html += f"""
        <span class="inline-flex items-center gap-1.5 px-3 py-1 bg-sky-950/80 border border-sky-700 text-sky-300 rounded-lg text-xs font-medium">
            <span>🏠 {amb_nome}</span>
            <form action="/remover-ambiente" method="post" class="inline">
                <input type="hidden" name="ambiente_nome" value="{amb_nome}">
                <button type="submit" class="hover:text-rose-400 font-bold ml-1 text-slate-400">✕</button>
            </form>
        </span>
        """

    estoque_cards_html = ""
    for est in estoque:
        is_baixo = est['quantidade'] <= est['qtd_minima']
        borda_cor = "border-rose-700/60 bg-rose-950/20" if is_baixo else "border-slate-800 bg-slate-950"
        tag_status = "<span class='text-[10px] text-rose-400 font-bold'>⚠️ Repor</span>" if is_baixo else "<span class='text-[10px] text-emerald-400'>✓ Regular</span>"
        estoque_cards_html += f"""
        <div class="p-3.5 rounded-xl border {borda_cor} flex flex-col justify-between space-y-2">
            <div class="flex justify-between items-start">
                <span class="text-[11px] font-semibold text-slate-300">{est['descricao']}</span>
                {tag_status}
            </div>
            <div class="flex justify-between items-end">
                <div>
                    <span class="text-2xl font-bold text-white">{est['quantidade']:,.0f}</span>
                    <span class="text-xs text-slate-400"> {est['unidade']}</span>
                </div>
                <span class="text-[10px] text-slate-500">Mín: {est['qtd_minima']:,.0f}</span>
            </div>
        </div>
        """

    # Mensagens Prontas de WhatsApp
    cond_texto_zap = f"Entrada de R$ {dre['entrada']:,.2f} + {dre['n_parc']}x de R$ {dre['valor_parcela']:,.2f}" if dre['n_parc'] > 1 else f"R$ {dre['pv']:,.2f} à vista"
    
    msg_proposta = f"Olá {data['cliente_nome']}! Segue a proposta da {empresa['nome_empresa']} para o projeto {data['cliente_ambiente']}: Total de R$ {dre['pv']:,.2f} ({cond_texto_zap}) com entrega em {data['prazo_entrega']}."
    url_proposta = f"https://api.whatsapp.com/send?phone=55{data['cliente_telefone']}&text={urllib.parse.quote(msg_proposta)}"

    msg_producao = f"Olá {data['cliente_nome']}! Temos boas notícias: o seu projeto ({data['cliente_ambiente']}) já entrou em processo de fabricação e corte em nossa marcenaria! Previsão de montagem para {data.get('data_entrega_prevista', data['prazo_entrega'])}."
    url_producao = f"https://api.whatsapp.com/send?phone=55{data['cliente_telefone']}&text={urllib.parse.quote(msg_producao)}"

    msg_montagem = f"Olá {data['cliente_nome']}! Nossos montadores estão confirmados para realizar a instalação do projeto ({data['cliente_ambiente']}) a partir de {data.get('data_entrega_prevista', 'breve')}. Qualquer dúvida estamos à disposição!"
    url_montagem = f"https://api.whatsapp.com/send?phone=55{data['cliente_telefone']}&text={urllib.parse.quote(msg_montagem)}"

    msg_cobranca = f"Olá {data['cliente_nome']}! Passando para lembrar sobre o saldo pendente de R$ {dre['saldo_devedor']:,.2f} referente ao projeto ({data['cliente_ambiente']}). Chave PIX: {empresa['pix']}."
    url_cobranca = f"https://api.whatsapp.com/send?phone=55{data['cliente_telefone']}&text={urllib.parse.quote(msg_cobranca)}"

    hoje = date.today()
    cronograma_cards_html = ""
    historico_html = ""
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, criado_em, cliente_nome, cliente_ambiente, preco_venda, lucro_liquido, status, estoque_baixado, data_entrega_prevista, valor_recebido FROM orcamentos ORDER BY id DESC LIMIT 25")
        historico_rows = cursor.fetchall()
        
        for h in historico_rows:
            current_st = h['status'] or 'Em Negociação'
            data_prev = h['data_entrega_prevista'] or (hoje + timedelta(days=20)).strftime("%Y-%m-%d")
            pv_item = float(h['preco_venda'] or 0.0)
            rec_item = float(h['valor_recebido'] or 0.0)
            
            if pv_item > 0 and rec_item >= pv_item:
                tag_pgto = "<span class='px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-950 text-emerald-300 border border-emerald-800'>🟢 Quitado</span>"
            elif rec_item > 0:
                tag_pgto = f"<span class='px-2 py-0.5 rounded text-[10px] font-semibold bg-amber-950 text-amber-300 border border-amber-800'>🟡 Pago: R$ {rec_item:,.0f}</span>"
            else:
                tag_pgto = "<span class='px-2 py-0.5 rounded text-[10px] font-semibold bg-rose-950 text-rose-300 border border-rose-800'>🔴 Pendente</span>"

            try:
                dt_obj = datetime.strptime(data_prev, "%Y-%m-%d").date()
                dias_restantes = (dt_obj - hoje).days
            except Exception:
                dias_restantes = 15
                dt_obj = hoje + timedelta(days=15)

            if current_st in ["Em Produção", "Aprovado"]:
                if dias_restantes < 0:
                    badge_tempo = f"<span class='text-rose-400 font-bold'>🔴 Atrasado ({abs(dias_restantes)}d)</span>"
                    card_border = "border-rose-700/60 bg-rose-950/20"
                elif dias_restantes <= 5:
                    badge_tempo = f"<span class='text-amber-400 font-bold'>🟡 {dias_restantes} dias restantes</span>"
                    card_border = "border-amber-700/60 bg-amber-950/20"
                else:
                    badge_tempo = f"<span class='text-emerald-400 font-bold'>🟢 {dias_restantes} dias restantes</span>"
                    card_border = "border-slate-800 bg-slate-950"

                cronograma_cards_html += f"""
                <div class="p-3.5 rounded-xl border {card_border} flex flex-col justify-between space-y-2">
                    <div class="flex justify-between items-start">
                        <div>
                            <span class="font-bold text-white text-xs block">{h['cliente_nome']}</span>
                            <span class="text-[11px] text-sky-400">{h['cliente_ambiente']}</span>
                        </div>
                        {badge_tempo}
                    </div>
                    <div class="flex justify-between items-center text-[11px] text-slate-400 border-t border-slate-800/80 pt-2">
                        <span>Montagem: <b>{dt_obj.strftime('%d/%m/%Y')}</b></span>
                        <span class="text-white font-semibold">R$ {h['preco_venda']:,.2f}</span>
                    </div>
                </div>
                """

            lucro_col = f"<td class='py-3 px-4 text-right text-emerald-400 font-semibold'>R$ {h['lucro_liquido']:,.2f}</td>" if is_admin else "<td class='py-3 px-4 text-right text-slate-500'>—</td>"
            baixado = int(h['estoque_baixado'] or 0)
            
            btn_baixa = "<span class='text-[10px] text-emerald-400 font-medium px-2 py-0.5 bg-emerald-950/60 rounded border border-emerald-800'>Baixado</span>" if baixado else f"""
            <form action="/dar-baixa-estoque" method="post" class="inline" onsubmit="return confirm('Confirmar baixa automática dos materiais no estoque?');">
                <input type="hidden" name="orcamento_id" value="{h['id']}">
                <button type="submit" class="px-2 py-1 bg-indigo-600 hover:bg-indigo-500 text-white rounded text-[10px] font-semibold">Baixar</button>
            </form>
            """

            historico_html += f"""
            <tr class="border-b border-slate-800 hover:bg-slate-800/40 text-xs item-linha" data-busca="{h['cliente_nome'].lower()} {h['cliente_ambiente'].lower()} {current_st.lower()}">
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
                    {tag_pgto}
                </td>
                <td class="py-3 px-4 text-center">
                    {btn_baixa}
                </td>
                <td class="py-3 px-4 text-center">
                    <div class="flex items-center justify-center space-x-1">
                        <form action="/carregar-orcamento" method="post" class="inline">
                            <input type="hidden" name="orcamento_id" value="{h['id']}">
                            <button type="submit" class="px-2 py-1 bg-sky-600 hover:bg-sky-500 text-white rounded text-[11px] font-semibold">Abrir</button>
                        </form>
                        <a href="/gerar-pdf?id={h['id']}" class="px-1 py-1 bg-emerald-700 hover:bg-emerald-600 text-white rounded text-[10px] font-semibold">Orç.</a>
                        <a href="/gerar-contrato?id={h['id']}" class="px-1 py-1 bg-amber-700 hover:bg-amber-600 text-white rounded text-[10px] font-semibold">Contrato</a>
                        <a href="/gerar-os?id={h['id']}" class="px-1 py-1 bg-blue-800 hover:bg-blue-700 text-white rounded text-[10px] font-semibold">O.S.</a>
                        <a href="/gerar-recibo?id={h['id']}" class="px-1 py-1 bg-blue-600 hover:bg-blue-500 text-white rounded text-[10px] font-semibold">Recibo</a>
                        <a href="/gerar-vistoria?id={h['id']}" class="px-1 py-1 bg-purple-700 hover:bg-purple-600 text-white rounded text-[10px] font-semibold">Vistoria</a>
                        <a href="/gerar-etiquetas?id={h['id']}" class="px-1 py-1 bg-teal-700 hover:bg-teal-600 text-white rounded text-[10px] font-semibold">Etiquetas</a>
                        <form action="/excluir-orcamento" method="post" class="inline" onsubmit="return confirm('Deseja excluir este orçamento?');">
                            <input type="hidden" name="orcamento_id" value="{h['id']}">
                            <button type="submit" class="px-1 py-1 bg-rose-700/60 hover:bg-rose-600 text-white rounded text-[10px]">✕</button>
                        </form>
                    </div>
                </td>
            </tr>
            """

        if not historico_rows:
            historico_html = "<tr><td colspan='10' class='py-6 text-center text-xs text-slate-500'>Nenhum orçamento salvo no histórico ainda.</td></tr>"

    cronograma_cards_html = cronograma_cards_html or "<div class='py-6 text-center text-xs text-slate-500 col-span-full'>Nenhum projeto em produção no momento. Passe orçamentos para 'Em Produção' ou 'Aprovado' para ver o cronograma.</div>"

    msg_cotacao = f"*COTAÇÃO DE MATERIAIS - {empresa['nome_empresa']}*\n"
    msg_cotacao += f"Projeto: {data['cliente_ambiente']}\n"
    msg_cotacao += f"- Chapas MDF: {compras['chapas_mdf']} un ({compras['area_m2']:.1f} m²)\n"
    msg_cotacao += f"- Fita Borda: {compras['fita_metros']} metros\n"
    msg_cotacao += f"- Dobradiças c/ amortecedor: {compras['dobradicas']} un\n"
    msg_cotacao += f"- Corrediças Telescópicas: {compras['corredicas']} pares\n"
    msg_cotacao += f"- Puxadores: {compras['puxadores']} un\n"
    msg_cotacao += f"Favor enviar cotação e disponibilidade."
    zap_cotacao_url = f"https://api.whatsapp.com/send?text={urllib.parse.quote(msg_cotacao)}"

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
            <p class="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">Faturamento Fechado</p>
            <p class="text-xl font-bold text-sky-400">R$ {metricas['faturamento_total']:,.2f}</p>
            <p class="text-[11px] text-slate-500">Recebido: R$ {metricas['total_recebido']:,.2f} | Saldo: R$ {metricas['saldo_a_receber']:,.2f}</p>
        </div>
        <div class="bg-slate-900 border border-slate-800 p-5 rounded-xl space-y-1 shadow-lg">
            <p class="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">Lucro Líquido Acumulado</p>
            <p class="text-xl font-bold text-emerald-400">R$ {metricas['lucro_acumulado']:,.2f}</p>
            <p class="text-[11px] text-slate-500">Saldo limpo gerado no caixa</p>
        </div>
        <div class="bg-slate-900 border border-slate-800 p-5 rounded-xl space-y-1 shadow-lg">
            <p class="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">Ticket Médio por Projeto</p>
            <p class="text-xl font-bold text-white">R$ {metricas['ticket_medio']:,.2f}</p>
            <p class="text-[11px] text-slate-500">{metricas['aprovados']} projetos fechados</p>
        </div>
        <div class="bg-slate-900 border border-slate-800 p-5 rounded-xl space-y-1 shadow-lg">
            <p class="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">Taxa de Conversão</p>
            <p class="text-xl font-bold text-amber-400">{metricas['taxa_conversao']:.1f}%</p>
            <p class="text-[11px] text-slate-500">{metricas['total_orcamentos']} orçamentos gerados no total</p>
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
    <!-- Módulo de Controle de Estoque & Entrada de Mercadorias -->
    <div class="bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-lg space-y-4">
        <div class="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-2 border-b border-slate-800 pb-3">
            <div>
                <h2 class="text-base font-semibold text-white">📦 Controle de Estoque & Insumos da Marcenaria</h2>
                <p class="text-xs text-slate-400">Saldos atuais de materiais com alerta automático de reposição</p>
            </div>
            <span class="text-xs text-indigo-400 font-medium">Baixa automática vinculada à produção</span>
        </div>
        
        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
            {estoque_cards_html}
        </div>

        <form action="/adicionar-estoque" method="post" class="bg-slate-950 p-4 rounded-xl border border-slate-800 flex flex-wrap items-end gap-3">
            <div class="flex-1 min-w-[180px]">
                <label class="block text-[11px] font-medium text-slate-400 mb-1">Insumo / Material p/ Entrada</label>
                <select name="codigo" class="w-full px-3 py-1.5 bg-slate-900 border border-slate-700 rounded-lg text-xs text-white">
                    <option value="mdf">Chapas de MDF (Chapas)</option>
                    <option value="fita">Fita de Borda PVC (Metros)</option>
                    <option value="dobradica">Dobradiças com Amortecedor (Un)</option>
                    <option value="corredica">Corrediças Telescópicas (Pares)</option>
                    <option value="puxador">Puxadores (Un)</option>
                </select>
            </div>
            <div class="w-32">
                <label class="block text-[11px] font-medium text-slate-400 mb-1">Qtd Comprada</label>
                <input type="number" step="1" min="1" name="quantidade" required value="10" class="w-full px-3 py-1.5 bg-slate-900 border border-slate-700 rounded-lg text-xs text-white">
            </div>
            <button type="submit" class="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-xs font-semibold shrink-0">
                + Dar Entrada no Estoque
            </button>
        </form>
    </div>

    <!-- Personalização dos Dados da Sua Marcenaria -->
    <div class="bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-lg space-y-4">
        <div class="flex justify-between items-center border-b border-slate-800 pb-3">
            <h2 class="text-base font-semibold text-white">🏢 Dados da Sua Marcenaria (Contrato, O.S., Recibo e Cabeçalho do PDF)</h2>
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

            <!-- Central de Notificações WhatsApp -->
            <div class="bg-slate-900 border border-emerald-900/60 rounded-xl p-6 shadow-lg space-y-3">
                <div class="flex justify-between items-center border-b border-slate-800 pb-3">
                    <div>
                        <h2 class="text-base font-semibold text-white">📲 Central de Notificações & Mensagens WhatsApp</h2>
                        <p class="text-xs text-emerald-400">Dispare atualizações automáticas direto no WhatsApp do cliente com 1 clique</p>
                    </div>
                    <span class="text-xs text-slate-400">Cliente: <b class="text-white">{data['cliente_nome']}</b> ({data['cliente_telefone']})</span>
                </div>
                <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 pt-1">
                    <a href="{url_proposta}" target="_blank" class="p-3 bg-slate-950 hover:bg-emerald-950/40 border border-slate-800 hover:border-emerald-700 rounded-xl text-left transition-colors group flex flex-col justify-between">
                        <div>
                            <span class="text-xs font-bold text-white group-hover:text-emerald-400 block">📄 Enviar Orçamento</span>
                            <span class="text-[11px] text-slate-400 leading-tight block mt-1">Resumo de valor total, entrada e prazos negociados.</span>
                        </div>
                        <span class="text-[10px] text-emerald-500 font-semibold mt-3">Disparar no WhatsApp →</span>
                    </a>
                    <a href="{url_producao}" target="_blank" class="p-3 bg-slate-950 hover:bg-emerald-950/40 border border-slate-800 hover:border-emerald-700 rounded-xl text-left transition-colors group flex flex-col justify-between">
                        <div>
                            <span class="text-xs font-bold text-white group-hover:text-emerald-400 block">🛠️ Início da Produção</span>
                            <span class="text-[11px] text-slate-400 leading-tight block mt-1">Notifica que as chapas entraram na linha de corte.</span>
                        </div>
                        <span class="text-[10px] text-emerald-500 font-semibold mt-3">Disparar no WhatsApp →</span>
                    </a>
                    <a href="{url_montagem}" target="_blank" class="p-3 bg-slate-950 hover:bg-emerald-950/40 border border-slate-800 hover:border-emerald-700 rounded-xl text-left transition-colors group flex flex-col justify-between">
                        <div>
                            <span class="text-xs font-bold text-white group-hover:text-emerald-400 block">🚚 Agendar Montagem</span>
                            <span class="text-[11px] text-slate-400 leading-tight block mt-1">Confirma a data de chegada da equipe na obra.</span>
                        </div>
                        <span class="text-[10px] text-emerald-500 font-semibold mt-3">Disparar no WhatsApp →</span>
                    </a>
                    <a href="{url_cobranca}" target="_blank" class="p-3 bg-slate-950 hover:bg-emerald-950/40 border border-slate-800 hover:border-emerald-700 rounded-xl text-left transition-colors group flex flex-col justify-between">
                        <div>
                            <span class="text-xs font-bold text-white group-hover:text-emerald-400 block">💳 Saldo / Chave PIX</span>
                            <span class="text-[11px] text-slate-400 leading-tight block mt-1">Envia lembrete do saldo devedor e chave PIX da loja.</span>
                        </div>
                        <span class="text-[10px] text-emerald-500 font-semibold mt-3">Disparar no WhatsApp →</span>
                    </a>
                </div>
            </div>

            <!-- Gestão Multi-Ambientes (Casa Completa) -->
            <div class="bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-lg space-y-4">
                <div class="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-2 border-b border-slate-800 pb-3">
                    <div>
                        <h2 class="text-base font-semibold text-white">🏠 Ambientes do Projeto / Casa Completa</h2>
                        <p class="text-xs text-slate-400">Adicione todos os cômodos para gerar um Contrato Master unificado</p>
                    </div>
                    <form action="/adicionar-ambiente" method="post" class="flex items-center gap-2">
                        <input type="text" name="novo_ambiente" placeholder="Ex: Quarto Casal, Lavabo..." required class="px-3 py-1.5 bg-slate-950 border border-slate-700 rounded-lg text-xs text-white focus:outline-none focus:border-sky-500">
                        <button type="submit" class="px-3 py-1.5 bg-sky-600 hover:bg-sky-500 text-white rounded-lg text-xs font-semibold shrink-0">
                            + Adicionar Cômodo
                        </button>
                    </form>
                </div>
                <div class="flex flex-wrap gap-2">
                    {ambientes_tags_html}
                </div>
            </div>

            <!-- Galeria de Imagens / Renders 3D -->
            <div class="bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-lg space-y-4">
                <div class="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-2 border-b border-slate-800 pb-3">
                    <div>
                        <h2 class="text-base font-semibold text-white">🖼️ Galeria de Renders 3D & Fotos da Obra</h2>
                        <p class="text-xs text-slate-400">Anexe imagens para constar no Orçamento, O.S. e na Vistoria</p>
                    </div>
                    <form action="/upload-imagem" method="post" enctype="multipart/form-data" class="flex items-center gap-2">
                        <input type="file" name="foto" accept="image/*" required class="block w-full text-xs text-slate-400 file:mr-2 file:py-1.5 file:px-3 file:rounded-lg file:border-0 file:text-xs file:font-semibold file:bg-slate-800 file:text-slate-200 hover:file:bg-slate-700 cursor-pointer">
                        <button type="submit" class="px-3 py-1.5 bg-sky-600 hover:bg-sky-500 text-white rounded-lg text-xs font-semibold shrink-0">
                            + Anexar Imagem
                        </button>
                    </form>
                </div>
                <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
                    {galeria_html}
                </div>
            </div>

            <!-- Agenda & Cronograma de Entregas e Montagens -->
            <div class="bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-lg space-y-4">
                <div class="flex justify-between items-center border-b border-slate-800 pb-3">
                    <div>
                        <h2 class="text-base font-semibold text-white">📅 Cronograma de Entregas & Montagens (Fábrica)</h2>
                        <p class="text-xs text-slate-400">Contagem de dias e monitoramento de prazos críticos</p>
                    </div>
                    <span class="text-xs text-sky-400 font-medium">Controle de Fábrica</span>
                </div>
                <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                    {cronograma_cards_html}
                </div>
            </div>

            <!-- Contas a Receber & Simulador de Pagamento -->
            <div class="bg-slate-900 border border-amber-900/50 rounded-xl p-6 shadow-lg space-y-4">
                <div class="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-2 border-b border-slate-800 pb-3">
                    <div>
                        <h2 class="text-base font-semibold text-white">💳 Contas a Receber, Parcelamento & Recibos</h2>
                        <p class="text-xs text-amber-400">Acompanhe entradas, registre pagamentos e emita recibos oficiais</p>
                    </div>
                    <div class="flex flex-wrap gap-2">
                        <a href="/gerar-os" class="px-3 py-1.5 bg-blue-800 hover:bg-blue-700 text-white font-medium text-xs rounded-lg transition-colors flex items-center space-x-1 shadow-md">
                            <span>🛠️ O.S. Fábrica (PDF)</span>
                        </a>
                        <a href="/gerar-recibo" class="px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-white font-medium text-xs rounded-lg transition-colors flex items-center space-x-1 shadow-md">
                            <span>📄 Emitir Recibo (PDF)</span>
                        </a>
                        <a href="/gerar-contrato" class="px-3 py-1.5 bg-amber-600 hover:bg-amber-500 text-white font-medium text-xs rounded-lg transition-colors flex items-center space-x-1 shadow-md">
                            <span>📑 Contrato Master (PDF)</span>
                        </a>
                        <a href="/gerar-vistoria" class="px-3 py-1.5 bg-purple-600 hover:bg-purple-500 text-white font-medium text-xs rounded-lg transition-colors flex items-center space-x-1 shadow-md">
                            <span>📋 Vistoria (PDF)</span>
                        </a>
                    </div>
                </div>
                <form action="/salvar-pagamento" method="post" class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
                    <div>
                        <label class="block text-xs font-medium text-slate-400 mb-1">Valor de Entrada (R$)</label>
                        <input type="number" step="50" name="entrada_valor" value="{data['entrada_valor']}" class="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-sm text-white focus:outline-none focus:border-amber-500">
                    </div>
                    <div>
                        <label class="block text-xs font-medium text-slate-400 mb-1">Nº de Parcelas</label>
                        <select name="num_parcelas" class="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-sm text-white focus:outline-none">
                            <option value="1" {'selected' if data.get('num_parcelas')==1 else ''}>1x (À vista / Parcela Única)</option>
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
                        <label class="block text-xs font-medium text-slate-400 mb-1">Valor Já Recebido (R$)</label>
                        <input type="number" step="50" name="valor_recebido" value="{data.get('valor_recebido', 0.0)}" class="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-sm text-white focus:outline-none focus:border-amber-500">
                    </div>
                    <div>
                        <label class="block text-xs font-medium text-slate-400 mb-1">Forma de Pagamento</label>
                        <input type="text" name="forma_pagamento" value="{data['forma_pagamento']}" placeholder="Ex: Entrada PIX + Cartão" class="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-sm text-white focus:outline-none focus:border-amber-500">
                    </div>
                    <div class="flex items-end">
                        <button type="submit" class="w-full py-2 bg-amber-600 hover:bg-amber-500 text-white rounded-lg text-xs font-semibold transition-colors">
                            Atualizar Pagamento
                        </button>
                    </div>
                </form>
                <div class="bg-slate-950 p-3 rounded-lg border border-slate-800 flex flex-wrap justify-between items-center text-xs">
                    <span class="text-slate-300">Total Proposta: <b>R$ {dre['pv']:,.2f}</b> | Recebido: <b class="text-emerald-400">R$ {dre['valor_recebido']:,.2f}</b> | Saldo Devedor: <b class="text-rose-400">R$ {dre['saldo_devedor']:,.2f}</b></span>
                    <span class="text-amber-400 font-semibold">{data['forma_pagamento']}</span>
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

            <!-- Dados do Cliente & Instruções da O.S. -->
            <div class="bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-lg space-y-4">
                <div class="flex justify-between items-center border-b border-slate-800 pb-3">
                    <h2 class="text-base font-semibold text-white">👤 Dados do Cliente, O.S. & Proposta</h2>
                    <span class="text-xs text-sky-400">Vinculado ao Cronograma, Contrato, O.S., Vistoria e WhatsApp</span>
                </div>
                <form action="/salvar-cliente" method="post" class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-6 gap-3">
                    <div>
                        <label class="block text-xs font-medium text-slate-400 mb-1">Nome do Cliente</label>
                        <input type="text" name="cliente_nome" value="{data['cliente_nome']}" required class="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-sm text-white focus:outline-none focus:border-sky-500">
                    </div>
                    <div>
                        <label class="block text-xs font-medium text-slate-400 mb-1">WhatsApp / Tel</label>
                        <input type="text" name="cliente_telefone" value="{data['cliente_telefone']}" required class="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-sm text-white focus:outline-none focus:border-sky-500">
                    </div>
                    <div>
                        <label class="block text-xs font-medium text-slate-400 mb-1">Projeto Master</label>
                        <input type="text" name="cliente_ambiente" value="{data['cliente_ambiente']}" required class="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-sm text-white focus:outline-none focus:border-sky-500">
                    </div>
                    <div>
                        <label class="block text-xs font-medium text-slate-400 mb-1">Data Montagem</label>
                        <input type="date" name="data_entrega_prevista" value="{data.get('data_entrega_prevista', '')}" required class="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-sm text-white focus:outline-none focus:border-sky-500">
                    </div>
                    <div>
                        <label class="block text-xs font-medium text-slate-400 mb-1">Status</label>
                        <select name="status" class="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-sm text-white focus:outline-none">
                            <option value="Em Negociação" {'selected' if data.get('status')=='Em Negociação' else ''}>🟡 Em Negociação</option>
                            <option value="Aprovado" {'selected' if data.get('status')=='Aprovado' else ''}>🟢 Aprovado</option>
                            <option value="Em Produção" {'selected' if data.get('status')=='Em Produção' else ''}>🔵 Em Produção</option>
                            <option value="Entregue" {'selected' if data.get('status')=='Entregue' else ''}>🟣 Entregue</option>
                            <option value="Cancelado" {'selected' if data.get('status')=='Cancelado' else ''}>🔴 Cancelado</option>
                        </select>
                    </div>
                    <div>
                        <label class="block text-xs font-medium text-slate-400 mb-1">Prazo Texto</label>
                        <input type="text" name="prazo_entrega" value="{data['prazo_entrega']}" required class="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-sm text-white focus:outline-none focus:border-sky-500">
                    </div>
                    <div class="col-span-full">
                        <label class="block text-xs font-medium text-slate-400 mb-1">Instruções Técnicas da Fábrica (O.S. / Montadores)</label>
                        <div class="flex gap-2">
                            <input type="text" name="observacoes_tecnicas" value="{data.get('observacoes_tecnicas', '')}" placeholder="Ex: Detalhes de furação, recortes de tomadas, puxadores..." class="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-sm text-white focus:outline-none focus:border-sky-500">
                            <button type="submit" class="px-6 py-2 bg-sky-600 hover:bg-sky-500 text-white rounded-lg text-xs font-semibold shrink-0">
                                Salvar Dados
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
                    <h2 class="text-base font-semibold text-white">Ações da Proposta & Produção</h2>
                    {markup_control}
                    
                    <div class="space-y-2">
                        <form action="/salvar-banco" method="post">
                            <button type="submit" class="w-full py-2 bg-blue-600 hover:bg-blue-500 text-white font-semibold text-center text-xs rounded-lg transition-colors flex items-center justify-center space-x-1 shadow-lg shadow-blue-600/20">
                                <span>💾 Salvar no Histórico (Banco)</span>
                            </button>
                        </form>
                        <div class="grid grid-cols-2 gap-1.5">
                            <a href="/gerar-pdf" class="py-2 bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-center text-[11px] rounded-lg transition-colors flex items-center justify-center shadow-lg shadow-emerald-600/20">
                                <span>📄 Orçamento</span>
                            </a>
                            <a href="/gerar-contrato" class="py-2 bg-amber-600 hover:bg-amber-500 text-white font-semibold text-center text-[11px] rounded-lg transition-colors flex items-center justify-center shadow-lg shadow-amber-600/20">
                                <span>📑 Contrato</span>
                            </a>
                            <a href="/gerar-os" class="py-2 bg-blue-800 hover:bg-blue-700 text-white font-semibold text-center text-[11px] rounded-lg transition-colors flex items-center justify-center shadow-lg shadow-blue-800/20">
                                <span>🛠️ O.S. Fábrica</span>
                            </a>
                            <a href="/gerar-recibo" class="py-2 bg-blue-600 hover:bg-blue-500 text-white font-semibold text-center text-[11px] rounded-lg transition-colors flex items-center justify-center shadow-lg shadow-blue-600/20">
                                <span>🧾 Recibo</span>
                            </a>
                            <a href="/gerar-vistoria" class="py-2 bg-purple-600 hover:bg-purple-500 text-white font-semibold text-center text-[11px] rounded-lg transition-colors flex items-center justify-center shadow-lg shadow-purple-600/20">
                                <span>📋 Vistoria</span>
                            </a>
                            <a href="/gerar-etiquetas" class="py-2 bg-teal-600 hover:bg-teal-500 text-white font-semibold text-center text-[11px] rounded-lg transition-colors flex items-center justify-center shadow-lg shadow-teal-600/20">
                                <span>🏷️ Etiquetas</span>
                            </a>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Histórico de Orçamentos com Busca e Contas a Receber -->
            <div class="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-lg">
                <div class="p-4 border-b border-slate-800 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3 bg-slate-850">
                    <div>
                        <h3 class="text-sm font-semibold text-white">📁 Histórico, Pedidos & Contas a Receber (Banco de Dados)</h3>
                        <span class="text-xs text-slate-400">Pesquise por cliente, emita O.S., recibos e gerencie recebimentos</span>
                    </div>
                    <div class="flex items-center space-x-2 w-full sm:w-auto">
                        <input type="text" id="campoBusca" onkeyup="filtrarTabela()" placeholder="🔍 Buscar cliente ou ambiente..." class="px-3 py-1.5 bg-slate-950 border border-slate-700 rounded-lg text-xs text-white focus:outline-none focus:border-sky-500 w-full sm:w-64">
                        <a href="/exportar-csv" class="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 rounded-lg text-xs font-semibold flex items-center space-x-1 shrink-0">
                            <span>📊 CSV</span>
                        </a>
                    </div>
                </div>
                <div class="overflow-x-auto">
                    <table class="w-full text-left border-collapse" id="tabelaHistorico">
                        <thead>
                            <tr class="bg-slate-800/40 border-b border-slate-800 text-xs font-semibold text-slate-400 uppercase">
                                <th class="py-3 px-4"># ID</th>
                                <th class="py-3 px-4">Data/Hora</th>
                                <th class="py-3 px-4">Cliente</th>
                                <th class="py-3 px-4">Ambiente</th>
                                <th class="py-3 px-4 text-right">Valor Venda</th>
                                <th class="py-3 px-4 text-right">Lucro Líquido</th>
                                <th class="py-3 px-4 text-center">Status</th>
                                <th class="py-3 px-4 text-center">Pagamento</th>
                                <th class="py-3 px-4 text-center">Estoque</th>
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

        <script>
            function filtrarTabela() {{
                var input = document.getElementById("campoBusca");
                var filter = input.value.toLowerCase();
                var rows = document.getElementsByClassName("item-linha");
                for (var i = 0; i < rows.length; i++) {{
                    var data = rows[i].getAttribute("data-busca");
                    if (data && data.indexOf(filter) > -1) {{
                        rows[i].style.display = "";
                    }} else {{
                        rows[i].style.display = "none";
                    }}
                }}
            }}
        </script>
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

@app.post("/adicionar-ambiente", response_class=HTMLResponse)
def adicionar_ambiente(novo_ambiente: str = Form(...)):
    if "ambientes" not in CURRENT_DATA:
        CURRENT_DATA["ambientes"] = []
    if novo_ambiente and novo_ambiente not in CURRENT_DATA["ambientes"]:
        CURRENT_DATA["ambientes"].append(novo_ambiente)
        CURRENT_DATA["cliente_ambiente"] = " + ".join(CURRENT_DATA["ambientes"])
    return RedirectResponse(url="/painel-get", status_code=303)

@app.post("/remover-ambiente", response_class=HTMLResponse)
def remover_ambiente(ambiente_nome: str = Form(...)):
    if "ambientes" in CURRENT_DATA and ambiente_nome in CURRENT_DATA["ambientes"]:
        CURRENT_DATA["ambientes"].remove(ambiente_nome)
        CURRENT_DATA["cliente_ambiente"] = " + ".join(CURRENT_DATA["ambientes"]) if CURRENT_DATA["ambientes"] else "Geral"
    return RedirectResponse(url="/painel-get", status_code=303)

@app.post("/upload-imagem", response_class=HTMLResponse)
async def upload_imagem(foto: UploadFile = File(...)):
    contents = await foto.read()
    if contents:
        img_b64 = base64.b64encode(contents).decode("utf-8")
        if "imagens" not in CURRENT_DATA:
            CURRENT_DATA["imagens"] = []
        CURRENT_DATA["imagens"].append(img_b64)
    return RedirectResponse(url="/painel-get", status_code=303)

@app.post("/remover-imagem", response_class=HTMLResponse)
def remover_imagem(img_index: int = Form(...)):
    if "imagens" in CURRENT_DATA and 0 <= img_index < len(CURRENT_DATA["imagens"]):
        CURRENT_DATA["imagens"].pop(img_index)
    return RedirectResponse(url="/painel-get", status_code=303)

@app.get("/exportar-csv")
def exportar_csv():
    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')
    
    writer.writerow([
        "ID", "Data/Hora", "Cliente", "Telefone", "Ambiente", "Prazo Entrega", "Data Prevista",
        "Status", "Custo Materiais (R$)", "Mao de Obra (R$)", "Frete e Montagem (R$)",
        "Impostos (%)", "Comissao (%)", "Markup", "Preco Venda (R$)", "Lucro Liquido (R$)",
        "Entrada (R$)", "Num Parcelas", "Valor Recebido (R$)", "Forma Pagamento", "Estoque Baixado"
    ])
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM orcamentos ORDER BY id DESC")
        for r in cursor.fetchall():
            writer.writerow([
                r["id"], r["criado_em"], r["cliente_nome"], r["cliente_telefone"], r["cliente_ambiente"],
                r["prazo_entrega"], r["data_entrega_prevista"] or "-", r["status"], f"{r['custo_materiais']:.2f}",
                f"{r['custo_mao_obra']:.2f}", f"{r['custo_frete_montagem']:.2f}", r["imposto_pct"],
                r["comissao_pct"], r["markup"], f"{r['preco_venda']:.2f}", f"{r['lucro_liquido']:.2f}",
                f"{r['entrada_valor'] or 0.0:.2f}", r["num_parcelas"] or 1, f"{r['valor_recebido'] or 0.0:.2f}",
                r["forma_pagamento"] or "PIX", "Sim" if r["estoque_baixado"] else "Nao"
            ])
            
    output.seek(0)
    nome_arquivo = f"relatorio-financeiro-marcenaria-{date.today().strftime('%d-%m-%Y')}.csv"
    return Response(
        content=output.getvalue().encode('utf-8-sig'),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={nome_arquivo}"}
    )

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

@app.post("/adicionar-estoque", response_class=HTMLResponse)
def adicionar_estoque(codigo: str = Form(...), quantidade: float = Form(...)):
    if CURRENT_DATA.get("user_perfil") == "admin":
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE estoque SET quantidade = quantidade + ? WHERE codigo = ?", (quantidade, codigo))
            conn.commit()
    return RedirectResponse(url="/painel-get", status_code=303)

@app.post("/dar-baixa-estoque", response_class=HTMLResponse)
def dar_baixa_estoque(orcamento_id: int = Form(...)):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT items_json, estoque_baixado FROM orcamentos WHERE id = ?", (orcamento_id,))
        row = cursor.fetchone()
        if row and not row["estoque_baixado"]:
            items = json.loads(row["items_json"]) if row["items_json"] else []
            compras = consolidar_compras_e_nesting(items)
            
            cursor.execute("UPDATE estoque SET quantidade = MAX(quantidade - ?, 0) WHERE codigo = 'mdf'", (compras["chapas_mdf"],))
            cursor.execute("UPDATE estoque SET quantidade = MAX(quantidade - ?, 0) WHERE codigo = 'fita'", (compras["fita_metros"],))
            cursor.execute("UPDATE estoque SET quantidade = MAX(quantidade - ?, 0) WHERE codigo = 'dobradica'", (compras["dobradicas"],))
            cursor.execute("UPDATE estoque SET quantidade = MAX(quantidade - ?, 0) WHERE codigo = 'corredica'", (compras["corredicas"],))
            cursor.execute("UPDATE estoque SET quantidade = MAX(quantidade - ?, 0) WHERE codigo = 'puxador'", (compras["puxadores"],))
            
            cursor.execute("UPDATE orcamentos SET estoque_baixado = 1 WHERE id = ?", (orcamento_id,))
            conn.commit()
            
    return RedirectResponse(url="/painel-get", status_code=303)

@app.post("/salvar-pagamento", response_class=HTMLResponse)
def salvar_pagamento(entrada_valor: float = Form(0.0), num_parcelas: int = Form(1), valor_recebido: float = Form(0.0), forma_pagamento: str = Form("PIX")):
    CURRENT_DATA["entrada_valor"] = entrada_valor
    CURRENT_DATA["num_parcelas"] = num_parcelas
    CURRENT_DATA["valor_recebido"] = valor_recebido
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
    CURRENT_DATA["cliente_ambiente"] = "Cozinha Planejada"
    CURRENT_DATA["prazo_entrega"] = "20 dias úteis"
    CURRENT_DATA["data_entrega_prevista"] = (date.today() + timedelta(days=20)).strftime("%Y-%m-%d")
    CURRENT_DATA["entrada_valor"] = 0.0
    CURRENT_DATA["num_parcelas"] = 1
    CURRENT_DATA["valor_recebido"] = 0.0
    CURRENT_DATA["forma_pagamento"] = "PIX / Transferência"
    CURRENT_DATA["estoque_baixado"] = 0
    CURRENT_DATA["imagens"] = []
    CURRENT_DATA["ambientes"] = ["Cozinha Planejada"]
    CURRENT_DATA["observacoes_tecnicas"] = ""
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
                    data_entrega_prevista = ?,
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
                    valor_recebido = ?,
                    imagens_json = ?,
                    ambientes_json = ?,
                    observacoes_tecnicas = ?,
                    items_json = ?
                WHERE id = ?
            """, (
                agora,
                CURRENT_DATA["cliente_nome"],
                CURRENT_DATA["cliente_telefone"],
                CURRENT_DATA["cliente_ambiente"],
                CURRENT_DATA["prazo_entrega"],
                CURRENT_DATA.get("data_entrega_prevista"),
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
                CURRENT_DATA.get("valor_recebido", 0.0),
                json.dumps(CURRENT_DATA.get("imagens", [])),
                json.dumps(CURRENT_DATA.get("ambientes", [])),
                CURRENT_DATA.get("observacoes_tecnicas", ""),
                json.dumps(CURRENT_DATA["items"]),
                CURRENT_DATA["orcamento_id"]
            ))
        else:
            cursor.execute("""
                INSERT INTO orcamentos (criado_em, cliente_nome, cliente_telefone, cliente_ambiente, prazo_entrega, data_entrega_prevista, status, custo_materiais, custo_mao_obra, custo_frete_montagem, imposto_pct, comissao_pct, markup, preco_venda, lucro_liquido, entrada_valor, num_parcelas, forma_pagamento, valor_recebido, imagens_json, ambientes_json, observacoes_tecnicas, items_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                agora,
                CURRENT_DATA["cliente_nome"],
                CURRENT_DATA["cliente_telefone"],
                CURRENT_DATA["cliente_ambiente"],
                CURRENT_DATA["prazo_entrega"],
                CURRENT_DATA.get("data_entrega_prevista"),
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
                CURRENT_DATA.get("valor_recebido", 0.0),
                json.dumps(CURRENT_DATA.get("imagens", [])),
                json.dumps(CURRENT_DATA.get("ambientes", [])),
                CURRENT_DATA.get("observacoes_tecnicas", ""),
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
            CURRENT_DATA["data_entrega_prevista"] = row["data_entrega_prevista"] or (date.today() + timedelta(days=20)).strftime("%Y-%m-%d")
            CURRENT_DATA["custo_materiais"] = row["custo_materiais"]
            CURRENT_DATA["imposto_pct"] = row["imposto_pct"] or 6.0
            CURRENT_DATA["comissao_pct"] = row["comissao_pct"] or 4.0
            CURRENT_DATA["markup"] = row["markup"] or 2.2
            try:
                CURRENT_DATA["entrada_valor"] = float(row["entrada_valor"] or 0.0)
                CURRENT_DATA["num_parcelas"] = int(row["num_parcelas"] or 1)
                CURRENT_DATA["forma_pagamento"] = row["forma_pagamento"] or "PIX"
                CURRENT_DATA["valor_recebido"] = float(row["valor_recebido"] or 0.0)
                CURRENT_DATA["estoque_baixado"] = int(row["estoque_baixado"] or 0)
                CURRENT_DATA["imagens"] = json.loads(row["imagens_json"]) if row["imagens_json"] else []
                CURRENT_DATA["ambientes"] = json.loads(row["ambientes_json"]) if row["ambientes_json"] else [row["cliente_ambiente"]]
                CURRENT_DATA["observacoes_tecnicas"] = row["observacoes_tecnicas"] or ""
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
    data_entrega_prevista: str = Form(...),
    observacoes_tecnicas: str = Form(""),
    status: str = Form("Em Negociação")
):
    CURRENT_DATA["cliente_nome"] = cliente_nome
    CURRENT_DATA["cliente_telefone"] = cliente_telefone
    CURRENT_DATA["cliente_ambiente"] = cliente_ambiente
    CURRENT_DATA["prazo_entrega"] = prazo_entrega
    CURRENT_DATA["data_entrega_prevista"] = data_entrega_prevista
    CURRENT_DATA["observacoes_tecnicas"] = observacoes_tecnicas
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
    ambiente_ativo = CURRENT_DATA.get("ambientes", ["Geral"])[0]

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
                    "ambiente": ambiente_ativo,
                    "largura": largura,
                    "altura": altura,
                    "dimensoes": f"{int(largura)} x {int(altura)} x {int(prof)}" if largura > 0 else "-",
                    "qtd": qtd,
                    "valor": custo_total_item
                })

        if not items:
            items = [
                {"nome": "Dobradiça Ecco Ø35mm Slowmotion", "tipo": "Ferragem (Dobradiça)", "ambiente": ambiente_ativo, "largura": 0, "altura": 0, "dimensoes": "-", "qtd": 22, "valor": 22 * precos["dobradica"]},
                {"nome": "Corrediça Telescópica 450mm", "tipo": "Ferragem (Corrediça)", "ambiente": ambiente_ativo, "largura": 0, "altura": 0, "dimensoes": "450 mm", "qtd": 4, "valor": 4 * precos["corredica"]},
                {"nome": "Lateral MDF Branco TX 18mm", "tipo": "Chapa MDF / Painel", "ambiente": ambiente_ativo, "largura": 2200, "altura": 600, "dimensoes": "2200 x 600 x 18", "qtd": 2, "valor": 2 * (2.2 * 0.6 * precos["mdf_m2"])},
                {"nome": "Fita de Borda PVC 22mm", "tipo": "Fita de Borda", "ambiente": ambiente_ativo, "largura": 0, "altura": 0, "dimensoes": "-", "qtd": 15, "valor": 15 * precos["fita_borda_m"]}
            ]
            total_mat = sum(i["valor"] for i in items)

    except Exception:
        items = [
            {"nome": "Dobradiça Ø35mm Reta Slowmotion", "tipo": "Ferragem (Dobradiça)", "ambiente": ambiente_ativo, "largura": 0, "altura": 0, "dimensoes": "-", "qtd": 10, "valor": 10 * precos["dobradica"]},
            {"nome": "Painel MDF Freijó 18mm", "tipo": "Chapa MDF / Painel", "ambiente": ambiente_ativo, "largura": 1800, "altura": 800, "dimensoes": "1800 x 800 x 18", "qtd": 2, "valor": 2 * (1.8 * 0.8 * precos["mdf_m2"])}
        ]
        total_mat = sum(i["valor"] for i in items)

    CURRENT_DATA["items"] = items
    CURRENT_DATA["custo_materiais"] = total_mat
    return RedirectResponse(url="/painel-get", status_code=303)

@app.get("/gerar-os")
def gerar_os(id: int = None):
    empresa = get_empresa_config()
    ambientes_list = []
    if id:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM orcamentos WHERE id = ?", (id,))
            row = cursor.fetchone()
            if row:
                c_nome = row["cliente_nome"]
                c_tel = row["cliente_telefone"]
                c_amb = row["cliente_ambiente"]
                orc_id = row["id"]
                c_prazo = row["prazo_entrega"]
                c_data = row["data_entrega_prevista"] or date.today().strftime("%Y-%m-%d")
                obs = row["observacoes_tecnicas"] or "Sem observações especiais."
                ambientes_list = json.loads(row["ambientes_json"]) if row["ambientes_json"] else [c_amb]
                items = json.loads(row["items_json"]) if row["items_json"] else []
            else:
                return Response(content="Orçamento não encontrado", status_code=404)
    else:
        c_nome = CURRENT_DATA['cliente_nome']
        c_tel = CURRENT_DATA['cliente_telefone']
        c_amb = CURRENT_DATA['cliente_ambiente']
        orc_id = CURRENT_DATA['orcamento_id'] or 1
        c_prazo = CURRENT_DATA['prazo_entrega']
        c_data = CURRENT_DATA.get('data_entrega_prevista', date.today().strftime("%Y-%m-%d"))
        obs = CURRENT_DATA.get('observacoes_tecnicas', 'Sem observações especiais.')
        ambientes_list = CURRENT_DATA.get("ambientes", [c_amb])
        items = CURRENT_DATA["items"]

    compras = consolidar_compras_e_nesting(items)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    styles = getSampleStyleSheet()
    elements = []

    title_style = ParagraphStyle(name='TitleStyle', parent=styles['Heading1'], fontSize=16, textColor=colors.HexColor('#0f172a'), spaceAfter=2)
    sub_empresa = ParagraphStyle(name='SubEmpresa', parent=styles['Normal'], fontSize=9, textColor=colors.HexColor('#475569'), spaceAfter=10)
    section_title = ParagraphStyle(name='SecTitle', parent=styles['Heading2'], fontSize=11, textColor=colors.HexColor('#0284c7'), spaceBefore=8, spaceAfter=4)
    body_style = ParagraphStyle(name='BodyStyle', parent=styles['Normal'], fontSize=9, leading=13, textColor=colors.HexColor('#1e293b'))

    elements.append(Paragraph(f"<b>{empresa['nome_empresa']}</b>", title_style))
    elements.append(Paragraph(f"ORDEM DE SERVIÇO & FICHA TÉCNICA DE PRODUÇÃO - O.S. #{orc_id:04d}", sub_empresa))

    meta_data = [
        ["Cliente:", c_nome, "Data Emissão:", date.today().strftime("%d/%m/%Y")],
        ["Telefone:", c_tel, "Data Prevista Montagem:", c_data],
        ["Ambientes:", ", ".join(ambientes_list), "Prazo:", c_prazo]
    ]
    meta_table = Table(meta_data, colWidths=[110, 160, 120, 150])
    meta_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#e0f2fe')),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#0369a1')),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#93c5fd')),
    ]))
    elements.append(meta_table)
    elements.append(Spacer(1, 8))

    elements.append(Paragraph("<b>1. Separação de Ferragens & Insumos para Montagem</b>", section_title))
    ferragens_data = [
        ["Insumo / Ferragem", "Quantidade", "Status Separação Oficina"],
        ["Dobradiças Slowmotion", f"{compras['dobradicas']} un", "[  ] Separado e Conferido"],
        ["Corrediças Telescópicas", f"{compras['corredicas']} pares", "[  ] Separado e Conferido"],
        ["Puxadores / Perfis", f"{compras['puxadores']} un", "[  ] Separado e Conferido"],
        ["Fita de Borda PVC", f"{compras['fita_metros']} metros", "[  ] Separado e Conferido"],
        ["Chapas MDF Estimadas", f"{compras['chapas_mdf']} chapas", "[  ] Cortado na Seccionadora"]
    ]
    ferragens_table = Table(ferragens_data, colWidths=[200, 140, 200])
    ferragens_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0284c7')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
    ]))
    elements.append(ferragens_table)
    elements.append(Spacer(1, 8))

    elements.append(Paragraph("<b>2. Relação de Peças a Cortar & Fitamento</b>", section_title))
    pecas_data = [["Peça / Descrição", "Ambiente", "Dimensões", "Qtd"]]
    for it in (items or [{"nome": "Módulo Geral", "ambiente": "Geral", "dimensoes": "-", "qtd": 1}]):
        pecas_data.append([
            it.get("nome", "Peça"),
            it.get("ambiente", "Geral"),
            it.get("dimensoes", "-"),
            str(it.get("qtd", 1))
        ])

    pecas_table = Table(pecas_data, colWidths=[220, 130, 140, 50])
    pecas_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#334155')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (3, 0), (3, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
    ]))
    elements.append(pecas_table)
    elements.append(Spacer(1, 8))

    elements.append(Paragraph("<b>3. Observações Técnicas & Instruções da Oficina</b>", section_title))
    elements.append(Paragraph(f"<b>Instruções:</b> {obs}", body_style))
    elements.append(Spacer(1, 16))

    sign_data = [
        ["_____________________________________________", "_____________________________________________"],
        ["Marceneiro Responsável (Oficina)", "Montador Responsável (Obra)"]
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
    nome_arquivo = f"ordem-servico-{c_nome.replace(' ', '_')}.pdf"
    return Response(content=buffer.getvalue(), media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename={nome_arquivo}"})

@app.get("/gerar-pdf")
def gerar_pdf(id: int = None):
    empresa = get_empresa_config()
    imagens = []
    ambientes_list = []
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
                imagens = json.loads(row["imagens_json"]) if row["imagens_json"] else []
                ambientes_list = json.loads(row["ambientes_json"]) if row["ambientes_json"] else [c_amb]
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
        imagens = CURRENT_DATA.get("imagens", [])
        ambientes_list = CURRENT_DATA.get("ambientes", [c_amb])
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
        ["Ambientes Inclusos:", ", ".join(ambientes_list), "Status:", c_status]
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
    elements.append(Spacer(1, 10))

    if imagens:
        try:
            img_bytes = io.BytesIO(base64.b64decode(imagens[0]))
            img_render = RLImage(img_bytes, width=540, height=220)
            elements.append(img_render)
            elements.append(Spacer(1, 10))
        except Exception:
            pass

    cond_texto = f"Entrada de R$ {entrada:,.2f} + {n_parc}x de R$ {v_parc:,.2f} ({forma_pgto})" if n_parc > 1 else f"À vista: R$ {pv:,.2f} ({forma_pgto})"

    dre_data = [
        ["Ambientes do Projeto", f"{', '.join(ambientes_list)}"],
        ["Prazo de Fabricação e Instalação", f"{c_prazo}"],
        ["Condições de Pagamento", cond_texto],
        ["Garantia Estrutural e Ferragens", "12 meses contra defeitos de fabricação"],
        ["VALOR TOTAL DO INVESTIMENTO (GLOBAL)", f"R$ {pv:,.2f}"]
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
    elements.append(Spacer(1, 12))

    sum_title = ParagraphStyle(name='SumTitle', parent=styles['Heading2'], fontSize=12, textColor=colors.HexColor('#0284c7'), spaceAfter=6)
    elements.append(Paragraph("Especificação dos Módulos e Componentes", sum_title))

    items = items or [{"nome": "Módulo Planejado", "dimensoes": "-", "qtd": 1, "ambiente": "Geral"}]
    table_data = [["Descrição do Componente", "Ambiente", "Dimensões", "Qtd"]]
    for it in items:
        table_data.append([
            it.get("nome", "Peça"),
            it.get("ambiente", "Geral"),
            it.get("dimensoes", "-"),
            str(it.get("qtd", 1))
        ])

    items_table = Table(table_data, colWidths=[220, 130, 140, 50])
    items_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0284c7')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (3, 0), (3, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
    ]))
    elements.append(items_table)

    doc.build(elements)
    buffer.seek(0)
    nome_arquivo = f"proposta-{c_nome.replace(' ', '_')}.pdf"
    return Response(content=buffer.getvalue(), media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename={nome_arquivo}"})

@app.get("/gerar-recibo")
def gerar_recibo(id: int = None):
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
                orc_id = row["id"]
                pv = row["preco_venda"]
                rec = float(row["valor_recebido"] or row["entrada_valor"] or row["preco_venda"])
                forma_pgto = row["forma_pagamento"] or "PIX"
            else:
                return Response(content="Orçamento não encontrado", status_code=404)
    else:
        dre = calcular_dre_completa(CURRENT_DATA)
        c_nome = CURRENT_DATA['cliente_nome']
        c_tel = CURRENT_DATA['cliente_telefone']
        c_amb = CURRENT_DATA['cliente_ambiente']
        orc_id = CURRENT_DATA['orcamento_id'] or 1
        pv = dre["pv"]
        rec = float(CURRENT_DATA.get('valor_recebido', 0.0) or dre['entrada'] or pv)
        forma_pgto = CURRENT_DATA.get("forma_pagamento", "PIX")

    extenso = numero_extenso_reais(rec)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    styles = getSampleStyleSheet()
    elements = []

    title_style = ParagraphStyle(name='TitleStyle', parent=styles['Heading1'], fontSize=16, alignment=1, textColor=colors.HexColor('#0f172a'), spaceAfter=4)
    sub_empresa = ParagraphStyle(name='SubEmpresa', parent=styles['Normal'], fontSize=9, alignment=1, textColor=colors.HexColor('#475569'), spaceAfter=14)
    body_style = ParagraphStyle(name='BodyStyle', parent=styles['Normal'], fontSize=10, leading=15, textColor=colors.HexColor('#1e293b'))
    recibo_val_style = ParagraphStyle(name='ValStyle', parent=styles['Normal'], fontSize=12, alignment=1, textColor=colors.HexColor('#0369a1'), fontName="Helvetica-Bold")

    elements.append(Paragraph(f"<b>{empresa['nome_empresa']}</b>", title_style))
    elements.append(Paragraph(f"CNPJ: {empresa['cnpj']} | Telefone: {empresa['telefone_empresa']} | Chave PIX: {empresa['pix']}", sub_empresa))

    val_box_data = [[
        Paragraph(f"<b>RECIBO DE PAGAMENTO Nº #{orc_id:04d}</b>", recibo_val_style),
        Paragraph(f"<b>VALOR: R$ {rec:,.2f}</b>", recibo_val_style)
    ]]
    val_box = Table(val_box_data, colWidths=[270, 270])
    val_box.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#e0f2fe')),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#0284c7')),
        ('PADDING', (0, 0), (-1, -1), 8),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
    ]))
    elements.append(val_box)
    elements.append(Spacer(1, 16))

    texto_recibo = f"""
    Recebemos de <b>{c_nome}</b> (Telefone: {c_tel}) a importância de <b>R$ {rec:,.2f} ({extenso})</b>, referente ao pagamento (entrada / quitação) da fabricação e instalação de móveis planejados sob medida para o projeto/ambiente: <b>{c_amb}</b>.<br/><br/>
    <b>Forma de Liquidação:</b> {forma_pgto}.<br/>
    <b>Valor Total Contratado da Obra:</b> R$ {pv:,.2f}.<br/>
    Para clareza e firmeza do que foi recebido, firmamos o presente recibo dando plena e geral quitação da quantia paga.
    """
    elements.append(Paragraph(texto_recibo, body_style))
    elements.append(Spacer(1, 24))

    data_extenso = date.today().strftime("%d de %B de %Y")
    elements.append(Paragraph(f"Emitido em {data_extenso}.", body_style))
    elements.append(Spacer(1, 30))

    sign_data = [
        ["________________________________________________________"],
        [f"<b>{empresa['nome_empresa']}</b>\nCNPJ: {empresa['cnpj']}\nRepresentante / Financeiro"]
    ]
    sign_table = Table(sign_data, colWidths=[400])
    sign_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#0f172a')),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    elements.append(sign_table)

    doc.build(elements)
    buffer.seek(0)
    nome_arquivo = f"recibo-pagamento-{c_nome.replace(' ', '_')}.pdf"
    return Response(content=buffer.getvalue(), media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename={nome_arquivo}"})

@app.get("/gerar-vistoria")
def gerar_vistoria(id: int = None):
    empresa = get_empresa_config()
    ambientes_list = []
    if id:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM orcamentos WHERE id = ?", (id,))
            row = cursor.fetchone()
            if row:
                c_nome = row["cliente_nome"]
                c_tel = row["cliente_telefone"]
                c_amb = row["cliente_ambiente"]
                ambientes_list = json.loads(row["ambientes_json"]) if row["ambientes_json"] else [c_amb]
                c_data = row["data_entrega_prevista"] or date.today().strftime("%Y-%m-%d")
            else:
                return Response(content="Orçamento não encontrado", status_code=404)
    else:
        c_nome = CURRENT_DATA['cliente_nome']
        c_tel = CURRENT_DATA['cliente_telefone']
        c_amb = CURRENT_DATA['cliente_ambiente']
        ambientes_list = CURRENT_DATA.get("ambientes", [c_amb])
        c_data = CURRENT_DATA.get('data_entrega_prevista', date.today().strftime("%Y-%m-%d"))

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    styles = getSampleStyleSheet()
    elements = []

    title_style = ParagraphStyle(name='TitleStyle', parent=styles['Heading1'], fontSize=15, alignment=1, textColor=colors.HexColor('#0f172a'), spaceAfter=2)
    sub_empresa = ParagraphStyle(name='SubEmpresa', parent=styles['Normal'], fontSize=9, alignment=1, textColor=colors.HexColor('#475569'), spaceAfter=12)
    body_style = ParagraphStyle(name='BodyStyle', parent=styles['Normal'], fontSize=9, leading=13, textColor=colors.HexColor('#1e293b'))
    section_title = ParagraphStyle(name='SecTitle', parent=styles['Heading2'], fontSize=11, textColor=colors.HexColor('#6b21a8'), spaceBefore=8, spaceAfter=4)

    elements.append(Paragraph(f"<b>{empresa['nome_empresa']}</b>", title_style))
    elements.append(Paragraph("TERMO DE VISTORIA, ENTREGA E ACEITE FINAL DE MONTAGEM", sub_empresa))

    meta_data = [
        ["Cliente:", c_nome, "Data da Vistoria:", date.today().strftime("%d/%m/%Y")],
        ["WhatsApp/Tel:", c_tel, "Ambientes Montados:", ", ".join(ambientes_list)]
    ]
    meta_table = Table(meta_data, colWidths=[110, 160, 120, 150])
    meta_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f3e8ff')),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#581c87')),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#d8b4fe')),
    ]))
    elements.append(meta_table)
    elements.append(Spacer(1, 10))

    elements.append(Paragraph("<b>1. Checklist de Vistoria de Campo e Qualidade</b>", section_title))
    
    check_data = [
        ["Item de Verificação Técnica", "Status de Inspeção", "Rubrica Cliente / Observações"],
        ["Alinhamento e folgas de portas e gavetas", "[  ] Conforme  [  ] Ajustado", "Sem atritos estruturais"],
        ["Amortecedores (Slowmotion) e Corrediças", "[  ] Conforme  [  ] Ajustado", "Abertura e fechamento suaves"],
        ["Acabamento de fitas de borda e tapa-furos", "[  ] Conforme  [  ] Ajustado", "Refilamento perfeito"],
        ["Fixações em alvenaria e prumo dos módulos", "[  ] Conforme  [  ] Ajustado", "Fixação reforçada"],
        ["Limpeza geral e ausência de riscos nos painéis", "[  ] Conforme  [  ] Ajustado", "Higienizado para entrega"]
    ]
    check_table = Table(check_data, colWidths=[240, 130, 170])
    check_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#7e22ce')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
    ]))
    elements.append(check_table)
    elements.append(Spacer(1, 10))

    elements.append(Paragraph("<b>2. Declaração de Aceite e Quitação de Entrega</b>", section_title))
    p_aceite = """
    Pelo presente instrumento, o <b>CONTRATANTE</b> declara que acompanhou a vistoria técnica final dos móveis sob medida instalados nos ambientes supracitados, constatando que os serviços foram integralmente executados de acordo com o projeto contratado, encontrando-se em perfeito estado de funcionamento, acabamento e limpeza, dando por <b>RECEBIDA E APROVADA A OBRA</b>.
    """
    elements.append(Paragraph(p_aceite, body_style))
    elements.append(Spacer(1, 24))

    sign_data = [
        ["_____________________________________________", "_____________________________________________"],
        [f"<b>{empresa['nome_empresa']}</b>\nResponsável Técnico / Montador", f"<b>{c_nome}</b>\nAssinatura do Cliente (Aceite)"]
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
    nome_arquivo = f"termo-vistoria-{c_nome.replace(' ', '_')}.pdf"
    return Response(content=buffer.getvalue(), media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename={nome_arquivo}"})

@app.get("/gerar-etiquetas")
def gerar_etiquetas(id: int = None):
    empresa = get_empresa_config()
    if id:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM orcamentos WHERE id = ?", (id,))
            row = cursor.fetchone()
            if row:
                c_nome = row["cliente_nome"]
                c_amb = row["cliente_ambiente"]
                orc_id = row["id"]
                items = json.loads(row["items_json"]) if row["items_json"] else []
            else:
                return Response(content="Orçamento não encontrado", status_code=404)
    else:
        c_nome = CURRENT_DATA['cliente_nome']
        c_amb = CURRENT_DATA['cliente_ambiente']
        orc_id = CURRENT_DATA['orcamento_id'] or 1
        items = CURRENT_DATA["items"]

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=20, leftMargin=20, topMargin=25, bottomMargin=25)
    styles = getSampleStyleSheet()
    elements = []

    title_style = ParagraphStyle(name='TitleStyle', parent=styles['Heading1'], fontSize=16, alignment=1, textColor=colors.HexColor('#0f172a'), spaceAfter=2)
    sub_title = ParagraphStyle(name='SubTitle', parent=styles['Normal'], fontSize=9, alignment=1, textColor=colors.HexColor('#64748b'), spaceAfter=14)
    
    elements.append(Paragraph(f"<b>{empresa['nome_empresa']}</b> - Etiquetas de Produção & Fitas de Borda", title_style))
    elements.append(Paragraph(f"Projeto: <b>{c_amb}</b> | Cliente: <b>{c_nome}</b> | Ref: #{orc_id}", sub_title))

    pecas_mdf = []
    for idx, it in enumerate(items, 1):
        if "MDF" in it.get("tipo", "") or it.get("largura", 0) > 0:
            qtd = int(it.get("qtd", 1))
            for q in range(1, qtd + 1):
                pecas_mdf.append({
                    "id_tag": f"#{orc_id}-P{len(pecas_mdf)+1:02d}",
                    "nome": it.get("nome", "Peça MDF"),
                    "dim": it.get("dimensoes", "-"),
                    "fitas": "Bordas: 2x Comp. / 1x Larg."
                })

    if not pecas_mdf:
        pecas_mdf = [
            {"id_tag": f"#{orc_id}-P01", "nome": "Lateral Direita Torre Quente", "dim": "2200 x 600 x 18 mm", "fitas": "Bordas: 2C / 1L"},
            {"id_tag": f"#{orc_id}-P02", "nome": "Lateral Esquerda Torre Quente", "dim": "2200 x 600 x 18 mm", "fitas": "Bordas: 2C / 1L"},
            {"id_tag": f"#{orc_id}-P03", "nome": "Base Inferior Balcão", "dim": "1200 x 580 x 18 mm", "fitas": "Bordas: 1C / 2L"},
            {"id_tag": f"#{orc_id}-P04", "nome": "Porta Basculante Superior", "dim": "800 x 400 x 18 mm", "fitas": "Bordas: 4 Lados 22mm"}
        ]

    cards_data = []
    linha_atual = []
    
    lbl_tag = ParagraphStyle(name='LblTag', parent=styles['Normal'], fontSize=8.5, leading=10, textColor=colors.HexColor('#0284c7'), fontName="Helvetica-Bold")
    lbl_nome = ParagraphStyle(name='LblNome', parent=styles['Normal'], fontSize=9.5, leading=12, textColor=colors.HexColor('#0f172a'), fontName="Helvetica-Bold")
    lbl_dim = ParagraphStyle(name='LblDim', parent=styles['Normal'], fontSize=8.5, leading=11, textColor=colors.HexColor('#334155'))
    lbl_fitas = ParagraphStyle(name='LblFitas', parent=styles['Normal'], fontSize=8, leading=10, textColor=colors.HexColor('#166534'), fontName="Helvetica-Bold")

    for p in pecas_mdf:
        conteudo_etiqueta = [
            [Paragraph(f"<b>{p['id_tag']}</b> | {c_amb[:20]}", lbl_tag)],
            [Paragraph(f"{p['nome'][:30]}", lbl_nome)],
            [Paragraph(f"Dimensões: <b>{p['dim']}</b>", lbl_dim)],
            [Paragraph(f"🏷️ {p['fitas']}", lbl_fitas)]
        ]
        t_card = Table(conteudo_etiqueta, colWidths=[270])
        t_card.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
            ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#94a3b8')),
            ('PADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
        ]))
        
        linha_atual.append(t_card)
        if len(linha_atual) == 2:
            cards_data.append(linha_atual)
            linha_atual = []

    if linha_atual:
        linha_atual.append("")
        cards_data.append(linha_atual)

    grid_table = Table(cards_data, colWidths=[280, 280])
    grid_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
    ]))
    elements.append(grid_table)

    doc.build(elements)
    buffer.seek(0)
    nome_arquivo = f"etiquetas-producao-{c_amb.replace(' ', '_')}.pdf"
    return Response(content=buffer.getvalue(), media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename={nome_arquivo}"})

@app.get("/gerar-contrato")
def gerar_contrato(id: int = None):
    empresa = get_empresa_config()
    ambientes_list = []
    if id:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM orcamentos WHERE id = ?", (id,))
            row = cursor.fetchone()
            if row:
                c_nome = row["cliente_nome"]
                c_tel = row["cliente_telefone"]
                c_amb = row["cliente_ambiente"]
                ambientes_list = json.loads(row["ambientes_json"]) if row["ambientes_json"] else [c_amb]
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
        ambientes_list = CURRENT_DATA.get("ambientes", [c_amb])
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

    elements.append(Paragraph("<b>1. IDENTIFICAÇÃO DAS PARTES CONTRATANTES</b>", clause_title))
    p_partes = f"""
    <b>CONTRATADA:</b> {empresa['nome_empresa']}, inscrita no CNPJ sob o nº {empresa['cnpj']}, contato {empresa['telefone_empresa']}.<br/>
    <b>CONTRATANTE:</b> {c_nome}, telefone/WhatsApp {c_tel}.
    """
    elements.append(Paragraph(p_partes, body_style))

    elements.append(Paragraph("<b>2. OBJETO DO CONTRATO (PROJETO COMPLETO)</b>", clause_title))
    p_obj = f"O presente contrato tem por objeto a fabricação, acabamento e instalação de móveis sob medida destinados aos seguintes ambientes: <b>{', '.join(ambientes_list)}</b>, em conformidade com o projeto executivo e relação de insumos aprovados."
    elements.append(Paragraph(p_obj, body_style))

    elements.append(Paragraph("<b>3. VALOR E FORMA DE PAGAMENTO</b>", clause_title))
    cond_extenso = f"Entrada no valor de <b>R$ {entrada:,.2f}</b> mais <b>{n_parc} parcela(s)</b> de <b>R$ {v_parc:,.2f}</b> através de {forma_pgto}." if n_parc > 1 else f"Pagamento à vista no valor de <b>R$ {pv:,.2f}</b> via {forma_pgto}."
    p_preco = f"Pela execução integral dos serviços descritos, o CONTRATANTE pagará à CONTRATADA o valor total de <b>R$ {pv:,.2f}</b>, nas seguintes condições: {cond_extenso}"
    elements.append(Paragraph(p_preco, body_style))

    elements.append(Paragraph("<b>4. PRAZO DE FABRICAÇÃO E INSTALAÇÃO</b>", clause_title))
    p_prazo = f"A CONTRATADA compromete-se a entregar e finalizar a montagem dos móveis no prazo estimado de <b>{c_prazo}</b>, contados a partir da aprovação final das medidas no local e confirmação do pagamento inicial."
    elements.append(Paragraph(p_prazo, body_style))

    elements.append(Paragraph("<b>5. TERMO DE GARANTIA</b>", clause_title))
    p_garantia = "A CONTRATADA concede a garantia de <b>12 (doze) meses</b> a contar da data de entrega, cobrindo eventuais defeitos de fabricação e montagem de ferragens estruturais, não cobrindo danos ocasionados por umidade excessiva, mau uso ou intervenções de terceiros."
    elements.append(Paragraph(p_garantia, body_style))
    elements.append(Spacer(1, 16))

    data_extenso = date.today().strftime("%d/%m/%Y")
    elements.append(Paragraph(f"Data de formalização: {data_extenso}.", body_style))
    elements.append(Spacer(1, 24))

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
    items_table_data = [["Descrição da Peça", "Ambiente", "Dimensões (mm)", "Qtd"]]
    for it in (items or [{"nome": "Sem itens", "ambiente": "-", "dimensoes": "-", "qtd": 1}]):
        items_table_data.append([
            it.get("nome", "Peça"),
            it.get("ambiente", "Geral"),
            it.get("dimensoes", "-"),
            str(it.get("qtd", 1))
        ])

    items_doc_table = Table(items_table_data, colWidths=[220, 130, 140, 50])
    items_doc_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#64748b')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (3, 0), (3, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
    ]))
    elements.append(items_doc_table)

    doc.build(elements)
    buffer.seek(0)
    nome_arquivo = f"lista-compras-{c_amb.replace(' ', '_')}.pdf"
    return Response(content=buffer.getvalue(), media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename={nome_arquivo}"})

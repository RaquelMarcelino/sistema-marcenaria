from fastapi import FastAPI, Form, UploadFile, File, Response, Request
from fastapi.responses import HTMLResponse, RedirectResponse
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
import traceback
import secrets
import xml.etree.ElementTree as ET
from datetime import datetime, date, timedelta
from typing import List

app = FastAPI(title="MVI Móveis Planejados - Master SaaS")
DB_PATH = "mvi_production_v10.db"

# ==========================================
# 1. TRATAMENTO DE ERROS GLOBAL
# ==========================================
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    err = traceback.format_exc()
    return HTMLResponse(content=f"""
    <div style="background:#0f172a; color:#f8fafc; font-family:sans-serif; padding:30px; min-height:100vh;">
        <h2 style="color:#f59e0b;">⚠️ Diagnóstico do Sistema MVI</h2>
        <pre style="background:#1e293b; color:#f43f5e; padding:15px; border-radius:10px; font-size:12px; overflow-x:auto;">{err}</pre>
        <a href="/" style="display:inline-block; margin-top:15px; padding:10px 20px; background:#f59e0b; color:#0f172a; font-weight:bold; border-radius:8px; text-decoration:none;">Voltar ao Login</a>
    </div>
    """, status_code=500)

# ==========================================
# 2. BANCO DE DADOS & SESSÃO
# ==========================================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS empresas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT UNIQUE,
            nome_empresa TEXT,
            cnpj TEXT,
            telefone TEXT,
            pix TEXT,
            precos_json TEXT,
            chave_mestra TEXT DEFAULT 'MVI2026'
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            email TEXT PRIMARY KEY,
            senha TEXT,
            nome TEXT,
            perfil TEXT,
            empresa_id INTEGER,
            token_primeiro_acesso TEXT DEFAULT '',
            primeiro_acesso_concluido INTEGER DEFAULT 1
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS estoque (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa_id INTEGER,
            codigo TEXT,
            descricao TEXT,
            quantidade REAL DEFAULT 0,
            qtd_minima REAL DEFAULT 0,
            unidade TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orcamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa_id INTEGER DEFAULT 1,
            criado_em TEXT,
            cliente_nome TEXT,
            cliente_cpf TEXT DEFAULT '',
            cliente_rg TEXT DEFAULT '',
            cliente_rg_emissor TEXT DEFAULT '',
            cliente_nascimento TEXT DEFAULT '',
            cliente_pais TEXT DEFAULT 'Brasil',
            cliente_cidade TEXT DEFAULT '',
            cliente_email TEXT DEFAULT '',
            cliente_telefone TEXT,
            cliente_telefone_2 TEXT DEFAULT '',
            cliente_cep_postal TEXT DEFAULT '',
            cliente_endereco_postal TEXT DEFAULT '',
            cliente_cep_entrega TEXT DEFAULT '',
            cliente_endereco_entrega TEXT DEFAULT '',
            cliente_banco TEXT DEFAULT '',
            cliente_agencia TEXT DEFAULT '',
            cliente_conta TEXT DEFAULT '',
            cliente_renda TEXT DEFAULT '',
            ref_nome_1 TEXT DEFAULT '',
            ref_tel_1 TEXT DEFAULT '',
            ref_nome_2 TEXT DEFAULT '',
            ref_tel_2 TEXT DEFAULT '',
            cliente_ambiente TEXT,
            descricao_promob TEXT DEFAULT '',
            descricao_manual TEXT DEFAULT '',
            adendo_descricao TEXT DEFAULT '',
            adendo_valor REAL DEFAULT 0,
            prazo_entrega TEXT,
            data_entrega_prevista TEXT,
            status TEXT DEFAULT 'Em Negociação',
            custo_materiais REAL DEFAULT 0,
            custo_mao_obra REAL DEFAULT 0,
            custo_frete_montagem REAL DEFAULT 0,
            imposto_pct REAL DEFAULT 6,
            comissao_pct REAL DEFAULT 4,
            markup REAL DEFAULT 2.2,
            preco_venda REAL DEFAULT 0,
            desconto_pct REAL DEFAULT 0,
            desconto_autorizado INTEGER DEFAULT 1,
            liberado_financeiro INTEGER DEFAULT 0,
            lucro_liquido REAL DEFAULT 0,
            entrada_valor REAL DEFAULT 0,
            num_parcelas INTEGER DEFAULT 1,
            forma_pagamento TEXT DEFAULT 'PIX',
            estoque_baixado INTEGER DEFAULT 0,
            valor_recebido REAL DEFAULT 0,
            imagens_json TEXT DEFAULT '[]',
            ambientes_json TEXT DEFAULT '[]',
            observacoes_tecnicas TEXT DEFAULT '',
            items_json TEXT DEFAULT '[]',
            contrato_assinado INTEGER DEFAULT 0,
            assinatura_data TEXT DEFAULT '',
            assinatura_img TEXT DEFAULT ''
        )
    """)
    conn.commit()

    cursor.execute("SELECT id FROM empresas WHERE id = 1")
    if not cursor.fetchone():
        precos_iniciais = {
            "mdf_m2": 65.0, "dobradica": 18.50, "corredica": 38.00,
            "fita_borda_m": 3.20, "puxador": 25.00, "outros_insumos": 15.00
        }
        cursor.execute("""
            INSERT INTO empresas (id, slug, nome_empresa, cnpj, telefone, pix, precos_json, chave_mestra)
            VALUES (1, 'mvi', 'MVI Móveis Planejados', '00.000.000/0001-00', '(11) 98888-7777', 'financeiro@mvi.com.br', ?, 'MVI2026')
        """, (json.dumps(precos_iniciais),))
        
        cursor.execute("INSERT OR REPLACE INTO usuarios VALUES ('admin@mvi.com', '123456', 'Administrador Geral MVI', 'admin', 1, '', 1)")
        cursor.execute("INSERT OR REPLACE INTO usuarios VALUES ('vendedor@mvi.com', '123456', 'Vendedor MVI', 'vendedor', 1, '', 1)")
        
        itens_estoque = [
            (1, 'mdf', 'Chapas de MDF (Duratex/Arauco/Guararapes)', 0.0, 0.0, 'chapas'),
            (1, 'fita', 'Fita de Borda PVC 22mm / 35mm', 0.0, 0.0, 'metros'),
            (1, 'dobradica', 'Dobradiças Amortecedor (Blum/Hettich/FGV)', 0.0, 0.0, 'unidades'),
            (1, 'corredica', 'Corrediças Telescópicas / Ocultas', 0.0, 0.0, 'pares'),
            (1, 'puxador', 'Puxadores Gola / Zen / Usinados', 0.0, 0.0, 'unidades')
        ]
        cursor.executemany("INSERT INTO estoque (empresa_id, codigo, descricao, quantidade, qtd_minima, unidade) VALUES (?, ?, ?, ?, ?, ?)", itens_estoque)
        conn.commit()

    conn.close()

init_db()

CURRENT_SESSION = {
    "user_email": "admin@mvi.com",
    "user_nome": "Administrador Geral MVI",
    "user_perfil": "admin",
    "empresa_id": 1
}

def get_empresa_dados(empresa_id=1):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM empresas WHERE id = ?", (empresa_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return dict(row)
    return {
        "id": 1, "slug": "mvi", "nome_empresa": "MVI Móveis Planejados",
        "cnpj": "00.000.000/0001-00", "telefone": "(11) 98888-7777",
        "pix": "contato@mvi.com.br", "precos_json": "{}", "chave_mestra": "MVI2026"
    }

def get_metricas():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT preco_venda, adendo_valor, lucro_liquido, status, valor_recebido FROM orcamentos WHERE empresa_id = ?", (CURRENT_SESSION.get("empresa_id", 1),))
    rows = cursor.fetchall()
    conn.close()
    
    total_orcamentos = len(rows)
    faturamento_total = 0.0
    lucro_acumulado = 0.0
    total_recebido = 0.0
    aprovados = 0
    
    for r in rows:
        st = r["status"] or "Em Negociação"
        pv = float(r["preco_venda"] or 0.0) + float(r["adendo_valor"] or 0.0)
        lucro = float(r["lucro_liquido"] or 0.0)
        rec = float(r["valor_recebido"] or 0.0)
        
        if st in ["Aprovado", "Em Produção", "Entregue", "Liberado para Financeiro & Fábrica", "Contrato Assinado Digitalmente"]:
            faturamento_total += pv
            lucro_acumulado += lucro
            total_recebido += rec
            aprovados += 1

    taxa = (aprovados / total_orcamentos * 100.0) if total_orcamentos > 0 else 0.0
    ticket = (faturamento_total / aprovados) if aprovados > 0 else 0.0
    saldo = max(faturamento_total - total_recebido, 0.0)
    
    return {
        "total": total_orcamentos, "aprovados": aprovados,
        "faturamento": faturamento_total, "lucro": lucro_acumulado,
        "recebido": total_recebido, "saldo": saldo,
        "ticket": ticket, "taxa": taxa
    }

def calcular_engenharia(ambientes: list, area_m2: float, exp_caixa: str, exp_tamp: str, fab_mdf: str, cor_mdf: str, mod_portas: str, marca_ferr: str):
    empresa = get_empresa_dados(CURRENT_SESSION.get("empresa_id", 1))
    precos = json.loads(empresa.get("precos_json") or "{}")
    mdf_preco = float(precos.get("mdf_m2", 65.0))
    dob_preco = float(precos.get("dobradica", 18.50))
    corr_preco = float(precos.get("corredica", 38.00))
    fita_preco = float(precos.get("fita_borda_m", 3.20))

    fator_caixa = 1.15 if "18mm" in exp_caixa else 1.0
    fator_tamp = 1.35 if "36mm" in exp_tamp else (1.20 if "25mm" in exp_tamp else 1.0)
    fator_mdf = 1.30 if any(c in cor_mdf for c in ["Freijó", "Carvalho", "Nogueira", "Grafite"]) else 1.0
    fator_portas = 1.50 if "Reflecta" in mod_portas else (1.25 if "Gola" in mod_portas else 1.0)

    if "Blum" in marca_ferr:
        dob_mult, corr_mult = 2.8, 3.2
    elif "Hettich" in marca_ferr:
        dob_mult, corr_mult = 2.5, 2.9
    elif "Häfele" in marca_ferr:
        dob_mult, corr_mult = 2.1, 2.4
    else:
        dob_mult, corr_mult = 1.0, 1.0

    custo_base_mdf = mdf_preco * fator_caixa * fator_tamp * fator_mdf * fator_portas
    area = max(area_m2, 5.0)
    qtd_amb = max(len(ambientes), 1)
    area_comodo = area / qtd_amb

    items = []
    desc_promob_auto = []

    for amb in ambientes:
        m_lin = max(area_comodo * 0.32, 3.2 if area >= 160 else 2.2)
        num_mod = max(int(math.ceil(m_lin / 0.8)), 2)
        
        items.append({
            "nome": f"Caixaria Estrutural ({exp_caixa}) - {amb}",
            "tipo": "MDF", "ambiente": amb, "qtd": num_mod,
            "valor": num_mod * 1.25 * custo_base_mdf
        })
        items.append({
            "nome": f"Portas/Frentes ({fab_mdf} {cor_mdf})",
            "tipo": "MDF", "ambiente": amb, "qtd": num_mod * 2,
            "valor": num_mod * 2 * 0.58 * custo_base_mdf
        })
        items.append({
            "nome": f"Dobradiças c/ Amortecedor ({marca_ferr})",
            "tipo": "Ferragem", "ambiente": amb, "qtd": num_mod * 4,
            "valor": num_mod * 4 * dob_preco * dob_mult
        })
        items.append({
            "nome": f"Corrediças Telescópicas/Ocultas ({marca_ferr})",
            "tipo": "Ferragem", "ambiente": amb, "qtd": 4,
            "valor": 4 * corr_preco * corr_mult
        })
        desc_promob_auto.append(f"{amb}: {num_mod} módulos caixaria {exp_caixa}, portas {fab_mdf} ({cor_mdf}), ferragens {marca_ferr} com amortecimento.")

    total_materiais = sum(i["valor"] for i in items)
    dias_prod = max(int(math.ceil(qtd_amb * 3.0)), 4)
    custo_mo = dias_prod * 180.0
    custo_frete = max(qtd_amb * 400.0, 800.0)
    markup = 2.2

    preco_venda = (total_materiais + custo_mo + custo_frete) * markup
    lucro = preco_venda - (total_materiais + custo_mo + custo_frete + (preco_venda * 0.10))

    return {
        "items": items, "total_mat": total_materiais,
        "custo_mo": custo_mo, "custo_frete": custo_frete,
        "preco_venda": preco_venda, "lucro": lucro,
        "desc_promob": "\n".join(desc_promob_auto)
    }

def processar_arquivo_promob(conteudo_texto: str, nome_arquivo: str):
    items = []
    precos = json.loads(get_empresa_dados(1).get("precos_json") or "{}")
    mdf_m2_base = float(precos.get("mdf_m2", 65.0))
    dob_base = float(precos.get("dobradica", 18.50))
    corr_base = float(precos.get("corredica", 38.00))

    if nome_arquivo.lower().endswith(".xml"):
        try:
            root = ET.fromstring(conteudo_texto)
            for item_elem in root.iter():
                tag = item_elem.tag.lower()
                if tag in ["item", "peca", "componente", "module", "piece"]:
                    nome = item_elem.attrib.get("DESCRIPTION") or item_elem.attrib.get("NOME") or item_elem.attrib.get("NAME") or "Peça Promob"
                    larg = float(item_elem.attrib.get("WIDTH") or item_elem.attrib.get("LARGURA") or item_elem.attrib.get("LARG") or 0)
                    alt = float(item_elem.attrib.get("HEIGHT") or item_elem.attrib.get("ALTURA") or item_elem.attrib.get("ALT") or 0)
                    qtd = int(float(item_elem.attrib.get("QUANTITY") or item_elem.attrib.get("QUANTIDADE") or item_elem.attrib.get("QTD") or 1))
                    
                    if larg > 0 and alt > 0:
                        area_m2 = (larg / 1000.0) * (alt / 1000.0)
                        items.append({
                            "nome": nome, "tipo": "MDF / Peça", "ambiente": "Promob Import",
                            "largura": larg, "altura": alt, "dimensoes": f"{larg}x{alt}mm",
                            "qtd": qtd, "valor": area_m2 * mdf_m2_base * 1.3 * qtd
                        })
        except Exception:
            pass

    if not items:
        linhas = conteudo_texto.splitlines()
        for l in linhas:
            partes = [p.strip() for p in l.replace(";", "\t").replace(",", "\t").split("\t") if p.strip()]
            if len(partes) >= 3:
                try:
                    nome_peca = partes[0]
                    dim1 = float(partes[1].replace("mm", "").replace("MM", ""))
                    dim2 = float(partes[2].replace("mm", "").replace("MM", ""))
                    qtd_peca = int(partes[3]) if len(partes) >= 4 and partes[3].isdigit() else 1
                    area_m2 = (dim1 / 1000.0) * (dim2 / 1000.0)
                    items.append({
                        "nome": nome_peca, "tipo": "MDF / Promob Cut", "ambiente": "Promob Import",
                        "largura": dim1, "altura": dim2, "dimensoes": f"{dim1}x{dim2}mm",
                        "qtd": qtd_peca, "valor": area_m2 * mdf_m2_base * 1.3 * qtd_peca
                    })
                except Exception:
                    continue

    if not items:
        items.append({"nome": "Módulo Importado Promob 01", "tipo": "MDF", "ambiente": "Importação", "largura": 800, "altura": 720, "dimensoes": "800x720mm", "qtd": 4, "valor": 4 * 1.25 * mdf_m2_base})
        items.append({"nome": "Portas/Frentes Promob", "tipo": "MDF", "ambiente": "Importação", "largura": 395, "altura": 700, "dimensoes": "395x700mm", "qtd": 8, "valor": 8 * 0.58 * mdf_m2_base})
        items.append({"nome": "Dobradiças Slowmotion (Blum)", "tipo": "Ferragem", "ambiente": "Importação", "largura": 0, "altura": 0, "dimensoes": "Ø35mm", "qtd": 16, "valor": 16 * dob_base * 2.8})
        items.append({"nome": "Corrediças Ocultas (Blum)", "tipo": "Ferragem", "ambiente": "Importação", "largura": 0, "altura": 0, "dimensoes": "450mm", "qtd": 6, "valor": 6 * corr_base * 3.2})

    total_mat = sum(i["valor"] for i in items)
    dias_prod = max(int(math.ceil(len(items) * 0.4)), 3)
    custo_mo = dias_prod * 180.0
    custo_frete = max(len(items) * 35.0, 600.0)
    markup = 2.2
    preco_venda = (total_mat + custo_mo + custo_frete) * markup
    lucro = preco_venda - (total_mat + custo_mo + custo_frete + (preco_venda * 0.10))

    return {
        "items": items, "total_mat": total_mat,
        "custo_mo": custo_mo, "custo_frete": custo_frete,
        "preco_venda": preco_venda, "lucro": lucro
    }

# ==========================================
# 3. FUNÇÕES DE RENDERIZAÇÃO HTML (DECLARADAS ANTES DAS ROTAS)
# ==========================================
def render_login(msg=""):
    erro = f"<div class='p-3 bg-rose-950/70 border border-rose-800 text-rose-300 text-xs rounded-xl text-center'>{msg}</div>" if msg else ""
    return f"""<!DOCTYPE html>
<html lang="pt-br">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MVI Móveis Planejados - Login</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-slate-950 text-slate-100 flex items-center justify-center min-h-screen p-4 font-sans">
    <div class="max-w-md w-full bg-slate-900 border border-amber-500/30 rounded-3xl p-8 shadow-2xl space-y-6">
        <div class="text-center space-y-2">
            <div class="w-14 h-14 mx-auto rounded-2xl bg-gradient-to-br from-amber-400 to-amber-600 flex items-center justify-center font-black text-slate-950 text-2xl shadow-lg">MVI</div>
            <h1 class="text-xl font-bold tracking-tight text-white">MVI Móveis Planejados</h1>
            <p class="text-xs text-slate-400">Hub Integrador Promob & Gestão Contratual</p>
        </div>
        {erro}
        <form action="/painel" method="post" class="space-y-4">
            <div>
                <label class="block text-xs font-semibold text-slate-300 uppercase mb-1">E-mail</label>
                <input type="email" name="username" required value="admin@mvi.com" class="w-full px-4 py-3 bg-slate-950 border border-slate-700 rounded-xl text-sm focus:outline-none focus:border-amber-500 text-slate-200">
            </div>
            <div>
                <label class="block text-xs font-semibold text-slate-300 uppercase mb-1">Senha</label>
                <input type="password" name="password" required value="123456" class="w-full px-4 py-3 bg-slate-950 border border-slate-700 rounded-xl text-sm focus:outline-none focus:border-amber-500 text-slate-200">
            </div>
            <button type="submit" class="w-full py-3.5 bg-gradient-to-r from-amber-500 to-amber-600 hover:from-amber-400 hover:to-amber-500 text-slate-950 font-bold rounded-xl text-sm transition-all shadow-lg">
                Acessar Painel
            </button>
        </form>
        <div class="border-t border-slate-800 pt-4 text-center">
            <a href="/solicitar-orcamento" target="_blank" class="text-xs text-amber-400 hover:underline font-semibold block mb-1">🔗 Ver Simulador Público (Instagram)</a>
            <p class="text-[11px] text-slate-500">Admin: <b>admin@mvi.com</b> | Vendedor: <b>vendedor@mvi.com</b> (Senha: 123456)</p>
        </div>
    </div>
</body>
</html>"""

def render_dashboard_view():
    empresa = get_empresa_dados(1)
    met = get_metricas()
    is_admin = (CURRENT_SESSION["user_perfil"] == "admin")
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM orcamentos WHERE empresa_id = 1 ORDER BY id DESC LIMIT 25")
    leads = cursor.fetchall()
    cursor.execute("SELECT * FROM usuarios WHERE empresa_id = 1")
    equipe = cursor.fetchall()
    conn.close()

    leads_html = ""
    for h in leads:
        pv = float(h["preco_venda"] or 0)
        adendo = float(h["adendo_valor"] or 0)
        pv_total = pv + adendo
        lucro = float(h["lucro_liquido"] or 0)
        st = h["status"] or "Em Negociação"
        desc = float(h["desconto_pct"] or 0)
        autorizado_desc = int(h["desconto_autorizado"] or 1)
        liberado_fin = int(h["liberado_financeiro"] or 0)
        
        acoes_admin = ""
        if not autorizado_desc and is_admin:
            acoes_admin += f"""
            <form action="/autorizar-com-chave" method="post" class="flex flex-col gap-1 my-1 p-2 bg-amber-950/60 border border-amber-500/40 rounded-xl">
                <span class='text-[10px] text-amber-300 font-bold'>⚠️ Desconto {desc:.1f}%</span>
                <input type="hidden" name="orcamento_id" value="{h['id']}">
                <input type="hidden" name="tipo_acao" value="desconto">
                <input type="password" name="chave_digitada" placeholder="Chave Mestra" required class="px-2 py-1 bg-slate-950 border border-slate-700 text-white rounded text-[10px]">
                <button type="submit" class="px-2 py-1 bg-amber-500 hover:bg-amber-400 text-slate-950 rounded text-[10px] font-bold">Autorizar</button>
            </form>
            """
        elif not autorizado_desc:
            acoes_admin += f"<span class='text-[10px] text-amber-400 font-bold'>Aguardando Admin ({desc:.1f}%)</span>"

        if not liberado_fin and is_admin:
            acoes_admin += f"""
            <form action="/autorizar-com-chave" method="post" class="flex flex-col gap-1 my-1 p-2 bg-sky-950/60 border border-sky-500/40 rounded-xl">
                <span class='text-[10px] text-sky-300 font-bold'>💳 Liberar Financeiro</span>
                <input type="hidden" name="orcamento_id" value="{h['id']}">
                <input type="hidden" name="tipo_acao" value="financeiro">
                <input type="password" name="chave_digitada" placeholder="Chave Mestra" required class="px-2 py-1 bg-slate-950 border border-slate-700 text-white rounded text-[10px]">
                <button type="submit" class="px-2 py-1 bg-sky-500 hover:bg-sky-400 text-slate-950 rounded text-[10px] font-bold">Liberar</button>
            </form>
            """
        elif liberado_fin:
            acoes_admin += "<span class='text-[10px] text-emerald-400 font-bold'>✓ Liberado Financeiro</span>"

        link_assinatura = f"/assinar/{h['id']}"
        status_contrato = f"<span class='text-emerald-400 font-bold'>✓ Assinado</span><br><a href='{link_assinatura}' target='_blank' class='text-[10px] text-sky-400 underline'>Ver Via</a>" if h["contrato_assinado"] else f"<a href='{link_assinatura}' target='_blank' class='text-amber-400 underline font-bold'>✍️ Enviar p/ Assinar</a>"
        lucro_col = f"<td class='py-3 px-4 text-right text-emerald-400 font-bold'>R$ {lucro:,.2f}</td>" if is_admin else "<td class='py-3 px-4 text-right text-slate-500'>—</td>"

        adendo_tag = f"<span class='block text-[10px] text-amber-400 font-bold'>+ Adendo R$ {adendo:,.2f}</span>" if adendo > 0 else ""

        leads_html += f"""
        <tr class="border-b border-slate-800 hover:bg-slate-800/40 text-xs">
            <td class="py-3 px-4 font-mono text-slate-400">#{h['id']}</td>
            <td class="py-3 px-4 text-slate-300">{h['criado_em']}</td>
            <td class="py-3 px-4 text-white font-medium">
                {h['cliente_nome']}
                <span class="block text-[10px] text-slate-400">{h['cliente_telefone']} | CPF: {h['cliente_cpf'] or 'Pendente'}</span>
            </td>
            <td class="py-3 px-4 text-slate-300">{h['cliente_ambiente']}</td>
            <td class="py-3 px-4 text-right text-amber-400 font-bold">
                R$ {pv_total:,.2f}
                {adendo_tag}
            </td>
            {lucro_col}
            <td class="py-3 px-4 text-center">{acoes_admin if acoes_admin else st}</td>
            <td class="py-3 px-4 text-center">{status_contrato}</td>
        </tr>
        """

    if not leads_html:
        leads_html = "<tr><td colspan='8' class='py-8 text-center text-xs text-slate-500'>Nenhum lead recebido ainda.</td></tr>"

    equipe_html = ""
    for u in equipe:
        perfil = "Administrador" if u["perfil"] == "admin" else "Vendedor"
        token = u["token_primeiro_acesso"]
        concluido = u["primeiro_acesso_concluido"]
        
        status_acesso = "<span class='text-emerald-400 font-bold'>✓ Ativo</span>" if concluido else f"""
        <a href="/primeiro-acesso/{token}" target="_blank" class="px-2 py-1 bg-amber-500/20 text-amber-300 border border-amber-500/40 rounded text-[10px] underline">Link Convite</a>
        """

        equipe_html += f"""
        <li class="flex items-center justify-between py-2.5 border-b border-slate-800 text-xs">
            <div><span class="font-semibold text-white">{u['nome']}</span><span class="text-slate-400 block text-[11px]">{u['email']}</span></div>
            <div class="flex items-center gap-2">
                <span class="text-[10px] bg-amber-950 text-amber-300 border border-amber-500/40 px-2 py-0.5 rounded-xl">{perfil}</span>
                {status_acesso}
            </div>
        </li>
        """

    admin_tabs_menu = """
    <button onclick="mudarAba('aba-equipe')" id="btn-aba-equipe" class="tab-btn px-4 py-2 rounded-xl text-xs font-bold border border-slate-700 text-slate-300 hover:bg-slate-800 shrink-0">👥 Equipe & Convites</button>
    <button onclick="mudarAba('aba-config')" id="btn-aba-config" class="tab-btn px-4 py-2 rounded-xl text-xs font-bold border border-slate-700 text-slate-300 hover:bg-slate-800 shrink-0">🔑 Chave Mestra & Empresa</button>
    """ if is_admin else ""

    return f"""<!DOCTYPE html>
<html lang="pt-br">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MVI Móveis Planejados - Master Cockpit</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        .tab-btn.active {{ background: linear-gradient(135deg, #f59e0b, #d97706); color: #0f172a; font-weight: 800; }}
        .tab-content {{ display: none; }}
        .tab-content.active {{ display: block; }}
    </style>
</head>
<body class="bg-slate-950 text-slate-100 min-h-screen font-sans">
    <header class="bg-slate-900 border-b border-slate-800 px-6 py-4 flex flex-wrap items-center justify-between gap-3">
        <div class="flex items-center space-x-3">
            <div class="w-9 h-9 rounded-xl bg-gradient-to-br from-amber-400 to-amber-600 flex items-center justify-center font-black text-slate-950 text-lg shadow">MVI</div>
            <span class="font-bold text-lg text-white">{empresa['nome_empresa']}</span>
            <span class="text-xs bg-slate-800 border border-slate-700 text-amber-400 px-2.5 py-1 rounded-full font-bold">Nível: {CURRENT_SESSION['user_perfil'].upper()}</span>
        </div>
        <div class="flex items-center space-x-3">
            <a href="/solicitar-orcamento" target="_blank" class="text-xs bg-amber-950 text-amber-300 border border-amber-500/40 px-3 py-1.5 rounded-xl hover:bg-amber-900/60">🔗 Link Instagram</a>
            <span class="text-xs text-slate-400">Operador: <b class="text-amber-400">{CURRENT_SESSION['user_nome']}</b></span>
            <a href="/" class="text-xs bg-slate-800 hover:bg-slate-700 px-3 py-1.5 rounded-xl text-slate-300 border border-slate-700">Sair</a>
        </div>
    </header>

    <nav class="bg-slate-900/80 border-b border-slate-800 px-6 py-3 sticky top-0 z-50 backdrop-blur-md">
        <div class="max-w-7xl mx-auto flex items-center gap-2 overflow-x-auto">
            <button onclick="mudarAba('aba-leads')" id="btn-aba-leads" class="tab-btn active px-4 py-2 rounded-xl text-xs font-bold border border-slate-700 text-slate-300 hover:bg-slate-800 shrink-0">🏠 Painel de Fechamentos</button>
            <button onclick="mudarAba('aba-promob')" id="btn-aba-promob" class="tab-btn px-4 py-2 rounded-xl text-xs font-bold border border-slate-700 text-slate-300 hover:bg-slate-800 shrink-0">🚀 Integrador Promob</button>
            <button onclick="mudarAba('aba-cadastro-contrato')" id="btn-aba-cadastro-contrato" class="tab-btn px-4 py-2 rounded-xl text-xs font-bold border border-slate-700 text-slate-300 hover:bg-slate-800 shrink-0">📋 Ficha Cadastral do Cliente & CEP</button>
            <button onclick="mudarAba('aba-adendo')" id="btn-aba-adendo" class="tab-btn px-4 py-2 rounded-xl text-xs font-bold border border-slate-700 text-slate-300 hover:bg-slate-800 shrink-0">➕ Anexo de Termo Aditivo</button>
            {admin_tabs_menu}
        </div>
    </nav>

    <main class="max-w-7xl mx-auto p-6 space-y-6">
        <!-- ABA PRINCIPAL -->
        <div id="aba-leads" class="tab-content active space-y-6">
            <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                <div class="bg-slate-900 border border-slate-800 p-5 rounded-2xl space-y-1 shadow">
                    <p class="text-[11px] font-semibold text-slate-400 uppercase">Faturamento Liberado</p>
                    <p class="text-xl font-bold text-amber-400">R$ {met['faturamento']:,.2f}</p>
                </div>
                <div class="bg-slate-900 border border-slate-800 p-5 rounded-2xl space-y-1 shadow">
                    <p class="text-[11px] font-semibold text-slate-400 uppercase">Lucro Líquido</p>
                    <p class="text-xl font-bold text-emerald-400">{'R$ ' + f"{met['lucro']:,.2f}" if is_admin else 'Restrito'}</p>
                </div>
                <div class="bg-slate-900 border border-slate-800 p-5 rounded-2xl space-y-1 shadow">
                    <p class="text-[11px] font-semibold text-slate-400 uppercase">Ticket Médio</p>
                    <p class="text-xl font-bold text-white">R$ {met['ticket']:,.2f}</p>
                </div>
                <div class="bg-slate-900 border border-slate-800 p-5 rounded-2xl space-y-1 shadow">
                    <p class="text-[11px] font-semibold text-slate-400 uppercase">Conversão</p>
                    <p class="text-xl font-bold text-amber-400">{met['taxa']:.1f}%</p>
                </div>
            </div>

            <div class="bg-slate-900 border border-slate-800 rounded-3xl overflow-hidden shadow">
                <div class="p-4 border-b border-slate-800 flex justify-between items-center bg-slate-850">
                    <div>
                        <h3 class="text-sm font-semibold text-white">📁 Processos Online & Fila de Liberações</h3>
                        <p class="text-xs text-slate-400">Autorização de descontos e liberação financeira</p>
                    </div>
                    <a href="/exportar-csv" class="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 rounded-xl text-xs font-semibold">📊 Exportar CSV</a>
                </div>
                <div class="overflow-x-auto">
                    <table class="w-full text-left border-collapse">
                        <thead>
                            <tr class="bg-slate-800/40 border-b border-slate-800 text-xs font-semibold text-slate-400 uppercase">
                                <th class="py-3 px-4"># ID</th>
                                <th class="py-3 px-4">Data</th>
                                <th class="py-3 px-4">Cliente</th>
                                <th class="py-3 px-4">Ambiente</th>
                                <th class="py-3 px-4 text-right">Valor Venda</th>
                                <th class="py-3 px-4 text-right">Lucro</th>
                                <th class="py-3 px-4 text-center">Fila de Liberação</th>
                                <th class="py-3 px-4 text-center">Assinatura Digital</th>
                            </tr>
                        </thead>
                        <tbody>{leads_html}</tbody>
                    </table>
                </div>
            </div>
        </div>

        <!-- ABA PROMOB -->
        <div id="aba-promob" class="tab-content space-y-6">
            <div class="bg-slate-900 border border-slate-800 rounded-3xl p-6 sm:p-8 shadow space-y-4">
                <div>
                    <h2 class="text-base font-bold text-white">🚀 Integrador Promob Universal (XML, Cut Pro, CSV, TXT)</h2>
                    <p class="text-xs text-slate-400">Importe qualquer arquivo exportado do Promob para gerar orçamento automático com cálculo de peças, ferragens e DRE em segundos.</p>
                </div>

                <form action="/importar-promob" method="post" enctype="multipart/form-data" class="grid grid-cols-1 sm:grid-cols-3 gap-4 text-xs">
                    <div>
                        <label class="block text-slate-400 mb-1">Nome do Cliente</label>
                        <input type="text" name="cliente_nome" required placeholder="Ex: Lucas Ferreira" class="w-full px-3 py-2.5 bg-slate-950 border border-slate-700 rounded-xl text-white">
                    </div>
                    <div>
                        <label class="block text-slate-400 mb-1">WhatsApp / Telefone</label>
                        <input type="text" name="cliente_telefone" required placeholder="(11) 99999-9999" class="w-full px-3 py-2.5 bg-slate-950 border border-slate-700 rounded-xl text-white">
                    </div>
                    <div>
                        <label class="block text-slate-400 mb-1">Ambientes do Projeto</label>
                        <input type="text" name="cliente_ambiente" required placeholder="Ex: Cozinha Integrada + Dormitório" class="w-full px-3 py-2.5 bg-slate-950 border border-slate-700 rounded-xl text-white">
                    </div>
                    <div class="sm:col-span-3 p-4 bg-slate-950 border border-slate-800 rounded-2xl space-y-2">
                        <label class="block font-bold text-amber-400">📁 Selecione o arquivo exportado do Promob (.xml, .csv, .txt, .cut)</label>
                        <input type="file" name="arquivo_promob" accept=".xml,.csv,.txt,.cut" required class="block w-full text-xs text-slate-400 file:mr-3 file:py-2 file:px-4 file:rounded-xl file:border-0 file:text-xs file:font-bold file:bg-amber-500 file:text-slate-950 hover:file:bg-amber-400 cursor-pointer">
                    </div>
                    <div class="col-span-full pt-2">
                        <button type="submit" class="px-8 py-3.5 bg-gradient-to-r from-amber-500 to-amber-600 hover:from-amber-400 hover:to-amber-500 text-slate-950 font-bold rounded-xl text-xs shadow-lg">
                            ⚡ Processar Promob & Gerar Orçamento no CRM
                        </button>
                    </div>
                </form>
            </div>
        </div>

        <!-- ABA FICHA CADASTRAL -->
        <div id="aba-cadastro-contrato" class="tab-content space-y-6">
            <div class="bg-slate-900 border border-slate-800 rounded-3xl p-6 sm:p-8 shadow space-y-6">
                <div>
                    <h2 class="text-base font-bold text-white">📑 Ficha Cadastral Completa para Emissão de Contrato</h2>
                    <p class="text-xs text-slate-400">Preencha todos os dados exigidos para o contrato jurídico e utilize a busca automática de CEP.</p>
                </div>
                
                <form action="/salvar-dados-completos-cliente" method="post" class="space-y-6 text-xs">
                    <div class="bg-slate-950 p-4 rounded-2xl border border-slate-800">
                        <label class="block text-amber-400 font-bold mb-1">Selecione o Projeto / Lead (#ID)</label>
                        <select name="orcamento_id" class="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-xl text-white">
                            {"".join([f"<option value='{h['id']}'>#{h['id']} - {h['cliente_nome']} ({h['cliente_ambiente']})</option>" for h in leads])}
                        </select>
                    </div>

                    <div class="space-y-3">
                        <h3 class="text-xs font-bold text-amber-400 uppercase tracking-wide">1. Identificação Pessoal do Cliente</h3>
                        <div class="grid grid-cols-1 sm:grid-cols-4 gap-3">
                            <div class="sm:col-span-2">
                                <label class="block text-slate-400 mb-1">Nome Completo</label>
                                <input type="text" name="cliente_nome" required placeholder="Ex: Roberto Alcantara Silveira" class="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-xl text-white">
                            </div>
                            <div>
                                <label class="block text-slate-400 mb-1">CPF</label>
                                <input type="text" name="cliente_cpf" required placeholder="000.000.000-00" class="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-xl text-white">
                            </div>
                            <div>
                                <label class="block text-slate-400 mb-1">RG e Órgão Emissor</label>
                                <div class="flex gap-1">
                                    <input type="text" name="cliente_rg" required placeholder="RG" class="w-2/3 px-3 py-2 bg-slate-950 border border-slate-700 rounded-xl text-white">
                                    <input type="text" name="cliente_rg_emissor" required placeholder="SSP/SP" class="w-1/3 px-2 py-2 bg-slate-950 border border-slate-700 rounded-xl text-white">
                                </div>
                            </div>
                            <div>
                                <label class="block text-slate-400 mb-1">Data de Nascimento</label>
                                <input type="date" name="cliente_nascimento" required class="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-xl text-white">
                            </div>
                            <div>
                                <label class="block text-slate-400 mb-1">País</label>
                                <input type="text" name="cliente_pais" value="Brasil" required class="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-xl text-white">
                            </div>
                            <div>
                                <label class="block text-slate-400 mb-1">Cidade / UF</label>
                                <input type="text" name="cliente_cidade" required placeholder="São Paulo / SP" class="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-xl text-white">
                            </div>
                            <div>
                                <label class="block text-slate-400 mb-1">E-mail para Envio</label>
                                <input type="email" name="cliente_email" required placeholder="cliente@gmail.com" class="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-xl text-white">
                            </div>
                            <div>
                                <label class="block text-slate-400 mb-1">Telefone Principal (WhatsApp)</label>
                                <input type="text" name="cliente_telefone" required placeholder="(11) 99999-9999" class="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-xl text-white">
                            </div>
                            <div>
                                <label class="block text-slate-400 mb-1">Telefone Secundário / Recado</label>
                                <input type="text" name="cliente_telefone_2" placeholder="(11) 98888-8888" class="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-xl text-white">
                            </div>
                        </div>
                    </div>

                    <div class="space-y-3 pt-2">
                        <h3 class="text-xs font-bold text-amber-400 uppercase tracking-wide">2. Endereço Postal & Endereço de Entrega da Obra (Busca por CEP)</h3>
                        
                        <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
                            <div class="p-4 bg-slate-950 rounded-2xl border border-slate-800 space-y-2">
                                <label class="block font-bold text-white">📬 Endereço Postal (Residencial / Cobrança)</label>
                                <div class="flex gap-2">
                                    <input type="text" id="cep_postal" name="cliente_cep_postal" placeholder="CEP: 00000-000" class="w-1/2 px-3 py-2 bg-slate-900 border border-slate-700 rounded-xl text-white">
                                    <button type="button" onclick="buscarCep('postal')" class="w-1/2 px-3 py-2 bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold rounded-xl">🔍 Buscar CEP</button>
                                </div>
                                <textarea id="end_postal" name="cliente_endereco_postal" rows="2" placeholder="Rua, Número, Bairro, Complemento, Cidade - UF" class="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-xl text-white"></textarea>
                            </div>

                            <div class="p-4 bg-slate-950 rounded-2xl border border-slate-800 space-y-2">
                                <label class="block font-bold text-white">🚚 Endereço de Entrega / Instalação da Obra</label>
                                <div class="flex gap-2">
                                    <input type="text" id="cep_entrega" name="cliente_cep_entrega" placeholder="CEP: 00000-000" class="w-1/2 px-3 py-2 bg-slate-900 border border-slate-700 rounded-xl text-white">
                                    <button type="button" onclick="buscarCep('entrega')" class="w-1/2 px-3 py-2 bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold rounded-xl">🔍 Buscar CEP</button>
                                </div>
                                <textarea id="end_entrega" name="cliente_endereco_entrega" rows="2" placeholder="Rua da Obra, Número, Apto/Bloco, Bairro, Cidade - UF" class="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-xl text-white"></textarea>
                            </div>
                        </div>
                    </div>

                    <div class="space-y-3 pt-2">
                        <h3 class="text-xs font-bold text-amber-400 uppercase tracking-wide">3. Dados Bancários, Renda & Contatos de Referência</h3>
                        <div class="grid grid-cols-1 sm:grid-cols-4 gap-3">
                            <div>
                                <label class="block text-slate-400 mb-1">Banco</label>
                                <input type="text" name="cliente_banco" placeholder="Ex: Itaú / Bradesco" class="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-xl text-white">
                            </div>
                            <div>
                                <label class="block text-slate-400 mb-1">Agência</label>
                                <input type="text" name="cliente_agencia" placeholder="0000" class="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-xl text-white">
                            </div>
                            <div>
                                <label class="block text-slate-400 mb-1">Conta Corrente</label>
                                <input type="text" name="cliente_conta" placeholder="00000-0" class="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-xl text-white">
                            </div>
                            <div>
                                <label class="block text-slate-400 mb-1">Renda Mensal Estimada</label>
                                <input type="text" name="cliente_renda" placeholder="R$ 15.000,00" class="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-xl text-white">
                            </div>
                            <div>
                                <label class="block text-slate-400 mb-1">Nome Referência 1</label>
                                <input type="text" name="ref_nome_1" placeholder="Nome completo" class="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-xl text-white">
                            </div>
                            <div>
                                <label class="block text-slate-400 mb-1">Telefone Referência 1</label>
                                <input type="text" name="ref_tel_1" placeholder="(11) 90000-0000" class="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-xl text-white">
                            </div>
                            <div>
                                <label class="block text-slate-400 mb-1">Nome Referência 2</label>
                                <input type="text" name="ref_nome_2" placeholder="Nome completo" class="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-xl text-white">
                            </div>
                            <div>
                                <label class="block text-slate-400 mb-1">Telefone Referência 2</label>
                                <input type="text" name="ref_tel_2" placeholder="(11) 90000-0000" class="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-xl text-white">
                            </div>
                        </div>
                    </div>

                    <div class="space-y-3 pt-2">
                        <h3 class="text-xs font-bold text-amber-400 uppercase tracking-wide">4. Memorial Descritivo do Projeto & Condições de Pagamento</h3>
                        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                            <div>
                                <label class="block text-slate-400 mb-1">Descrição Técnica Manual do Projeto (Detalhes adicionais / Promob)</label>
                                <textarea name="descricao_manual" rows="3" placeholder="Ex: Cozinha com ilha gourmet, aéreos com fita LED embutida, dobradiças Blumotion, perfil gola Rometal e portas com vidro reflecta bronze..." class="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-xl text-white"></textarea>
                            </div>
                            <div class="grid grid-cols-1 sm:grid-cols-3 gap-2">
                                <div class="sm:col-span-3">
                                    <label class="block text-slate-400 mb-1">Forma de Pagamento</label>
                                    <input type="text" name="forma_pagamento" value="Entrada no PIX + 5x no Cartão" class="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-xl text-white">
                                </div>
                                <div>
                                    <label class="block text-slate-400 mb-1">Valor Entrada (R$)</label>
                                    <input type="number" step="100" name="entrada_valor" value="5000" class="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-xl text-white">
                                </div>
                                <div>
                                    <label class="block text-slate-400 mb-1">Parcelas</label>
                                    <input type="number" name="num_parcelas" value="5" class="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-xl text-white">
                                </div>
                                <div>
                                    <label class="block text-slate-400 mb-1">Desconto (%)</label>
                                    <input type="number" step="0.5" name="desconto_pct" value="0.0" class="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-xl text-white">
                                </div>
                            </div>
                        </div>
                    </div>

                    <div class="pt-4 border-t border-slate-800">
                        <button type="submit" class="w-full sm:w-auto px-8 py-3.5 bg-gradient-to-r from-amber-500 to-amber-600 hover:from-amber-400 hover:to-amber-500 text-slate-950 font-bold rounded-xl text-sm shadow-lg">
                            💾 Salvar Ficha Cadastral e Liberar Contrato para Assinatura Online
                        </button>
                    </div>
                </form>
            </div>
        </div>

        <!-- ABA ADENDO -->
        <div id="aba-adendo" class="tab-content space-y-6">
            <div class="bg-slate-900 border border-slate-800 rounded-3xl p-6 sm:p-8 shadow space-y-4">
                <div>
                    <h2 class="text-base font-bold text-white">➕ Anexo de Termo Aditivo / Complementos Pós-Fechamento</h2>
                    <p class="text-xs text-slate-400">Registre novos módulos, gavetas extras ou complementos adicionados pós-fechamento do contrato.</p>
                </div>

                <form action="/salvar-adendo" method="post" class="grid grid-cols-1 sm:grid-cols-3 gap-4 text-xs">
                    <div>
                        <label class="block text-slate-400 mb-1">Selecione o Contrato do Cliente</label>
                        <select name="orcamento_id" class="w-full px-3 py-2.5 bg-slate-950 border border-slate-700 rounded-xl text-white">
                            {"".join([f"<option value='{h['id']}'>#{h['id']} - {h['cliente_nome']} ({h['cliente_ambiente']})</option>" for h in leads])}
                        </select>
                    </div>
                    <div>
                        <label class="block text-slate-400 mb-1">Valor Adicional do Adendo (R$)</label>
                        <input type="number" step="50" name="adendo_valor" required placeholder="Ex: 3500.00" class="w-full px-3 py-2.5 bg-slate-950 border border-slate-700 rounded-xl text-white">
                    </div>
                    <div class="sm:col-span-3">
                        <label class="block text-slate-400 mb-1">Descrição dos Itens Adicionados (Termo Aditivo)</label>
                        <textarea name="adendo_descricao" rows="3" required placeholder="Ex: Inclusão de cristaleira com iluminação em LED no living e 2 gaveteiros extras no closet master..." class="w-full px-3 py-2.5 bg-slate-950 border border-slate-700 rounded-xl text-white"></textarea>
                    </div>
                    <div class="col-span-full pt-2">
                        <button type="submit" class="px-6 py-3 bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold rounded-xl text-xs">
                            ➕ Registrar Adendo Contratual
                        </button>
                    </div>
                </form>
            </div>
        </div>

        <!-- ABA EQUIPE -->
        <div id="aba-equipe" class="tab-content space-y-6">
            <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <div class="lg:col-span-2 bg-slate-900 border border-slate-800 rounded-3xl p-6 shadow space-y-4">
                    <div>
                        <h2 class="text-base font-semibold text-white">Cadastrar Novo Funcionário / Administrador</h2>
                        <p class="text-xs text-slate-400">O sistema gera um link seguro de primeiro acesso para o usuário definir sua própria senha.</p>
                    </div>
                    <form action="/criar-usuario" method="post" class="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                        <div>
                            <label class="block text-slate-400 mb-1">Nome Completo</label>
                            <input type="text" name="nome" required placeholder="Ex: Rodrigo Mendes" class="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-xl text-white">
                        </div>
                        <div>
                            <label class="block text-slate-400 mb-1">E-mail do Usuário</label>
                            <input type="email" name="email" required placeholder="rodrigo@mvi.com" class="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-xl text-white">
                        </div>
                        <div>
                            <label class="block text-slate-400 mb-1">WhatsApp para Envio do Convite</label>
                            <input type="text" name="telefone" placeholder="(11) 99999-9999" class="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-xl text-white">
                        </div>
                        <div>
                            <label class="block text-slate-400 mb-1">Nível de Acesso</label>
                            <select name="perfil" class="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-xl text-white">
                                <option value="vendedor">Vendedor (Sem acesso a margens/liberações)</option>
                                <option value="admin">Administrador Geral</option>
                            </select>
                        </div>
                        <div class="col-span-full pt-2">
                            <button type="submit" class="px-6 py-3 bg-gradient-to-r from-amber-500 to-amber-600 hover:from-amber-400 hover:to-amber-500 text-slate-950 font-bold rounded-xl text-xs shadow-lg">
                                🚀 Gerar Link & Enviar Convite de Primeiro Acesso
                            </button>
                        </div>
                    </form>
                </div>
                <div class="bg-slate-900 border border-slate-800 rounded-3xl p-6 shadow">
                    <h3 class="text-xs font-semibold text-slate-300 uppercase mb-3">Equipe MVI</h3>
                    <ul class="divide-y divide-slate-800">{equipe_html}</ul>
                </div>
            </div>
        </div>

        <!-- ABA CONFIG -->
        <div id="aba-config" class="tab-content space-y-6">
            <div class="bg-slate-900 border border-slate-800 rounded-3xl p-6 shadow space-y-4">
                <h2 class="text-base font-semibold text-white">Configuração da Empresa & Chave Mestra</h2>
                <form action="/salvar-empresa" method="post" class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4 text-xs">
                    <div>
                        <label class="block text-slate-400 mb-1">Nome Fantasia</label>
                        <input type="text" name="nome_empresa" value="{empresa['nome_empresa']}" required class="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-xl text-white">
                    </div>
                    <div>
                        <label class="block text-slate-400 mb-1">CNPJ</label>
                        <input type="text" name="cnpj" value="{empresa['cnpj']}" required class="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-xl text-white">
                    </div>
                    <div>
                        <label class="block text-slate-400 mb-1">WhatsApp de Atendimento</label>
                        <input type="text" name="telefone" value="{empresa['telefone']}" required class="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-xl text-white">
                    </div>
                    <div>
                        <label class="block text-slate-400 mb-1">Chave PIX</label>
                        <input type="text" name="pix" value="{empresa['pix']}" required class="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-xl text-white">
                    </div>
                    <div>
                        <label class="block text-amber-400 font-bold mb-1">🔑 Chave Mestra (PIN Admin)</label>
                        <div class="flex gap-2">
                            <input type="text" name="chave_mestra" value="{empresa.get('chave_mestra', 'MVI2026')}" required class="w-full px-3 py-2 bg-slate-950 border border-amber-500/50 rounded-xl text-amber-300 font-bold">
                            <button type="submit" class="px-4 py-2 bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold rounded-xl shrink-0">Salvar</button>
                        </div>
                    </div>
                </form>
            </div>
        </div>
    </main>

    <script>
        function mudarAba(abaId) {{
            var contents = document.getElementsByClassName('tab-content');
            for (var i = 0; i < contents.length; i++) {{ contents[i].classList.remove('active'); }}
            var btns = document.getElementsByClassName('tab-btn');
            for (var i = 0; i < btns.length; i++) {{ btns[i].classList.remove('active'); }}
            var target = document.getElementById(abaId);
            if (target) target.classList.add('active');
            var btn = document.getElementById('btn-' + abaId);
            if (btn) btn.classList.add('active');
            window.scrollTo({{ top: 0, behavior: 'smooth' }});
        }}

        function buscarCep(tipo) {{
            var cepInput = document.getElementById(tipo === 'postal' ? 'cep_postal' : 'cep_entrega');
            var endText = document.getElementById(tipo === 'postal' ? 'end_postal' : 'end_entrega');
            var cep = cepInput.value.replace(/\\D/g, '');

            if (cep.length !== 8) {{
                alert("Por favor, digite um CEP válido com 8 dígitos.");
                return;
            }}

            endText.value = "Buscando endereço nos Correios...";

            fetch('https://viacep.com.br/ws/' + cep + '/json/')
                .then(function(res) {{ return res.json(); }})
                .then(function(dados) {{
                    if (dados.erro) {{
                        alert("CEP não encontrado!");
                        endText.value = "";
                    }} else {{
                        endText.value = dados.logradouro + ", Nº [DIGITE O NÚMERO], " + (dados.bairro ? dados.bairro + ", " : "") + dados.localidade + " - " + dados.uf;
                    }}
                }})
                .catch(function() {{
                    alert("Erro ao buscar CEP.");
                    endText.value = "";
                }});
        }}
    </script>
</body>
</html>"""

def render_form_captacao(empresa):
    return f"""<!DOCTYPE html>
<html lang="pt-br">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{empresa['nome_empresa']} - Simulador de Projetos</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-slate-950 text-slate-100 min-h-screen flex flex-col justify-between font-sans">
    <header class="bg-slate-900 border-b border-slate-800 px-6 py-4 flex items-center justify-between">
        <div class="flex items-center space-x-3">
            <div class="w-9 h-9 rounded-xl bg-gradient-to-br from-amber-400 to-amber-600 flex items-center justify-center font-black text-slate-950 text-lg shadow">MVI</div>
            <span class="font-bold text-base sm:text-lg text-white">{empresa['nome_empresa']}</span>
        </div>
        <span class="text-xs text-amber-400 font-semibold">Móveis Sob Medida</span>
    </header>

    <main class="max-w-3xl w-full mx-auto p-4 sm:p-6 my-auto">
        <form action="/enviar-solicitacao-lead" method="post" enctype="multipart/form-data" class="space-y-4 bg-slate-900 border border-slate-800 p-6 sm:p-8 rounded-3xl shadow-2xl">
            <div class="space-y-1 border-b border-slate-800 pb-3">
                <h2 class="text-lg font-bold text-white">Simulador MVI de Móveis Sob Medida</h2>
                <p class="text-xs text-slate-400">Suporte a plantas compactas e grandes projetos residenciais (acima de 160m²).</p>
            </div>

            <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                    <label class="block text-xs font-semibold text-slate-300 uppercase mb-1">Seu Nome Completo</label>
                    <input type="text" name="nome" required placeholder="Ex: Mariana Silva" class="w-full px-4 py-2.5 bg-slate-950 border border-slate-700 rounded-xl text-sm text-white focus:outline-none focus:border-amber-500">
                </div>
                <div>
                    <label class="block text-xs font-semibold text-slate-300 uppercase mb-1">Seu WhatsApp (com DDD)</label>
                    <input type="text" name="whatsapp" required placeholder="Ex: (11) 99999-8888" class="w-full px-4 py-2.5 bg-slate-950 border border-slate-700 rounded-xl text-sm text-white focus:outline-none focus:border-amber-500">
                </div>
            </div>

            <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                    <label class="block text-xs font-semibold text-slate-300 uppercase mb-1">Metragem Total do Imóvel (m²)</label>
                    <input type="number" step="any" min="5.0" max="5000.0" name="area_m2_total" value="180.0" required class="w-full px-4 py-2.5 bg-slate-950 border border-slate-700 rounded-xl text-sm text-white focus:outline-none focus:border-amber-500">
                </div>
                <div>
                    <label class="block text-xs font-semibold text-slate-300 uppercase mb-1">Cidade / Bairro da Obra</label>
                    <input type="text" name="cidade" required placeholder="Ex: São Paulo / Moema / Alphaville" class="w-full px-4 py-2.5 bg-slate-950 border border-slate-700 rounded-xl text-sm text-white focus:outline-none focus:border-amber-500">
                </div>
            </div>

            <div>
                <label class="block text-xs font-semibold text-slate-300 uppercase mb-2">Ambientes Inclusos:</label>
                <div class="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
                    <label class="flex items-center space-x-2 bg-slate-950 p-2.5 rounded-xl border border-slate-800 cursor-pointer hover:border-amber-500">
                        <input type="checkbox" name="ambientes_check" value="Cozinha c/ Ilha" checked class="rounded text-amber-500">
                        <span>🍳 Cozinha / Ilha</span>
                    </label>
                    <label class="flex items-center space-x-2 bg-slate-950 p-2.5 rounded-xl border border-slate-800 cursor-pointer hover:border-amber-500">
                        <input type="checkbox" name="ambientes_check" value="Varanda Gourmet" checked class="rounded text-amber-500">
                        <span>🥩 Gourmet</span>
                    </label>
                    <label class="flex items-center space-x-2 bg-slate-950 p-2.5 rounded-xl border border-slate-800 cursor-pointer hover:border-amber-500">
                        <input type="checkbox" name="ambientes_check" value="Suíte Master c/ Closet" checked class="rounded text-amber-500">
                        <span>🛏️ Suíte/Closet</span>
                    </label>
                    <label class="flex items-center space-x-2 bg-slate-950 p-2.5 rounded-xl border border-slate-800 cursor-pointer hover:border-amber-500">
                        <input type="checkbox" name="ambientes_check" value="Banheiros" checked class="rounded text-amber-500">
                        <span>🚿 Banheiros</span>
                    </label>
                </div>
            </div>

            <!-- CATÁLOGO DE FABRICANTES E CORES DE MADEIRA -->
            <div class="bg-slate-950 p-4 rounded-2xl border border-slate-800 space-y-3 text-xs">
                <h3 class="text-xs font-bold text-amber-400 uppercase tracking-wide">🪵 Catálogo de Fabricantes, Madeiras & Ferragens</h3>
                <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div>
                        <label class="block text-slate-300 font-semibold mb-1">Fabricante MDF</label>
                        <select name="fabricante_mdf" class="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-xl text-white">
                            <option value="Duratex">Duratex</option>
                            <option value="Arauco">Arauco</option>
                            <option value="Guararapes">Guararapes</option>
                            <option value="Eucatex">Eucatex</option>
                        </select>
                    </div>
                    <div>
                        <label class="block text-slate-300 font-semibold mb-1">Padrão / Cor da Madeira</label>
                        <select name="cor_mdf" class="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-xl text-white">
                            <option value="Freijó Puro / Natural">Freijó Puro / Natural</option>
                            <option value="Carvalho Boreal / Canela">Carvalho Boreal / Canela</option>
                            <option value="Nogueira Cadiz / Pecan">Nogueira Cadiz / Pecan</option>
                            <option value="Gianduia Trama / Savana">Gianduia Trama / Savana</option>
                            <option value="Cinza Grafite / Preto Matt">Cinza Grafite / Preto Matt</option>
                            <option value="Branco TX Essencial">Branco TX Essencial</option>
                        </select>
                    </div>
                </div>
                <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div>
                        <label class="block text-slate-300 font-semibold mb-1">Marca das Ferragens</label>
                        <select name="marca_ferragens" class="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-xl text-white">
                            <option value="Blum (Linha Blumotion Áustria)">Blum (Áustria / Alto Padrão)</option>
                            <option value="Hettich (Linha Sensys Alemanha)">Hettich (Alemanha)</option>
                            <option value="Häfele (Linha Matrix Box)">Häfele</option>
                            <option value="FGVTN (Linha Slowmotion)">FGVTN</option>
                            <option value="Standard com Amortecedor">Standard</option>
                        </select>
                    </div>
                    <div>
                        <label class="block text-slate-300 font-semibold mb-1">Modelo de Portas</label>
                        <select name="modelo_portas" class="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-xl text-white">
                            <option value="Perfil Gola em Alumínio (Rometal)">Perfil Gola Alumínio</option>
                            <option value="Cava Usinada na Madeira (Usinado)">Cava Usinada</option>
                            <option value="Perfil Slim com Vidro Reflecta">Perfil Slim Vidro Reflecta</option>
                            <option value="Puxadores Design (Zen / Torralba)">Puxadores Design Zen</option>
                            <option value="Lisa Tradicional">Lisa Tradicional</option>
                        </select>
                    </div>
                </div>
                <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-1">
                    <div>
                        <label class="block text-slate-300 font-semibold mb-1">Espessura da Caixa</label>
                        <select name="espessura_caixa" class="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-xl text-white">
                            <option value="MDF 18mm">MDF 18mm (Reforçado)</option>
                            <option value="MDF 15mm">MDF 15mm (Padrão)</option>
                        </select>
                    </div>
                    <div>
                        <label class="block text-slate-300 font-semibold mb-1">Tamponamento</label>
                        <select name="espessura_tamponamento" class="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-xl text-white">
                            <option value="Tamponamento 25mm">Tamponamento 25mm</option>
                            <option value="Tamponamento 36mm Engrossado">Tamponamento 36mm Engrossado</option>
                            <option value="Tamponamento 18mm">Tamponamento 18mm</option>
                            <option value="Sem Tamponamento">Sem Tamponamento</option>
                        </select>
                    </div>
                </div>
            </div>

            <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div class="bg-slate-950 p-3.5 rounded-2xl border border-slate-800 space-y-1">
                    <label class="block text-xs font-bold text-amber-400 uppercase">📐 1. Planta Baixa</label>
                    <input type="file" name="planta" accept="image/*" required class="block w-full text-xs text-slate-400 file:mr-3 file:py-1.5 file:px-3 file:rounded-lg file:border-0 file:text-xs file:font-semibold file:bg-amber-600 file:text-slate-950 hover:file:bg-amber-500 cursor-pointer">
                </div>
                <div class="bg-slate-950 p-3.5 rounded-2xl border border-slate-800 space-y-1">
                    <label class="block text-xs font-bold text-slate-300 uppercase">🖼️ 2. Foto de Inspiração</label>
                    <input type="file" name="inspiracao" accept="image/*" class="block w-full text-xs text-slate-400 file:mr-3 file:py-1.5 file:px-3 file:rounded-lg file:border-0 file:text-xs file:font-semibold file:bg-slate-800 file:text-white hover:file:bg-slate-700 cursor-pointer">
                </div>
            </div>

            <div>
                <label class="block text-xs font-semibold text-slate-300 uppercase mb-1">Observações (Opcional)</label>
                <textarea name="descricao" rows="2" placeholder="Ex: Iluminação em LED nos aéreos, torre quente na cozinha..." class="w-full px-4 py-2.5 bg-slate-950 border border-slate-700 rounded-xl text-sm text-white focus:outline-none focus:border-amber-500"></textarea>
            </div>

            <button type="submit" class="w-full py-4 bg-gradient-to-r from-amber-500 to-amber-600 hover:from-amber-400 hover:to-amber-500 text-slate-950 font-black rounded-xl text-sm transition-all shadow-lg flex items-center justify-center space-x-2">
                <span>⚡ Simular Projeto & Receber Proposta MVI</span>
            </button>
        </form>
    </main>

    <footer class="bg-slate-900 border-t border-slate-800 p-4 text-center text-xs text-slate-500">
        <p>{empresa['nome_empresa']} | Atendimento: {empresa['telefone']}</p>
    </footer>
</body>
</html>"""

def render_sucesso(empresa, estimativa, zap_url):
    return f"""<!DOCTYPE html>
<html lang="pt-br">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{empresa['nome_empresa']} - Sucesso</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-slate-950 text-slate-100 min-h-screen flex items-center justify-center p-4 font-sans">
    <div class="max-w-md w-full bg-slate-900 border border-amber-500/50 p-6 sm:p-8 rounded-3xl text-center space-y-4 shadow-2xl">
        <span class="text-5xl block animate-bounce">✨</span>
        <h2 class="text-xl font-bold text-white">Projeto & Orçamento Calculados!</h2>
        
        <div class="bg-slate-950 p-5 rounded-2xl border border-amber-500/30 inline-block text-center space-y-1 my-2">
            <p class="text-xs text-slate-400">Estimativa Preliminar:</p>
            <p class="text-3xl font-black text-amber-400">R$ {estimativa:,.2f}</p>
            <p class="text-[11px] text-slate-400">Entrada + Parcelamento em até 12x</p>
        </div>

        <p class="text-xs text-slate-300">
            Redirecionando para o WhatsApp da <b>{empresa['nome_empresa']}</b> com seu briefing...
        </p>

        <div class="pt-2">
            <a href="{zap_url}" target="_blank" class="inline-block w-full px-6 py-3.5 bg-gradient-to-r from-amber-500 to-amber-600 hover:from-amber-400 hover:to-amber-500 text-slate-950 text-xs font-black rounded-xl shadow-lg transition-all">
                👉 Abrir Conversa no WhatsApp
            </a>
        </div>

        <script>
            setTimeout(function() {{
                window.location.href = "{zap_url}";
            }}, 2000);
        </script>
    </div>
</body>
</html>"""

def render_convite_gerado(nome, email, perfil, telefone, link):
    msg_zap = f"""Olá {nome}!
Você foi cadastrado como {perfil.upper()} na plataforma *MVI Móveis Planejados*.

👉 Para ativar seu acesso e cadastrar sua senha pessoal, clique no link abaixo:
{link}"""
    
    tel_limpo = telefone.replace("(", "").replace(")", "").replace("-", "").replace(" ", "")
    zap_url = f"https://api.whatsapp.com/send?phone=55{tel_limpo}&text={urllib.parse.quote(msg_zap)}" if tel_limpo else ""
    btn_zap = f"""<a href="{zap_url}" target="_blank" class="px-6 py-3 bg-emerald-600 hover:bg-emerald-500 text-white font-bold rounded-xl text-xs shadow-lg">📲 Enviar Convite no WhatsApp</a>""" if zap_url else ""

    return f"""<!DOCTYPE html>
<html lang="pt-br">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Convite de Acesso Gerado</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-slate-950 text-slate-100 flex items-center justify-center min-h-screen p-4 font-sans">
    <div class="max-w-lg w-full bg-slate-900 border border-amber-500/40 rounded-3xl p-8 space-y-5 shadow-2xl">
        <div class="text-center space-y-2">
            <span class="text-4xl block">✉️</span>
            <h1 class="text-xl font-bold text-white">Convite de Acesso Gerado!</h1>
            <p class="text-xs text-slate-400">Usuário: <b>{nome}</b> ({email}) - {perfil.upper()}</p>
        </div>

        <div class="bg-slate-950 p-4 rounded-2xl border border-slate-800 space-y-2">
            <label class="block text-[11px] font-semibold text-amber-400 uppercase">Link Exclusivo de Primeiro Acesso:</label>
            <input type="text" readonly id="linkInput" value="{link}" class="w-full px-3 py-2.5 bg-slate-900 border border-slate-700 rounded-xl text-xs text-slate-200 font-mono">
            <button onclick="navigator.clipboard.writeText(document.getElementById('linkInput').value); alert('Link copiado com sucesso!');" class="w-full py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-xl text-xs font-bold">📋 Copiar Link</button>
        </div>

        <div class="flex flex-col sm:flex-row gap-2 pt-2 justify-center">
            {btn_zap}
            <a href="/painel-get" class="px-6 py-3 bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold rounded-xl text-xs shadow-lg text-center">Voltar ao Painel</a>
        </div>
    </div>
</body>
</html>"""

def render_tela_nova_senha(user, token):
    return f"""<!DOCTYPE html>
<html lang="pt-br">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Primeiro Acesso - Definir Senha</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-slate-950 text-slate-100 flex items-center justify-center min-h-screen p-4 font-sans">
    <div class="max-w-md w-full bg-slate-900 border border-amber-500/30 rounded-3xl p-8 shadow-2xl space-y-6">
        <div class="text-center space-y-2">
            <div class="w-14 h-14 mx-auto rounded-2xl bg-gradient-to-br from-amber-400 to-amber-600 flex items-center justify-center font-black text-slate-950 text-xl shadow">MVI</div>
            <h1 class="text-xl font-bold text-white">Bem-vindo(a), {user['nome']}!</h1>
            <p class="text-xs text-slate-400">Cadastre sua senha pessoal para ativar sua conta.</p>
        </div>

        <form action="/salvar-nova-senha" method="post" class="space-y-4">
            <input type="hidden" name="token" value="{token}">
            <div>
                <label class="block text-xs font-semibold text-slate-300 uppercase mb-1">Seu E-mail</label>
                <input type="email" readonly value="{user['email']}" class="w-full px-4 py-2.5 bg-slate-950 border border-slate-800 rounded-xl text-sm text-slate-400">
            </div>
            <div>
                <label class="block text-xs font-semibold text-slate-300 uppercase mb-1">Nova Senha (Mínimo 6 dígitos)</label>
                <input type="password" name="nova_senha" required placeholder="******" class="w-full px-4 py-3 bg-slate-950 border border-slate-700 rounded-xl text-sm text-white focus:outline-none focus:border-amber-500">
            </div>
            <div>
                <label class="block text-xs font-semibold text-slate-300 uppercase mb-1">Confirme a Nova Senha</label>
                <input type="password" name="confirma_senha" required placeholder="******" class="w-full px-4 py-3 bg-slate-950 border border-slate-700 rounded-xl text-sm text-white focus:outline-none focus:border-amber-500">
            </div>
            <button type="submit" class="w-full py-3.5 bg-gradient-to-r from-amber-500 to-amber-600 hover:from-amber-400 hover:to-amber-500 text-slate-950 font-bold rounded-xl text-sm transition-all shadow-lg">
                Ativar Minha Conta & Entrar
            </button>
        </form>
    </div>
</body>
</html>"""

def render_assinatura_online(orc, empresa):
    adendo_bloco = f"""
    <div class="p-4 bg-amber-950/40 border border-amber-500/40 rounded-xl space-y-1">
        <span class="text-amber-400 font-bold block">➕ ANEXO - TERMO ADITIVO CONTRATUAL:</span>
        <p>{orc['adendo_descricao']}</p>
        <p class="font-bold text-white">Valor Complementar do Adendo: R$ {float(orc['adendo_valor'] or 0):,.2f}</p>
    </div>
    """ if float(orc['adendo_valor'] or 0) > 0 else ""

    pv_total_contrato = float(orc['preco_venda'] or 0) + float(orc['adendo_valor'] or 0)

    return f"""<!DOCTYPE html>
<html lang="pt-br">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Assinatura Digital de Contrato - {empresa['nome_empresa']}</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdn.jsdelivr.net/npm/signature_pad@4.1.7/dist/signature_pad.umd.min.js"></script>
</head>
<body class="bg-slate-950 text-slate-100 min-h-screen p-4 sm:p-8 font-sans">
    <div class="max-w-4xl mx-auto bg-slate-900 border border-slate-800 rounded-3xl p-6 sm:p-10 shadow-2xl space-y-6">
        <div class="flex justify-between items-center border-b border-slate-800 pb-4">
            <div>
                <h1 class="text-xl font-bold text-white">INSTRUMENTO PARTICULAR DE PRESTAÇÃO DE SERVIÇOS DE MARCENARIA</h1>
                <p class="text-xs text-amber-400">{empresa['nome_empresa']} | CNPJ: {empresa['cnpj']}</p>
            </div>
            <span class="px-3 py-1 bg-amber-950 text-amber-300 border border-amber-500/40 rounded-xl text-xs font-bold">Contrato #{orc['id']:04d}</span>
        </div>

        <div class="bg-slate-950 p-6 rounded-2xl border border-slate-800 text-xs space-y-4 leading-relaxed text-slate-300 max-h-96 overflow-y-auto">
            <p><b>1. DAS PARTES CONTRATANTES:</b><br>
            <b>CONTRATADA:</b> {empresa['nome_empresa']}, inscrita no CNPJ sob o nº {empresa['cnpj']}, com atendimento pelo telefone {empresa['telefone']}.<br>
            <b>CONTRATANTE:</b> <b>{orc['cliente_nome']}</b>, portador do CPF nº <b>{orc['cliente_cpf']}</b>, RG nº <b>{orc['cliente_rg']} ({orc['cliente_rg_emissor']})</b>, nascido em <b>{orc['cliente_nascimento']}</b>, residente no endereço postal: <b>{orc['cliente_endereco_postal']} (CEP: {orc['cliente_cep_postal']})</b>, com telefone <b>{orc['cliente_telefone']}</b> e e-mail <b>{orc['cliente_email']}</b>.</p>

            <p><b>2. DO OBJETO DO CONTRATO:</b><br>
            A CONTRATADA compromete-se a fabricar, entregar e instalar os móveis sob medida para os ambientes: <b>{orc['cliente_ambiente']}</b>, no endereço da obra: <b>{orc['cliente_endereco_entrega']} (CEP: {orc['cliente_cep_entrega']})</b>.</p>

            <p><b>3. DO MEMORIAL DESCRITIVO E ESPECIFICAÇÕES TÉCNICAS:</b><br>
            <b>Descritivo do Projeto / Promob:</b><br>
            {orc['descricao_promob'] or 'Conforme projeto executivo aprovado.'}<br><br>
            <b>Detalhamento Técnico Manual:</b><br>
            {orc['descricao_manual'] or 'Conforme padrão construtivo MVI com amortecedores e caixaria reforçada.'}</p>

            {adendo_bloco}

            <p><b>4. DO VALOR E CONDIÇÕES DE PAGAMENTO:</b><br>
            Pela execução integral dos serviços descritos, o CONTRATANTE pagará à CONTRATADA o valor líquido total de <b>R$ {pv_total_contrato:,.2f}</b>, nas seguintes condições: <b>{orc['forma_pagamento']}</b>, sendo Entrada de <b>R$ {float(orc['entrada_valor'] or 0):,.2f}</b> mais saldo parcelado em <b>{orc['num_parcelas']} parcela(s)</b>.</p>

            <p><b>5. DO PRAZO DE FABRICAÇÃO E INSTALAÇÃO:</b><br>
            O prazo estimado para entrega e finalização da montagem é de <b>{orc['prazo_entrega']}</b>, contados a partir da aprovação final das medidas no local e confirmação do pagamento inicial.</p>

            <p><b>6. DA GARANTIA E PÓS-VENDA:</b><br>
            A CONTRATADA concede a garantia de <b>5 (cinco) anos</b> para as ferragens estruturais e amortecedores, e <b>12 (doze) meses</b> para os painéis de MDF contra defeitos de fabricação e montagem.</p>
        </div>

        <div class="bg-slate-950 p-6 rounded-2xl border border-slate-800 space-y-3">
            <h3 class="text-xs font-bold text-white uppercase">✍️ Assinatura Digital do Contratante</h3>
            <p class="text-[11px] text-slate-400">Desenhe sua assinatura no quadro abaixo com o dedo ou caneta touch no celular:</p>
            
            <div class="border-2 border-dashed border-slate-700 rounded-xl bg-white flex justify-center">
                <canvas id="signature-pad" width="600" height="200" class="touch-none cursor-crosshair w-full max-w-[600px] h-[200px]"></canvas>
            </div>
            
            <div class="flex justify-between items-center pt-2">
                <button type="button" id="clear-btn" class="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-xl text-xs">Limpar Assinatura</button>
                <form id="sign-form" action="/confirmar-assinatura" method="post">
                    <input type="hidden" name="orcamento_id" value="{orc['id']}">
                    <input type="hidden" name="assinatura_base64" id="assinatura_base64">
                    <button type="button" id="save-btn" class="px-6 py-2.5 bg-gradient-to-r from-emerald-500 to-emerald-600 hover:from-emerald-400 hover:to-emerald-500 text-slate-950 font-bold rounded-xl text-xs shadow-lg">
                        Confirmar e Assinar Contrato Digitalmente
                    </button>
                </form>
            </div>
        </div>
    </div>

    <script>
        var canvas = document.getElementById('signature-pad');
        var signaturePad = new SignaturePad(canvas, {{ backgroundColor: 'rgb(255, 255, 255)' }});
        
        document.getElementById('clear-btn').addEventListener('click', function () {{
            signaturePad.clear();
        }});

        document.getElementById('save-btn').addEventListener('click', function () {{
            if (signaturePad.isEmpty()) {{
                alert("Por favor, faça sua assinatura antes de confirmar.");
            }} else {{
                var dataURL = signaturePad.toDataURL();
                document.getElementById('assinatura_base64').value = dataURL;
                document.getElementById('sign-form').submit();
            }}
        }});
    </script>
</body>
</html>"""

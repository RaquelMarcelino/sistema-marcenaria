from fastapi import FastAPI, Form, UploadFile, File, Response, Request
from fastapi.responses import HTMLResponse, RedirectResponse
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
DB_PATH = "mvi_production_v25.db"

# ==============================================================================
# 1. TRATAMENTO DE ERROS GLOBAL
# ==============================================================================
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    err = traceback.format_exc()
    return HTMLResponse(content=f"""
    <div style="background:#0f172a; color:#f8fafc; font-family:sans-serif; padding:30px; min-height:100vh;">
        <h2 style="color:#f59e0b;">⚠️ Diagnóstico do Sistema MVI</h2>
        <pre style="background:#1e293b; color:#f43f5e; padding:15px; border-radius:10px; font-size:12px; overflow-x:auto;">{err}</pre>
        <a href="/painel" style="display:inline-block; margin-top:15px; padding:10px 20px; background:#f59e0b; color:#0f172a; font-weight:bold; border-radius:8px; text-decoration:none;">Voltar ao Painel</a>
    </div>
    """, status_code=500)

# ==============================================================================
# 2. BANCO DE DADOS & SESSÃO
# ==============================================================================
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
            primeiro_acesso_concluido INTEGER DEFAULT 1,
            ativo INTEGER DEFAULT 1
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
            prazo_entrega TEXT DEFAULT '30 dias úteis',
            data_entrega_prevista TEXT DEFAULT '',
            status TEXT DEFAULT 'Em Negociação',
            custo_materiais REAL DEFAULT 0,
            custo_mao_obra REAL DEFAULT 0,
            custo_frete_montagem REAL DEFAULT 0,
            imposto_pct REAL DEFAULT 6,
            comissao_pct REAL DEFAULT 4,
            markup REAL DEFAULT 2.2,
            preco_bruto REAL DEFAULT 0,
            preco_venda REAL DEFAULT 0,
            desconto_pct REAL DEFAULT 0,
            desconto_valor REAL DEFAULT 0,
            desconto_autorizado INTEGER DEFAULT 1,
            liberado_financeiro INTEGER DEFAULT 0,
            lucro_liquido REAL DEFAULT 0,
            entrada_valor REAL DEFAULT 0,
            num_parcelas INTEGER DEFAULT 1,
            modalidade_pagamento TEXT DEFAULT 'Cartão de Crédito em até 12x',
            forma_pagamento TEXT DEFAULT 'Entrada + Saldo Parcelado',
            valor_parcela REAL DEFAULT 0,
            valor_recebido REAL DEFAULT 0,
            tipo_agendamento TEXT DEFAULT 'Agendamento na Loja',
            preferencia_horario TEXT DEFAULT 'Tarde (14h às 18h)',
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
            "fita_borda_m": 3.20, "puxador": 25.00
        }
        cursor.execute("""
            INSERT INTO empresas (id, slug, nome_empresa, cnpj, telefone, pix, precos_json, chave_mestra)
            VALUES (1, 'mvi', 'MVI Móveis Planejados', '00.000.000/0001-00', '(11) 98888-7777', 'financeiro@mvi.com.br', ?, 'MVI2026')
        """, (json.dumps(precos_iniciais),))
        
        cursor.execute("INSERT OR REPLACE INTO usuarios VALUES ('admin@mvi.com', '123456', 'Administrador Geral MVI', 'admin', 1, '', 1, 1)")
        cursor.execute("INSERT OR REPLACE INTO usuarios VALUES ('vendedor@mvi.com', '123456', 'Vendedor MVI', 'vendedor', 1, '', 1, 1)")
        conn.commit()

    conn.close()

init_db()

CURRENT_SESSION = {
    "user_email": "admin@mvi.com",
    "user_nome": "Administrador Geral MVI",
    "user_perfil": "admin",
    "empresa_id": 1,
    "cliente_ativo_id": None
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
    
    total = len(rows)
    fat_total, lucro_total, aprovados = 0.0, 0.0, 0
    
    for r in rows:
        st = r["status"] or "Em Negociação"
        pv = float(r["preco_venda"] or 0) + float(r["adendo_valor"] or 0)
        lucro = float(r["lucro_liquido"] or 0)
        
        if st in ["Aprovado", "Em Produção", "Entregue", "Liberado para Financeiro & Fábrica", "Contrato Assinado Digitalmente", "Desconto Autorizado pela Diretoria"]:
            fat_total += pv
            lucro_total += lucro
            aprovados += 1

    taxa = (aprovados / total * 100.0) if total > 0 else 0.0
    ticket = (fat_total / aprovados) if aprovados > 0 else 0.0
    
    return {"total": total, "aprovados": aprovados, "faturamento": fat_total, "lucro": lucro_total, "ticket": ticket, "taxa": taxa}

# ==============================================================================
# 3. ENGENHARIA & PROMOB
# ==============================================================================
def calcular_engenharia(
    ambientes: list,
    area_m2: float,
    esp_caixa: str,
    cor_caixa: str,
    esp_porta: str,
    cor_porta: str,
    acabamento_porta: str,
    esp_tamp: str,
    marca_ferr: str
):
    empresa = get_empresa_dados(CURRENT_SESSION.get("empresa_id", 1))
    precos = json.loads(empresa.get("precos_json") or "{}")
    mdf_preco = float(precos.get("mdf_m2", 65.0))
    dob_preco = float(precos.get("dobradica", 18.50))
    corr_preco = float(precos.get("corredica", 38.00))

    fator_caixa_esp = 1.15 if "18mm" in esp_caixa else 1.0
    fator_caixa_cor = 1.15 if "Amadeirado" in cor_caixa else 1.0

    fator_porta_esp = 1.15 if "18mm" in esp_porta else 1.0
    fator_porta_cor = 1.20 if "Amadeirado" in cor_porta else 1.0

    if "Lacca" in acabamento_porta:
        fator_acab = 1.60
    elif "Vidro" in acabamento_porta or "Reflecta" in acabamento_porta:
        fator_acab = 1.50
    elif "Provençal" in acabamento_porta:
        fator_acab = 1.35
    elif "Americana" in acabamento_porta:
        fator_acab = 1.30
    elif "Passantes" in acabamento_porta:
        fator_acab = 1.25
    else:
        fator_acab = 1.00

    if "36mm" in esp_tamp:
        fator_tamp = 1.35
    elif "25mm" in esp_tamp:
        fator_tamp = 1.20
    elif "18mm" in esp_tamp:
        fator_tamp = 1.10
    else:
        fator_tamp = 1.00

    if "Blum" in marca_ferr:
        dob_mult, corr_mult = 2.8, 3.2
    elif "Hettich" in marca_ferr:
        dob_mult, corr_mult = 2.5, 2.9
    elif "Häfele" in marca_ferr:
        dob_mult, corr_mult = 2.1, 2.4
    else:
        dob_mult, corr_mult = 1.0, 1.0

    custo_base_caixa = mdf_preco * fator_caixa_esp * fator_caixa_cor * fator_tamp
    custo_base_porta = mdf_preco * fator_porta_esp * fator_porta_cor * fator_acab

    area = max(area_m2, 5.0)
    qtd_amb = max(len(ambientes), 1)
    area_comodo = area / qtd_amb

    items, desc_promob_auto = [], []
    for amb in ambientes:
        m_lin = max(area_comodo * 0.32, 3.2 if area >= 160 else 2.2)
        num_mod = max(int(math.ceil(m_lin / 0.8)), 2)
        
        items.append({"nome": f"Caixaria ({esp_caixa} - {cor_caixa}) - {amb}", "valor": num_mod * 1.25 * custo_base_caixa})
        items.append({"nome": f"Portas ({acabamento_porta} - {cor_porta} {esp_porta})", "valor": num_mod * 2 * 0.58 * custo_base_porta})
        items.append({"nome": f"Dobradiças c/ Amortecedor ({marca_ferr})", "valor": num_mod * 4 * dob_preco * dob_mult})
        items.append({"nome": f"Corrediças Telescópicas/Ocultas ({marca_ferr})", "valor": 4 * corr_preco * corr_mult})
        desc_promob_auto.append(f"{amb}: {num_mod} módulos caixaria {esp_caixa} ({cor_caixa}), portas {acabamento_porta} ({cor_porta} {esp_porta}), tamponamento {esp_tamp}, ferragens {marca_ferr}.")

    total_materiais = sum(i["valor"] for i in items)
    dias_prod = max(int(math.ceil(qtd_amb * 3.0)), 4)
    custo_mo = dias_prod * 180.0
    custo_frete = max(qtd_amb * 400.0, 800.0)
    markup = 2.2

    preco_bruto = (total_materiais + custo_mo + custo_frete) * markup
    preco_venda = preco_bruto
    lucro = preco_venda - (total_materiais + custo_mo + custo_frete + (preco_venda * 0.10))

    return {
        "items": items, "total_mat": total_materiais,
        "custo_mo": custo_mo, "custo_frete": custo_frete,
        "preco_bruto": preco_bruto, "preco_venda": preco_venda, "lucro": lucro,
        "desc_promob": "\n".join(desc_promob_auto)
    }

def processar_arquivo_promob(conteudo_texto: str, nome_arquivo: str):
    items = []
    precos = json.loads(get_empresa_dados(1).get("precos_json") or "{}")
    mdf_preco = float(precos.get("mdf_m2", 65.0))
    dob_preco = float(precos.get("dobradica", 18.50))
    corr_preco = float(precos.get("corredica", 38.00))

    ext = nome_arquivo.lower()
    
    if ext.endswith(".xml") or "<" in conteudo_texto[:100]:
        try:
            root = ET.fromstring(conteudo_texto)
            for el in root.iter():
                tag = el.tag.lower()
                if tag in ["item", "peca", "piece", "component", "componente", "panel", "modulo", "entity", "itembudget"]:
                    nome = (el.attrib.get("DESCRIPTION") or el.attrib.get("NOME") or el.attrib.get("NAME") or el.attrib.get("DESCRICAO") or "Peça Promob").strip()
                    larg = float(el.attrib.get("WIDTH") or el.attrib.get("LARGURA") or el.attrib.get("LARG") or 0)
                    alt = float(el.attrib.get("HEIGHT") or el.attrib.get("ALTURA") or el.attrib.get("ALT") or 0)
                    qtd = int(float(el.attrib.get("QUANTITY") or el.attrib.get("QUANTIDADE") or el.attrib.get("QTD") or 1))
                    
                    if larg > 0 and alt > 0:
                        area = (larg / 1000.0) * (alt / 1000.0)
                        items.append({"nome": nome[:40], "dimensoes": f"{int(larg)}x{int(alt)}mm", "qtd": qtd, "valor": area * mdf_preco * 1.35 * qtd})
        except Exception:
            pass

    if not items:
        linhas = conteudo_texto.splitlines()
        for l in linhas:
            limpa = l.replace(";", "\t").replace(",", "\t").replace("|", "\t")
            partes = [p.strip() for p in limpa.split("\t") if p.strip()]
            if len(partes) >= 3:
                try:
                    nome_p = partes[0]
                    d1 = float(partes[1].lower().replace("mm", "").replace("cm", "").replace(" ", ""))
                    d2 = float(partes[2].lower().replace("mm", "").replace("cm", "").replace(" ", ""))
                    q_p = int(partes[3]) if len(partes) >= 4 and partes[3].isdigit() else 1
                    if d1 > 0 and d2 > 0:
                        area_m2 = (d1 / 1000.0) * (d2 / 1000.0)
                        items.append({"nome": nome_p[:40], "dimensoes": f"{int(d1)}x{int(d2)}mm", "qtd": q_p, "valor": area_m2 * mdf_preco * 1.35 * q_p})
                except Exception:
                    continue

    if not items:
        items = [
            {"nome": "Módulo de Caixaria Promob 800mm", "dimensoes": "800x720mm", "qtd": 4, "valor": 4 * 1.25 * mdf_preco},
            {"nome": "Portas / Frentes MDF Promob", "dimensoes": "395x700mm", "qtd": 8, "valor": 8 * 0.58 * mdf_preco},
            {"nome": "Dobradiças Slowmotion Blum/Hettich", "dimensoes": "Ø35mm", "qtd": 16, "valor": 16 * dob_preco * 2.8},
            {"nome": "Corrediças Telescópicas Ocultas", "dimensoes": "450mm", "qtd": 6, "valor": 6 * corr_preco * 3.2}
        ]

    total_mat = sum(i["valor"] for i in items)
    dias = max(int(math.ceil(len(items) * 0.3)), 4)
    custo_mo = dias * 180.0
    custo_frete = max(len(items) * 35.0, 600.0)
    preco_bruto = (total_mat + custo_mo + custo_frete) * 2.2
    preco_venda = preco_bruto
    lucro = preco_venda - (total_mat + custo_mo + custo_frete + (preco_venda * 0.10))

    return {"items": items, "total_mat": total_mat, "custo_mo": custo_mo, "custo_frete": custo_frete, "preco_bruto": preco_bruto, "preco_venda": preco_venda, "lucro": lucro}

# ==============================================================================
# 4. FUNÇÕES DE RENDERIZAÇÃO HTML (DECLARADAS ANTES DAS ROTAS)
# ==============================================================================
def render_login(msg=""):
    erro = f"<div class='p-3 bg-rose-950/70 border border-rose-800 text-rose-300 text-xs rounded-xl text-center'>{msg}</div>" if msg else ""
    return f"""<!DOCTYPE html>
<html lang="pt-br">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MVI - Login</title><script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-slate-950 text-slate-100 flex items-center justify-center min-h-screen p-4 font-sans">
    <div class="max-w-md w-full bg-slate-900 border border-amber-500/30 rounded-3xl p-8 shadow-2xl space-y-6">
        <div class="text-center space-y-2">
            <div class="w-14 h-14 mx-auto rounded-2xl bg-gradient-to-br from-amber-400 to-amber-600 flex items-center justify-center font-black text-slate-950 text-2xl shadow-lg">MVI</div>
            <h1 class="text-xl font-bold text-white">MVI Móveis Planejados</h1>
            <p class="text-xs text-slate-400">Hub Integrador Promob & Gestão</p>
        </div>
        {erro}
        <form action="/painel" method="post" class="space-y-4">
            <div><label class="block text-xs font-semibold text-slate-300 uppercase mb-1">E-mail</label>
            <input type="email" name="username" required value="admin@mvi.com" class="w-full px-4 py-3 bg-slate-950 border border-slate-700 rounded-xl text-sm text-white"></div>
            <div><label class="block text-xs font-semibold text-slate-300 uppercase mb-1">Senha</label>
            <input type="password" name="password" required value="123456" class="w-full px-4 py-3 bg-slate-950 border border-slate-700 rounded-xl text-sm text-white"></div>
            <button type="submit" class="w-full py-3.5 bg-gradient-to-r from-amber-500 to-amber-600 hover:to-amber-500 text-slate-950 font-bold rounded-xl text-sm shadow-lg">Acessar Painel</button>
        </form>
        <div class="border-t border-slate-800 pt-4 text-center">
            <a href="/solicitar-orcamento" target="_blank" class="text-xs text-amber-400 hover:underline font-semibold block mb-1">🔗 Ver Simulador Público (Instagram)</a>
            <p class="text-[11px] text-slate-500">Admin: <b>admin@mvi.com</b> | Senha: <b>123456</b></p>
        </div>
    </div>
</body></html>"""

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

    cliente_ativo = None
    if CURRENT_SESSION.get("cliente_ativo_id"):
        for h in leads:
            if h["id"] == CURRENT_SESSION["cliente_ativo_id"]:
                cliente_ativo = h
                break
    if not cliente_ativo and leads:
        cliente_ativo = leads[0]
        CURRENT_SESSION["cliente_ativo_id"] = cliente_ativo["id"]

    c_id = cliente_ativo["id"] if cliente_ativo else 0
    c_nome = cliente_ativo["cliente_nome"] if cliente_ativo else "Selecione um Cliente"
    c_amb = cliente_ativo["cliente_ambiente"] if cliente_ativo else "Geral"
    c_p_bruto = float(cliente_ativo["preco_bruto"] or cliente_ativo["preco_venda"] or 0) if cliente_ativo else 0.0
    c_p_venda = float(cliente_ativo["preco_venda"] or 0) if cliente_ativo else 0.0
    c_lucro = float(cliente_ativo["lucro_liquido"] or 0) if cliente_ativo else 0.0
    c_desc_pct = float(cliente_ativo["desconto_pct"] or 0) if cliente_ativo else 0.0
    c_markup = float(cliente_ativo["markup"] or 2.2) if cliente_ativo else 2.2
    c_entrada = float(cliente_ativo["entrada_valor"] or 0) if cliente_ativo else 0.0
    c_parc = int(cliente_ativo["num_parcelas"] or 1) if cliente_ativo else 1
    c_mod = cliente_ativo["modalidade_pagamento"] if cliente_ativo and cliente_ativo["modalidade_pagamento"] else "Cartão de Crédito em até 12x"
    c_aut_desc = int(cliente_ativo["desconto_autorizado"] or 1) if cliente_ativo else 1
    
    saldo_financiar = max(c_p_venda - c_entrada, 0.0)
    valor_por_parcela = saldo_financiar / c_parc if c_parc > 0 else 0.0

    leads_html = ""
    for h in leads:
        pv = float(h["preco_venda"] or 0)
        adendo = float(h["adendo_valor"] or 0)
        pv_total = pv + adendo
        lucro = float(h["lucro_liquido"] or 0)
        st = h["status"] or "Em Negociação"
        desc = float(h["desconto_pct"] or 0)
        aut_desc = int(h["desconto_autorizado"] or 1)
        lib_fin = int(h["liberado_financeiro"] or 0)
        
        acoes_admin = ""
        if not aut_desc and is_admin:
            acoes_admin += f"""<form action="/autorizar-com-chave" method="post" class="flex flex-col gap-1 my-1 p-2 bg-amber-950/60 border border-amber-500/40 rounded-xl"><span class='text-[10px] text-amber-300 font-bold'>⚠️ Desconto {desc:.1f}%</span><input type="hidden" name="orcamento_id" value="{h['id']}"><input type="hidden" name="tipo_acao" value="desconto"><input type="password" name="chave_digitada" placeholder="Chave Mestra" required class="px-2 py-1 bg-slate-950 border border-slate-700 text-white rounded text-[10px]"><button type="submit" class="px-2 py-1 bg-amber-500 hover:bg-amber-400 text-slate-950 rounded text-[10px] font-bold">Autorizar</button></form>"""
        elif not aut_desc:
            acoes_admin += f"<span class='text-[10px] text-rose-400 font-bold animate-pulse'>🚨 Bloqueado Admin ({desc:.1f}%)</span>"

        if not lib_fin and is_admin:
            acoes_admin += f"""<form action="/autorizar-com-chave" method="post" class="flex flex-col gap-1 my-1 p-2 bg-sky-950/60 border border-sky-500/40 rounded-xl"><span class='text-[10px] text-sky-300 font-bold'>💳 Liberar Financeiro</span><input type="hidden" name="orcamento_id" value="{h['id']}"><input type="hidden" name="tipo_acao" value="financeiro"><input type="password" name="chave_digitada" placeholder="Chave" required class="px-2 py-1 bg-slate-950 border border-slate-700 text-white rounded text-[10px]"><button type="submit" class="px-2 py-1 bg-sky-500 text-slate-950 rounded text-[10px] font-bold">Liberar</button></form>"""
        elif lib_fin:
            acoes_admin += "<span class='text-[10px] text-emerald-400 font-bold'>✓ Financeiro OK</span>"

        link_ass = f"/assinar/{h['id']}"
        link_previa = f"/minuta-contrato/{h['id']}"
        
        status_ass = f"""
        <div class="flex flex-col gap-1 items-center">
            <span class='text-emerald-400 font-bold'>✓ Assinado</span>
            <a href='{link_ass}' target='_blank' class='text-[10px] text-sky-400 underline'>Ver Via do Sistema</a>
        </div>
        """ if h["contrato_assinado"] else (
            f"""
            <div class="flex flex-col gap-1 items-center">
                <a href='{link_previa}' target='_blank' class='text-[10px] text-slate-300 hover:text-white underline font-semibold'>👁️ Prévia Contrato</a>
                <a href='{link_ass}' target='_blank' class='text-[11px] text-amber-400 underline font-bold'>✍️ Enviar p/ Assinar</a>
            </div>
            """ if aut_desc else "<span class='text-[10px] text-rose-400 font-bold'>🔒 Contrato Travado</span>"
        )
        
        lucro_td = f"<td class='py-3 px-4 text-right text-emerald-400 font-bold valor-lucro-col'>R$ {lucro:,.2f}</td>" if is_admin else ""
        adendo_tag = f"<span class='block text-[10px] text-amber-400 font-bold'>+ Adendo R$ {adendo:,.2f}</span>" if adendo > 0 else ""

        btn_selecionar = f"""
        <form action="/selecionar-cliente-trabalho" method="post" class="inline">
            <input type="hidden" name="orcamento_id" value="{h['id']}">
            <button type="submit" class="px-2.5 py-1 bg-amber-500/20 hover:bg-amber-500/30 text-amber-300 border border-amber-500/40 rounded-lg text-[10px] font-bold">
                ⚡ Negociar
            </button>
        </form>
        """

        leads_html += f"""<tr class="border-b border-slate-800 hover:bg-slate-800/40 text-xs">
            <td class="py-3 px-4 font-mono text-slate-400">#{h['id']}</td>
            <td class="py-3 px-4 text-white font-medium">{h['cliente_nome']}<span class="block text-[10px] text-slate-400">CPF: {h['cliente_cpf'] or 'Pendente'}</span></td>
            <td class="py-3 px-4 text-slate-300">{h['cliente_ambiente']}</td>
            <td class="py-3 px-4 text-right text-amber-400 font-bold">R$ {pv_total:,.2f}{adendo_tag}</td>
            {lucro_td}
            <td class="py-3 px-4 text-center">{acoes_admin if acoes_admin else st}</td>
            <td class="py-3 px-4 text-center">{status_ass}</td>
            <td class="py-3 px-4 text-center">{btn_selecionar}</td>
        </tr>"""

    if not leads_html:
        leads_html = "<tr><td colspan='8' class='py-8 text-center text-xs text-slate-500'>Nenhum projeto registrado ainda.</td></tr>"

    th_lucro = "<th class='py-3 px-4 text-right'>Lucro Líquido</th>" if is_admin else ""

    eq_html = ""
    for u in equipe:
        perf = "Admin" if u["perfil"] == "admin" else "Vendedor"
        ativo = u["ativo"] if "ativo" in u.keys() else 1
        st_acesso = f"""<div class='flex items-center gap-2'>
            <span class='{"text-emerald-400" if ativo else "text-rose-400"} font-bold'>{"✓ Ativo" if ativo else "🚫 Bloqueado"}</span>
            <form action='/redefinir-senha-funcionario' method='post' class='inline'><input type='hidden' name='email_funcionario' value='{u['email']}'><button type='submit' class='px-2 py-1 bg-amber-500/20 text-amber-300 border border-amber-500/40 rounded text-[10px]'>Reset Senha</button></form>
            <form action='/alternar-status-funcionario' method='post' class='inline'><input type='hidden' name='email_funcionario' value='{u['email']}'><button type='submit' class='px-2 py-1 {"bg-rose-500/20 text-rose-300" if ativo else "bg-emerald-500/20 text-emerald-300"} rounded text-[10px] font-bold'>{"Bloquear" if ativo else "Reativar"}</button></form>
        </div>""" if u["primeiro_acesso_concluido"] else f"<a href='/primeiro-acesso/{u['token_primeiro_acesso']}' target='_blank' class='px-2 py-1 bg-amber-500/20 text-amber-300 rounded text-[10px] underline'>Link Convite</a>"
        eq_html += f"<li class='flex justify-between py-2 border-b border-slate-800 text-xs'><div><span class='font-bold text-white'>{u['nome']}</span><span class='text-slate-400 block text-[11px]'>{u['email']}</span></div><div class='flex gap-2'><span class='bg-amber-950 text-amber-300 px-2 rounded-xl'>{perf}</span>{st_acesso}</div></li>"

    admin_tabs = """<button onclick="mudarAba('aba-equipe')" id="btn-aba-equipe" class="tab-btn px-4 py-2 rounded-xl text-xs font-bold border border-slate-700 text-slate-300">👥 Equipe</button>
                    <button onclick="mudarAba('aba-config')" id="btn-aba-config" class="tab-btn px-4 py-2 rounded-xl text-xs font-bold border border-slate-700 text-slate-300">🔑 Configurações</button>""" if is_admin else ""

    admin_content = f"""
        <div id="aba-equipe" class="tab-content space-y-6">
            <div class="grid lg:grid-cols-3 gap-6">
                <div class="lg:col-span-2 bg-slate-900 border border-slate-800 rounded-3xl p-6 shadow">
                    <h2 class="text-base font-bold text-white mb-4">Cadastrar Novo Usuário</h2>
                    <form action="/criar-usuario" method="post" class="grid sm:grid-cols-2 gap-3 text-xs">
                        <input type="text" name="nome" required placeholder="Nome Completo" class="px-3 py-2 bg-slate-950 border border-slate-700 rounded-xl text-white">
                        <input type="email" name="email" required placeholder="E-mail" class="px-3 py-2 bg-slate-950 border border-slate-700 rounded-xl text-white">
                        <input type="text" name="telefone" placeholder="WhatsApp para Envio" class="px-3 py-2 bg-slate-950 border border-slate-700 rounded-xl text-white">
                        <select name="perfil" class="px-3 py-2 bg-slate-950 border border-slate-700 rounded-xl text-white"><option value="vendedor">Vendedor</option><option value="admin">Administrador</option></select>
                        <button type="submit" class="col-span-full py-3 bg-amber-500 text-slate-950 font-bold rounded-xl">Gerar Link de Convite</button>
                    </form>
                </div>
                <div class="bg-slate-900 border border-slate-800 rounded-3xl p-6 shadow"><h3 class="text-xs font-bold text-slate-300 uppercase mb-3">Equipe MVI</h3><ul class="divide-y divide-slate-800">{eq_html}</ul></div>
            </div>
        </div>
        <div id="aba-config" class="tab-content space-y-6">
            <div class="bg-slate-900 border border-slate-800 rounded-3xl p-6 shadow">
                <h2 class="text-base font-bold text-white mb-4">Configuração da Empresa e Chave Mestra</h2>
                <form action="/salvar-empresa" method="post" class="grid sm:grid-cols-4 gap-4 text-xs">
                    <input type="text" name="nome_empresa" value="{empresa['nome_empresa']}" required placeholder="Nome da Empresa" class="px-3 py-2 bg-slate-950 border border-slate-700 rounded-xl text-white">
                    <input type="text" name="cnpj" value="{empresa.get('cnpj','')}" required placeholder="CNPJ" class="px-3 py-2 bg-slate-950 border border-slate-700 rounded-xl text-white">
                    <input type="text" name="telefone" value="{empresa['telefone']}" required placeholder="WhatsApp" class="px-3 py-2 bg-slate-950 border border-slate-700 rounded-xl text-white">
                    <input type="text" name="chave_mestra" value="{empresa['chave_mestra']}" required placeholder="Chave Mestra (PIN)" class="px-3 py-2 bg-slate-950 border border-amber-500/50 rounded-xl text-amber-300 font-bold">
                    <button type="submit" class="col-span-full py-3 bg-amber-500 text-slate-950 font-bold rounded-xl">Salvar Configurações</button>
                </form>
            </div>
        </div>
    """ if is_admin else ""

    lucro_card = f"""<div class="bg-slate-900 border border-slate-800 p-5 rounded-2xl shadow"><p class="text-[11px] font-bold text-slate-400 uppercase">Lucro Líquido</p><p class="text-xl font-bold text-emerald-400 valor-ocultavel">R$ {met['lucro']:,.2f}</p></div>""" if is_admin else ""
    
    lucro_negociacao_box = f"""
    <div class="bg-slate-950 p-4 border border-emerald-500/30 rounded-2xl flex items-center justify-between gap-4">
        <div>
            <span class="text-[11px] text-slate-400 font-bold uppercase block">Lucro Líquido da Operação</span>
            <span id="valor_lucro_operacao" data-real="R$ {c_lucro:,.2f}" class="text-2xl font-black text-emerald-400">R$ {c_lucro:,.2f}</span>
        </div>
        <button type="button" onclick="alternarOlhoLucro()" id="btn_olho_lucro" title="Ocultar / Revelar Lucro" class="p-2.5 bg-slate-900 hover:bg-slate-800 border border-slate-700 rounded-xl text-slate-300 text-base">
            👁️
        </button>
    </div>
    """ if is_admin else ""

    options_leads = "<option value='0'>➕ Cadastrar Novo Cliente / Orçamento Manual</option>"
    for h in leads:
        sel = "selected" if h["id"] == c_id else ""
        options_leads += f"<option value='{h['id']}' {sel}>#{h['id']} - {h['cliente_nome']} ({h['cliente_ambiente']})</option>"

    return f"""<!DOCTYPE html>
<html lang="pt-br">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>MVI - Master Cockpit</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>.tab-btn.active {{ background: linear-gradient(135deg, #f59e0b, #d97706); color: #0f172a; font-weight: 800; }} .tab-content {{ display: none; }} .tab-content.active {{ display: block; }}</style>
</head>
<body class="bg-slate-950 text-slate-100 min-h-screen font-sans">
    <header class="bg-slate-900 border-b border-slate-800 px-6 py-4 flex flex-wrap items-center justify-between gap-3">
        <div class="flex items-center gap-3"><div class="w-9 h-9 rounded-xl bg-gradient-to-br from-amber-400 to-amber-600 flex items-center justify-center font-black text-slate-950 text-lg shadow">MVI</div><span class="font-bold text-lg text-white">{empresa['nome_empresa']}</span><span class="text-[10px] bg-slate-800 border border-slate-700 text-amber-400 px-2 py-0.5 rounded-full font-bold uppercase">{CURRENT_SESSION['user_perfil']}</span></div>
        <div class="flex items-center gap-3"><a href="/solicitar-orcamento" target="_blank" class="text-xs bg-amber-950 text-amber-300 border border-amber-500/40 px-3 py-1.5 rounded-xl">🔗 Simulador Público</a><span class="text-xs text-slate-400">Operador: <b class="text-amber-400">{CURRENT_SESSION['user_nome']}</b></span><a href="/" class="text-xs bg-slate-800 hover:bg-slate-700 px-3 py-1.5 rounded-xl text-slate-300 border border-slate-700">Sair</a></div>
    </header>

    <nav class="bg-slate-900/80 border-b border-slate-800 px-6 py-3 sticky top-0 z-50 backdrop-blur-md">
        <div class="max-w-7xl mx-auto flex items-center gap-2 overflow-x-auto">
            <button onclick="mudarAba('aba-leads')" id="btn-aba-leads" class="tab-btn active px-4 py-2 rounded-xl text-xs font-bold border border-slate-700 text-slate-300">🏠 Fechamentos & Mesa de Negociação</button>
            <button onclick="mudarAba('aba-promob')" id="btn-aba-promob" class="tab-btn px-4 py-2 rounded-xl text-xs font-bold border border-slate-700 text-slate-300">🚀 Promob</button>
            <button onclick="mudarAba('aba-cadastro')" id="btn-aba-cadastro" class="tab-btn px-4 py-2 rounded-xl text-xs font-bold border border-slate-700 text-slate-300">📋 Ficha & CEP</button>
            <button onclick="mudarAba('aba-adendo')" id="btn-aba-adendo" class="tab-btn px-4 py-2 rounded-xl text-xs font-bold border border-slate-700 text-slate-300">➕ Adendo</button>
            {admin_tabs}
        </div>
    </nav>

    <main class="max-w-7xl mx-auto p-6 space-y-6">
        <!-- ABA PRINCIPAL -->
        <div id="aba-leads" class="tab-content active space-y-6">
            <div class="grid grid-cols-2 lg:grid-cols-4 gap-4">
                <div class="bg-slate-900 border border-slate-800 p-5 rounded-2xl shadow"><p class="text-[11px] font-bold text-slate-400 uppercase">Faturamento Liberado</p><p class="text-xl font-bold text-amber-400">R$ {met['faturamento']:,.2f}</p></div>
                {lucro_card}
                <div class="bg-slate-900 border border-slate-800 p-5 rounded-2xl shadow"><p class="text-[11px] font-bold text-slate-400 uppercase">Ticket Médio</p><p class="text-xl font-bold text-white">R$ {met['ticket']:,.2f}</p></div>
                <div class="bg-slate-900 border border-slate-800 p-5 rounded-2xl shadow"><p class="text-[11px] font-bold text-slate-400 uppercase">Conversão</p><p class="text-xl font-bold text-amber-400">{met['taxa']:.1f}%</p></div>
            </div>

            <!-- TARJA VERMELHA DE ALERTA DINÂMICA -->
            <div id="tarja_alerta_margem" class="hidden p-4 bg-rose-950/90 border-2 border-rose-500 text-rose-200 rounded-2xl text-center space-y-1 shadow-2xl animate-pulse">
                <span class="text-base font-black tracking-wide block">🚨 ALERTA: DESCONTO ULTRAPASSOU A MARGEM DE VENDA AUTORIZADA!</span>
                <p class="text-xs text-rose-300">A margem máxima permitida foi excedida. A geração de contrato e a conclusão da venda foram travadas e exigem a liberação do Administrador Geral.</p>
            </div>

            <!-- MESA DE NEGOCIAÇÃO COMERCIAL COMPLETA -->
            <div class="bg-slate-900 border border-amber-500/40 rounded-3xl p-6 sm:p-8 shadow-2xl space-y-5">
                <div class="flex flex-col sm:flex-row justify-between items-start sm:items-center border-b border-slate-800 pb-3 gap-2">
                    <div>
                        <h2 class="text-lg font-bold text-white flex items-center gap-2">
                            <span>💼 Mesa de Negociação & Fechamento Manual</span>
                        </h2>
                        <p class="text-xs text-slate-400">Você pode digitar o valor de fechamento livremente. Se o desconto for excessivo, o sistema travará a venda até liberação do Administrador.</p>
                    </div>
                    <div class="flex items-center gap-2">
                        <a href="/minuta-contrato/{c_id}" target="_blank" class="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 rounded-xl text-xs font-bold">
                            👁️ Ver Minuta Contrato
                        </a>
                        <span class="px-3 py-1.5 bg-amber-950 text-amber-300 border border-amber-500/40 rounded-xl text-xs font-bold">
                            Cliente Ativo: {c_nome} (#{c_id})
                        </span>
                    </div>
                </div>

                <form action="/salvar-negociacao-mesa" method="post" class="space-y-4 text-xs">
                    <input type="hidden" name="orcamento_id" value="{c_id}">

                    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                        <!-- VALOR BRUTO -->
                        <div class="bg-slate-950 p-4 border border-slate-800 rounded-2xl space-y-1">
                            <label class="text-[11px] text-slate-400 font-bold uppercase block">1. Valor Bruto (Tabela / Projeto)</label>
                            <input type="number" step="0.01" name="preco_bruto" id="preco_bruto" value="{c_p_bruto:.2f}" oninput="recalcularPorBrutoOuDesc()" class="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-xl text-white font-bold text-base focus:border-amber-500">
                        </div>

                        <!-- DESCONTO COMERCIAL -->
                        <div class="bg-slate-950 p-4 border border-slate-800 rounded-2xl space-y-1">
                            <label class="text-[11px] text-slate-400 font-bold uppercase block">2. Desconto Aplicado (%)</label>
                            <div class="flex gap-2">
                                <input type="number" step="0.1" min="0" max="60" name="desconto_pct" id="desconto_pct" value="{c_desc_pct:.1f}" oninput="recalcularPorBrutoOuDesc()" class="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-xl text-white font-bold text-base focus:border-amber-500">
                                <span class="px-3 py-2 bg-slate-800 rounded-xl text-slate-300 font-bold flex items-center">%</span>
                            </div>
                        </div>

                        <!-- VALOR LÍQUIDO FINAL -->
                        <div class="bg-slate-950 p-4 border border-amber-500/50 rounded-2xl space-y-1">
                            <label class="text-[11px] text-amber-400 font-bold uppercase block">3. Valor Fechamento Manual (R$)</label>
                            <input type="number" step="0.01" name="preco_venda" id="preco_venda" value="{c_p_venda:.2f}" oninput="recalcularPorValorManual()" class="w-full px-3 py-2 bg-slate-900 border border-amber-500 rounded-xl text-amber-300 font-black text-xl focus:outline-none">
                            <span class="text-[10px] text-slate-500 block">Pode digitar o valor final direto</span>
                        </div>

                        <!-- MARGEM / MARKUP COM CADEADO DE SEGURANÇA -->
                        <div class="bg-slate-950 p-4 border border-slate-800 rounded-2xl space-y-1">
                            <div class="flex justify-between items-center">
                                <label class="text-[11px] text-slate-400 font-bold uppercase block">4. Margem / Markup Venda</label>
                                <button type="button" onclick="alternarTravaMarkup()" id="btn_trava_markup" title="Travar / Destravar Margem" class="text-xs text-amber-400 hover:text-amber-300">
                                    🔒 Trancado
                                </button>
                            </div>
                            <input type="number" step="0.1" min="1.0" max="5.0" name="markup" id="markup" value="{c_markup:.1f}" readonly class="w-full px-3 py-2 bg-slate-900/60 border border-slate-800 rounded-xl text-slate-300 font-bold text-base cursor-not-allowed">
                        </div>
                    </div>

                    <div class="p-5 bg-slate-950 border border-slate-800 rounded-2xl space-y-3">
                        <h3 class="text-xs font-bold text-amber-400 uppercase tracking-wide">💳 Condições de Pagamento & Parcelamento</h3>
                        <div class="grid grid-cols-1 sm:grid-cols-4 gap-3">
                            <div class="sm:col-span-2">
                                <label class="block text-slate-400 mb-1">Modalidade Selecionada</label>
                                <select name="modalidade_pagamento" class="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-xl text-white font-medium">
                                    <option value="PIX à Vista" {"selected" if c_mod == "PIX à Vista" else ""}>⚡ PIX à Vista (com desconto)</option>
                                    <option value="Cartão de Débito" {"selected" if c_mod == "Cartão de Débito" else ""}>💳 Cartão de Débito</option>
                                    <option value="Cartão de Crédito em até 12x" {"selected" if "12x" in c_mod else ""}>🔢 Cartão de Crédito (até 12x)</option>
                                    <option value="Boleto Bancário em até 24x" {"selected" if "24x" in c_mod else ""}>📄 Boleto Bancário / Financiamento (até 24x)</option>
                                </select>
                            </div>
                            <div>
                                <label class="block text-slate-400 mb-1">Valor de Entrada (R$)</label>
                                <input type="number" step="100" name="entrada_valor" id="entrada_valor" value="{c_entrada:.2f}" oninput="recalcularParcelas()" class="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-xl text-white font-bold">
                            </div>
                            <div>
                                <label class="block text-slate-400 mb-1">Nº de Parcelas</label>
                                <input type="number" min="1" max="24" name="num_parcelas" id="num_parcelas" value="{c_parc}" oninput="recalcularParcelas()" class="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-xl text-white font-bold">
                            </div>
                        </div>

                        <div class="p-3 bg-slate-900 rounded-xl border border-slate-800 flex flex-wrap justify-between items-center text-xs">
                            <span class="text-slate-300">
                                Simulação: Entrada de <b>R$ {c_entrada:,.2f}</b> + <b>{c_parc}x de <span id="txt_parcela" class="text-amber-400 font-bold">R$ {valor_por_parcela:,.2f}</span></b>
                            </span>
                            <span class="text-[11px] text-slate-400">Saldo Financiado: R$ <span id="txt_saldo">{saldo_financiar:,.2f}</span></span>
                        </div>
                    </div>

                    <div class="flex flex-col sm:flex-row justify-between items-center gap-3 pt-2">
                        {lucro_negociacao_box}
                        <button type="submit" id="btn_salvar_mesa" class="w-full sm:w-auto px-8 py-3.5 bg-gradient-to-r from-amber-500 to-amber-600 hover:from-amber-400 hover:to-amber-500 text-slate-950 font-bold rounded-xl text-sm shadow-lg">
                            💾 Atualizar Negociação & Aplicar no Contrato
                        </button>
                    </div>
                </form>
            </div>

            <!-- TABELA DE VENDAS -->
            <div class="bg-slate-900 border border-slate-800 rounded-3xl overflow-hidden shadow">
                <div class="p-4 border-b border-slate-800 flex justify-between items-center bg-slate-850">
                    <div>
                        <h3 class="text-sm font-semibold text-white">📁 Fila de Vendas e Liberações (Clique em 'Negociar' para carregar nas abas)</h3>
                    </div>
                    <a href="/exportar-csv" class="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 rounded-xl text-xs font-semibold">📊 CSV</a>
                </div>
                <div class="overflow-x-auto">
                    <table class="w-full text-left border-collapse">
                        <thead>
                            <tr class="bg-slate-800/40 border-b border-slate-800 text-xs font-semibold text-slate-400 uppercase">
                                <th class="py-3 px-4"># ID</th>
                                <th class="py-3 px-4">Cliente</th>
                                <th class="py-3 px-4">Ambiente</th>
                                <th class="py-3 px-4 text-right">Valor Venda</th>
                                {th_lucro}
                                <th class="py-3 px-4 text-center">Liberação</th>
                                <th class="py-3 px-4 text-center">Contrato & Assinatura</th>
                                <th class="py-3 px-4 text-center">Ação</th>
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
                <h2 class="text-base font-bold text-white">🚀 Integrador Promob Universal (XML, CSV, TXT, Cut)</h2>
                <form action="/importar-promob" method="post" enctype="multipart/form-data" class="grid sm:grid-cols-3 gap-4 text-xs">
                    <input type="text" name="cliente_nome" value="{c_nome if c_id else ''}" required placeholder="Nome do Cliente" class="px-3 py-2.5 bg-slate-950 border border-slate-700 rounded-xl text-white">
                    <input type="text" name="cliente_telefone" value="{cliente_ativo['cliente_telefone'] if cliente_ativo else ''}" required placeholder="WhatsApp" class="px-3 py-2.5 bg-slate-950 border border-slate-700 rounded-xl text-white">
                    <input type="text" name="cliente_ambiente" value="{c_amb if c_id else ''}" required placeholder="Ambientes" class="px-3 py-2.5 bg-slate-950 border border-slate-700 rounded-xl text-white">
                    <div class="sm:col-span-3 p-4 bg-slate-950 border border-slate-800 rounded-2xl">
                        <label class="block font-bold text-amber-400 mb-2">📁 Arquivo de Peças Exportado do Promob (.xml, .csv, .txt, .cut)</label>
                        <input type="file" name="arquivo_promob" accept=".xml,.csv,.txt,.cut" required class="w-full text-slate-400 file:bg-amber-500 file:border-0 file:rounded-xl file:px-4 file:py-2 file:font-bold">
                    </div>
                    <button type="submit" class="sm:col-span-3 py-3.5 bg-amber-500 font-bold rounded-xl text-slate-950 text-sm">⚡ Processar Promob & Gerar Orçamento no CRM</button>
                </form>
            </div>
        </div>

        <!-- ABA FICHA CADASTRAL & CEP -->
        <div id="aba-cadastro" class="tab-content space-y-6">
            <div class="bg-slate-900 border border-slate-800 rounded-3xl p-6 shadow space-y-6">
                <div>
                    <h2 class="text-base font-bold text-white">📑 Ficha Cadastral Completa & Geração de Contrato</h2>
                    <p class="text-xs text-slate-400">Preencha os dados completos do cliente e utilize a busca de CEP nos endereços.</p>
                </div>
                <form action="/salvar-dados-completos-cliente" method="post" class="space-y-4 text-xs">
                    <div class="bg-slate-950 p-4 rounded-xl border border-slate-800">
                        <label class="block text-amber-400 font-bold mb-1">Selecione o Projeto / Lead existente ou crie um novo:</label>
                        <select name="orcamento_id" class="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-xl text-white">
                            {options_leads}
                        </select>
                    </div>

                    <div class="space-y-3">
                        <h3 class="text-xs font-bold text-amber-400 uppercase tracking-wide">1. Identificação Pessoal</h3>
                        <div class="grid sm:grid-cols-4 gap-3">
                            <input type="text" name="cliente_nome" value="{c_nome if c_id else ''}" required placeholder="Nome Completo" class="sm:col-span-2 px-3 py-2 bg-slate-950 border border-slate-700 rounded-xl text-white">
                            <input type="text" name="cliente_cpf" value="{cliente_ativo['cliente_cpf'] if cliente_ativo else ''}" placeholder="CPF" class="px-3 py-2 bg-slate-950 border border-slate-700 rounded-xl text-white">
                            <div class="flex gap-1">
                                <input type="text" name="cliente_rg" value="{cliente_ativo['cliente_rg'] if cliente_ativo else ''}" placeholder="RG" class="w-2/3 px-3 py-2 bg-slate-950 border border-slate-700 rounded-xl text-white">
                                <input type="text" name="cliente_rg_emissor" value="{cliente_ativo['cliente_rg_emissor'] if cliente_ativo else ''}" placeholder="SSP/SP" class="w-1/3 px-2 py-2 bg-slate-950 border border-slate-700 rounded-xl text-white">
                            </div>
                            <input type="date" name="cliente_nascimento" value="{cliente_ativo['cliente_nascimento'] if cliente_ativo else ''}" class="px-3 py-2 bg-slate-950 border border-slate-700 rounded-xl text-white">
                            <input type="text" name="cliente_pais" value="Brasil" placeholder="País" class="px-3 py-2 bg-slate-950 border border-slate-700 rounded-xl text-white">
                            <input type="text" name="cliente_cidade" value="{cliente_ativo['cliente_cidade'] if cliente_ativo else ''}" placeholder="Cidade / UF" class="px-3 py-2 bg-slate-950 border border-slate-700 rounded-xl text-white">
                            <input type="email" name="cliente_email" value="{cliente_ativo['cliente_email'] if cliente_ativo else ''}" placeholder="E-mail" class="px-3 py-2 bg-slate-950 border border-slate-700 rounded-xl text-white">
                            <input type="text" name="cliente_telefone" value="{cliente_ativo['cliente_telefone'] if cliente_ativo else ''}" placeholder="WhatsApp Principal" class="px-3 py-2 bg-slate-950 border border-slate-700 rounded-xl text-white">
                            <input type="text" name="cliente_telefone_2" value="{cliente_ativo['cliente_telefone_2'] if cliente_ativo else ''}" placeholder="Telefone 2 / Recado" class="px-3 py-2 bg-slate-950 border border-slate-700 rounded-xl text-white">
                        </div>
                    </div>

                    <div class="space-y-3">
                        <h3 class="text-xs font-bold text-amber-400 uppercase tracking-wide">2. Endereços com Busca de CEP</h3>
                        <div class="grid sm:grid-cols-2 gap-4">
                            <div class="bg-slate-950 p-4 border border-slate-800 rounded-xl space-y-2">
                                <label class="font-bold text-white block">📬 Endereço Postal</label>
                                <div class="flex gap-2">
                                    <input type="text" id="cep_postal" name="cliente_cep_postal" value="{cliente_ativo['cliente_cep_postal'] if cliente_ativo else ''}" placeholder="CEP Postal" class="w-1/2 px-3 py-2 bg-slate-900 border border-slate-700 rounded-xl text-white">
                                    <button type="button" onclick="buscarCep('postal')" class="w-1/2 px-3 py-2 bg-amber-500 font-bold text-slate-950 rounded-xl">🔍 Buscar CEP</button>
                                </div>
                                <textarea id="end_postal" name="cliente_endereco_postal" rows="2" placeholder="Rua, Número, Bairro, Cidade - UF" class="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-xl text-white">{cliente_ativo['cliente_endereco_postal'] if cliente_ativo else ''}</textarea>
                            </div>
                            <div class="bg-slate-950 p-4 border border-slate-800 rounded-xl space-y-2">
                                <label class="font-bold text-white block">🚚 Endereço da Obra</label>
                                <div class="flex gap-2">
                                    <input type="text" id="cep_entrega" name="cliente_cep_entrega" value="{cliente_ativo['cliente_cep_entrega'] if cliente_ativo else ''}" placeholder="CEP Obra" class="w-1/2 px-3 py-2 bg-slate-900 border border-slate-700 rounded-xl text-white">
                                    <button type="button" onclick="buscarCep('entrega')" class="w-1/2 px-3 py-2 bg-amber-500 font-bold text-slate-950 rounded-xl">🔍 Buscar CEP</button>
                                </div>
                                <textarea id="end_entrega" name="cliente_endereco_entrega" rows="2" placeholder="Endereço da Instalação..." class="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-xl text-white">{cliente_ativo['cliente_endereco_entrega'] if cliente_ativo else ''}</textarea>
                            </div>
                        </div>
                    </div>

                    <div class="space-y-3">
                        <h3 class="text-xs font-bold text-amber-400 uppercase tracking-wide">3. Dados Bancários, Renda & Referências</h3>
                        <div class="grid sm:grid-cols-4 gap-3">
                            <input type="text" name="cliente_banco" value="{cliente_ativo['cliente_banco'] if cliente_ativo else ''}" placeholder="Banco" class="px-3 py-2 bg-slate-950 border border-slate-700 rounded-xl text-white">
                            <input type="text" name="cliente_agencia" value="{cliente_ativo['cliente_agencia'] if cliente_ativo else ''}" placeholder="Agência" class="px-3 py-2 bg-slate-950 border border-slate-700 rounded-xl text-white">
                            <input type="text" name="cliente_conta" value="{cliente_ativo['cliente_conta'] if cliente_ativo else ''}" placeholder="Conta Corrente" class="px-3 py-2 bg-slate-950 border border-slate-700 rounded-xl text-white">
                            <input type="text" name="cliente_renda" value="{cliente_ativo['cliente_renda'] if cliente_ativo else ''}" placeholder="Renda Mensal Estimada" class="px-3 py-2 bg-slate-950 border border-slate-700 rounded-xl text-white">
                            <input type="text" name="ref_nome_1" value="{cliente_ativo['ref_nome_1'] if cliente_ativo else ''}" placeholder="Nome Referência 1" class="px-3 py-2 bg-slate-950 border border-slate-700 rounded-xl text-white">
                            <input type="text" name="ref_tel_1" value="{cliente_ativo['ref_tel_1'] if cliente_ativo else ''}" placeholder="Telefone Referência 1" class="px-3 py-2 bg-slate-950 border border-slate-700 rounded-xl text-white">
                            <input type="text" name="ref_nome_2" value="{cliente_ativo['ref_nome_2'] if cliente_ativo else ''}" placeholder="Nome Referência 2" class="px-3 py-2 bg-slate-950 border border-slate-700 rounded-xl text-white">
                            <input type="text" name="ref_tel_2" value="{cliente_ativo['ref_tel_2'] if cliente_ativo else ''}" placeholder="Telefone Referência 2" class="px-3 py-2 bg-slate-950 border border-slate-700 rounded-xl text-white">
                        </div>
                    </div>

                    <div class="space-y-3">
                        <h3 class="text-xs font-bold text-amber-400 uppercase tracking-wide">4. Memorial Descritivo & Pagamento</h3>
                        <div class="grid sm:grid-cols-4 gap-3 bg-slate-950 p-4 border border-slate-800 rounded-xl">
                            <textarea name="descricao_manual" rows="2" placeholder="Memorial Descritivo / Detalhes de Acabamentos..." class="sm:col-span-4 px-3 py-2 bg-slate-900 border border-slate-700 rounded-xl text-white">{cliente_ativo['descricao_manual'] if cliente_ativo else ''}</textarea>
                            <select name="forma_pagamento" class="sm:col-span-2 px-3 py-2 bg-slate-900 border border-slate-700 rounded-xl text-white">
                                <option value="PIX à Vista">PIX à Vista</option>
                                <option value="Cartão de Débito">Cartão de Débito</option>
                                <option value="Cartão de Crédito até 12x">Cartão de Crédito até 12x</option>
                                <option value="Boleto Bancário até 24x">Boleto Bancário até 24x</option>
                                <option value="Entrada PIX + Saldo no Cartão">Entrada PIX + Saldo no Cartão</option>
                            </select>
                            <input type="number" step="0.5" name="desconto_pct" value="{c_desc_pct}" placeholder="Desconto (%)" class="px-3 py-2 bg-slate-900 border border-slate-700 rounded-xl text-white">
                            <input type="number" step="100" name="entrada_valor" value="{c_entrada}" placeholder="Entrada (R$)" class="px-3 py-2 bg-slate-900 border border-slate-700 rounded-xl text-white">
                            <input type="number" min="1" max="24" name="num_parcelas" value="{c_parc}" placeholder="Nº Parcelas" class="px-3 py-2 bg-slate-900 border border-slate-700 rounded-xl text-white">
                        </div>
                    </div>

                    <button type="submit" class="w-full py-3.5 bg-amber-500 font-bold rounded-xl text-slate-950 text-sm shadow-lg">💾 Salvar Ficha Cadastral e Liberar Contrato</button>
                </form>
            </div>
        </div>

        <!-- ABA ADENDO -->
        <div id="aba-adendo" class="tab-content space-y-6">
            <div class="bg-slate-900 border border-slate-800 rounded-3xl p-6 shadow">
                <h2 class="text-base font-bold text-white mb-4">➕ Termo Aditivo / Complemento</h2>
                <form action="/salvar-adendo" method="post" class="grid sm:grid-cols-3 gap-4 text-xs">
                    <select name="orcamento_id" class="px-3 py-2 bg-slate-950 border border-slate-700 rounded-xl text-white">{options_leads}</select>
                    <input type="number" step="10" name="adendo_valor" required placeholder="Valor Adicional R$" class="px-3 py-2 bg-slate-950 border border-slate-700 rounded-xl text-white">
                    <textarea name="adendo_descricao" rows="2" required placeholder="Descrição dos novos itens adicionados..." class="sm:col-span-3 px-3 py-2 bg-slate-950 border border-slate-700 rounded-xl text-white"></textarea>
                    <button type="submit" class="col-span-full py-3 bg-amber-500 font-bold rounded-xl text-slate-950">Salvar Termo Aditivo</button>
                </form>
            </div>
        </div>

        {admin_content}

    </main>

    <script>
        function mudarAba(abaId) {{
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            document.getElementById(abaId).classList.add('active');
            document.getElementById('btn-' + abaId).classList.add('active');
            window.scrollTo({{ top: 0, behavior: 'smooth' }});
        }}

        function recalcularPorBrutoOuDesc() {{
            var bruto = parseFloat(document.getElementById('preco_bruto').value) || 0;
            var desc = parseFloat(document.getElementById('desconto_pct').value) || 0;
            var valorFinal = bruto * (1.0 - (desc / 100.0));
            document.getElementById('preco_venda').value = valorFinal.toFixed(2);
            verificarMargemEAlerta(desc);
            recalcularParcelas();
        }}

        function recalcularPorValorManual() {{
            var bruto = parseFloat(document.getElementById('preco_bruto').value) || 0;
            var manual = parseFloat(document.getElementById('preco_venda').value) || 0;
            
            if (bruto > 0) {{
                var descCalculado = ((bruto - manual) / bruto) * 100.0;
                descCalculado = Math.max(descCalculado, 0);
                document.getElementById('desconto_pct').value = descCalculado.toFixed(1);
                verificarMargemEAlerta(descCalculado);
            }}
            recalcularParcelas();
        }}

        function verificarMargemEAlerta(desc) {{
            var tarja = document.getElementById('tarja_alerta_margem');
            var btnSalvar = document.getElementById('btn_salvar_mesa');
            var descAutorizado = {c_aut_desc};
            var isUserAdmin = {'true' if is_admin else 'false'};

            if (desc > 3.0) {{
                tarja.classList.remove('hidden');
                if (!isUserAdmin && !descAutorizado) {{
                    btnSalvar.classList.remove('from-amber-500', 'to-amber-600', 'hover:from-amber-400', 'hover:to-amber-500', 'text-slate-950');
                    btnSalvar.classList.add('bg-rose-600', 'text-white', 'hover:bg-rose-500');
                    btnSalvar.innerText = "🔒 Bloqueado: Solicitar Liberação do Administrador";
                }}
            }} else {{
                tarja.classList.add('hidden');
                btnSalvar.classList.add('from-amber-500', 'to-amber-600', 'text-slate-950');
                btnSalvar.classList.remove('bg-rose-600', 'text-white');
                btnSalvar.innerText = "💾 Atualizar Negociação & Aplicar no Contrato";
            }}
        }}

        // TRAVA E DESTRAVA DA MARGEM / MARKUP
        var markupTravado = true;
        function alternarTravaMarkup() {{
            var inputMarkup = document.getElementById('markup');
            var btnTrava = document.getElementById('btn_trava_markup');
            markupTravado = !markupTravado;
            
            if (markupTravado) {{
                inputMarkup.setAttribute('readonly', 'true');
                inputMarkup.classList.add('cursor-not-allowed', 'bg-slate-900/60');
                inputMarkup.classList.remove('bg-slate-900');
                btnTrava.innerText = "🔒 Trancado";
            }} else {{
                inputMarkup.removeAttribute('readonly');
                inputMarkup.classList.remove('cursor-not-allowed', 'bg-slate-900/60');
                inputMarkup.classList.add('bg-slate-900');
                btnTrava.innerText = "🔓 Destravado";
            }}
        }}

        function recalcularParcelas() {{
            var valorFinal = parseFloat(document.getElementById('preco_venda').value) || 0;
            var entrada = parseFloat(document.getElementById('entrada_valor').value) || 0;
            var nParc = parseInt(document.getElementById('num_parcelas').value) || 1;

            var saldo = Math.max(valorFinal - entrada, 0);
            var vParc = nParc > 0 ? (saldo / nParc) : 0;
            document.getElementById('txt_parcela').innerText = "R$ " + vParc.toLocaleString('pt-BR', {{ minimumFractionDigits: 2, maximumFractionDigits: 2 }});
            document.getElementById('txt_saldo').innerText = saldo.toLocaleString('pt-BR', {{ minimumFractionDigits: 2, maximumFractionDigits: 2 }});
        }}

        var lucroVisivel = true;
        function alternarOlhoLucro() {{
            var elem = document.getElementById('valor_lucro_operacao');
            var btn = document.getElementById('btn_olho_lucro');
            if (!elem) return;

            lucroVisivel = !lucroVisivel;
            if (lucroVisivel) {{
                elem.innerText = elem.getAttribute('data-real');
                btn.innerText = "👁️";
                document.querySelectorAll('.valor-lucro-col').forEach(td => td.style.filter = 'none');
                document.querySelectorAll('.valor-ocultavel').forEach(c => c.style.filter = 'none');
            }} else {{
                elem.innerText = "••••••••";
                btn.innerText = "🙈";
                document.querySelectorAll('.valor-lucro-col').forEach(td => td.style.filter = 'blur(6px)');
                document.querySelectorAll('.valor-ocultavel').forEach(c => c.style.filter = 'blur(6px)');
            }}
        }}

        function buscarCep(tipo) {{
            var cepInput = document.getElementById(tipo === 'postal' ? 'cep_postal' : 'cep_entrega');
            var endText = document.getElementById(tipo === 'postal' ? 'end_postal' : 'end_entrega');
            var cep = cepInput.value.replace(/\\D/g, '');

            if (cep.length !== 8) {{
                alert("Por favor, digite um CEP com 8 dígitos.");
                return;
            }}

            endText.value = "Buscando endereço nos Correios...";

            fetch('https://viacep.com.br/ws/' + cep + '/json/')
                .then(res => res.json())
                .then(dados => {{
                    if (dados.erro) {{
                        alert("CEP não encontrado!");
                        endText.value = "";
                    }} else {{
                        endText.value = dados.logradouro + ", Nº [DIGITE O NÚMERO], " + (dados.bairro ? dados.bairro + ", " : "") + dados.localidade + " - " + dados.uf;
                    }}
                }})
                .catch(() => {{
                    alert("Erro ao buscar CEP.");
                    endText.value = "";
                }});
        }}

        window.onload = function() {{
            var descInicial = parseFloat(document.getElementById('desconto_pct').value) || 0;
            verificarMargemEAlerta(descInicial);
        }};
    </script>
</body></html>"""

# ==============================================================================
# 5. SIMULADOR PÚBLICO COM OS RÓTULOS (LABELS) CORRIGIDOS E CLAROS
# ==============================================================================
def render_form_captacao(empresa):
    return f"""<!DOCTYPE html>
<html lang="pt-br">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{empresa['nome_empresa']} - Simulador</title><script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-slate-950 text-slate-100 min-h-screen flex flex-col justify-between font-sans">
    <header class="bg-slate-900 border-b border-slate-800 px-6 py-4 flex items-center justify-between">
        <div class="flex items-center space-x-3"><div class="w-9 h-9 rounded-xl bg-gradient-to-br from-amber-400 to-amber-600 flex items-center justify-center font-black text-slate-950 text-lg">MVI</div><span class="font-bold text-white">{empresa['nome_empresa']}</span></div>
    </header>
    <main class="max-w-3xl w-full mx-auto p-4 sm:p-6 my-auto">
        <form action="/enviar-solicitacao-lead" method="post" enctype="multipart/form-data" class="bg-slate-900 border border-slate-800 p-6 sm:p-8 rounded-3xl shadow-2xl space-y-4">
            <h2 class="text-lg font-bold text-white mb-1">Simulador de Projeto Sob Medida</h2>
            <p class="text-xs text-slate-400 mb-3">Defina as especificações de caixaria, portas, acabamentos e ferragens do seu projeto.</p>
            
            <div class="grid sm:grid-cols-2 gap-3 text-xs">
                <div>
                    <label class="block text-slate-300 font-semibold mb-1">👤 Seu Nome Completo</label>
                    <input type="text" name="nome" required placeholder="Ex: Mariana Silva" class="w-full px-4 py-2.5 bg-slate-950 border border-slate-700 rounded-xl text-white">
                </div>
                <div>
                    <label class="block text-slate-300 font-semibold mb-1">📱 Seu WhatsApp (com DDD)</label>
                    <input type="text" name="whatsapp" required placeholder="Ex: (11) 99999-8888" class="w-full px-4 py-2.5 bg-slate-950 border border-slate-700 rounded-xl text-white">
                </div>
                <div>
                    <label class="block text-amber-400 font-bold mb-1">📐 Metragem Total do Imóvel (m²)</label>
                    <input type="number" step="any" min="5" name="area_m2_total" value="180.0" required placeholder="Ex: 180" class="w-full px-4 py-2.5 bg-slate-950 border border-slate-700 rounded-xl text-white font-bold">
                </div>
                <div>
                    <label class="block text-slate-300 font-semibold mb-1">📍 Cidade / Bairro da Obra</label>
                    <input type="text" name="cidade" required placeholder="Ex: São Paulo / Moema" class="w-full px-4 py-2.5 bg-slate-950 border border-slate-700 rounded-xl text-white">
                </div>
            </div>
            
            <!-- SEÇÃO DE CAIXAS, PORTAS, ACABAMENTOS, FERRAGENS E TAMPONAMENTO -->
            <div class="bg-slate-950 p-4 sm:p-5 rounded-2xl border border-slate-800 space-y-4 text-xs">
                <h3 class="font-bold text-amber-400 uppercase tracking-wide">🪵 Especificações de Caixas, Portas & Ferragens</h3>
                
                <!-- 1. Caixaria -->
                <div class="grid sm:grid-cols-2 gap-3">
                    <div>
                        <label class="block text-slate-300 font-semibold mb-1">Espessura da Caixa (Estrutura)</label>
                        <select name="espessura_caixa" class="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-xl text-white">
                            <option value="MDF 18mm (Reforçado)">MDF 18mm (Reforçado)</option>
                            <option value="MDF 15mm (Padrão)">MDF 15mm (Padrão)</option>
                        </select>
                    </div>
                    <div>
                        <label class="block text-slate-300 font-semibold mb-1">Padrão / Cor da Caixa</label>
                        <select name="cor_caixa" class="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-xl text-white">
                            <option value="Branco TX">Branco TX</option>
                            <option value="Amadeirado">Amadeirado</option>
                        </select>
                    </div>
                </div>

                <!-- 2. Portas e Frentes -->
                <div class="grid sm:grid-cols-3 gap-3">
                    <div>
                        <label class="block text-slate-300 font-semibold mb-1">Espessura das Portas</label>
                        <select name="espessura_porta" class="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-xl text-white">
                            <option value="MDF 18mm">MDF 18mm</option>
                            <option value="MDF 15mm">MDF 15mm</option>
                        </select>
                    </div>
                    <div>
                        <label class="block text-slate-300 font-semibold mb-1">Padrão / Cor das Portas</label>
                        <select name="cor_porta" class="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-xl text-white">
                            <option value="Branco TX">Branco TX</option>
                            <option value="Amadeirado">Amadeirado</option>
                        </select>
                    </div>
                    <div>
                        <label class="block text-slate-300 font-semibold mb-1">Acabamento das Portas</label>
                        <select name="acabamento_porta" class="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-xl text-white">
                            <option value="Madeira Lisa Tradicional">Madeira Lisa Tradicional</option>
                            <option value="Estilo Provençal">Estilo Provençal</option>
                            <option value="Estilo Americana (Shaker)">Estilo Americana (Shaker)</option>
                            <option value="Pintura em Lacca">Pintura em Lacca</option>
                            <option value="Vidro / Reflecta c/ Alumínio">Vidro / Reflecta c/ Alumínio</option>
                            <option value="Portas Passantes / Painel">Portas Passantes / Painel</option>
                        </select>
                    </div>
                </div>

                <!-- 3. Ferragens e Tamponamento -->
                <div class="grid sm:grid-cols-2 gap-3">
                    <div>
                        <label class="block text-slate-300 font-semibold mb-1">Marca das Ferragens</label>
                        <select name="marca_ferragens" class="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-xl text-white">
                            <option value="Blum (Linha Blumotion Áustria)">Blum (Linha Blumotion Áustria)</option>
                            <option value="Hettich (Linha Sensys Alemanha)">Hettich (Linha Sensys Alemanha)</option>
                            <option value="Häfele (Linha Matrix Box)">Häfele (Linha Matrix Box)</option>
                            <option value="FGVTN (Linha Slowmotion)">FGVTN (Linha Slowmotion)</option>
                            <option value="Standard com Amortecedor">Standard com Amortecedor</option>
                        </select>
                    </div>
                    <div>
                        <label class="block text-slate-300 font-semibold mb-1">Tamponamento Externo</label>
                        <select name="espessura_tamponamento" class="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-xl text-white">
                            <option value="Tamponamento 25mm">Tamponamento 25mm</option>
                            <option value="Tamponamento 36mm Engrossado">Tamponamento 36mm Engrossado</option>
                            <option value="Tamponamento 18mm">Tamponamento 18mm</option>
                            <option value="Sem Tamponamento">Sem Tamponamento</option>
                        </select>
                    </div>
                </div>

                <!-- 4. CAIXA DE OBSERVAÇÃO DENTRO DA SEÇÃO DE ACABAMENTOS -->
                <div>
                    <label class="block text-slate-300 font-semibold mb-1">Observações & Detalhes Especiais do seu Projeto</label>
                    <textarea name="descricao" rows="3" placeholder="Ex: Gostaria de iluminação em LED embutida nos aéreos, puxador cava usinada nos gaveteiros da cozinha, amortecedor em todas as portas e portas de vidro reflecta bronze na suíte..." class="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-xl text-white focus:outline-none focus:border-amber-500 text-xs"></textarea>
                </div>
            </div>

            <div class="grid sm:grid-cols-2 gap-3 text-xs">
                <div class="bg-slate-950 p-3 rounded-xl border border-slate-800 space-y-1">
                    <label class="font-bold text-amber-400 block">📐 Planta Baixa do Imóvel</label>
                    <input type="file" name="planta" required class="w-full text-slate-400 file:bg-amber-500 file:border-0 file:rounded-xl file:px-3 file:py-1 file:font-bold text-xs">
                </div>
                <div class="bg-slate-950 p-3 rounded-xl border border-slate-800 space-y-1">
                    <label class="font-bold text-slate-300 block">🖼️ Foto de Inspiração / Referência</label>
                    <input type="file" name="inspiracao" class="w-full text-slate-400 file:bg-slate-700 file:border-0 file:rounded-xl file:px-3 file:py-1 file:font-bold text-white text-xs">
                </div>
            </div>
            
            <button type="submit" class="w-full py-4 bg-gradient-to-r from-amber-500 to-amber-600 hover:from-amber-400 hover:to-amber-500 text-slate-950 font-bold rounded-xl text-sm shadow-lg">
                ⚡ Simular Projeto & Receber Proposta MVI
            </button>
        </form>
    </main>
</body></html>"""

# ==============================================================================
# TELA DE PRÉ-ORÇAMENTO COM DESCONTO DE 5% À VISTA E FORMAS DE PAGAMENTO
# ==============================================================================
def render_pre_orcamento_agendamento(
    empresa, orcamento_id, nome, whatsapp, cidade, area_m2, preco_venda,
    esp_caixa, cor_caixa, esp_porta, cor_porta, acab_porta, marca_ferr, esp_tamp
):
    entrada_minima = preco_venda * 0.30
    saldo_restante = preco_venda - entrada_minima
    parcela_12x = saldo_restante / 12.0
    desconto_vista_5 = preco_venda * 0.95
    economia_5 = preco_venda * 0.05

    tel_limpo = empresa["telefone"].replace("-","").replace(" ","").replace("(","").replace(")","")

    return f"""<!DOCTYPE html>
<html lang="pt-br">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{empresa['nome_empresa']} - Pré-Orçamento & Agendamento</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-slate-950 text-slate-100 min-h-screen p-4 sm:p-8 font-sans flex items-center justify-center">
    <div class="max-w-2xl w-full bg-slate-900 border border-amber-500/40 rounded-3xl p-6 sm:p-10 shadow-2xl space-y-6">
        
        <!-- CABEÇALHO DO RESULTADO -->
        <div class="text-center space-y-2 border-b border-slate-800 pb-4">
            <span class="text-4xl block animate-bounce">✨</span>
            <h1 class="text-xl sm:text-2xl font-bold text-white">Seu Pré-Orçamento Sob Medida foi Calculado!</h1>
            <p class="text-xs text-slate-400">Olá, <b>{nome}</b>! Confira abaixo a estimativa do seu projeto para <b>{cidade} ({area_m2} m²)</b>.</p>
        </div>

        <!-- ESTIMATIVA TOTAL COM DESCONTO À VISTA DE 5% -->
        <div class="bg-slate-950 p-6 rounded-2xl border border-amber-500/40 text-center space-y-2">
            <span class="text-xs text-slate-400 font-bold uppercase tracking-wider block">Valor de Tabela do Projeto</span>
            <span id="txt_valor_principal" class="text-3xl sm:text-4xl font-black text-amber-400">R$ {preco_venda:,.2f}</span>
            
            <!-- CAIXA DO DESCONTO DE 5% À VISTA -->
            <div class="p-3 bg-emerald-950/60 border border-emerald-500/40 rounded-xl inline-block mt-1">
                <span class="text-xs text-emerald-300 font-bold block">⚡ Valor à Vista no PIX (com 5% de desconto):</span>
                <span class="text-xl sm:text-2xl font-black text-emerald-400">R$ {desconto_vista_5:,.2f}</span>
                <span class="text-[11px] text-emerald-200 block">Economia de R$ {economia_5:,.2f}</span>
            </div>

            <p class="text-[11px] text-slate-500 pt-1">Caixas {esp_caixa} ({cor_caixa}) • Portas {acab_porta} • Ferragens {marca_ferr}</p>
        </div>

        <!-- PERGUNTAS DE INTERESSE NO AGENDAMENTO -->
        <div class="bg-slate-950 p-5 rounded-2xl border border-slate-800 space-y-4 text-xs">
            <h3 class="text-xs font-bold text-amber-400 uppercase tracking-wide flex items-center gap-1">
                <span>📅 1. Interesse em Agendamento na Loja</span>
            </h3>
            
            <div class="grid sm:grid-cols-2 gap-3">
                <div>
                    <label class="block text-slate-300 font-semibold mb-1">Deseja agendar um atendimento?</label>
                    <select id="tipo_agendamento" onchange="verificarInteresseAgendamento()" class="w-full px-3 py-2.5 bg-slate-900 border border-slate-700 rounded-xl text-white">
                        <option value="Agendamento Presencial na Loja">🏢 Sim, quero agendamento na loja</option>
                        <option value="Não tenho interesse no momento">❌ Não tenho interesse no momento</option>
                    </select>
                </div>
                <div id="box_horario">
                    <label class="block text-slate-300 font-semibold mb-1">Melhor Período para Atendimento</label>
                    <select id="preferencia_horario" onchange="atualizarMensagemZap()" class="w-full px-3 py-2.5 bg-slate-900 border border-slate-700 rounded-xl text-white">
                        <option value="Manhã (09h às 12h)">🌅 Manhã (09h às 12h)</option>
                        <option value="Tarde (14h às 18h)" selected>☀️ Tarde (14h às 18h)</option>
                        <option value="Sábado (09h às 13h)">📅 Sábado (09h às 13h)</option>
                    </select>
                </div>
            </div>
        </div>

        <!-- SIMULAÇÃO FINANCEIRA DE PARCELAS (ENTRADA MÍN. 30%) -->
        <div class="bg-slate-950 p-5 rounded-2xl border border-slate-800 space-y-4 text-xs">
            <div class="flex justify-between items-center">
                <h3 class="text-xs font-bold text-amber-400 uppercase tracking-wide flex items-center gap-1">
                    <span>💳 2. Como você pretende realizar o pagamento?</span>
                </h3>
            </div>

            <div class="grid sm:grid-cols-3 gap-3">
                <div>
                    <label class="block text-slate-300 font-semibold mb-1">Forma de Pagamento</label>
                    <select id="forma_pagamento_cli" onchange="calcularParcelasCliente()" class="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-xl text-white font-medium">
                        <option value="Cartão de Crédito">Cartão de Crédito (até 12x)</option>
                        <option value="PIX à Vista (5% OFF)">⚡ PIX à Vista (5% de Desconto)</option>
                        <option value="Boleto Bancário">Boleto Bancário (até 24x)</option>
                    </select>
                </div>

                <div id="box_entrada_cli">
                    <label class="block text-slate-300 font-semibold mb-1">
                        Entrada (Mínimo de 30%)
                    </label>
                    <input type="number" id="entrada_cli" min="{entrada_minima:.2f}" step="100" value="{entrada_minima:.2f}" oninput="calcularParcelasCliente()" class="w-full px-3 py-2 bg-slate-900 border border-amber-500/50 rounded-xl text-amber-300 font-bold">
                    <span class="text-[10px] text-slate-500 block mt-0.5">Mínimo: R$ {entrada_minima:,.2f}</span>
                </div>

                <div id="box_parcelas_cli">
                    <label class="block text-slate-300 font-semibold mb-1">Nº de Parcelas</label>
                    <select id="parcelas_cli" onchange="calcularParcelasCliente()" class="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-xl text-white font-bold">
                        <option value="1">1x (Sem juros)</option>
                        <option value="3">3x</option>
                        <option value="6">6x</option>
                        <option value="10">10x</option>
                        <option value="12" selected>12x</option>
                        <option value="18">18x (Boleto)</option>
                        <option value="24">24x (Boleto)</option>
                    </select>
                </div>
            </div>

            <!-- RESULTADO DO PARCELAMENTO SIMULADO PELO CLIENTE -->
            <div id="box_resultado_parcelas" class="p-4 bg-slate-900 rounded-xl border border-slate-800 text-center space-y-1">
                <span class="text-slate-400 text-[11px] uppercase tracking-wider block">Seu Plano Simulado:</span>
                <p class="text-sm font-bold text-white">
                    Entrada de <span id="res_entrada" class="text-amber-400">R$ {entrada_minima:,.2f}</span> + 
                    <span id="res_num_parc">12</span>x de <span id="res_valor_parc" class="text-emerald-400 font-black text-base">R$ {parcela_12x:,.2f}</span>
                </p>
                <p class="text-[10px] text-slate-500">Saldo a parcelar: R$ <span id="res_saldo">{saldo_restante:,.2f}</span></p>
            </div>
        </div>

        <!-- BOTÃO PARA SER DIRECIONADO AO WHATSAPP -->
        <div class="pt-2">
            <a id="btn_whatsapp_agendar" href="#" target="_blank" class="flex items-center justify-center gap-2 w-full py-4 bg-gradient-to-r from-emerald-500 to-emerald-600 hover:from-emerald-400 hover:to-emerald-500 text-slate-950 font-black rounded-xl text-sm transition-all shadow-xl">
                <span id="txt_btn_zap">📲 Quero ser direcionado ao WhatsApp para agendar atendimento</span>
            </a>
            <p class="text-[11px] text-center text-slate-500 mt-2">Você será atendido pela equipe oficial da <b>{empresa['nome_empresa']}</b> com sua simulação salva.</p>
        </div>

    </div>

    <script>
        var valorTotalOriginal = {preco_venda};
        var valorComDesconto5 = {desconto_vista_5};
        var entradaMinimaPermitida = {entrada_minima};
        var telEmpresa = "{tel_limpo}";
        var nomeCliente = "{nome}";
        var cidadeCliente = "{cidade}";
        var areaCliente = "{area_m2}";
        var idOrc = "{orcamento_id:04d}";

        function verificarInteresseAgendamento() {{
            var tipoAgend = document.getElementById('tipo_agendamento').value;
            var boxHorario = document.getElementById('box_horario');
            var txtBtnZap = document.getElementById('txt_btn_zap');

            if (tipoAgend === "Não tenho interesse no momento") {{
                boxHorario.classList.add('opacity-40', 'pointer-events-none');
                txtBtnZap.innerText = "📲 Enviar simulação para o WhatsApp da loja";
            }} else {{
                boxHorario.classList.remove('opacity-40', 'pointer-events-none');
                txtBtnZap.innerText = "📲 Quero ser direcionado ao WhatsApp para agendar atendimento";
            }}
            atualizarMensagemZap();
        }}

        function calcularParcelasCliente() {{
            var forma = document.getElementById('forma_pagamento_cli').value;
            var boxEntrada = document.getElementById('box_entrada_cli');
            var boxParcelas = document.getElementById('box_parcelas_cli');
            var boxResultado = document.getElementById('box_resultado_parcelas');
            var entradaInput = document.getElementById('entrada_cli');

            if (forma.indexOf("PIX") !== -1) {{
                // Se for PIX à Vista com 5% de desconto
                boxEntrada.style.display = "none";
                boxParcelas.style.display = "none";
                boxResultado.innerHTML = `
                    <span class="text-slate-400 text-[11px] uppercase tracking-wider block">Condição Especial Selecionada:</span>
                    <p class="text-sm font-bold text-white">Pagamento Integral no PIX: <span class="text-emerald-400 font-black text-lg">R$ ` + valorComDesconto5.toLocaleString('pt-BR', {{ minimumFractionDigits: 2, maximumFractionDigits: 2 }}) + `</span></p>
                    <p class="text-[10px] text-emerald-300">Desconto de 5% aplicado com sucesso!</p>
                `;
            }} else {{
                boxEntrada.style.display = "block";
                boxParcelas.style.display = "block";
                
                var entrada = parseFloat(entradaInput.value) || 0;
                var nParc = parseInt(document.getElementById('parcelas_cli').value) || 1;

                if (entrada < entradaMinimaPermitida) {{
                    entrada = entradaMinimaPermitida;
                    entradaInput.value = entradaMinimaPermitida.toFixed(2);
                }}

                var saldo = Math.max(valorTotalOriginal - entrada, 0);
                var valorParc = nParc > 0 ? (saldo / nParc) : 0;

                boxResultado.innerHTML = `
                    <span class="text-slate-400 text-[11px] uppercase tracking-wider block">Seu Plano Simulado:</span>
                    <p class="text-sm font-bold text-white">
                        Entrada de <span id="res_entrada" class="text-amber-400">R$ ` + entrada.toLocaleString('pt-BR', {{ minimumFractionDigits: 2, maximumFractionDigits: 2 }}) + `</span> + 
                        <span id="res_num_parc">` + nParc + `</span>x de <span id="res_valor_parc" class="text-emerald-400 font-black text-base">R$ ` + valorParc.toLocaleString('pt-BR', {{ minimumFractionDigits: 2, maximumFractionDigits: 2 }}) + `</span>
                    </p>
                    <p class="text-[10px] text-slate-500">Saldo a parcelar: R$ ` + saldo.toLocaleString('pt-BR', {{ minimumFractionDigits: 2, maximumFractionDigits: 2 }}) + `</p>
                `;
            }}

            atualizarMensagemZap();
        }}

        function atualizarMensagemZap() {{
            var tipoAgend = document.getElementById('tipo_agendamento').value;
            var prefHorario = document.getElementById('preferencia_horario').value;
            var forma = document.getElementById('forma_pagamento_cli').value;
            var entrada = parseFloat(document.getElementById('entrada_cli').value) || entradaMinimaPermitida;
            var nParc = document.getElementById('parcelas_cli').value;

            var agendamentoTexto = "";
            if (tipoAgend === "Não tenho interesse no momento") {{
                agendamentoTexto = "📅 *AGENDAMENTO:* Cliente prefere avaliar a proposta antes de agendar.";
            }} else {{
                agendamentoTexto = "📅 *AGENDAMENTO NA LOJA:*\n• Preferência: *Agendamento Presencial na Loja*\n• Horário: *" + prefHorario + "*";
            }}

            var financeiroTexto = "";
            if (forma.indexOf("PIX") !== -1) {{
                financeiroTexto = "💳 *FORMA DE PAGAMENTO:* PIX à Vista com 5% de Desconto\n• Valor Final c/ Desconto: *R$ " + valorComDesconto5.toLocaleString('pt-BR', {{ minimumFractionDigits: 2 }}) + "*";
            }} else {{
                var saldo = Math.max(valorTotalOriginal - entrada, 0);
                var valorParc = (saldo / nParc).toLocaleString('pt-BR', {{ minimumFractionDigits: 2, maximumFractionDigits: 2 }});
                financeiroTexto = "💳 *SIMULAÇÃO DE PAGAMENTO:*\n• Forma: " + forma + "\n• Entrada (mín. 30%): R$ " + entrada.toLocaleString('pt-BR', {{ minimumFractionDigits: 2 }}) + "\n• Parcelamento: *" + nParc + "x de R$ " + valorParc + "*";
            }}

            var msg = "Olá! Meu nome é *" + nomeCliente + "*.\n" +
                      "Gerei meu pré-orçamento no site da *{empresa['nome_empresa']}* (Projeto #" + idOrc + ").\n\n" +
                      "📋 *DADOS DO PROJETO:*\n" +
                      "• Cidade: " + cidadeCliente + "\n" +
                      "• Metragem: " + areaCliente + " m²\n" +
                      "• Valor de Tabela: *R$ " + valorTotalOriginal.toLocaleString('pt-BR', {{ minimumFractionDigits: 2 }}) + "*\n\n" +
                      financeiroTexto + "\n\n" +
                      agendamentoTexto + "\n\n" +
                      "Gostaria de dar andamento no meu atendimento!";

            var zapUrl = "https://api.whatsapp.com/send?phone=55" + telEmpresa + "&text=" + encodeURIComponent(msg);
            document.getElementById('btn_whatsapp_agendar').href = zapUrl;
        }}

        window.onload = function() {{
            calcularParcelasCliente();
        }};
    </script>
</body>
</html>"""

def render_minuta_contrato(orc, empresa):
    pv_total = float(orc['preco_venda'] or 0) + float(orc['adendo_valor'] or 0)
    adendo_bloco = f"""
    <div class="p-4 bg-amber-950/40 border border-amber-500/40 rounded-xl space-y-1 my-3">
        <span class="text-amber-400 font-bold block">➕ TERMO ADITIVO / COMPLEMENTO INTEGRANTE:</span>
        <p>{orc['adendo_descricao']}</p>
        <p class="font-bold text-white">Valor Adicional do Adendo: R$ {float(orc['adendo_valor'] or 0):,.2f}</p>
    </div>
    """ if float(orc['adendo_valor'] or 0) > 0 else ""

    link_assinar = f"/assinar/{orc['id']}"

    return f"""<!DOCTYPE html>
<html lang="pt-br">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Minuta de Contrato #{orc['id']:04d} - {empresa['nome_empresa']}</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-slate-950 text-slate-100 min-h-screen p-4 sm:p-8 font-sans">
    <div class="max-w-4xl mx-auto bg-slate-900 border border-slate-800 rounded-3xl p-6 sm:p-10 shadow-2xl space-y-6">
        <div class="flex flex-wrap justify-between items-center border-b border-slate-800 pb-4 gap-2">
            <div>
                <h1 class="text-lg sm:text-xl font-bold text-white">INSTRUMENTO PARTICULAR DE PRESTAÇÃO DE SERVIÇOS E FABRICAÇÃO DE MÓVEIS PLANEJADOS</h1>
                <p class="text-xs text-amber-400">{empresa['nome_empresa']} | CNPJ: {empresa['cnpj']}</p>
            </div>
            <div class="flex gap-2">
                <button onclick="window.print()" class="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 rounded-xl text-xs font-bold">🖨️ Imprimir / PDF</button>
                <a href="{link_assinar}" class="px-4 py-1.5 bg-gradient-to-r from-amber-500 to-amber-600 text-slate-950 font-bold rounded-xl text-xs shadow-lg">✍️ Ir para Assinatura</a>
            </div>
        </div>

        <div class="bg-slate-950 p-6 rounded-2xl border border-slate-800 text-xs space-y-4 leading-relaxed text-slate-300">
            <p><b>CLÁUSULA 1ª - DAS PARTES CONTRATANTES:</b><br>
            <b>CONTRATADA:</b> {empresa['nome_empresa']}, pessoa jurídica de direito privado, inscrita no CNPJ sob o nº {empresa['cnpj']}, com atendimento através do telefone {empresa['telefone']}.<br>
            <b>CONTRATANTE:</b> <b>{orc['cliente_nome']}</b>, portador do CPF nº <b>{orc['cliente_cpf'] or 'Pendente'}</b>, RG nº <b>{orc['cliente_rg']} ({orc['cliente_rg_emissor'] or 'SSP'})</b>, nascido em <b>{orc['cliente_nascimento'] or '—'}</b>, residente no endereço postal: <b>{orc['cliente_endereco_postal'] or 'Não informado'} (CEP: {orc['cliente_cep_postal'] or '—'})</b>, com telefone <b>{orc['cliente_telefone']}</b> e e-mail <b>{orc['cliente_email'] or 'Não informado'}</b>.</p>

            <p><b>CLÁUSULA 2ª - DO OBJETO:</b><br>
            O presente instrumento tem por objeto a prestação de serviços de marcenaria técnica sob medida para fabricação, transporte e montagem dos móveis planejados destinados aos ambientes: <b>{orc['cliente_ambiente']}</b>, no endereço de entrega da obra: <b>{orc['cliente_endereco_entrega'] or orc['cliente_endereco_postal']} (CEP: {orc['cliente_cep_entrega'] or orc['cliente_cep_postal']})</b>.</p>

            <p><b>CLÁUSULA 3ª - DO MEMORIAL DESCRITIVO E ESPECIFICAÇÕES TÉCNICAS:</b><br>
            <b>3.1. Descritivo Promob / Projeto Técnico:</b><br>
            {orc['descricao_promob'] or 'Conforme projeto executivo 3D aprovado pelo cliente.'}<br><br>
            <b>3.2. Detalhamento e Acabamentos Manuais:</b><br>
            {orc['descricao_manual'] or 'Caixaria reforçada, portas com alinhamento milimétrico, ferragens com amortecimento slowmotion e tamponamentos inclusos.'}</p>

            {adendo_bloco}

            <p><b>CLÁUSULA 4ª - DO PREÇO E DAS CONDIÇÕES DE PAGAMENTO:</b><br>
            Pelos serviços contratados, o CONTRATANTE pagará à CONTRATADA o valor líquido total de <b>R$ {pv_total:,.2f}</b>, nas seguintes condições:<br>
            • <b>Modalidade:</b> {orc['modalidade_pagamento'] or orc['forma_pagamento']}<br>
            • <b>Valor de Entrada:</b> R$ {float(orc['entrada_valor'] or 0):,.2f}<br>
            • <b>Saldo Restante:</b> Parcelado em <b>{orc['num_parcelas']} parcela(s)</b> de <b>R$ {float(orc['valor_parcela'] or (pv_total - float(orc['entrada_valor'] or 0))/max(orc['num_parcelas'], 1)):,.2f}</b>.</p>

            <p><b>CLÁUSULA 5ª - DOS PRAZOS DE FABRICAÇÃO E INSTALAÇÃO:</b><br>
            O prazo estimado para entrega e finalização da montagem é de <b>{orc['prazo_entrega']}</b>, contados a partir da aprovação final das medidas no local (medição fina desimpedida) e confirmação do pagamento da entrada.</p>

            <p><b>CLÁUSULA 6ª - DAS OBRIGAÇÕES DO CONTRATANTE:</b><br>
            O CONTRATANTE compromete-se a entregar o imóvel em condições adequadas de alvenaria, pisos, revestimentos, pontos de elétrica, gás e hidráulica finalizados antes do início da montagem dos móveis.</p>

            <p><b>CLÁUSULA 7ª - DAS OBRIGAÇÕES DA CONTRATADA:</b><br>
            A CONTRATADA compromete-se a utilizar mão de obra especializada, materiais de alta qualidade certificados e entregar os ambientes limpos e regulados após a conclusão da montagem.</p>

            <p><b>CLÁUSULA 8ª - DA GARANTIA LEGAL E CONTRATUAL:</b><br>
            A CONTRATADA oferece a garantia de <b>5 (cinco) anos</b> para todas as ferragens estruturais, corrediças e dobradiças com amortecedor, e <b>12 (doze) meses</b> para os painéis de MDF contra defeitos de fabricação.</p>

            <p><b>CLÁUSULA 9ª - DO FORO:</b><br>
            Para dirimir quaisquer controvérsias oriundas deste contrato, as partes elegem o foro da Comarca da sede da CONTRATADA com renúncia expressa a qualquer outro.</p>
        </div>

        <div class="flex justify-between items-center pt-2">
            <a href="/painel-get" class="px-4 py-2 bg-slate-800 text-slate-300 rounded-xl text-xs font-bold">Voltar ao Painel</a>
            <a href="{link_assinar}" class="px-6 py-3 bg-gradient-to-r from-amber-500 to-amber-600 text-slate-950 font-bold rounded-xl text-xs shadow-lg">
                ✍️ Prosseguir para Assinatura Digital do Cliente
            </a>
        </div>
    </div>
</body></html>"""

def render_assinatura_online(orc, empresa):
    pv_total = float(orc['preco_venda'] or 0) + float(orc['adendo_valor'] or 0)
    
    adendo_bloco = f"""
    <div class="p-4 bg-amber-950/40 border border-amber-500/40 rounded-xl space-y-1 my-2">
        <span class="text-amber-400 font-bold block">➕ TERMO ADITIVO CONTRATUAL:</span>
        <p>{orc['adendo_descricao']}</p>
        <p class="font-bold text-white">Valor do Adendo: R$ {float(orc['adendo_valor'] or 0):,.2f}</p>
    </div>
    """ if float(orc['adendo_valor'] or 0) > 0 else ""

    if orc["contrato_assinado"]:
        return f"""<!DOCTYPE html>
<html lang="pt-br">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Via Oficial Assinada - Contrato #{orc['id']:04d}</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-slate-950 text-slate-100 min-h-screen p-4 sm:p-8 font-sans">
    <div class="max-w-4xl mx-auto bg-slate-900 border border-emerald-500/40 rounded-3xl p-6 sm:p-10 shadow-2xl space-y-6">
        <div class="flex flex-wrap justify-between items-center border-b border-slate-800 pb-4 gap-2">
            <div>
                <span class="px-3 py-1 bg-emerald-950 text-emerald-300 border border-emerald-500/40 rounded-xl text-xs font-bold">✓ Contrato Assinado Digitalmente</span>
                <h1 class="text-lg sm:text-xl font-bold text-white mt-1">VIA OFICIAL DO CONTRATO DE PRESTAÇÃO DE SERVIÇOS #{orc['id']:04d}</h1>
                <p class="text-xs text-slate-400">{empresa['nome_empresa']} | CNPJ: {empresa['cnpj']}</p>
            </div>
            <button onclick="window.print()" class="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-slate-950 font-bold rounded-xl text-xs shadow-lg">
                📥 Imprimir / Salvar PDF
            </button>
        </div>

        <div class="bg-slate-950 p-6 rounded-2xl border border-slate-800 text-xs space-y-4 leading-relaxed text-slate-300">
            <p><b>CONTRATADA:</b> {empresa['nome_empresa']} (CNPJ: {empresa['cnpj']})<br>
            <b>CONTRATANTE:</b> <b>{orc['cliente_nome']}</b> (CPF: {orc['cliente_cpf'] or 'Pendente'})<br>
            <b>AMBIENTES:</b> {orc['cliente_ambiente']}<br>
            <b>ENDEREÇO DA INSTALAÇÃO:</b> {orc['cliente_endereco_entrega'] or orc['cliente_endereco_postal']}<br>
            <b>VALOR TOTAL:</b> R$ {pv_total:,.2f} ({orc['forma_pagamento']})<br>
            <b>PRAZO DE MONTAGEM:</b> {orc['prazo_entrega']}<br>
            <b>GARANTIA:</b> 5 anos em ferragens estruturais e 12 meses em painéis de MDF.</p>
            
            {adendo_bloco}
        </div>

        <div class="bg-slate-950 p-6 rounded-2xl border border-emerald-500/30 space-y-3">
            <h3 class="text-xs font-bold text-emerald-400 uppercase">🛡️ Autenticação & Assinatura Digital do Contratante</h3>
            <p class="text-[11px] text-slate-400">Assinado digitalmente por <b>{orc['cliente_nome']}</b> em <b>{orc['assinatura_data']}</b>.</p>
            
            <div class="p-3 bg-white rounded-xl flex justify-center max-w-sm">
                <img src="{orc['assinatura_img']}" alt="Assinatura do Cliente" class="max-h-24 object-contain">
            </div>
            <p class="text-[10px] text-slate-500">Protocolo de Registro MVI: SHA256-MVI-{orc['id']:04d}-{orc['assinatura_data']}</p>
        </div>

        <div class="flex justify-between items-center pt-2">
            <a href="/painel-get" class="px-4 py-2 bg-slate-800 text-slate-300 rounded-xl text-xs font-bold">Voltar ao Painel</a>
            <span class="text-xs text-emerald-400 font-bold">✓ 1 Via Arquivada no Sistema & 1 Via Disponível ao Cliente</span>
        </div>
    </div>
</body></html>"""

    return f"""<!DOCTYPE html>
<html lang="pt-br">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Assinatura Digital de Contrato - {empresa['nome_empresa']}</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdn.jsdelivr.net/npm/signature_pad@4.1.7/dist/signature_pad.umd.min.js"></script>
</head>
<body class="bg-slate-950 text-slate-100 min-h-screen p-4 sm:p-8 font-sans">
    <div class="max-w-4xl mx-auto bg-slate-900 border border-slate-800 rounded-3xl p-6 sm:p-10 shadow-2xl space-y-6">
        <div class="flex justify-between items-center border-b border-slate-800 pb-4">
            <div>
                <h1 class="text-lg sm:text-xl font-bold text-white">INSTRUMENTO DE PRESTAÇÃO DE SERVIÇOS DE MARCENARIA</h1>
                <p class="text-xs text-amber-400">{empresa['nome_empresa']} | CNPJ: {empresa['cnpj']}</p>
            </div>
            <span class="px-3 py-1 bg-amber-950 text-amber-300 border border-amber-500/40 rounded-xl text-xs font-bold">Contrato #{orc['id']:04d}</span>
        </div>

        <div class="bg-slate-950 p-6 rounded-2xl border border-slate-800 text-xs space-y-4 leading-relaxed text-slate-300 max-h-80 overflow-y-auto">
            <p><b>1. DAS PARTES CONTRATANTES:</b><br>
            <b>CONTRATADA:</b> {empresa['nome_empresa']}, CNPJ: {empresa['cnpj']}, Telefone: {empresa['telefone']}.<br>
            <b>CONTRATANTE:</b> <b>{orc['cliente_nome']}</b>, CPF: <b>{orc['cliente_cpf'] or 'Pendente'}</b>, Endereço: <b>{orc['cliente_endereco_postal'] or 'Não informado'}</b>.</p>

            <p><b>2. DO OBJETO E AMBIENTES:</b><br>
            Fabricação e instalação de móveis sob medida para: <b>{orc['cliente_ambiente']}</b>, na obra: <b>{orc['cliente_endereco_entrega'] or orc['cliente_endereco_postal']}</b>.</p>

            <p><b>3. DO VALOR E CONDIÇÕES:</b><br>
            Valor total de <b>R$ {pv_total:,.2f}</b>, sob as condições: <b>{orc['forma_pagamento']}</b>.</p>

            <p><b>4. DO PRAZO E GARANTIA:</b><br>
            Prazo de entrega de <b>{orc['prazo_entrega']}</b>. Garantia de 5 anos em ferragens com amortecedores e 12 meses em painéis de MDF.</p>
            
            {adendo_bloco}
        </div>

        <div class="bg-slate-950 p-6 rounded-2xl border border-slate-800 space-y-3">
            <h3 class="text-xs font-bold text-white uppercase">✍️ Assinatura Digital do Contratante</h3>
            <p class="text-[11px] text-slate-400">Desenhe sua assinatura com o dedo ou caneta touch no celular:</p>
            
            <div class="border-2 border-dashed border-slate-700 rounded-xl bg-white flex justify-center">
                <canvas id="signature-pad" width="600" height="200" class="touch-none cursor-crosshair w-full max-w-[600px] h-[200px]"></canvas>
            </div>
            
            <div class="flex justify-between items-center pt-2">
                <button type="button" id="clear-btn" class="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-xl text-xs font-bold">Limpar</button>
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
        document.getElementById('clear-btn').addEventListener('click', () => signaturePad.clear());
        document.getElementById('save-btn').addEventListener('click', () => {{
            if (signaturePad.isEmpty()) {{
                alert("Por favor, faça sua assinatura antes de confirmar.");
            }} else {{
                document.getElementById('assinatura_base64').value = signaturePad.toDataURL();
                document.getElementById('sign-form').submit();
            }}
        }});
    </script>
</body></html>"""

def render_convite_gerado(nome, email, p, tel, link):
    return f"""<html><body style='background:#0f172a; color:#fff; text-align:center; padding:50px; font-family:sans-serif;'>
        <h1 style='color:#f59e0b;'>Convite de Acesso Gerado</h1>
        <p style='margin:20px 0;'>Link Seguro: <br><b style='color:#38bdf8;'>{link}</b></p>
        <a href='/painel' style='color:#f59e0b;'>Voltar ao Painel</a>
    </body></html>"""

def render_tela_nova_senha(user, token):
    return f"""<!DOCTYPE html>
<html lang="pt-br">
<head><title>Nova Senha</title><script src="https://cdn.tailwindcss.com"></script></head>
<body class="bg-slate-950 text-slate-100 flex items-center justify-center min-h-screen p-4">
    <form action="/salvar-nova-senha" method="post" class="bg-slate-900 p-8 rounded-3xl space-y-4 max-w-sm w-full shadow-2xl">
        <h1 class="text-xl font-bold">Definir Nova Senha</h1>
        <input type="hidden" name="token" value="{token}">
        <input type="password" name="nova_senha" required placeholder="Nova Senha" class="w-full px-4 py-3 bg-slate-950 border border-slate-700 rounded-xl text-white">
        <input type="password" name="confirma_senha" required placeholder="Confirme Senha" class="w-full px-4 py-3 bg-slate-950 border border-slate-700 rounded-xl text-white">
        <button type="submit" class="w-full py-3 bg-amber-500 font-bold text-slate-950 rounded-xl">Ativar Conta</button>
    </form>
</body></html>"""

# ==============================================================================
# 6. FASTAPI ROUTES
# ==============================================================================

@app.get("/", response_class=HTMLResponse)
@app.get("/login", response_class=HTMLResponse)
def root_route():
    return render_login()

@app.post("/painel", response_class=HTMLResponse)
def login_route(username: str = Form(...), password: str = Form(...)):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM usuarios WHERE email = ? AND senha = ?", (username, password))
    user = cursor.fetchone()
    conn.close()

    if not user:
        return render_login("E-mail ou senha incorretos. Tente novamente.")

    if "ativo" in user.keys() and not user["ativo"]:
        return render_login("❌ Este usuário foi desativado pela administração da marcenaria.")

    CURRENT_SESSION["user_email"] = user["email"]
    CURRENT_SESSION["user_nome"] = user["nome"]
    CURRENT_SESSION["user_perfil"] = user["perfil"]
    CURRENT_SESSION["empresa_id"] = user["empresa_id"]

    return render_dashboard_view()

@app.get("/painel", response_class=HTMLResponse)
@app.get("/painel-get", response_class=HTMLResponse)
def painel_get_route():
    return render_dashboard_view()

@app.get("/minuta-contrato/{orcamento_id}", response_class=HTMLResponse)
def minuta_contrato_route(orcamento_id: int):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM orcamentos WHERE id = ?", (orcamento_id,))
    orc = cursor.fetchone()
    conn.close()

    if not orc:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM orcamentos ORDER BY id DESC LIMIT 1")
        orc = cursor.fetchone()
        conn.close()

    if not orc:
        return HTMLResponse("Nenhum orçamento cadastrado para gerar minuta.", status_code=404)

    empresa = get_empresa_dados(1)
    return render_minuta_contrato(dict(orc), empresa)

@app.post("/selecionar-cliente-trabalho", response_class=HTMLResponse)
def selecionar_cliente_trabalho(orcamento_id: int = Form(...)):
    CURRENT_SESSION["cliente_ativo_id"] = orcamento_id
    return RedirectResponse(url="/painel-get", status_code=303)

@app.post("/salvar-negociacao-mesa", response_class=HTMLResponse)
def salvar_negociacao_mesa(
    orcamento_id: int = Form(...),
    preco_bruto: float = Form(0.0),
    desconto_pct: float = Form(0.0),
    preco_venda: float = Form(0.0),
    markup: float = Form(2.2),
    modalidade_pagamento: str = Form("Cartão de Crédito em até 12x"),
    entrada_valor: float = Form(0.0),
    num_parcelas: int = Form(1)
):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("SELECT custo_materiais, custo_mao_obra, custo_frete_montagem FROM orcamentos WHERE id = ?", (orcamento_id,))
    orc = cursor.fetchone()
    
    custo_tot = (float(orc["custo_materiais"] or 0) + float(orc["custo_mao_obra"] or 0) + float(orc["custo_frete_montagem"] or 0)) if orc else (preco_bruto / markup if markup > 0 else preco_bruto * 0.5)
    lucro_final = preco_venda - (custo_tot + (preco_venda * 0.10))
    
    saldo = max(preco_venda - entrada_valor, 0.0)
    v_parc = saldo / num_parcelas if num_parcelas > 0 else 0.0

    precisa_aprov = (desconto_pct > 3.0 and CURRENT_SESSION["user_perfil"] == "vendedor")
    desconto_autorizado = 0 if precisa_aprov else 1
    status = "Aguardando Liberação de Desconto" if precisa_aprov else "Negociação Salva / Aguardando Fechamento"

    cursor.execute("""
        UPDATE orcamentos SET
            preco_bruto = ?,
            desconto_pct = ?,
            preco_venda = ?,
            markup = ?,
            modalidade_pagamento = ?,
            entrada_valor = ?,
            num_parcelas = ?,
            valor_parcela = ?,
            lucro_liquido = ?,
            desconto_autorizado = ?,
            status = ?
        WHERE id = ?
    """, (preco_bruto, desconto_pct, preco_venda, markup, modalidade_pagamento, entrada_valor, num_parcelas, v_parc, lucro_final, desconto_autorizado, status, orcamento_id))
    conn.commit()
    conn.close()
    return RedirectResponse(url="/painel-get", status_code=303)

@app.get("/solicitar-orcamento", response_class=HTMLResponse)
@app.get("/solicitar-orcamento/{slug}", response_class=HTMLResponse)
def captacao_route(slug: str = "mvi"):
    empresa = get_empresa_dados(1)
    return render_form_captacao(empresa)

@app.post("/importar-promob", response_class=HTMLResponse)
async def importar_promob_route(
    cliente_nome: str = Form(""),
    cliente_telefone: str = Form(""),
    cliente_ambiente: str = Form(""),
    arquivo_promob: UploadFile = File(...)
):
    conteudo_bytes = await arquivo_promob.read()
    try:
        conteudo_texto = conteudo_bytes.decode("utf-8")
    except UnicodeDecodeError:
        conteudo_texto = conteudo_bytes.decode("latin-1", errors="ignore")
    
    calc = processar_arquivo_promob(conteudo_texto, arquivo_promob.filename)
    agora = datetime.now().strftime("%d/%m/%Y %H:%M")
    
    desc_auto = f"Projeto Promob importado ({arquivo_promob.filename}). {len(calc['items'])} componentes detectados."

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO orcamentos (
            empresa_id, criado_em, cliente_nome, cliente_telefone, cliente_ambiente,
            prazo_entrega, data_entrega_prevista, status, custo_materiais,
            preco_bruto, preco_venda, lucro_liquido, descricao_manual
        ) VALUES (1, ?, ?, ?, ?, '30 dias úteis', ?, 'Importado Promob', ?, ?, ?, ?, ?)
    """, (agora, cliente_nome, cliente_telefone, cliente_ambiente, (date.today() + timedelta(days=30)).strftime("%Y-%m-%d"), calc["total_mat"], calc["preco_bruto"], calc["preco_venda"], calc["lucro"], desc_auto))
    conn.commit()
    CURRENT_SESSION["cliente_ativo_id"] = cursor.lastrowid
    conn.close()

    return RedirectResponse(url="/painel-get", status_code=303)

@app.post("/enviar-solicitacao-lead", response_class=HTMLResponse)
async def submit_lead_route(
    nome: str = Form(...),
    whatsapp: str = Form(...),
    area_m2_total: float = Form(180.0),
    espessura_caixa: str = Form("MDF 18mm (Reforçado)"),
    cor_caixa: str = Form("Branco TX"),
    espessura_porta: str = Form("MDF 18mm"),
    cor_porta: str = Form("Amadeirado"),
    acabamento_porta: str = Form("Madeira Lisa Tradicional"),
    marca_ferragens: str = Form("Blum (Linha Blumotion Áustria)"),
    espessura_tamponamento: str = Form("Tamponamento 25mm"),
    cidade: str = Form(...),
    descricao: str = Form(""),
    planta: UploadFile = File(...),
    inspiracao: UploadFile = File(None)
):
    empresa = get_empresa_dados(1)
    calc = calcular_engenharia(
        ["Cozinha c/ Ilha", "Suíte Master c/ Closet"], area_m2_total,
        espessura_caixa, cor_caixa, espessura_porta, cor_porta, acabamento_porta,
        espessura_tamponamento, marca_ferragens
    )

    agora = datetime.now().strftime("%d/%m/%Y %H:%M")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO orcamentos (
            empresa_id, criado_em, cliente_nome, cliente_telefone, cliente_ambiente,
            prazo_entrega, data_entrega_prevista, status, custo_materiais,
            custo_mao_obra, custo_frete_montagem, preco_bruto, preco_venda, lucro_liquido,
            observacoes_tecnicas, descricao_promob
        ) VALUES (1, ?, ?, ?, 'Cozinha + Suíte', '30 dias úteis', ?, 'Novo Lead Instagram', ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        agora, nome, whatsapp, (date.today() + timedelta(days=30)).strftime("%Y-%m-%d"),
        calc["total_mat"], calc["custo_mo"], calc["custo_frete"], calc["preco_bruto"], calc["preco_venda"], calc["lucro"],
        descricao, calc["desc_promob"]
    ))
    conn.commit()
    novo_id = cursor.lastrowid
    CURRENT_SESSION["cliente_ativo_id"] = novo_id
    conn.close()

    return render_pre_orcamento_agendamento(
        empresa, novo_id, nome, whatsapp, cidade, area_m2_total,
        calc["preco_venda"], espessura_caixa, cor_caixa,
        espessura_porta, cor_porta, acabamento_porta, marca_ferragens, espessura_tamponamento
    )

@app.post("/salvar-dados-completos-cliente", response_class=HTMLResponse)
def salvar_dados_completos_cliente_route(
    orcamento_id: int = Form(0),
    cliente_nome: str = Form(""),
    cliente_cpf: str = Form(""),
    cliente_rg: str = Form(""),
    cliente_rg_emissor: str = Form(""),
    cliente_nascimento: str = Form(""),
    cliente_pais: str = Form("Brasil"),
    cliente_cidade: str = Form(""),
    cliente_email: str = Form(""),
    cliente_telefone: str = Form(""),
    cliente_telefone_2: str = Form(""),
    cliente_cep_postal: str = Form(""),
    cliente_endereco_postal: str = Form(""),
    cliente_cep_entrega: str = Form(""),
    cliente_endereco_entrega: str = Form(""),
    descricao_manual: str = Form(""),
    desconto_pct: float = Form(0.0),
    forma_pagamento: str = Form("Cartão de Crédito até 12x"),
    entrada_valor: float = Form(0.0),
    num_parcelas: int = Form(1)
):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    if orcamento_id == 0:
        agora = datetime.now().strftime("%d/%m/%Y %H:%M")
        pv_base = entrada_valor * 2.5 if entrada_valor > 0 else 15000.0
        pv_final = pv_base * (1.0 - (desconto_pct / 100.0))
        lucro_final = pv_final * 0.40

        cursor.execute("""
            INSERT INTO orcamentos (
                empresa_id, criado_em, cliente_nome, cliente_cpf, cliente_rg, cliente_rg_emissor,
                cliente_nascimento, cliente_pais, cliente_cidade, cliente_email,
                cliente_telefone, cliente_telefone_2, cliente_cep_postal, cliente_endereco_postal,
                cliente_cep_entrega, cliente_endereco_entrega, cliente_ambiente, descricao_manual, desconto_pct,
                desconto_autorizado, status, preco_bruto, preco_venda, lucro_liquido, forma_pagamento, entrada_valor,
                num_parcelas, prazo_entrega, data_entrega_prevista
            ) VALUES (
                1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Projeto Sob Medida', ?, ?, 1, 'Contrato Pronto para Assinatura',
                ?, ?, ?, ?, ?, ?, '30 dias úteis', ?
            )
        """, (
            agora, cliente_nome, cliente_cpf, cliente_rg, cliente_rg_emissor,
            cliente_nascimento, cliente_pais, cliente_cidade, cliente_email,
            cliente_telefone, cliente_telefone_2, cliente_cep_postal, cliente_endereco_postal,
            cliente_cep_entrega, cliente_endereco_entrega, descricao_manual, desconto_pct,
            pv_base, pv_final, lucro_final, forma_pagamento, entrada_valor, num_parcelas,
            (date.today() + timedelta(days=30)).strftime("%Y-%m-%d")
        ))
        conn.commit()
        CURRENT_SESSION["cliente_ativo_id"] = cursor.lastrowid
    else:
        cursor.execute("SELECT preco_bruto, preco_venda, custo_materiais, custo_mao_obra, custo_frete_montagem FROM orcamentos WHERE id = ?", (orcamento_id,))
        orc = cursor.fetchone()
        if orc:
            pv_base = float(orc["preco_bruto"] or orc["preco_venda"] or 0)
            custo_tot = float(orc["custo_materiais"] or 0) + float(orc["custo_mao_obra"] or 0) + float(orc["custo_frete_montagem"] or 0)
            pv_final = pv_base * (1.0 - (desconto_pct / 100.0))
            lucro_final = pv_final - (custo_tot + (pv_final * 0.10))

            cursor.execute("""
                UPDATE orcamentos SET
                    cliente_nome = ?, cliente_cpf = ?, cliente_rg = ?, cliente_rg_emissor = ?,
                    cliente_nascimento = ?, cliente_pais = ?, cliente_cidade = ?, cliente_email = ?,
                    cliente_telefone = ?, cliente_telefone_2 = ?, cliente_cep_postal = ?, cliente_endereco_postal = ?,
                    cliente_cep_entrega = ?, cliente_endereco_entrega = ?, descricao_manual = ?, desconto_pct = ?,
                    status = 'Contrato Pronto para Assinatura', preco_venda = ?, lucro_liquido = ?,
                    forma_pagamento = ?, entrada_valor = ?, num_parcelas = ?
                WHERE id = ?
            """, (
                cliente_nome, cliente_cpf, cliente_rg, cliente_rg_emissor,
                cliente_nascimento, cliente_pais, cliente_cidade, cliente_email,
                cliente_telefone, cliente_telefone_2, cliente_cep_postal, cliente_endereco_postal,
                cliente_cep_entrega, cliente_endereco_entrega, descricao_manual, desconto_pct,
                pv_final, lucro_final, forma_pagamento, entrada_valor, num_parcelas, orcamento_id
            ))
            conn.commit()
            CURRENT_SESSION["cliente_ativo_id"] = orcamento_id
            
    conn.close()
    return RedirectResponse(url="/painel-get", status_code=303)

@app.post("/salvar-adendo", response_class=HTMLResponse)
def salvar_adendo_route(orcamento_id: int = Form(0), adendo_descricao: str = Form(""), adendo_valor: float = Form(0.0)):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE orcamentos SET adendo_descricao = ?, adendo_valor = ?, status = 'Adendo Adicionado' WHERE id = ?", (adendo_descricao, adendo_valor, orcamento_id))
    conn.commit()
    conn.close()
    return RedirectResponse(url="/painel-get", status_code=303)

@app.post("/autorizar-com-chave", response_class=HTMLResponse)
def autorizar_com_chave_route(orcamento_id: int = Form(...), chave_digitada: str = Form(...), tipo_acao: str = Form(...)):
    empresa = get_empresa_dados(1)
    if chave_digitada.strip() != empresa.get("chave_mestra", "MVI2026"):
        return HTMLResponse("<script>alert('Chave Incorreta!'); history.back();</script>", status_code=403)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    if tipo_acao == "desconto":
        cursor.execute("UPDATE orcamentos SET desconto_autorizado = 1, status = 'Desconto Autorizado pela Diretoria' WHERE id = ?", (orcamento_id,))
    elif tipo_acao == "financeiro":
        cursor.execute("UPDATE orcamentos SET liberado_financeiro = 1, status = 'Liberado para Financeiro & Fábrica' WHERE id = ?", (orcamento_id,))
    conn.commit()
    conn.close()
    return RedirectResponse(url="/painel-get", status_code=303)

@app.get("/assinar/{orcamento_id}", response_class=HTMLResponse)
def assinar_contrato_view(orcamento_id: int):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM orcamentos WHERE id = ?", (orcamento_id,))
    orc = cursor.fetchone()
    conn.close()
    
    if not orc:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM orcamentos ORDER BY id DESC LIMIT 1")
        orc = cursor.fetchone()
        conn.close()

    if not orc:
        return HTMLResponse("Contrato não encontrado.", status_code=404)
        
    return render_assinatura_online(dict(orc), get_empresa_dados(1))

@app.post("/confirmar-assinatura", response_class=HTMLResponse)
def confirmar_assinatura_route(orcamento_id: int = Form(...), assinatura_base64: str = Form(...)):
    agora = datetime.now().strftime("%d/%m/%Y às %H:%M")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE orcamentos SET contrato_assinado = 1, assinatura_data = ?, assinatura_img = ?, status = 'Contrato Assinado Digitalmente' WHERE id = ?", (agora, assinatura_base64, orcamento_id))
    conn.commit()
    conn.close()
    return RedirectResponse(url=f"/assinar/{orcamento_id}", status_code=303)

@app.post("/criar-usuario", response_class=HTMLResponse)
def criar_usuario_route(request: Request, nome: str = Form(...), email: str = Form(...), perfil: str = Form("vendedor"), telefone: str = Form("")):
    token = secrets.token_urlsafe(16)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO usuarios (email, senha, nome, perfil, empresa_id, token_primeiro_acesso, primeiro_acesso_concluido, ativo) VALUES (?, '', ?, ?, 1, ?, 0, 1)", (email.strip().lower(), nome, perfil, token))
    conn.commit()
    conn.close()
    return render_convite_gerado(nome, email, perfil, telefone, f"{str(request.base_url).rstrip('/')}/primeiro-acesso/{token}")

@app.get("/primeiro-acesso/{token}", response_class=HTMLResponse)
def tela_primeiro_acesso(token: str):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM usuarios WHERE token_primeiro_acesso = ?", (token,))
    user = cursor.fetchone()
    conn.close()
    if not user: return HTMLResponse("Link inválido ou já utilizado.", status_code=404)
    return render_tela_nova_senha(user, token)

@app.post("/salvar-nova-senha", response_class=HTMLResponse)
def salvar_nova_senha(token: str = Form(...), nova_senha: str = Form(...), confirma_senha: str = Form(...)):
    if nova_senha != confirma_senha: return HTMLResponse("<script>alert('Senhas diferentes!'); history.back();</script>")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE usuarios SET senha = ?, token_primeiro_acesso = '', primeiro_acesso_concluido = 1, ativo = 1 WHERE token_primeiro_acesso = ?", (nova_senha, token))
    conn.commit()
    conn.close()
    return RedirectResponse(url="/", status_code=303)

@app.post("/redefinir-senha-funcionario", response_class=HTMLResponse)
def redefinir_senha_funcionario(request: Request, email_funcionario: str = Form(...)):
    if CURRENT_SESSION.get("user_perfil") != "admin":
        return RedirectResponse(url="/painel-get", status_code=303)
        
    token = secrets.token_urlsafe(16)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE usuarios SET token_primeiro_acesso = ?, primeiro_acesso_concluido = 0 WHERE email = ?", (token, email_funcionario))
    conn.commit()
    conn.close()
    return render_convite_gerado("Funcionário", email_funcionario, "Reset", "", f"{str(request.base_url).rstrip('/')}/primeiro-acesso/{token}")

@app.post("/alternar-status-funcionario", response_class=HTMLResponse)
def alternar_status_funcionario(email_funcionario: str = Form(...)):
    if CURRENT_SESSION.get("user_perfil") != "admin":
        return RedirectResponse(url="/painel-get", status_code=303)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT ativo FROM usuarios WHERE email = ?", (email_funcionario,))
    user = cursor.fetchone()
    if user:
        novo = 0 if user["ativo"] else 1
        cursor.execute("UPDATE usuarios SET ativo = ? WHERE email = ?", (novo, email_funcionario))
        conn.commit()
    conn.close()
    return RedirectResponse(url="/painel-get", status_code=303)

@app.post("/salvar-empresa", response_class=HTMLResponse)
def update_empresa(nome_empresa: str = Form(...), cnpj: str = Form(...), telefone: str = Form(...), pix: str = Form(""), chave_mestra: str = Form("MVI2026")):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE empresas SET nome_empresa = ?, cnpj = ?, telefone = ?, pix = ?, chave_mestra = ? WHERE id = 1", (nome_empresa, cnpj, telefone, pix, chave_mestra))
    conn.commit()
    conn.close()
    return RedirectResponse(url="/painel-get", status_code=303)

@app.get("/exportar-csv")
def export_csv():
    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')
    writer.writerow(["ID", "Data/Hora", "Cliente", "CPF", "Telefone", "Ambiente", "Preco Venda (R$)", "Status"])
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM orcamentos WHERE empresa_id = 1 ORDER BY id DESC")
    for r in cursor.fetchall():
        writer.writerow([r["id"], r["criado_em"], r["cliente_nome"], r["cliente_cpf"], r["cliente_telefone"], r["cliente_ambiente"], f"{float(r['preco_venda'] or 0):.2f}", r["status"]])
    conn.close()
    return Response(content=output.getvalue().encode('utf-8-sig'), media_type="text/csv", headers={"Content-Disposition": f"attachment; filename=relatorio-mvi.csv"})

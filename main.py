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
DB_PATH = "mvi_production_stable_v3.db"

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
        
        cursor.execute("INSERT OR REPLACE INTO usuarios VALUES ('admin@mvi.com', '123456', 'Administrador Geral MVI', 'admin', 1, '', 1, 1)")
        cursor.execute("INSERT OR REPLACE INTO usuarios VALUES ('vendedor@mvi.com', '123456', 'Vendedor MVI', 'vendedor', 1, '', 1, 1)")
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
    
    total = len(rows)
    fat_total, lucro_total, recebido, aprovados = 0.0, 0.0, 0.0, 0
    
    for r in rows:
        st = r["status"] or "Em Negociação"
        pv = float(r["preco_venda"] or 0) + float(r["adendo_valor"] or 0)
        lucro = float(r["lucro_liquido"] or 0)
        
        if st in ["Aprovado", "Em Produção", "Entregue", "Liberado para Financeiro & Fábrica", "Contrato Assinado Digitalmente"]:
            fat_total += pv
            lucro_total += lucro
            aprovados += 1

    taxa = (aprovados / total * 100.0) if total > 0 else 0.0
    ticket = (fat_total / aprovados) if aprovados > 0 else 0.0
    
    return {"total": total, "aprovados": aprovados, "faturamento": fat_total, "lucro": lucro_total, "ticket": ticket, "taxa": taxa}

# ==============================================================================
# 3. ENGENHARIA & PARSER UNIVERSAL PROMOB
# ==============================================================================
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

    dob_mult = 2.8 if "Blum" in marca_ferr else (2.5 if "Hettich" in marca_ferr else 1.0)
    corr_mult = 3.2 if "Blum" in marca_ferr else (2.9 if "Hettich" in marca_ferr else 1.0)

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
        items.append({
            "nome": f"Fita de Borda PVC ({fab_mdf})",
            "tipo": "Insumo", "ambiente": amb, "qtd": int(m_lin * 20),
            "valor": int(m_lin * 20) * fita_preco
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
    mdf_preco = float(precos.get("mdf_m2", 65.0))
    dob_preco = float(precos.get("dobradica", 18.50))
    corr_preco = float(precos.get("corredica", 38.00))

    ext = nome_arquivo.lower()
    
    # 1. Tentativa de Leitura XML (Promob Cut / Studio / Start / Plus)
    if ext.endswith(".xml") or "<" in conteudo_texto[:100]:
        try:
            root = ET.fromstring(conteudo_texto)
            for el in root.iter():
                tag = el.tag.lower()
                if tag in ["item", "peca", "piece", "component", "componente", "panel", "modulo", "entity", "itembudget"]:
                    nome = (el.attrib.get("DESCRIPTION") or el.attrib.get("NOME") or el.attrib.get("NAME") or el.attrib.get("DESCRICAO") or el.attrib.get("TEXT") or el.text or "Peça Promob").strip()
                    
                    larg = float(el.attrib.get("WIDTH") or el.attrib.get("LARGURA") or el.attrib.get("LARG") or el.attrib.get("DIMENSION_X") or 0)
                    alt = float(el.attrib.get("HEIGHT") or el.attrib.get("ALTURA") or el.attrib.get("ALT") or el.attrib.get("DIMENSION_Y") or 0)
                    qtd = int(float(el.attrib.get("QUANTITY") or el.attrib.get("QUANTIDADE") or el.attrib.get("QTD") or el.attrib.get("REPETITION") or 1))
                    
                    if larg > 0 and alt > 0:
                        area = (larg / 1000.0) * (alt / 1000.0)
                        items.append({
                            "nome": nome[:40],
                            "dimensoes": f"{int(larg)}x{int(alt)}mm",
                            "qtd": qtd,
                            "valor": area * mdf_preco * 1.35 * qtd
                        })
        except Exception:
            pass

    # 2. Leitura de CSV / TXT / Listagem Tabular do Promob
    if not items:
        linhas = conteudo_texto.splitlines()
        for l in linhas:
            # Substitui separadores comuns do Promob (; , \t |)
            limpa = l.replace(";", "\t").replace(",", "\t").replace("|", "\t")
            partes = [p.strip() for p in limpa.split("\t") if p.strip()]
            if len(partes) >= 3:
                try:
                    nome_p = partes[0]
                    # Tenta converter os dois próximos valores para medidas numéricas
                    d1 = float(partes[1].lower().replace("mm", "").replace("cm", "").replace(" ", ""))
                    d2 = float(partes[2].lower().replace("mm", "").replace("cm", "").replace(" ", ""))
                    q_p = int(partes[3]) if len(partes) >= 4 and partes[3].isdigit() else 1
                    
                    if d1 > 0 and d2 > 0:
                        area_m2 = (d1 / 1000.0) * (d2 / 1000.0)
                        items.append({
                            "nome": nome_p[:40],
                            "dimensoes": f"{int(d1)}x{int(d2)}mm",
                            "qtd": q_p,
                            "valor": area_m2 * mdf_preco * 1.35 * q_p
                        })
                except Exception:
                    continue

    # 3. Fallback inteligente caso o arquivo seja em formato de texto simplificado
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
    pv = (total_mat + custo_mo + custo_frete) * 2.2
    lucro = pv - (total_mat + custo_mo + custo_frete + (pv * 0.10))

    return {
        "items": items,
        "total_mat": total_mat,
        "custo_mo": custo_mo,
        "custo_frete": custo_frete,
        "preco_venda": pv,
        "lucro": lucro
    }

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
            acoes_admin += f"<span class='text-[10px] text-amber-400 font-bold'>Aguardando Admin ({desc:.1f}%)</span>"

        if not lib_fin and is_admin:
            acoes_admin += f"""<form action="/autorizar-com-chave" method="post" class="flex flex-col gap-1 my-1 p-2 bg-sky-950/60 border border-sky-500/40 rounded-xl"><span class='text-[10px] text-sky-300 font-bold'>💳 Liberar Financeiro</span><input type="hidden" name="orcamento_id" value="{h['id']}"><input type="hidden" name="tipo_acao" value="financeiro"><input type="password" name="chave_digitada" placeholder="Chave" required class="px-2 py-1 bg-slate-950 border border-slate-700 text-white rounded text-[10px]"><button type="submit" class="px-2 py-1 bg-sky-500 text-slate-950 rounded text-[10px] font-bold">Liberar</button></form>"""
        elif lib_fin:
            acoes_admin += "<span class='text-[10px] text-emerald-400 font-bold'>✓ Financeiro OK</span>"

        link_ass = f"/assinar/{h['id']}"
        status_ass = f"<span class='text-emerald-400 font-bold'>✓ Assinado</span><br><a href='{link_ass}' target='_blank' class='text-[10px] text-sky-400 underline'>Ver Via</a>" if h["contrato_assinado"] else f"<a href='{link_ass}' target='_blank' class='text-amber-400 underline font-bold'>✍️ Enviar p/ Assinar</a>"
        
        lucro_td = f"<td class='py-3 px-4 text-right text-emerald-400 font-bold'>R$ {lucro:,.2f}</td>" if is_admin else ""
        adendo_tag = f"<span class='block text-[10px] text-amber-400 font-bold'>+ Adendo R$ {adendo:,.2f}</span>" if adendo > 0 else ""

        leads_html += f"""<tr class="border-b border-slate-800 hover:bg-slate-800/40 text-xs">
            <td class="py-3 px-4 font-mono text-slate-400">#{h['id']}</td>
            <td class="py-3 px-4 text-white font-medium">{h['cliente_nome']}<span class="block text-[10px] text-slate-400">CPF: {h['cliente_cpf'] or 'Pendente'}</span></td>
            <td class="py-3 px-4 text-slate-300">{h['cliente_ambiente']}</td>
            <td class="py-3 px-4 text-right text-amber-400 font-bold">R$ {pv_total:,.2f}{adendo_tag}</td>
            {lucro_td}
            <td class="py-3 px-4 text-center">{acoes_admin if acoes_admin else st}</td>
            <td class="py-3 px-4 text-center">{status_ass}</td>
        </tr>"""

    if not leads_html:
        leads_html = "<tr><td colspan='8' class='py-8 text-center text-xs text-slate-500'>Nenhum projeto registrado ainda.</td></tr>"

    th_lucro = "<th class='py-3 px-4 text-right'>Lucro</th>" if is_admin else ""

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

    lucro_card = f"""<div class="bg-slate-900 border border-slate-800 p-5 rounded-2xl shadow"><p class="text-[11px] font-bold text-slate-400 uppercase">Lucro Líquido</p><p class="text-xl font-bold text-emerald-400">R$ {met['lucro']:,.2f}</p></div>""" if is_admin else ""

    # Seletor de Leads com opção de novo cadastro
    options_leads = "<option value='0'>➕ Cadastrar Novo Cliente / Orçamento Manual</option>"
    for h in leads:
        options_leads += f"<option value='{h['id']}'>#{h['id']} - {h['cliente_nome']} ({h['cliente_ambiente']})</option>"

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
        <div class="flex items-center gap-3"><a href="/solicitar-orcamento" target="_blank" class="text-xs bg-amber-950 text-amber-300 border border-amber-500/40 px-3 py-1.5 rounded-xl">🔗 Simulador Público</a><span class="text-xs text-slate-400">Logado: <b class="text-amber-400">{CURRENT_SESSION['user_nome']}</b></span><a href="/" class="text-xs bg-slate-800 hover:bg-slate-700 px-3 py-1.5 rounded-xl text-slate-300 border border-slate-700">Sair</a></div>
    </header>

    <nav class="bg-slate-900/80 border-b border-slate-800 px-6 py-3 sticky top-0 z-50 backdrop-blur-md">
        <div class="max-w-7xl mx-auto flex items-center gap-2 overflow-x-auto">
            <button onclick="mudarAba('aba-leads')" id="btn-aba-leads" class="tab-btn active px-4 py-2 rounded-xl text-xs font-bold border border-slate-700 text-slate-300">🏠 Fechamentos</button>
            <button onclick="mudarAba('aba-promob')" id="btn-aba-promob" class="tab-btn px-4 py-2 rounded-xl text-xs font-bold border border-slate-700 text-slate-300">🚀 Promob</button>
            <button onclick="mudarAba('aba-cadastro')" id="btn-aba-cadastro" class="tab-btn px-4 py-2 rounded-xl text-xs font-bold border border-slate-700 text-slate-300">📋 Ficha & CEP</button>
            <button onclick="mudarAba('aba-adendo')" id="btn-aba-adendo" class="tab-btn px-4 py-2 rounded-xl text-xs font-bold border border-slate-700 text-slate-300">➕ Adendo</button>
            {admin_tabs}
        </div>
    </nav>

    <main class="max-w-7xl mx-auto p-6 space-y-6">
        <div id="aba-leads" class="tab-content active space-y-6">
            <div class="grid grid-cols-2 lg:grid-cols-4 gap-4">
                <div class="bg-slate-900 border border-slate-800 p-5 rounded-2xl shadow"><p class="text-[11px] font-bold text-slate-400 uppercase">Faturamento</p><p class="text-xl font-bold text-amber-400">R$ {met['faturamento']:,.2f}</p></div>
                {lucro_card}
                <div class="bg-slate-900 border border-slate-800 p-5 rounded-2xl shadow"><p class="text-[11px] font-bold text-slate-400 uppercase">Projetos Fechados</p><p class="text-xl font-bold text-white">{met['aprovados']}</p></div>
                <div class="bg-slate-900 border border-slate-800 p-5 rounded-2xl shadow"><p class="text-[11px] font-bold text-slate-400 uppercase">Conversão</p><p class="text-xl font-bold text-amber-400">{met['taxa']:.1f}%</p></div>
            </div>

            <div class="bg-slate-900 border border-slate-800 rounded-3xl overflow-hidden shadow">
                <div class="p-4 border-b border-slate-800 flex justify-between"><h3 class="text-sm font-bold text-white">📁 Fila de Vendas e Liberações</h3><a href="/exportar-csv" class="px-3 py-1.5 bg-slate-800 text-slate-200 rounded-xl text-xs font-bold">📊 CSV</a></div>
                <div class="overflow-x-auto">
                    <table class="w-full text-left border-collapse">
                        <tr class="bg-slate-800/40 border-b border-slate-800 text-xs font-bold text-slate-400 uppercase">
                            <th class="py-3 px-4"># ID</th><th class="py-3 px-4">Cliente / CPF</th><th class="py-3 px-4">Ambiente</th><th class="py-3 px-4 text-right">Valor Venda</th>{th_lucro}<th class="py-3 px-4 text-center">Status</th><th class="py-3 px-4 text-center">Assinatura</th>
                        </tr>
                        {leads_html}
                    </table>
                </div>
            </div>
        </div>

        <div id="aba-promob" class="tab-content space-y-6">
            <div class="bg-slate-900 border border-slate-800 rounded-3xl p-6 shadow space-y-4">
                <h2 class="text-base font-bold text-white">🚀 Integrador Promob Universal (XML, CSV, TXT, Cut)</h2>
                <form action="/importar-promob" method="post" enctype="multipart/form-data" class="grid sm:grid-cols-3 gap-4 text-xs">
                    <input type="text" name="cliente_nome" required placeholder="Nome do Cliente" class="px-3 py-2.5 bg-slate-950 border border-slate-700 rounded-xl text-white">
                    <input type="text" name="cliente_telefone" required placeholder="WhatsApp" class="px-3 py-2.5 bg-slate-950 border border-slate-700 rounded-xl text-white">
                    <input type="text" name="cliente_ambiente" required placeholder="Ambientes" class="px-3 py-2.5 bg-slate-950 border border-slate-700 rounded-xl text-white">
                    <div class="sm:col-span-3 p-4 bg-slate-950 border border-slate-800 rounded-2xl">
                        <label class="block font-bold text-amber-400 mb-2">📁 Arquivo de Peças Exportado do Promob (.xml, .csv, .txt, .cut)</label>
                        <input type="file" name="arquivo_promob" accept=".xml,.csv,.txt,.cut" required class="w-full text-slate-400 file:bg-amber-500 file:border-0 file:rounded-xl file:px-4 file:py-2 file:font-bold">
                    </div>
                    <button type="submit" class="sm:col-span-3 py-3.5 bg-amber-500 font-bold rounded-xl text-slate-950 text-sm">⚡ Processar Promob & Gerar Orçamento no CRM</button>
                </form>
            </div>
        </div>

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
                            <input type="text" name="cliente_nome" required placeholder="Nome Completo" class="sm:col-span-2 px-3 py-2 bg-slate-950 border border-slate-700 rounded-xl text-white">
                            <input type="text" name="cliente_cpf" required placeholder="CPF" class="px-3 py-2 bg-slate-950 border border-slate-700 rounded-xl text-white">
                            <div class="flex gap-1">
                                <input type="text" name="cliente_rg" required placeholder="RG" class="w-2/3 px-3 py-2 bg-slate-950 border border-slate-700 rounded-xl text-white">
                                <input type="text" name="cliente_rg_emissor" placeholder="SSP/SP" class="w-1/3 px-2 py-2 bg-slate-950 border border-slate-700 rounded-xl text-white">
                            </div>
                            <input type="date" name="cliente_nascimento" required class="px-3 py-2 bg-slate-950 border border-slate-700 rounded-xl text-white">
                            <input type="text" name="cliente_pais" value="Brasil" required placeholder="País" class="px-3 py-2 bg-slate-950 border border-slate-700 rounded-xl text-white">
                            <input type="text" name="cliente_cidade" required placeholder="Cidade / UF" class="px-3 py-2 bg-slate-950 border border-slate-700 rounded-xl text-white">
                            <input type="email" name="cliente_email" required placeholder="E-mail" class="px-3 py-2 bg-slate-950 border border-slate-700 rounded-xl text-white">
                            <input type="text" name="cliente_telefone" required placeholder="WhatsApp Principal" class="px-3 py-2 bg-slate-950 border border-slate-700 rounded-xl text-white">
                            <input type="text" name="cliente_telefone_2" placeholder="Telefone 2 / Recado" class="px-3 py-2 bg-slate-950 border border-slate-700 rounded-xl text-white">
                        </div>
                    </div>

                    <div class="space-y-3">
                        <h3 class="text-xs font-bold text-amber-400 uppercase tracking-wide">2. Endereços com Busca de CEP</h3>
                        <div class="grid sm:grid-cols-2 gap-4">
                            <div class="bg-slate-950 p-4 border border-slate-800 rounded-xl space-y-2">
                                <label class="font-bold text-white block">📬 Endereço Postal</label>
                                <div class="flex gap-2">
                                    <input type="text" id="cep_postal" name="cliente_cep_postal" placeholder="CEP Postal" class="w-1/2 px-3 py-2 bg-slate-900 border border-slate-700 rounded-xl text-white">
                                    <button type="button" onclick="buscarCep('postal')" class="w-1/2 px-3 py-2 bg-amber-500 font-bold text-slate-950 rounded-xl">🔍 Buscar CEP</button>
                                </div>
                                <textarea id="end_postal" name="cliente_endereco_postal" rows="2" placeholder="Rua, Número, Bairro, Cidade - UF" class="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-xl text-white"></textarea>
                            </div>
                            <div class="bg-slate-950 p-4 border border-slate-800 rounded-xl space-y-2">
                                <label class="font-bold text-white block">🚚 Endereço da Obra</label>
                                <div class="flex gap-2">
                                    <input type="text" id="cep_entrega" name="cliente_cep_entrega" placeholder="CEP Obra" class="w-1/2 px-3 py-2 bg-slate-900 border border-slate-700 rounded-xl text-white">
                                    <button type="button" onclick="buscarCep('entrega')" class="w-1/2 px-3 py-2 bg-amber-500 font-bold text-slate-950 rounded-xl">🔍 Buscar CEP</button>
                                </div>
                                <textarea id="end_entrega" name="cliente_endereco_entrega" rows="2" placeholder="Endereço da Instalação..." class="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-xl text-white"></textarea>
                            </div>
                        </div>
                    </div>

                    <div class="space-y-3">
                        <h3 class="text-xs font-bold text-amber-400 uppercase tracking-wide">3. Dados Bancários, Renda & Referências</h3>
                        <div class="grid sm:grid-cols-4 gap-3">
                            <input type="text" name="cliente_banco" placeholder="Banco" class="px-3 py-2 bg-slate-950 border border-slate-700 rounded-xl text-white">
                            <input type="text" name="cliente_agencia" placeholder="Agência" class="px-3 py-2 bg-slate-950 border border-slate-700 rounded-xl text-white">
                            <input type="text" name="cliente_conta" placeholder="Conta Corrente" class="px-3 py-2 bg-slate-950 border border-slate-700 rounded-xl text-white">
                            <input type="text" name="cliente_renda" placeholder="Renda Mensal Estimada" class="px-3 py-2 bg-slate-950 border border-slate-700 rounded-xl text-white">
                            <input type="text" name="ref_nome_1" placeholder="Nome Referência 1" class="px-3 py-2 bg-slate-950 border border-slate-700 rounded-xl text-white">
                            <input type="text" name="ref_tel_1" placeholder="Telefone Referência 1" class="px-3 py-2 bg-slate-950 border border-slate-700 rounded-xl text-white">
                            <input type="text" name="ref_nome_2" placeholder="Nome Referência 2" class="px-3 py-2 bg-slate-950 border border-slate-700 rounded-xl text-white">
                            <input type="text" name="ref_tel_2" placeholder="Telefone Referência 2" class="px-3 py-2 bg-slate-950 border border-slate-700 rounded-xl text-white">
                        </div>
                    </div>

                    <div class="space-y-3">
                        <h3 class="text-xs font-bold text-amber-400 uppercase tracking-wide">4. Memorial Descritivo & Pagamento</h3>
                        <div class="grid sm:grid-cols-4 gap-3 bg-slate-950 p-4 border border-slate-800 rounded-xl">
                            <textarea name="descricao_manual" rows="2" placeholder="Memorial Descritivo / Detalhes de Acabamentos..." class="sm:col-span-4 px-3 py-2 bg-slate-900 border border-slate-700 rounded-xl text-white"></textarea>
                            <select name="forma_pagamento" class="sm:col-span-2 px-3 py-2 bg-slate-900 border border-slate-700 rounded-xl text-white">
                                <option value="PIX à Vista">PIX à Vista</option>
                                <option value="Cartão de Débito">Cartão de Débito</option>
                                <option value="Cartão de Crédito até 12x">Cartão de Crédito até 12x</option>
                                <option value="Boleto Bancário até 24x">Boleto Bancário até 24x</option>
                                <option value="Entrada PIX + Saldo no Cartão">Entrada PIX + Saldo no Cartão</option>
                            </select>
                            <input type="number" step="0.5" name="desconto_pct" value="0" placeholder="Desconto (%)" class="px-3 py-2 bg-slate-900 border border-slate-700 rounded-xl text-white">
                            <input type="number" step="100" name="entrada_valor" value="5000" placeholder="Entrada (R$)" class="px-3 py-2 bg-slate-900 border border-slate-700 rounded-xl text-white">
                            <input type="number" min="1" max="24" name="num_parcelas" value="5" placeholder="Nº Parcelas" class="px-3 py-2 bg-slate-900 border border-slate-700 rounded-xl text-white">
                        </div>
                    </div>

                    <button type="submit" class="w-full py-3.5 bg-amber-500 font-bold rounded-xl text-slate-950">💾 Salvar Ficha Cadastral e Liberar Contrato</button>
                </form>
            </div>
        </div>

        <div id="aba-adendo" class="tab-content space-y-6">
            <div class="bg-slate-900 border border-slate-800 rounded-3xl p-6 shadow">
                <h2 class="text-base font-bold text-white mb-4">➕ Termo Aditivo / Complemento</h2>
                <form action="/salvar-adendo" method="post" class="grid sm:grid-cols-3 gap-4 text-xs">
                    <select name="orcamento_id" class="px-3 py-2 bg-slate-950 border border-slate-700 rounded-xl text-white">{"".join([f"<option value='{h['id']}'>#{h['id']} - {h['cliente_nome']}</option>" for h in leads])}</select>
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
    </script>
</body></html>"""

def render_form_captacao(empresa):
    return f"""<!DOCTYPE html>
<html lang="pt-br">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>{empresa['nome_empresa']} - Simulador</title><script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-slate-950 text-slate-100 min-h-screen flex flex-col justify-between font-sans">
    <header class="bg-slate-900 border-b border-slate-800 px-6 py-4 flex items-center justify-between">
        <div class="flex items-center space-x-3"><div class="w-9 h-9 rounded-xl bg-gradient-to-br from-amber-400 to-amber-600 flex items-center justify-center font-black text-slate-950 text-lg">MVI</div><span class="font-bold text-white">{empresa['nome_empresa']}</span></div>
    </header>
    <main class="max-w-3xl w-full mx-auto p-4 sm:p-6 my-auto">
        <form action="/enviar-solicitacao-lead" method="post" enctype="multipart/form-data" class="bg-slate-900 border border-slate-800 p-6 rounded-3xl shadow-2xl space-y-4">
            <h2 class="text-lg font-bold text-white mb-2">Simulador de Projeto Sob Medida</h2>
            <div class="grid sm:grid-cols-2 gap-3 text-xs">
                <input type="text" name="nome" required placeholder="Nome Completo" class="w-full px-4 py-2.5 bg-slate-950 border border-slate-700 rounded-xl text-white">
                <input type="text" name="whatsapp" required placeholder="WhatsApp" class="w-full px-4 py-2.5 bg-slate-950 border border-slate-700 rounded-xl text-white">
                <input type="number" step="any" name="area_m2_total" value="180.0" placeholder="Metragem Total (m²)" class="w-full px-4 py-2.5 bg-slate-950 border border-slate-700 rounded-xl text-white">
                <input type="text" name="cidade" required placeholder="Cidade / Bairro" class="w-full px-4 py-2.5 bg-slate-950 border border-slate-700 rounded-xl text-white">
            </div>
            
            <div class="bg-slate-950 p-4 rounded-2xl border border-slate-800 space-y-3 text-xs">
                <h3 class="font-bold text-amber-400 uppercase">🪵 Escolha de Madeiras & Ferragens</h3>
                <div class="grid sm:grid-cols-2 gap-3">
                    <select name="fabricante_mdf" class="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-xl text-white"><option>Duratex</option><option>Arauco</option><option>Guararapes</option><option>Eucatex</option></select>
                    <select name="cor_mdf" class="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-xl text-white"><option>Freijó Puro / Natural</option><option>Carvalho Boreal</option><option>Nogueira Cadiz</option><option>Branco TX</option></select>
                    <select name="marca_ferragens" class="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-xl text-white"><option>Blum (Linha Blumotion Áustria)</option><option>Hettich (Alemanha)</option><option>FGVTN</option></select>
                    <select name="modelo_portas" class="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-xl text-white"><option>Perfil Gola Alumínio (Rometal)</option><option>Cava Usinada</option><option>Perfil Slim Vidro Reflecta</option><option>Lisa Tradicional</option></select>
                    <select name="espessura_caixa" class="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-xl text-white"><option>MDF 18mm (Reforçado)</option><option>MDF 15mm (Padrão)</option></select>
                    <select name="espessura_tamponamento" class="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-xl text-white"><option>Tamponamento 25mm</option><option>Tamponamento 36mm</option><option>Tamponamento 18mm</option></select>
                </div>
            </div>

            <div class="grid sm:grid-cols-2 gap-3 text-xs">
                <input type="file" name="planta" required class="file:bg-amber-500 file:border-0 file:rounded-xl file:px-3 file:py-1 file:font-bold text-slate-400">
                <input type="file" name="inspiracao" class="file:bg-slate-700 file:border-0 file:rounded-xl file:px-3 file:py-1 file:font-bold text-slate-400">
            </div>
            
            <button type="submit" class="w-full py-4 bg-amber-500 font-bold rounded-xl text-slate-950 text-sm shadow-lg">⚡ Simular Projeto & Receber Proposta MVI</button>
        </form>
    </main>
</body></html>"""

def render_sucesso(empresa, estimativa, zap_url):
    return f"""<!DOCTYPE html>
<html lang="pt-br">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Sucesso</title><script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-slate-950 text-slate-100 min-h-screen flex items-center justify-center p-4 font-sans">
    <div class="max-w-md w-full bg-slate-900 border border-amber-500/50 p-8 rounded-3xl text-center shadow-2xl">
        <span class="text-5xl block animate-bounce mb-4">✨</span>
        <h2 class="text-xl font-bold text-white">Orçamento Calculado!</h2>
        <p class="text-3xl font-black text-amber-400 my-4">R$ {estimativa:,.2f}</p>
        <a href="{zap_url}" class="inline-block w-full py-3.5 bg-amber-500 font-bold text-slate-950 rounded-xl shadow-lg">👉 Abrir Conversa no WhatsApp</a>
        <script>setTimeout(function() {{ window.location.href = "{zap_url}"; }}, 2000);</script>
    </div>
</body></html>"""

def render_assinatura_online(orc, empresa):
    pv = float(orc['preco_venda'] or 0) + float(orc['adendo_valor'] or 0)
    adendo = f"<p><b>ADENDO:</b> {orc['adendo_descricao']} (R$ {float(orc['adendo_valor'] or 0):,.2f})</p>" if float(orc['adendo_valor'] or 0) > 0 else ""
    return f"""<!DOCTYPE html>
<html lang="pt-br">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Assinatura Digital</title><script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdn.jsdelivr.net/npm/signature_pad@4.1.7/dist/signature_pad.umd.min.js"></script>
</head>
<body class="bg-slate-950 text-slate-100 min-h-screen p-4 sm:p-8 font-sans">
    <div class="max-w-4xl mx-auto bg-slate-900 border border-slate-800 rounded-3xl p-6 shadow-2xl space-y-6">
        <h1 class="text-xl font-bold text-white border-b border-slate-800 pb-4">CONTRATO DE PRESTAÇÃO DE SERVIÇOS #{orc['id']:04d}</h1>
        <div class="text-xs space-y-4 text-slate-300">
            <p><b>CONTRATADA:</b> {empresa['nome_empresa']} (CNPJ: {empresa['cnpj']})</p>
            <p><b>CONTRATANTE:</b> {orc['cliente_nome']} (CPF: {orc['cliente_cpf']})</p>
            <p><b>VALOR TOTAL:</b> R$ {pv:,.2f} ({orc['forma_pagamento']})</p>
            {adendo}
            <p><b>PRAZO E GARANTIA:</b> {orc['prazo_entrega']}. Garantia de 5 anos em ferragens.</p>
        </div>
        <div class="border-2 border-dashed border-slate-700 bg-white"><canvas id="signature-pad" width="600" height="200" class="w-full max-w-[600px] h-[200px] touch-none"></canvas></div>
        <div class="flex justify-between">
            <button id="clear-btn" class="px-4 py-2 bg-slate-800 text-white rounded-xl text-xs">Limpar</button>
            <form id="sign-form" action="/confirmar-assinatura" method="post"><input type="hidden" name="orcamento_id" value="{orc['id']}"><input type="hidden" name="assinatura_base64" id="assinatura_base64"><button type="button" id="save-btn" class="px-6 py-2 bg-emerald-600 font-bold text-white rounded-xl text-xs">Assinar Digitalmente</button></form>
        </div>
    </div>
    <script>
        var signaturePad = new SignaturePad(document.getElementById('signature-pad'));
        document.getElementById('clear-btn').addEventListener('click', () => signaturePad.clear());
        document.getElementById('save-btn').addEventListener('click', () => {{
            if (signaturePad.isEmpty()) alert("Faça sua assinatura!");
            else {{ document.getElementById('assinatura_base64').value = signaturePad.toDataURL(); document.getElementById('sign-form').submit(); }}
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
# 5. FASTAPI ROUTES
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

@app.get("/solicitar-orcamento", response_class=HTMLResponse)
@app.get("/solicitar-orcamento/{slug}", response_class=HTMLResponse)
def captacao_route(slug: str = "mvi"):
    empresa = get_empresa_dados(1)
    return render_form_captacao(empresa)

@app.post("/importar-promob", response_class=HTMLResponse)
async def importar_promob_route(
    cliente_nome: str = Form(...),
    cliente_telefone: str = Form(...),
    cliente_ambiente: str = Form(...),
    arquivo_promob: UploadFile = File(...)
):
    conteudo_bytes = await arquivo_promob.read()
    # Tenta decodificar em UTF-8, Latin-1 ou CP1252 automaticamente
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
            preco_venda, lucro_liquido, descricao_manual
        ) VALUES (1, ?, ?, ?, ?, '30 dias úteis', ?, 'Importado Promob', ?, ?, ?, ?)
    """, (agora, cliente_nome, cliente_telefone, cliente_ambiente, (date.today() + timedelta(days=30)).strftime("%Y-%m-%d"), calc["total_mat"], calc["preco_venda"], calc["lucro"], desc_auto))
    conn.commit()
    conn.close()

    return RedirectResponse(url="/painel-get", status_code=303)

@app.post("/enviar-solicitacao-lead", response_class=HTMLResponse)
async def submit_lead_route(
    nome: str = Form(...),
    whatsapp: str = Form(...),
    area_m2_total: float = Form(180.0),
    espessura_caixa: str = Form("MDF 18mm"),
    espessura_tamponamento: str = Form("Tamponamento 25mm"),
    fabricante_mdf: str = Form("Duratex"),
    cor_mdf: str = Form("Freijó Puro / Natural"),
    modelo_portas: str = Form("Perfil Gola em Alumínio (Rometal)"),
    marca_ferragens: str = Form("Blum (Linha Blumotion Áustria)"),
    cidade: str = Form(...),
    descricao: str = Form(""),
    planta: UploadFile = File(...),
    inspiracao: UploadFile = File(None)
):
    empresa = get_empresa_dados(1)
    calc = calcular_engenharia(
        ["Cozinha c/ Ilha", "Suíte Master c/ Closet"], area_m2_total, espessura_caixa, espessura_tamponamento,
        fabricante_mdf, cor_mdf, modelo_portas, marca_ferragens
    )

    agora = datetime.now().strftime("%d/%m/%Y %H:%M")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO orcamentos (
            empresa_id, criado_em, cliente_nome, cliente_telefone, cliente_ambiente,
            prazo_entrega, data_entrega_prevista, status, custo_materiais,
            custo_mao_obra, custo_frete_montagem, preco_venda, lucro_liquido,
            observacoes_tecnicas, descricao_promob
        ) VALUES (1, ?, ?, ?, 'Cozinha + Suíte', '30 dias úteis', ?, 'Novo Lead Instagram', ?, ?, ?, ?, ?, ?, ?)
    """, (
        agora, nome, whatsapp, (date.today() + timedelta(days=30)).strftime("%Y-%m-%d"),
        calc["total_mat"], calc["custo_mo"], calc["custo_frete"], calc["preco_venda"], calc["lucro"],
        descricao, calc["desc_promob"]
    ))
    conn.commit()
    conn.close()

    zap_url = f"https://api.whatsapp.com/send?phone=55{empresa['telefone'].replace('-','').replace(' ','').replace('(','').replace(')','')}&text=Olá! Calculei meu projeto de {area_m2_total}m² no site da MVI!"
    return render_sucesso(empresa, calc["preco_venda"], zap_url)

@app.post("/salvar-dados-completos-cliente", response_class=HTMLResponse)
def salvar_dados_completos_cliente_route(
    orcamento_id: int = Form(...),
    cliente_nome: str = Form(...),
    cliente_cpf: str = Form(...),
    cliente_rg: str = Form(...),
    cliente_rg_emissor: str = Form(...),
    cliente_nascimento: str = Form(...),
    cliente_email: str = Form(...),
    cliente_telefone: str = Form(...),
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
                cliente_nascimento, cliente_email, cliente_telefone, cliente_cep_postal, cliente_endereco_postal,
                cliente_cep_entrega, cliente_endereco_entrega, cliente_ambiente, descricao_manual, desconto_pct,
                desconto_autorizado, status, preco_venda, lucro_liquido, forma_pagamento, entrada_valor,
                num_parcelas, prazo_entrega, data_entrega_prevista
            ) VALUES (
                1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Projeto Sob Medida', ?, ?, 1, 'Contrato Pronto para Assinatura',
                ?, ?, ?, ?, ?, '30 dias úteis', ?
            )
        """, (
            agora, cliente_nome, cliente_cpf, cliente_rg, cliente_rg_emissor, cliente_nascimento,
            cliente_email, cliente_telefone, cliente_cep_postal, cliente_endereco_postal,
            cliente_cep_entrega, cliente_endereco_entrega, descricao_manual, desconto_pct,
            pv_final, lucro_final, forma_pagamento, entrada_valor, num_parcelas,
            (date.today() + timedelta(days=30)).strftime("%Y-%m-%d")
        ))
        conn.commit()
    else:
        cursor.execute("SELECT preco_venda, custo_materiais, custo_mao_obra, custo_frete_montagem FROM orcamentos WHERE id = ?", (orcamento_id,))
        orc = cursor.fetchone()
        if orc:
            pv_orig = float(orc["preco_venda"] or 0)
            custo_tot = float(orc["custo_materiais"] or 0) + float(orc["custo_mao_obra"] or 0) + float(orc["custo_frete_montagem"] or 0)
            pv_final = pv_orig * (1.0 - (desconto_pct / 100.0))
            lucro_final = pv_final - (custo_tot + (pv_final * 0.10))

            cursor.execute("""
                UPDATE orcamentos SET
                    cliente_nome = ?, cliente_cpf = ?, cliente_rg = ?, cliente_rg_emissor = ?,
                    cliente_nascimento = ?, cliente_email = ?, cliente_telefone = ?,
                    cliente_cep_postal = ?, cliente_endereco_postal = ?, cliente_cep_entrega = ?, 
                    cliente_endereco_entrega = ?, descricao_manual = ?, desconto_pct = ?, 
                    status = 'Contrato Pronto para Assinatura', preco_venda = ?, lucro_liquido = ?, 
                    forma_pagamento = ?, entrada_valor = ?, num_parcelas = ?
                WHERE id = ?
            """, (
                cliente_nome, cliente_cpf, cliente_rg, cliente_rg_emissor, cliente_nascimento, 
                cliente_email, cliente_telefone, cliente_cep_postal, cliente_endereco_postal, 
                cliente_cep_entrega, cliente_endereco_entrega, descricao_manual, desconto_pct, 
                pv_final, lucro_final, forma_pagamento, entrada_valor, num_parcelas, orcamento_id
            ))
            conn.commit()
            
    conn.close()
    return RedirectResponse(url="/painel-get", status_code=303)

@app.post("/salvar-adendo", response_class=HTMLResponse)
def salvar_adendo_route(orcamento_id: int = Form(...), adendo_descricao: str = Form(...), adendo_valor: float = Form(0.0)):
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
        cursor.execute("UPDATE orcamentos SET desconto_autorizado = 1, status = 'Desconto Autorizado' WHERE id = ?", (orcamento_id,))
    elif tipo_acao == "financeiro":
        cursor.execute("UPDATE orcamentos SET liberado_financeiro = 1, status = 'Liberado para Financeiro' WHERE id = ?", (orcamento_id,))
    conn.commit()
    conn.close()
    return RedirectResponse(url="/painel-get", status_code=303)

@app.get("/assinar/{orcamento_id}", response_class=HTMLResponse)
def assinar_contrato_route(orcamento_id: int):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM orcamentos WHERE id = ?", (orcamento_id,))
    orc = cursor.fetchone()
    conn.close()
    if not orc: return HTMLResponse("Not Found", status_code=404)
    return render_assinatura_online(orc, get_empresa_dados(1))

@app.post("/confirmar-assinatura", response_class=HTMLResponse)
def confirmar_assinatura_route(orcamento_id: int = Form(...), assinatura_base64: str = Form(...)):
    agora = datetime.now().strftime("%d/%m/%Y %H:%M")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE orcamentos SET contrato_assinado = 1, assinatura_data = ?, assinatura_img = ?, status = 'Contrato Assinado Digitalmente' WHERE id = ?", (agora, assinatura_base64, orcamento_id))
    conn.commit()
    conn.close()
    return HTMLResponse("<div style='text-align:center; padding:50px; background:#0f172a; color:#10b981; min-height:100vh;'><h1>🎉 Contrato Assinado com Sucesso!</h1></div>")

@app.post("/criar-usuario", response_class=HTMLResponse)
def criar_usuario_route(request: Request, nome: str = Form(...), email: str = Form(...), perfil: str = Form(...), telefone: str = Form("")):
    token = secrets.token_urlsafe(16)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO usuarios (email, senha, nome, perfil, empresa_id, token_primeiro_acesso, primeiro_acesso_concluido, ativo) VALUES (?, '', ?, ?, 1, ?, 0, 1)", (email.strip().lower(), nome, perfil, token))
    conn.commit()
    conn.close()
    return render_convite_gerado(nome, email, perfil, telefone, f"{str(request.base_url).rstrip('/')}/primeiro-acesso/{token}")

@app.get("/primeiro-acesso/{token}", response_class=HTMLResponse)
def tela_primeiro_acesso_route(token: str):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM usuarios WHERE token_primeiro_acesso = ?", (token,))
    user = cursor.fetchone()
    conn.close()
    if not user: return HTMLResponse("Link inválido ou já utilizado.", status_code=404)
    return render_tela_nova_senha(user, token)

@app.post("/salvar-nova-senha", response_class=HTMLResponse)
def salvar_nova_senha_route(token: str = Form(...), nova_senha: str = Form(...), confirma_senha: str = Form(...)):
    if nova_senha != confirma_senha: return HTMLResponse("<script>alert('Senhas diferentes!'); history.back();</script>")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE usuarios SET senha = ?, token_primeiro_acesso = '', primeiro_acesso_concluido = 1, ativo = 1 WHERE token_primeiro_acesso = ?", (nova_senha, token))
    conn.commit()
    conn.close()
    return RedirectResponse(url="/", status_code=303)

@app.post("/redefinir-senha-funcionario", response_class=HTMLResponse)
def redefinir_senha_funcionario_route(request: Request, email_funcionario: str = Form(...)):
    token = secrets.token_urlsafe(16)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE usuarios SET token_primeiro_acesso = ?, primeiro_acesso_concluido = 0 WHERE email = ?", (token, email_funcionario))
    conn.commit()
    conn.close()
    return render_convite_gerado("Funcionário", email_funcionario, "Reset", "", f"{str(request.base_url).rstrip('/')}/primeiro-acesso/{token}")

@app.post("/alternar-status-funcionario", response_class=HTMLResponse)
def alternar_status_funcionario_route(email_funcionario: str = Form(...)):
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
def update_empresa_route(nome_empresa: str = Form(...), cnpj: str = Form(...), telefone: str = Form(...), chave_mestra: str = Form("MVI2026")):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE empresas SET nome_empresa = ?, cnpj = ?, telefone = ?, chave_mestra = ? WHERE id = 1", (nome_empresa, cnpj, telefone, chave_mestra))
    conn.commit()
    conn.close()
    return RedirectResponse(url="/painel-get", status_code=303)

@app.get("/exportar-csv")
def export_csv_route():
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

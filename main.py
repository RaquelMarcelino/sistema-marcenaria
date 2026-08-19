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
DB_PATH = "mvi_production_v40.db"

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
        <a href="/painel-get" style="display:inline-block; margin-top:15px; padding:10px 20px; background:#f59e0b; color:#0f172a; font-weight:bold; border-radius:8px; text-decoration:none;">Voltar ao Painel</a>
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
            prazo_entrega TEXT DEFAULT '45 dias úteis',
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
            modalidade_pagamento TEXT DEFAULT 'Entrada + Cartão de Crédito',
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
        cursor.execute("INSERT OR REPLACE INTO usuarios VALUES ('vendedor@mvi.com', '123456', 'Raquel Marcelino', 'vendedor', 1, '', 1, 1)")
        conn.commit()

    conn.close()

init_db()

CURRENT_SESSION = {
    "user_email": "admin@mvi.com",
    "user_nome": "Raquel Marcelino",
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

    preco_bruto = round((total_materiais + custo_mo + custo_frete) * markup)
    preco_venda = preco_bruto
    lucro = round(preco_venda - (total_materiais + custo_mo + custo_frete + (preco_venda * 0.10)))

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
    preco_bruto = round((total_mat + custo_mo + custo_frete) * 2.2)
    preco_venda = preco_bruto
    lucro = round(preco_venda - (total_mat + custo_mo + custo_frete + (preco_venda * 0.10)))

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
            <p class="text-xs text-slate-400 mb-3">Defina seus ambientes, caixaria, portas, acabamentos e ferragens.</p>
            
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
            
            <div class="bg-slate-950 p-4 sm:p-5 rounded-2xl border border-slate-800 space-y-3 text-xs">
                <h3 class="font-bold text-amber-400 uppercase tracking-wide">🏠 Escolha os Ambientes do seu Projeto</h3>
                
                <div class="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
                    <label class="flex items-center space-x-2 bg-slate-900 p-2.5 rounded-xl border border-slate-800 cursor-pointer hover:border-amber-500">
                        <input type="checkbox" name="amb_cozinha" value="1" checked class="rounded text-amber-500">
                        <span>🍳 Cozinha</span>
                    </label>

                    <label class="flex items-center space-x-2 bg-slate-900 p-2.5 rounded-xl border border-slate-800 cursor-pointer hover:border-amber-500">
                        <input type="checkbox" name="amb_lavanderia" value="1" checked class="rounded text-amber-500">
                        <span>🧺 Lavanderia</span>
                    </label>

                    <label class="flex items-center space-x-2 bg-slate-900 p-2.5 rounded-xl border border-slate-800 cursor-pointer hover:border-amber-500">
                        <input type="checkbox" name="amb_sala" value="1" checked class="rounded text-amber-500">
                        <span>🛋️ Sala</span>
                    </label>

                    <label class="flex items-center space-x-2 bg-slate-900 p-2.5 rounded-xl border border-slate-800 cursor-pointer hover:border-amber-500">
                        <input type="checkbox" name="amb_sacada" value="1" class="rounded text-amber-500">
                        <span>🌿 Sacada</span>
                    </label>

                    <label class="flex items-center space-x-2 bg-slate-900 p-2.5 rounded-xl border border-slate-800 cursor-pointer hover:border-amber-500">
                        <input type="checkbox" name="amb_gourmet" value="1" class="rounded text-amber-500">
                        <span>🥩 Área Gourmet</span>
                    </label>
                </div>

                <div class="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-2 border-t border-slate-800/80">
                    <div class="bg-slate-900 p-2.5 rounded-xl border border-slate-800 flex justify-between items-center">
                        <label class="font-semibold text-slate-300">🛏️ Dorm. Solteiro</label>
                        <select name="qtd_dorm_solteiro" class="px-2 py-1 bg-slate-950 border border-slate-700 rounded-lg text-white font-bold">
                            <option value="0">0</option>
                            <option value="1" selected>1</option>
                            <option value="2">2</option>
                            <option value="3">3</option>
                            <option value="4">4</option>
                            <option value="5">5</option>
                            <option value="6">6</option>
                        </select>
                    </div>

                    <div class="bg-slate-900 p-2.5 rounded-xl border border-slate-800 flex justify-between items-center">
                        <label class="font-semibold text-slate-300">👑 Dorm. Casal / Suíte</label>
                        <select name="qtd_dorm_casal" class="px-2 py-1 bg-slate-950 border border-slate-700 rounded-lg text-white font-bold">
                            <option value="0">0</option>
                            <option value="1" selected>1</option>
                            <option value="2">2</option>
                            <option value="3">3</option>
                            <option value="4">4</option>
                            <option value="5">5</option>
                            <option value="6">6</option>
                        </select>
                    </div>

                    <div class="bg-slate-900 p-2.5 rounded-xl border border-slate-800 flex justify-between items-center">
                        <label class="font-semibold text-slate-300">🚿 Banheiro</label>
                        <select name="qtd_banheiro" class="px-2 py-1 bg-slate-950 border border-slate-700 rounded-lg text-white font-bold">
                            <option value="0">0</option>
                            <option value="1">1</option>
                            <option value="2" selected>2</option>
                            <option value="3">3</option>
                            <option value="4">4</option>
                            <option value="5">5</option>
                            <option value="6">6</option>
                        </select>
                    </div>
                </div>
            </div>
            
            <div class="bg-slate-950 p-4 sm:p-5 rounded-2xl border border-slate-800 space-y-4 text-xs">
                <h3 class="font-bold text-amber-400 uppercase tracking-wide">🪵 Especificações de Caixas, Portas & Ferragens</h3>
                
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
                    <input type="file" name="inspiracao" class="w-full text-slate-400 file:bg-slate-700 file:border-0 file:rounded-xl file:px-3 file:py-1 file:font-bold file:text-white text-xs">
                </div>
            </div>
            
            <button type="submit" class="w-full py-4 bg-gradient-to-r from-amber-500 to-amber-600 hover:from-amber-400 hover:to-amber-500 text-slate-950 font-bold rounded-xl text-sm shadow-lg">
                ⚡ Simular Projeto & Receber Proposta MVI
            </button>
        </form>
    </main>
</body></html>"""

def render_pre_orcamento_agendamento(
    empresa, orcamento_id, nome, whatsapp, cidade, area_m2, preco_venda,
    esp_caixa, cor_caixa, esp_porta, cor_porta, acab_porta, marca_ferr, esp_tamp, ambientes_str
):
    pv_redondo = round(preco_venda)
    entrada_minima = round(pv_redondo * 0.20)
    saldo_restante = pv_redondo - entrada_minima
    parcela_12x = round(saldo_restante / 12.0)
    desconto_vista_5 = round(pv_redondo * 0.95)
    economia_5 = pv_redondo - desconto_vista_5

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
        
        <div class="text-center space-y-2 border-b border-slate-800 pb-4">
            <span class="text-4xl block animate-bounce">✨</span>
            <h1 class="text-xl sm:text-2xl font-bold text-white">Seu Pré-Orçamento Sob Medida foi Calculado!</h1>
            <p class="text-xs text-slate-400">Olá, <b>{nome}</b>! Estimativa para <b>{cidade} ({area_m2} m²)</b>.</p>
            <p class="text-[11px] text-amber-300 font-semibold">{ambientes_str}</p>
        </div>

        <div class="bg-slate-950 p-6 rounded-2xl border border-amber-500/40 text-center space-y-2">
            <span class="text-xs text-slate-400 font-bold uppercase tracking-wider block">Valor de Tabela do Projeto</span>
            <span id="txt_valor_principal" class="text-3xl sm:text-4xl font-black text-amber-400">R$ {pv_redondo:,.0f}</span>
            
            <div class="p-3 bg-emerald-950/60 border border-emerald-500/40 rounded-xl inline-block mt-1">
                <span class="text-xs text-emerald-300 font-bold block">⚡ Valor à Vista no PIX (com 5% de desconto):</span>
                <span class="text-xl sm:text-2xl font-black text-emerald-400">R$ {desconto_vista_5:,.0f}</span>
                <span class="text-[11px] text-emerald-200 block">Economia de R$ {economia_5:,.0f}</span>
            </div>

            <p class="text-[11px] text-slate-500 pt-1">Caixas {esp_caixa} ({cor_caixa}) • Portas {acab_porta} • Ferragens {marca_ferr}</p>
        </div>

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

        <div class="bg-slate-950 p-5 rounded-2xl border border-slate-800 space-y-4 text-xs">
            <h3 class="text-xs font-bold text-amber-400 uppercase tracking-wide flex items-center gap-1">
                <span>💳 2. Como você pretende realizar o pagamento?</span>
            </h3>

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
                        Entrada (Mínimo de 20%)
                    </label>
                    <input type="number" id="entrada_cli" min="{entrada_minima}" step="100" value="{entrada_minima}" oninput="calcularParcelasCliente()" class="w-full px-3 py-2 bg-slate-900 border border-amber-500/50 rounded-xl text-amber-300 font-bold">
                    <span class="text-[10px] text-slate-500 block mt-0.5">Mínimo: R$ {entrada_minima:,.0f}</span>
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

            <div id="box_resultado_parcelas" class="p-4 bg-slate-900 rounded-xl border border-slate-800 text-center space-y-1">
                <span class="text-slate-400 text-[11px] uppercase tracking-wider block">Seu Plano Simulado:</span>
                <p class="text-sm font-bold text-white">
                    Entrada de <span id="res_entrada" class="text-amber-400">R$ {entrada_minima:,.0f}</span> + 
                    <span id="res_num_parc">12</span>x de <span id="res_valor_parc" class="text-emerald-400 font-black text-base">R$ {parcela_12x:,.0f}</span>
                </p>
                <p class="text-[10px] text-slate-500">Saldo a parcelar: R$ <span id="res_saldo">{saldo_restante:,.0f}</span></p>
            </div>
        </div>

        <div class="pt-2">
            <a id="btn_whatsapp_agendar" href="#" target="_blank" class="flex items-center justify-center gap-2 w-full py-4 bg-gradient-to-r from-emerald-500 to-emerald-600 hover:from-emerald-400 hover:to-emerald-500 text-slate-950 font-black rounded-xl text-sm transition-all shadow-xl">
                <span id="txt_btn_zap">📲 Quero ser direcionado ao WhatsApp para agendar atendimento</span>
            </a>
            <p class="text-[11px] text-center text-slate-500 mt-2">Você será atendido pela equipe oficial da <b>{empresa['nome_empresa']}</b> com sua simulação salva.</p>
        </div>

    </div>

    <script>
        var valorTotalOriginal = {pv_redondo};
        var valorComDesconto5 = {desconto_vista_5};
        var entradaMinimaPermitida = {entrada_minima};
        var telEmpresa = "{tel_limpo}";
        var nomeCliente = "{nome}";
        var cidadeCliente = "{cidade}";
        var areaCliente = "{area_m2}";
        var ambientesTexto = "{ambientes_str}";
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
                boxEntrada.style.display = "none";
                boxParcelas.style.display = "none";
                boxResultado.innerHTML = `
                    <span class="text-slate-400 text-[11px] uppercase tracking-wider block">Condição Especial Selecionada:</span>
                    <p class="text-sm font-bold text-white">Pagamento Integral no PIX: <span class="text-emerald-400 font-black text-lg">R$ ` + valorComDesconto5.toLocaleString('pt-BR') + `</span></p>
                    <p class="text-[10px] text-emerald-300">Desconto de 5% aplicado com sucesso!</p>
                `;
            }} else {{
                boxEntrada.style.display = "block";
                boxParcelas.style.display = "block";
                
                var entrada = Math.round(parseFloat(entradaInput.value) || 0);
                var nParc = parseInt(document.getElementById('parcelas_cli').value) || 1;

                if (entrada < entradaMinimaPermitida) {{
                    entrada = entradaMinimaPermitida;
                    entradaInput.value = entradaMinimaPermitida;
                }}

                var saldo = Math.max(valorTotalOriginal - entrada, 0);
                var valorParc = nParc > 0 ? Math.round(saldo / nParc) : 0;

                boxResultado.innerHTML = `
                    <span class="text-slate-400 text-[11px] uppercase tracking-wider block">Seu Plano Simulado:</span>
                    <p class="text-sm font-bold text-white">
                        Entrada de <span id="res_entrada" class="text-amber-400">R$ ` + entrada.toLocaleString('pt-BR') + `</span> + 
                        <span id="res_num_parc">` + nParc + `</span>x de <span id="res_valor_parc" class="text-emerald-400 font-black text-base">R$ ` + valorParc.toLocaleString('pt-BR') + `</span>
                    </p>
                    <p class="text-[10px] text-slate-500">Saldo a parcelar: R$ ` + saldo.toLocaleString('pt-BR') + `</p>
                `;
            }}

            atualizarMensagemZap();
        }}

        function atualizarMensagemZap() {{
            var tipoAgend = document.getElementById('tipo_agendamento').value;
            var prefHorario = document.getElementById('preferencia_horario').value;
            var forma = document.getElementById('forma_pagamento_cli').value;
            var entrada = Math.round(parseFloat(document.getElementById('entrada_cli').value) || entradaMinimaPermitida);
            var nParc = document.getElementById('parcelas_cli').value;

            var agendamentoTexto = "";
            if (tipoAgend === "Não tenho interesse no momento") {{
                agendamentoTexto = "📅 *AGENDAMENTO:* Cliente prefere avaliar a proposta antes de agendar.";
            }} else {{
                agendamentoTexto = "📅 *AGENDAMENTO NA LOJA:*\n• Preferência: *Agendamento Presencial na Loja*\n• Horário: *" + prefHorario + "*";
            }}

            var financeiroTexto = "";
            if (forma.indexOf("PIX") !== -1) {{
                financeiroTexto = "💳 *FORMA DE PAGAMENTO:* PIX à Vista com 5% de Desconto\n• Valor Final c/ Desconto: *R$ " + valorComDesconto5.toLocaleString('pt-BR') + "*";
            }} else {{
                var saldo = Math.max(valorTotalOriginal - entrada, 0);
                var valorParc = Math.round(saldo / nParc).toLocaleString('pt-BR');
                financeiroTexto = "💳 *SIMULAÇÃO DE PAGAMENTO:*\n• Forma: " + forma + "\n• Entrada (mín. 20%): R$ " + entrada.toLocaleString('pt-BR') + "\n• Parcelamento: *" + nParc + "x de R$ " + valorParc + "*";
            }}

            var msg = "Olá! Meu nome é *" + nomeCliente + "*.\n" +
                      "Gerei meu pré-orçamento no site da *{empresa['nome_empresa']}* (Projeto #" + idOrc + ").\n\n" +
                      "📋 *DADOS DO PROJETO:*\n" +
                      "• Cidade: " + cidadeCliente + "\n" +
                      "• Metragem: " + areaCliente + " m²\n" +
                      "• Ambientes: " + ambientesTexto + "\n" +
                      "• Valor de Tabela: *R$ " + valorTotalOriginal.toLocaleString('pt-BR') + "*\n\n" +
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

def render_convite_gerado(nome, email, p, tel, link):
    return f"""<html><body style='background:#0f172a; color:#fff; text-align:center; padding:50px; font-family:sans-serif;'>
        <h1 style='color:#f59e0b;'>Convite de Acesso Gerado</h1>
        <p style='margin:20px 0;'>Link Seguro: <br><b style='color:#38bdf8;'>{link}</b></p>
        <a href='/painel-get' style='color:#f59e0b;'>Voltar ao Painel</a>
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
# NOVO LAYOUT DO COCKPIT COM ALTERNÂNCIA COMPLETA ENTRE DASHBOARD E PASTAS
# ==============================================================================
def render_dashboard_view():
    empresa = get_empresa_dados(1)
    met = get_metricas()
    is_admin = (CURRENT_SESSION["user_perfil"] == "admin")
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM orcamentos WHERE empresa_id = 1 ORDER BY id DESC LIMIT 50")
    leads = cursor.fetchall()
    cursor.execute("SELECT * FROM usuarios WHERE empresa_id = 1")
    equipe = cursor.fetchall()
    conn.close()

    cliente_ativo = {}
    if CURRENT_SESSION.get("cliente_ativo_id"):
        for h in leads:
            if h["id"] == CURRENT_SESSION["cliente_ativo_id"]:
                cliente_ativo = dict(h)
                break
    
    tem_cliente = bool(cliente_ativo)
    c_id = cliente_ativo.get("id", 0)
    c_nome = cliente_ativo.get("cliente_nome") or "Nenhum cliente selecionado"
    c_cpf = cliente_ativo.get("cliente_cpf") or "Não informado"
    c_rg = cliente_ativo.get("cliente_rg") or "—"
    c_tel = cliente_ativo.get("cliente_telefone") or "—"
    c_cep_post = cliente_ativo.get("cliente_cep_postal") or ""
    c_end_post = cliente_ativo.get("cliente_endereco_postal") or ""
    c_cep_ent = cliente_ativo.get("cliente_cep_entrega") or ""
    c_end_ent = cliente_ativo.get("cliente_endereco_entrega") or ""
    c_email = cliente_ativo.get("cliente_email") or ""

    c_prazo = cliente_ativo.get("prazo_entrega") or "45 dias úteis"
    c_amb = cliente_ativo.get("cliente_ambiente") or "Geral"
    c_data_venda = cliente_ativo.get("criado_em") or datetime.now().strftime("%d/%m/%Y")
    
    c_p_bruto = round(float(cliente_ativo.get("preco_bruto") or cliente_ativo.get("preco_venda") or 0))
    c_p_venda = round(float(cliente_ativo.get("preco_venda") or 0))
    c_lucro = round(float(cliente_ativo.get("lucro_liquido") or 0))
    c_desc_pct = float(cliente_ativo.get("desconto_pct") or 0)
    c_entrada = round(float(cliente_ativo.get("entrada_valor") or 0))
    c_parc = int(cliente_ativo.get("num_parcelas") or 1)
    c_mod = cliente_ativo.get("modalidade_pagamento") or "Entrada + Cartão de Crédito"
    c_aut_desc = int(cliente_ativo.get("desconto_autorizado") or 1)
    c_lib_fin = int(cliente_ativo.get("liberado_financeiro") or 0)
    c_assinado = int(cliente_ativo.get("contrato_assinado") or 0)
    
    saldo_financiar = max(c_p_venda - c_entrada, 0)
    valor_por_parcela = round(saldo_financiar / c_parc) if c_parc > 0 else 0

    # Linhas da tabela de parcelas detalhada da pasta
    linhas_parcelas = ""
    hoje = date.today()
    for i in range(1, c_parc + 1):
        dt_parc = (hoje + timedelta(days=30 * i)).strftime("%d/%m/%Y")
        linhas_parcelas += f"""
        <tr class="border-b border-slate-200 text-xs hover:bg-slate-50">
            <td class="py-2 px-3 text-center text-slate-500 font-mono">{i}</td>
            <td class="py-2 px-3 text-slate-700">{dt_parc}</td>
            <td class="py-2 px-3 font-bold text-slate-800 text-right">R$ {valor_por_parcela:,.2f}</td>
            <td class="py-2 px-3 text-slate-600">{c_mod}</td>
            <td class="py-2 px-3 text-center text-slate-400">—</td>
            <td class="py-2 px-3 text-center text-slate-400">—</td>
            <td class="py-2 px-3 text-center text-slate-400">—</td>
            <td class="py-2 px-3 text-slate-500">Parcela regular do projeto</td>
            <td class="py-2 px-3 text-center"><button class="text-sky-600 hover:underline">📄</button></td>
        </tr>
        """

    if not linhas_parcelas:
        linhas_parcelas = "<tr><td colspan='9' class='py-4 text-center text-xs text-slate-400'>Nenhuma parcela gerada.</td></tr>"

    # Geração de linhas da tabela geral (Dashboard Geral com todos os clientes)
    leads_geral_html = ""
    options_leads = "<option value='0'>📂 Selecionar outra pasta...</option>"
    for h in leads:
        h_d = dict(h)
        pv = round(float(h_d.get("preco_venda") or 0))
        adendo = round(float(h_d.get("adendo_valor") or 0))
        pv_total = pv + adendo
        lucro = round(float(h_d.get("lucro_liquido") or 0))
        st = h_d.get("status") or "Em Negociação"
        
        sel = "selected" if h_d.get("id") == c_id else ""
        options_leads += f"<option value='{h_d['id']}' {sel}>Pasta P{h_d['id']:05d} - {h_d.get('cliente_nome','')} ({h_d.get('cliente_ambiente','')})</option>"

        leads_geral_html += f"""
        <tr class="border-b border-slate-200 text-xs hover:bg-slate-50">
            <td class="py-3 px-4 font-mono font-bold text-sky-700">P{h_d['id']:05d}</td>
            <td class="py-3 px-4 text-slate-800 font-bold">{h_d.get('cliente_nome','')}<span class="block text-[11px] text-slate-400 font-normal">CPF: {h_d.get('cliente_cpf') or 'Pendente'}</span></td>
            <td class="py-3 px-4 text-slate-600">{h_d.get('cliente_ambiente','')}</td>
            <td class="py-3 px-4 text-slate-700 font-bold text-right">R$ {pv_total:,.2f}</td>
            <td class="py-3 px-4 text-center"><span class="px-2 py-0.5 rounded text-[11px] font-bold bg-amber-100 text-amber-800">{st}</span></td>
            <td class="py-3 px-4 text-center">
                <form action="/selecionar-cliente-trabalho" method="post" class="inline">
                    <input type="hidden" name="orcamento_id" value="{h_d['id']}">
                    <button type="submit" class="px-3 py-1 bg-sky-600 hover:bg-sky-500 text-white font-bold rounded text-xs shadow-sm">
                        📂 Abrir Pasta / Negociar
                    </button>
                </form>
            </td>
        </tr>
        """

    if not leads_geral_html:
        leads_geral_html = "<tr><td colspan='6' class='py-8 text-center text-xs text-slate-400'>Nenhum cliente ou orçamento cadastrado ainda.</td></tr>"

    # Define qual tela abre por padrão
    mostrar_pasta = "block" if tem_cliente else "none"
    mostrar_geral = "none" if tem_cliente else "block"
    tab_geral_active = "active font-bold text-sky-700 bg-white" if not tem_cliente else "bg-slate-200 text-slate-600"
    tab_pasta_active = "active font-bold text-sky-700 bg-white border-t-2 border-sky-600" if tem_cliente else "bg-slate-200 text-slate-600"

    return f"""<!DOCTYPE html>
<html lang="pt-br">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MVI Gestão - Contrato P{c_id:05d}</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        .tree-item {{ transition: all 0.2s; cursor: pointer; }}
        .tree-item:hover {{ background-color: #f1f5f9; }}
        .tree-item.active {{ background-color: #e0f2fe; color: #0369a1; font-weight: bold; border-left: 3px solid #0284c7; }}
        .tab-content {{ display: none; }}
        .tab-content.active {{ display: block; }}
    </style>
</head>
<body class="bg-slate-100 text-slate-800 font-sans min-h-screen">
    
    <!-- 1. HEADER SUPERIOR AZUL PADRÃO ERP -->
    <header class="bg-[#1e73be] text-white px-6 py-2.5 flex flex-wrap items-center justify-between shadow-md">
        <div class="flex items-center space-x-6">
            <div class="flex items-center space-x-2 cursor-pointer" onclick="abrirDashboardGeral()">
                <div class="w-8 h-8 rounded-lg bg-amber-400 text-slate-900 font-black flex items-center justify-center text-sm">MVI</div>
                <span class="font-bold text-sm tracking-wide">MVI SISTEMAS</span>
            </div>
            <nav class="flex items-center space-x-4 text-xs font-semibold">
                <button onclick="abrirDashboardGeral()" class="hover:text-amber-300">Comercial</button>
                <a href="/solicitar-orcamento" target="_blank" class="hover:text-amber-300">Simulador Web</a>
                <a href="/exportar-csv" class="hover:text-amber-300">Consultas</a>
                <a href="/solicitar-orcamento" target="_blank" class="hover:text-amber-300">Integrador</a>
            </nav>
        </div>

        <div class="flex items-center space-x-4 text-xs">
            <form action="/selecionar-cliente-trabalho" method="post" class="flex items-center gap-1">
                <select name="orcamento_id" onchange="this.form.submit()" class="px-3 py-1 rounded bg-white text-slate-800 text-xs font-medium border-0 focus:ring-2 focus:ring-amber-400">
                    {options_leads}
                </select>
            </form>
            <span class="bg-rose-600 px-2 py-0.5 rounded font-bold">{met['aprovados']}</span>
            <span class="font-semibold text-white">{empresa['nome_empresa']}</span>
            <span class="text-amber-300 font-bold">{CURRENT_SESSION['user_nome']}</span>
            <a href="/" class="bg-sky-800 hover:bg-sky-900 px-2.5 py-1 rounded text-white font-semibold">Sair</a>
        </div>
    </header>

    <!-- 2. SUB-BARRA DE ABAS RÁPIDAS COM BOTÃO DE FECHAR (✕) -->
    <div class="bg-[#f8fafc] border-b border-slate-300 px-6 pt-2 flex items-center space-x-2 text-xs">
        <button onclick="abrirDashboardGeral()" id="tab-top-geral" class="px-4 py-2 rounded-t-lg font-semibold {tab_geral_active}">
            Dashboard Geral
        </button>
        
        <div id="tab-top-pasta" class="flex items-center rounded-t-lg shadow-sm {tab_pasta_active}" style="display: {'flex' if tem_cliente else 'none'};">
            <button onclick="abrirPastaAtiva()" class="px-3 py-2 font-bold">
                Pasta Ativa P{c_id:05d}
            </button>
            <button onclick="fecharPastaAtiva()" class="pr-3 pl-1 py-2 font-black hover:text-rose-600 text-slate-400" title="Fechar Pasta Ativa">
                ✕
            </button>
        </div>
    </div>

    <!-- 3. TELA DO DASHBOARD GERAL COM TODAS AS PASTAS/CLIENTES -->
    <div id="view-dashboard-geral" class="max-w-7xl mx-auto p-4 sm:p-6 space-y-5" style="display: {mostrar_geral};">
        <div class="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <div class="bg-white border border-slate-300 p-4 rounded-xl shadow-sm"><p class="text-[11px] font-bold text-slate-400 uppercase">Faturamento Liberado</p><p class="text-xl font-bold text-sky-700">R$ {met['faturamento']:,.2f}</p></div>
            <div class="bg-white border border-slate-300 p-4 rounded-xl shadow-sm"><p class="text-[11px] font-bold text-slate-400 uppercase">Projetos Aprovados</p><p class="text-xl font-bold text-emerald-600">{met['aprovados']}</p></div>
            <div class="bg-white border border-slate-300 p-4 rounded-xl shadow-sm"><p class="text-[11px] font-bold text-slate-400 uppercase">Ticket Médio</p><p class="text-xl font-bold text-slate-800">R$ {met['ticket']:,.2f}</p></div>
            <div class="bg-white border border-slate-300 p-4 rounded-xl shadow-sm"><p class="text-[11px] font-bold text-slate-400 uppercase">Conversão Comercial</p><p class="text-xl font-bold text-amber-600">{met['taxa']:.1f}%</p></div>
        </div>

        <div class="bg-white border border-slate-300 rounded-xl overflow-hidden shadow-sm">
            <div class="bg-slate-50 px-5 py-3 border-b border-slate-200 flex justify-between items-center">
                <h3 class="font-bold text-xs uppercase text-slate-700 tracking-wide">📂 Carteira Geral de Contratos e Negociações</h3>
                <a href="/solicitar-orcamento" target="_blank" class="px-3 py-1.5 bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold rounded text-xs shadow-sm">
                    ➕ Novo Orçamento Web
                </a>
            </div>
            <div class="overflow-x-auto">
                <table class="w-full text-left text-xs border-collapse">
                    <thead class="bg-slate-100 border-b border-slate-200 text-slate-500 font-semibold uppercase">
                        <tr>
                            <th class="py-3 px-4">Pasta</th>
                            <th class="py-3 px-4">Cliente / Contratante</th>
                            <th class="py-3 px-4">Ambientes</th>
                            <th class="py-3 px-4 text-right">Valor Venda</th>
                            <th class="py-3 px-4 text-center">Status</th>
                            <th class="py-3 px-4 text-center">Ação</th>
                        </tr>
                    </thead>
                    <tbody>{leads_geral_html}</tbody>
                </table>
            </div>
        </div>
    </div>

    <!-- 4. TELA DA PASTA ATIVA DO CLIENTE (ARQUITETURA DE 3 COLUNAS) -->
    <div id="view-pasta-cliente" class="max-w-7xl mx-auto p-4 sm:p-6" style="display: {mostrar_pasta};">
        
        <!-- IDENTIFICAÇÃO DA PASTA ATIVA -->
        <div class="bg-white border border-slate-300 rounded-xl px-5 py-2.5 mb-4 flex justify-between items-center text-xs font-semibold text-slate-600 shadow-sm">
            <div>Contratos Fechados - Ativos <span class="mx-2">›</span> <span class="bg-sky-100 text-sky-800 px-2.5 py-0.5 rounded font-bold">Pasta P{c_id:05d}</span></div>
            <div class="text-[11px]">Status: <b class="text-emerald-600">{cliente_ativo.get('status','Em Negociação')}</b></div>
        </div>

        <div class="grid grid-cols-1 lg:grid-cols-12 gap-5">
            <!-- COLUNA 1: MENU LATERAL -->
            <div class="lg:col-span-3 bg-white border border-slate-300 rounded-xl p-4 shadow-sm space-y-4 text-xs">
                <div>
                    <h3 class="font-bold text-slate-800 flex items-center gap-1.5 pb-2 border-b border-slate-200">
                        <span>📁 Pasta P{c_id:05d}</span>
                    </h3>
                    <ul class="mt-2 space-y-1">
                        <li><button onclick="mudarAba('aba-resumo')" id="btn-aba-resumo" class="tree-item active w-full text-left flex items-center gap-2 p-2 rounded">📋 Resumo Financeiro</button></li>
                        <li><button onclick="mudarAba('aba-cliente')" id="btn-aba-cliente" class="tree-item w-full text-left flex items-center gap-2 p-2 rounded">👤 Dados do Cliente & CEP</button></li>
                        <li><button onclick="mudarAba('aba-mesa')" id="btn-aba-mesa" class="tree-item w-full text-left flex items-center gap-2 p-2 rounded">💼 Mesa de Negociação</button></li>
                        <li><button onclick="mudarAba('aba-promob')" id="btn-aba-promob" class="tree-item w-full text-left flex items-center gap-2 p-2 rounded">🚀 Integrador Promob</button></li>
                        <li><a href="/minuta-contrato/{c_id}" target="_blank" class="tree-item flex items-center gap-2 p-2 rounded text-sky-700 font-bold hover:bg-sky-50">📜 Contrato & Minuta Jurídica</a></li>
                        <li><a href="/assinar/{c_id}" target="_blank" class="tree-item flex items-center gap-2 p-2 rounded text-emerald-700 font-bold hover:bg-emerald-50">✍️ Assinaturas (Touch/2 Vias)</a></li>
                    </ul>
                </div>

                <div>
                    <div class="flex justify-between items-center pb-1 border-b border-slate-200 font-bold text-slate-800">
                        <span>🏠 Ambientes</span>
                        <button onclick="mudarAba('aba-novo-ambiente')" class="text-[11px] text-sky-600 hover:underline font-bold">➕ Novo</button>
                    </div>
                    <ul class="mt-2 space-y-1 text-slate-600">
                        <li class="p-2 bg-slate-50 rounded border border-slate-200 flex justify-between items-center">
                            <span>📦 {c_amb}</span>
                            <span class="font-bold text-slate-700">R$ {c_p_venda:,.2f}</span>
                        </li>
                    </ul>
                </div>

                <div>
                    <div class="flex justify-between items-center pb-1 border-b border-slate-200 font-bold text-slate-800">
                        <span>⭐ Orçamentos</span>
                        <span class="text-[11px] text-emerald-600 font-bold">Ativo #1</span>
                    </div>
                    <p class="mt-1 text-slate-500 text-[11px]">Proposta de Fechamento Principal</p>
                </div>
            </div>

            <!-- COLUNA 2: PAINEL CENTRAL DINÂMICO -->
            <div class="lg:col-span-6 space-y-4">
                
                <!-- ABA 1: RESUMO FINANCEIRO E CONTRATO (DEFAULT) -->
                <div id="aba-resumo" class="tab-content active space-y-4">
                    <div class="bg-white border border-slate-300 rounded-xl p-5 shadow-sm space-y-3">
                        <div class="text-center pb-2 border-b border-slate-200">
                            <h2 class="text-xs font-bold text-sky-800 uppercase tracking-wide">CONTRATO IT{c_id:05d} vendido em: {c_data_venda} por {CURRENT_SESSION['user_nome']}</h2>
                        </div>

                        <div class="flex flex-wrap gap-2 justify-between items-center">
                            <div class="flex gap-2">
                                <a href="/minuta-contrato/{c_id}" target="_blank" class="px-3 py-1 bg-slate-100 hover:bg-slate-200 border border-slate-300 rounded text-xs font-semibold text-slate-700">🖨️ Imprimir Contrato</a>
                                <a href="/assinar/{c_id}" target="_blank" class="px-3 py-1 bg-sky-600 hover:bg-sky-500 text-white rounded text-xs font-bold shadow">✍️ Assinatura Digital</a>
                            </div>
                            <span class="text-[11px] text-slate-500 font-semibold">MVI Enterprise</span>
                        </div>

                        <div class="grid grid-cols-2 gap-3 text-xs pt-2">
                            <div><span class="text-slate-400 block text-[11px]">Cliente:</span><span class="font-bold text-sky-900 text-sm">{c_nome}</span></div>
                            <div><span class="text-slate-400 block text-[11px]">CPF / CNPJ:</span><span class="font-bold text-slate-700">{c_cpf}</span></div>
                            <div><span class="text-slate-400 block text-[11px]">Prazo de Entrega:</span><span class="font-bold text-slate-700">{c_prazo}</span></div>
                            <div><span class="text-slate-400 block text-[11px]">Telefone / Contato:</span><span class="font-bold text-slate-700">{c_tel}</span></div>
                        </div>
                    </div>

                    <!-- TABELA DE ENTRADA -->
                    <div class="bg-white border border-slate-300 rounded-xl overflow-hidden shadow-sm">
                        <div class="bg-slate-100 px-4 py-2 border-b border-slate-300 text-xs font-bold text-sky-800 text-center uppercase tracking-wide">ENTRADA</div>
                        <table class="w-full text-left text-xs border-collapse">
                            <thead class="bg-slate-50 border-b border-slate-200 text-slate-500 font-semibold">
                                <tr>
                                    <th class="py-2 px-3 text-center">#</th>
                                    <th class="py-2 px-3">Data Entrada</th>
                                    <th class="py-2 px-3 text-right">Valor</th>
                                    <th class="py-2 px-3">Tipo de Cobrança</th>
                                    <th class="py-2 px-3 text-center">Banco</th>
                                    <th class="py-2 px-3 text-center">Agência</th>
                                    <th class="py-2 px-3 text-center">Conta</th>
                                </tr>
                            </thead>
                            <tbody>
                                <tr class="border-b border-slate-100">
                                    <td class="py-2.5 px-3 text-center text-slate-500">1</td>
                                    <td class="py-2.5 px-3 text-slate-700">{hoje.strftime('%d/%m/%Y')}</td>
                                    <td class="py-2.5 px-3 font-bold text-emerald-700 text-right">R$ {c_entrada:,.2f}</td>
                                    <td class="py-2.5 px-3 text-sky-700 font-semibold">{c_mod}</td>
                                    <td class="py-2.5 px-3 text-center text-slate-400">—</td>
                                    <td class="py-2.5 px-3 text-center text-slate-400">—</td>
                                    <td class="py-2.5 px-3 text-center text-slate-400">—</td>
                                </tr>
                            </tbody>
                        </table>
                    </div>

                    <!-- TABELA DE PARCELAS DETALHADAS -->
                    <div class="bg-white border border-slate-300 rounded-xl overflow-hidden shadow-sm">
                        <div class="bg-slate-100 px-4 py-2 border-b border-slate-300 text-xs font-bold text-sky-800 text-center uppercase tracking-wide">CRONOGRAMA DE PARCELAS</div>
                        <div class="overflow-x-auto">
                            <table class="w-full text-left text-xs border-collapse">
                                <thead class="bg-slate-50 border-b border-slate-200 text-slate-500 font-semibold">
                                    <tr>
                                        <th class="py-2 px-3 text-center">#</th>
                                        <th class="py-2 px-3">Data Parcelas</th>
                                        <th class="py-2 px-3 text-right">Valor</th>
                                        <th class="py-2 px-3">Tipo de Cobrança</th>
                                        <th class="py-2 px-3 text-center">Bco</th>
                                        <th class="py-2 px-3 text-center">Ag</th>
                                        <th class="py-2 px-3 text-center">Conta</th>
                                        <th class="py-2 px-3">Observação</th>
                                        <th class="py-2 px-3 text-center">Ação</th>
                                    </tr>
                                </thead>
                                <tbody>{linhas_parcelas}</tbody>
                            </table>
                        </div>
                    </div>
                </div>

                <!-- ABA 2: DADOS DO CLIENTE & BUSCA DE CEP -->
                <div id="aba-cliente" class="tab-content bg-white border border-slate-300 rounded-xl p-5 shadow-sm space-y-4 text-xs">
                    <h3 class="font-bold text-slate-800 uppercase pb-1 border-b border-slate-200">👤 Ficha Cadastral do Cliente & Endereços</h3>
                    <form action="/salvar-dados-completos-cliente" method="post" class="space-y-3">
                        <input type="hidden" name="orcamento_id" value="{c_id}">
                        <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
                            <div class="sm:col-span-2">
                                <label class="block text-slate-500 mb-1">Nome Completo</label>
                                <input type="text" name="cliente_nome" value="{c_nome}" required class="w-full p-2 bg-slate-50 border border-slate-300 rounded font-bold">
                            </div>
                            <div>
                                <label class="block text-slate-500 mb-1">CPF</label>
                                <input type="text" name="cliente_cpf" value="{c_cpf if c_cpf != 'Não informado' else ''}" placeholder="000.000.000-00" class="w-full p-2 bg-slate-50 border border-slate-300 rounded">
                            </div>
                            <div>
                                <label class="block text-slate-500 mb-1">RG</label>
                                <input type="text" name="cliente_rg" value="{c_rg if c_rg != '—' else ''}" placeholder="RG" class="w-full p-2 bg-slate-50 border border-slate-300 rounded">
                            </div>
                            <div>
                                <label class="block text-slate-500 mb-1">Telefone Principal</label>
                                <input type="text" name="cliente_telefone" value="{c_tel if c_tel != '—' else ''}" placeholder="WhatsApp" class="w-full p-2 bg-slate-50 border border-slate-300 rounded">
                            </div>
                            <div>
                                <label class="block text-slate-500 mb-1">E-mail</label>
                                <input type="email" name="cliente_email" value="{c_email}" placeholder="E-mail" class="w-full p-2 bg-slate-50 border border-slate-300 rounded">
                            </div>
                        </div>

                        <div class="border-t border-slate-200 pt-3 grid grid-cols-1 sm:grid-cols-2 gap-4">
                            <div class="bg-slate-50 p-3 rounded-lg border border-slate-200 space-y-2">
                                <label class="font-bold text-slate-700 block">📬 Endereço Postal</label>
                                <div class="flex gap-2">
                                    <input type="text" id="cep_postal" name="cliente_cep_postal" value="{c_cep_post}" placeholder="CEP" class="w-1/2 p-2 bg-white border border-slate-300 rounded">
                                    <button type="button" onclick="buscarCep('postal')" class="w-1/2 px-2 py-1 bg-sky-600 text-white rounded font-bold">🔍 Buscar CEP</button>
                                </div>
                                <textarea id="end_postal" name="cliente_endereco_postal" rows="2" placeholder="Rua, Número, Bairro, Cidade - UF" class="w-full p-2 bg-white border border-slate-300 rounded">{c_end_post}</textarea>
                            </div>
                            <div class="bg-slate-50 p-3 rounded-lg border border-slate-200 space-y-2">
                                <label class="font-bold text-slate-700 block">🚚 Endereço da Obra</label>
                                <div class="flex gap-2">
                                    <input type="text" id="cep_entrega" name="cliente_cep_entrega" value="{c_cep_ent}" placeholder="CEP Obra" class="w-1/2 p-2 bg-white border border-slate-300 rounded">
                                    <button type="button" onclick="buscarCep('entrega')" class="w-1/2 px-2 py-1 bg-sky-600 text-white rounded font-bold">🔍 Buscar CEP</button>
                                </div>
                                <textarea id="end_entrega" name="cliente_endereco_entrega" rows="2" placeholder="Endereço da Instalação..." class="w-full p-2 bg-white border border-slate-300 rounded">{c_end_ent}</textarea>
                            </div>
                        </div>

                        <button type="submit" class="w-full py-2.5 bg-sky-600 hover:bg-sky-500 text-white font-bold rounded shadow">💾 Salvar Dados do Cliente</button>
                    </form>
                </div>

                <!-- ABA 3: MESA DE NEGOCIAÇÃO E FECHAMENTO COM TODAS AS OPÇÕES E OLHO -->
                <div id="aba-mesa" class="tab-content bg-white border border-slate-300 rounded-xl p-5 shadow-sm space-y-4 text-xs">
                    <div class="flex justify-between items-center pb-1 border-b border-slate-200">
                        <h3 class="font-bold text-slate-800 uppercase">💼 Mesa de Negociação & Fechamento Financeiro</h3>
                        <input type="hidden" id="preco_bruto_base" value="{c_p_bruto if c_p_bruto > 0 else c_p_venda}">
                    </div>

                    <form id="form_mesa_negociacao" action="/salvar-negociacao-mesa" method="post" class="space-y-4" onkeydown="impedirEnterSubmit(event)">
                        <input type="hidden" name="orcamento_id" value="{c_id}">

                        <div class="grid grid-cols-1 sm:grid-cols-3 gap-3">
                            <!-- VALOR DE VENDA MANUAL (CALCULA DESCONTO AUTOMATICAMENTE AO DIGITAR) -->
                            <div>
                                <label class="block text-slate-500 mb-1 font-semibold">Valor Venda (R$)</label>
                                <input type="number" step="1" name="preco_venda" id="preco_venda_input" value="{c_p_venda}" required oninput="calcularDescontoPorValorVenda()" class="w-full p-2 bg-slate-50 border border-slate-300 rounded font-bold text-sky-800 text-sm focus:border-sky-500">
                            </div>

                            <!-- DESCONTO (%) + BOTÃO DE SIMULAÇÃO -->
                            <div>
                                <label class="block text-slate-500 mb-1 font-semibold">Desconto (%)</label>
                                <div class="flex gap-1.5">
                                    <input type="number" step="0.1" name="desconto_pct" id="desconto_pct_input" value="{c_desc_pct}" oninput="calcularValorVendaPorDesconto()" class="w-2/3 p-2 bg-slate-50 border border-slate-300 rounded font-bold">
                                    <button type="button" onclick="calcularValorVendaPorDesconto()" class="w-1/3 px-2 py-1 bg-amber-500 hover:bg-amber-400 text-slate-900 font-bold rounded text-[11px]" title="Atualizar simulação de desconto">
                                        ⚡ Simular
                                    </button>
                                </div>
                            </div>

                            <!-- VALOR DE ENTRADA -->
                            <div>
                                <label class="block text-slate-500 mb-1 font-semibold">Entrada (R$)</label>
                                <input type="number" step="100" name="entrada_valor" id="entrada_valor_input" value="{c_entrada}" required oninput="recalcularLucroEMesa()" class="w-full p-2 bg-slate-50 border border-slate-300 rounded font-bold text-emerald-700 text-sm">
                            </div>
                        </div>

                        <!-- FORMA DE PAGAMENTO COM SELEÇÃO DE PARCELAS EMBUTIDA -->
                        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                            <div>
                                <label class="block text-slate-500 mb-1 font-semibold">Forma de Pagamento</label>
                                <select name="forma_opcao" id="forma_opcao_select" onchange="atualizarFormaPagamento()" class="w-full p-2 bg-slate-50 border border-slate-300 rounded font-semibold text-slate-800">
                                    <option value="Entrada PIX + 3 à Vista" {"selected" if "3 à Vista" in c_mod or "PIX + 3" in c_mod else ""}>Entrada PIX + 3 à Vista (PIX/TED)</option>
                                    <option value="Entrada + Cartão de Crédito" {"selected" if "Cartão" in c_mod and "3 à Vista" not in c_mod else ""}>Entrada + Cartão de Crédito</option>
                                    <option value="Entrada + Boleto Bancário" {"selected" if "Boleto" in c_mod else ""}>Entrada + Boleto Bancário</option>
                                    <option value="PIX Integral à Vista" {"selected" if "PIX Integral" in c_mod else ""}>PIX Integral à Vista (5% OFF)</option>
                                </select>
                                <input type="hidden" name="modalidade_pagamento" id="modalidade_pagamento_hidden" value="{c_mod}">
                            </div>

                            <div id="box_parcelas_dinamico">
                                <label class="block text-slate-500 mb-1 font-semibold" id="label_vezes">Quantidade de Parcelas</label>
                                <select name="num_parcelas" id="num_parcelas_select" onchange="atualizarFormaPagamento()" class="w-full p-2 bg-slate-50 border border-slate-300 rounded font-bold text-slate-800">
                                    <!-- Preenchido dinamicamente via JS -->
                                </select>
                            </div>
                        </div>

                        <!-- LUCRO LÍQUIDO COM OLHO DE VISUALIZAÇÃO -->
                        <div class="p-3.5 bg-emerald-50 border border-emerald-200 rounded-lg flex justify-between items-center">
                            <div>
                                <span class="font-bold text-emerald-900 block text-xs">Lucro Líquido da Operação:</span>
                                <span id="valor_lucro_operacao" data-real="R$ {c_lucro:,.2f}" class="font-black text-emerald-700 text-lg">R$ {c_lucro:,.2f}</span>
                            </div>
                            <button type="button" onclick="alternarOlhoLucro()" id="btn_olho_lucro" title="Ocultar / Revelar Lucro" class="p-2 bg-white hover:bg-emerald-100 border border-emerald-300 rounded-lg text-slate-700 text-sm font-bold shadow-sm">
                                👁️
                            </button>
                        </div>

                        <button type="submit" class="w-full py-3 bg-sky-600 hover:bg-sky-500 text-white font-bold rounded-lg text-xs shadow-md">
                            💾 Salvar Negociação da Pasta
                        </button>
                    </form>
                </div>

                <!-- ABA 4: NOVO AMBIENTE -->
                <div id="aba-novo-ambiente" class="tab-content bg-white border border-slate-300 rounded-xl p-5 shadow-sm space-y-4 text-xs">
                    <h3 class="font-bold text-slate-800 uppercase pb-1 border-b border-slate-200">➕ Lançar / Adicionar Novo Ambiente</h3>
                    <form action="/salvar-dados-completos-cliente" method="post" class="space-y-3">
                        <input type="hidden" name="orcamento_id" value="0">
                        <input type="text" name="cliente_nome" placeholder="Nome do Cliente / Projeto" required class="w-full p-2 bg-slate-50 border border-slate-300 rounded font-bold">
                        <input type="text" name="cliente_telefone" placeholder="Telefone / WhatsApp" required class="w-full p-2 bg-slate-50 border border-slate-300 rounded">
                        <textarea name="descricao_manual" rows="3" placeholder="Descreva o novo ambiente (Ex: Cozinha com Ilha, Tamponamento 25mm, Portas em Lacca...)" required class="w-full p-2 bg-slate-50 border border-slate-300 rounded"></textarea>
                        <button type="submit" class="w-full py-2.5 bg-sky-600 hover:bg-sky-500 text-white font-bold rounded shadow">⚡ Criar Pasta & Salvar Ambiente</button>
                    </form>
                </div>

                <!-- ABA 5: PROMOB INTEGRADOR -->
                <div id="aba-promob" class="tab-content bg-white border border-slate-300 rounded-xl p-5 shadow-sm space-y-4 text-xs">
                    <h3 class="font-bold text-slate-800 uppercase pb-1 border-b border-slate-200">🚀 Importação Direta de Arquivo Promob</h3>
                    <form action="/importar-promob" method="post" enctype="multipart/form-data" class="space-y-3">
                        <input type="text" name="cliente_nome" value="{c_nome}" placeholder="Nome do Cliente" required class="w-full p-2 bg-slate-50 border border-slate-300 rounded font-bold">
                        <input type="text" name="cliente_telefone" value="{c_tel}" placeholder="WhatsApp" required class="w-full p-2 bg-slate-50 border border-slate-300 rounded">
                        <input type="text" name="cliente_ambiente" value="{c_amb}" placeholder="Ambiente" required class="w-full p-2 bg-slate-50 border border-slate-300 rounded">
                        <div class="p-3 bg-slate-50 border border-slate-200 rounded">
                            <label class="block font-bold text-slate-700 mb-1">Selecione o arquivo exportado (.xml, .csv, .txt, .cut):</label>
                            <input type="file" name="arquivo_promob" accept=".xml,.csv,.txt,.cut" required class="w-full text-slate-600">
                        </div>
                        <button type="submit" class="w-full py-2.5 bg-sky-600 hover:bg-sky-500 text-white font-bold rounded shadow">⚡ Processar Peças & Gerar Orçamento</button>
                    </form>
                </div>

            </div>

            <!-- COLUNA 3: RESUMO DA VENDA & CHECKLIST LATERAL (3 colunas) -->
            <div class="lg:col-span-3 space-y-4">
                
                <div class="bg-white border border-slate-300 rounded-xl p-5 shadow-sm space-y-3 text-xs">
                    <h3 class="font-bold text-sky-800 pb-1 border-b border-slate-200 uppercase tracking-wide">Resumo da Venda</h3>
                    
                    <div class="space-y-1.5 text-slate-600">
                        <div class="flex justify-between"><span class="text-slate-400">Responsável:</span> <span class="font-semibold text-slate-800">{CURRENT_SESSION['user_nome']}</span></div>
                        <div class="flex justify-between"><span class="text-slate-400">Orçamento:</span> <span class="font-semibold text-slate-800">#1</span></div>
                        <div class="flex justify-between"><span class="text-slate-400">Tipo de Venda:</span> <span class="font-semibold text-slate-800">Normal</span></div>
                    </div>

                    <div class="pt-2 border-t border-slate-200 space-y-1">
                        <div class="flex justify-between items-center"><span class="text-slate-500 font-semibold">Valor da Venda:</span> <span class="font-bold text-sky-700 text-sm">R$ {c_p_venda:,.2f}</span></div>
                        <div class="flex justify-between items-center"><span class="text-slate-500 font-semibold">Valor da Entrada:</span> <span class="font-bold text-emerald-600 text-sm">R$ {c_entrada:,.2f}</span></div>
                        <div class="flex justify-between items-center"><span class="text-slate-400">Opção de Pagto:</span> <span class="font-semibold text-slate-700">{c_mod}</span></div>
                        <div class="flex justify-between items-center"><span class="text-slate-400">Parcelas:</span> <span class="font-semibold text-slate-700">1 + {c_parc}x</span></div>
                    </div>

                    <div class="pt-2 border-t border-slate-200">
                        <span class="text-[11px] font-bold text-slate-500 block mb-1">Ambientes Vendidos</span>
                        <div class="flex justify-between text-[11px] font-medium text-slate-700 bg-slate-50 p-2 rounded border border-slate-200">
                            <span>{c_amb}</span>
                            <span class="font-bold">R$ {c_p_venda:,.2f}</span>
                        </div>
                    </div>
                </div>

                <div class="bg-white border border-slate-300 rounded-xl p-5 shadow-sm space-y-3 text-xs">
                    <h3 class="font-bold text-slate-800 pb-1 border-b border-slate-200 uppercase tracking-wide">Check List</h3>
                    
                    <ul class="space-y-2.5">
                        <li class="flex justify-between items-center">
                            <span class="font-medium text-slate-700">Dados do Cliente:</span>
                            <span class="w-3.5 h-3.5 rounded-full {'bg-emerald-500' if c_cpf != 'Não informado' else 'bg-rose-500'}"></span>
                        </li>
                        <li class="flex justify-between items-center">
                            <span class="font-medium text-slate-700">Aprovação Comercial:</span>
                            <span class="w-3.5 h-3.5 rounded-full {'bg-emerald-500' if c_aut_desc else 'bg-amber-500'}"></span>
                        </li>
                        <li class="flex justify-between items-center">
                            <span class="font-medium text-slate-700">Aprovação Financeira:</span>
                            <span class="w-3.5 h-3.5 rounded-full {'bg-emerald-500' if c_lib_fin else 'bg-slate-300'}"></span>
                        </li>
                        <li class="flex justify-between items-center">
                            <span class="font-medium text-slate-700">Assinatura do Contrato:</span>
                            <span class="w-3.5 h-3.5 rounded-full {'bg-emerald-500' if c_assinado else 'bg-slate-300'}"></span>
                        </li>
                    </ul>
                </div>

            </div>

        </div>

    </div>

    <!-- RODAPÉ ERP -->
    <footer class="text-center py-4 text-[11px] text-slate-400">
        Copyright © 2026 - MVI Sistemas de Marcenaria Sob Medida. Todos os direitos reservados.
    </footer>

    <!-- JAVASCRIPT DE CONTROLE DAS ABAS, SIMULAÇÃO E OLHO -->
    <script>
        var parcelasSalvas = {c_parc};

        function abrirDashboardGeral() {{
            document.getElementById('view-dashboard-geral').style.display = "block";
            document.getElementById('view-pasta-cliente').style.display = "none";
            document.getElementById('tab-top-geral').className = "px-4 py-2 rounded-t-lg font-bold text-sky-700 bg-white shadow-sm border-t-2 border-sky-600";
            if (document.getElementById('tab-top-pasta')) {{
                document.getElementById('tab-top-pasta').className = "flex items-center rounded-t-lg bg-slate-200 text-slate-600";
            }}
        }}

        function abrirPastaAtiva() {{
            document.getElementById('view-dashboard-geral').style.display = "none";
            document.getElementById('view-pasta-cliente').style.display = "block";
            document.getElementById('tab-top-geral').className = "px-4 py-2 rounded-t-lg font-semibold bg-slate-200 text-slate-600";
            if (document.getElementById('tab-top-pasta')) {{
                document.getElementById('tab-top-pasta').className = "flex items-center rounded-t-lg bg-white text-sky-700 font-bold shadow-sm border-t-2 border-sky-600";
            }}
        }}

        function fecharPastaAtiva() {{
            window.location.href = "/fechar-pasta-ativa";
        }}

        function mudarAba(abaId) {{
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            document.querySelectorAll('.tree-item').forEach(b => b.classList.remove('active'));
            
            var targetAba = document.getElementById(abaId);
            var targetBtn = document.getElementById('btn-' + abaId);
            
            if (targetAba) targetAba.classList.add('active');
            if (targetBtn) targetBtn.classList.add('active');
        }}

        function impedirEnterSubmit(event) {{
            if (event.key === "Enter" || event.keyCode === 13) {{
                event.preventDefault();
                recalcularLucroEMesa();
                return false;
            }}
        }}

        function calcularDescontoPorValorVenda() {{
            var precoBruto = parseFloat(document.getElementById('preco_bruto_base').value) || 0;
            var precoVendaManual = parseFloat(document.getElementById('preco_venda_input').value) || 0;

            if (precoBruto > 0 && precoVendaManual > 0) {{
                var desc = ((precoBruto - precoVendaManual) / precoBruto) * 100.0;
                desc = Math.max(desc, 0);
                document.getElementById('desconto_pct_input').value = desc.toFixed(1);
            }}
            recalcularLucroEMesa();
        }}

        function calcularValorVendaPorDesconto() {{
            var precoBruto = parseFloat(document.getElementById('preco_bruto_base').value) || 0;
            var descPct = parseFloat(document.getElementById('desconto_pct_input').value) || 0;

            if (precoBruto > 0) {{
                var precoFinal = Math.round(precoBruto * (1.0 - (descPct / 100.0)));
                document.getElementById('preco_venda_input').value = precoFinal;
            }}
            recalcularLucroEMesa();
        }}

        function atualizarFormaPagamento() {{
            var opcao = document.getElementById('forma_opcao_select').value;
            var boxParc = document.getElementById('box_parcelas_dinamico');
            var selectParc = document.getElementById('num_parcelas_select');
            var hiddenMod = document.getElementById('modalidade_pagamento_hidden');

            selectParc.innerHTML = "";

            if (opcao === "Entrada PIX + 3 à Vista") {{
                boxParc.style.display = "block";
                selectParc.innerHTML = `
                    <option value="1" ` + (parcelasSalvas == 1 ? 'selected' : '') + `>1x (À Vista)</option>
                    <option value="2" ` + (parcelasSalvas == 2 ? 'selected' : '') + `>2x (30/60 dias)</option>
                    <option value="3" ` + (parcelasSalvas == 3 ? 'selected' : '') + `>3x (30/60/90 dias)</option>
                `;
                hiddenMod.value = "Entrada PIX + 3 à Vista";
            }} else if (opcao === "Entrada + Cartão de Crédito") {{
                boxParc.style.display = "block";
                for (var i = 1; i <= 12; i++) {{
                    selectParc.innerHTML += `<option value="` + i + `" ` + (parcelasSalvas == i ? 'selected' : '') + `>` + i + `x no Cartão</option>`;
                }}
                hiddenMod.value = "Entrada + " + selectParc.value + "x no Cartão";
            }} else if (opcao === "Entrada + Boleto Bancário") {{
                boxParc.style.display = "block";
                for (var i = 1; i <= 24; i++) {{
                    selectParc.innerHTML += `<option value="` + i + `" ` + (parcelasSalvas == i ? 'selected' : '') + `>` + i + `x no Boleto</option>`;
                }}
                hiddenMod.value = "Entrada + " + selectParc.value + "x no Boleto";
            }} else {{
                boxParc.style.display = "none";
                selectParc.innerHTML = `<option value="1" selected>1x (Integral)</option>`;
                hiddenMod.value = "PIX Integral à Vista (5% OFF)";
            }}

            recalcularLucroEMesa();
        }}

        function recalcularLucroEMesa() {{
            var precoVenda = parseFloat(document.getElementById('preco_venda_input').value) || 0;
            var custoEstimado = precoVenda * 0.50;
            var impostoComissao = precoVenda * 0.10;
            var lucroFinal = Math.max(precoVenda - (custoEstimado + impostoComissao), 0);

            var elem = document.getElementById('valor_lucro_operacao');
            var lucroFormatado = "R$ " + lucroFinal.toLocaleString('pt-BR', {{ minimumFractionDigits: 2, maximumFractionDigits: 2 }});
            elem.setAttribute('data-real', lucroFormatado);

            if (lucroVisivel) {{
                elem.innerText = lucroFormatado;
            }}
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
                elem.style.filter = "none";
            }} else {{
                elem.innerText = "••••••••";
                btn.innerText = "🙈";
                elem.style.filter = "blur(4px)";
            }}
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
            atualizarFormaPagamento();
        }};
    </script>
</body></html>"""

# ==============================================================================
# 5. FASTAPI ROUTES (DECLARADAS APÓS TODAS AS FUNÇÕES DE RENDERIZAÇÃO)
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

@app.get("/fechar-pasta-ativa", response_class=HTMLResponse)
def fechar_pasta_ativa_route():
    CURRENT_SESSION["cliente_ativo_id"] = None
    return RedirectResponse(url="/painel-get", status_code=303)

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
    if orcamento_id == 0:
        CURRENT_SESSION["cliente_ativo_id"] = None
    else:
        CURRENT_SESSION["cliente_ativo_id"] = orcamento_id
    return RedirectResponse(url="/painel-get", status_code=303)

@app.post("/salvar-negociacao-mesa", response_class=HTMLResponse)
def salvar_negociacao_mesa(
    orcamento_id: int = Form(...),
    preco_venda: float = Form(0.0),
    desconto_pct: float = Form(0.0),
    markup: float = Form(2.2),
    forma_opcao: str = Form("Entrada + Cartão de Crédito"),
    num_parcelas: int = Form(1),
    entrada_valor: float = Form(0.0)
):
    modalidade = f"{forma_opcao} ({num_parcelas}x)" if forma_opcao != "PIX Integral à Vista" else forma_opcao
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("SELECT custo_materiais, custo_mao_obra, custo_frete_montagem FROM orcamentos WHERE id = ?", (orcamento_id,))
    orc = cursor.fetchone()
    
    custo_tot = (float(orc["custo_materiais"] or 0) + float(orc["custo_mao_obra"] or 0) + float(orc["custo_frete_montagem"] or 0)) if orc else (preco_venda * 0.5)
    lucro_final = round(preco_venda - (custo_tot + (preco_venda * 0.10)))
    
    saldo = max(preco_venda - entrada_valor, 0.0)
    v_parc = round(saldo / num_parcelas) if num_parcelas > 0 else 0.0

    precisa_aprov = (desconto_pct > 3.0 and CURRENT_SESSION["user_perfil"] == "vendedor")
    desconto_autorizado = 0 if precisa_aprov else 1
    status = "Aguardando Liberação de Desconto" if precisa_aprov else "Em Negociação"

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
    """, (round(preco_venda), desconto_pct, round(preco_venda), markup, modalidade, round(entrada_valor), num_parcelas, v_parc, lucro_final, desconto_autorizado, status, orcamento_id))
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
        ) VALUES (1, ?, ?, ?, ?, '45 dias úteis', ?, 'Importado Promob', ?, ?, ?, ?, ?)
    """, (agora, cliente_nome, cliente_telefone, cliente_ambiente, (date.today() + timedelta(days=45)).strftime("%Y-%m-%d"), calc["total_mat"], calc["preco_bruto"], calc["preco_venda"], calc["lucro"], desc_auto))
    conn.commit()
    CURRENT_SESSION["cliente_ativo_id"] = cursor.lastrowid
    conn.close()

    return RedirectResponse(url="/painel-get", status_code=303)

@app.post("/enviar-solicitacao-lead", response_class=HTMLResponse)
async def submit_lead_route(
    nome: str = Form(...),
    whatsapp: str = Form(...),
    area_m2_total: float = Form(180.0),
    cidade: str = Form(...),
    amb_cozinha: int = Form(0),
    amb_lavanderia: int = Form(0),
    amb_sala: int = Form(0),
    amb_sacada: int = Form(0),
    amb_gourmet: int = Form(0),
    qtd_dorm_solteiro: int = Form(0),
    qtd_dorm_casal: int = Form(0),
    qtd_banheiro: int = Form(0),
    espessura_caixa: str = Form("MDF 18mm (Reforçado)"),
    cor_caixa: str = Form("Branco TX"),
    espessura_porta: str = Form("MDF 18mm"),
    cor_porta: str = Form("Amadeirado"),
    acabamento_porta: str = Form("Madeira Lisa Tradicional"),
    marca_ferragens: str = Form("Blum (Linha Blumotion Áustria)"),
    espessura_tamponamento: str = Form("Tamponamento 25mm"),
    descricao: str = Form(""),
    planta: UploadFile = File(...),
    inspiracao: UploadFile = File(None)
):
    ambientes_selecionados = []
    if amb_cozinha: ambientes_selecionados.append("Cozinha")
    if amb_lavanderia: ambientes_selecionados.append("Lavanderia")
    if amb_sala: ambientes_selecionados.append("Sala")
    if amb_sacada: ambientes_selecionados.append("Sacada")
    if amb_gourmet: ambientes_selecionados.append("Área Gourmet")
    if qtd_dorm_solteiro > 0: ambientes_selecionados.append(f"{qtd_dorm_solteiro}x Dorm. Solteiro")
    if qtd_dorm_casal > 0: ambientes_selecionados.append(f"{qtd_dorm_casal}x Dorm. Casal/Suíte")
    if qtd_banheiro > 0: ambientes_selecionados.append(f"{qtd_banheiro}x Banheiro")
    
    if not ambientes_selecionados:
        ambientes_selecionados = ["Projeto Completo Sob Medida"]

    ambientes_str = " + ".join(ambientes_selecionados)

    empresa = get_empresa_dados(1)
    calc = calcular_engenharia(
        ambientes_selecionados, area_m2_total,
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
        ) VALUES (1, ?, ?, ?, ?, '45 dias úteis', ?, 'Novo Lead Instagram', ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        agora, nome, whatsapp, ambientes_str, (date.today() + timedelta(days=45)).strftime("%Y-%m-%d"),
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
        espessura_porta, cor_porta, acabamento_porta, marca_ferragens, espessura_tamponamento,
        ambientes_str
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
    forma_pagamento: str = Form("Boleto Bancário"),
    entrada_valor: float = Form(0.0),
    num_parcelas: int = Form(1)
):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    if orcamento_id == 0:
        agora = datetime.now().strftime("%d/%m/%Y %H:%M")
        pv_base = round(entrada_valor * 2.5 if entrada_valor > 0 else 15000.0)
        pv_final = round(pv_base * (1.0 - (desconto_pct / 100.0)))
        lucro_final = round(pv_final * 0.40)

        cursor.execute("""
            INSERT INTO orcamentos (
                empresa_id, criado_em, cliente_nome, cliente_cpf, cliente_rg, cliente_rg_emissor,
                cliente_nascimento, cliente_pais, cliente_cidade, cliente_email,
                cliente_telefone, cliente_telefone_2, cliente_cep_postal, cliente_endereco_postal,
                cliente_cep_entrega, cliente_endereco_entrega, cliente_ambiente, descricao_manual, desconto_pct,
                desconto_autorizado, status, preco_bruto, preco_venda, lucro_liquido, forma_pagamento, entrada_valor,
                num_parcelas, prazo_entrega, data_entrega_prevista
            ) VALUES (
                1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Projeto Sob Medida', ?, ?, 1, 'Em Negociação',
                ?, ?, ?, ?, ?, ?, '45 dias úteis', ?
            )
        """, (
            agora, cliente_nome, cliente_cpf, cliente_rg, cliente_rg_emissor,
            cliente_nascimento, cliente_pais, cliente_cidade, cliente_email,
            cliente_telefone, cliente_telefone_2, cliente_cep_postal, cliente_endereco_postal,
            cliente_cep_entrega, cliente_endereco_entrega, descricao_manual, desconto_pct,
            pv_base, pv_final, lucro_final, forma_pagamento, round(entrada_valor), num_parcelas,
            (date.today() + timedelta(days=45)).strftime("%Y-%m-%d")
        ))
        conn.commit()
        CURRENT_SESSION["cliente_ativo_id"] = cursor.lastrowid
    else:
        cursor.execute("SELECT preco_bruto, preco_venda, custo_materiais, custo_mao_obra, custo_frete_montagem FROM orcamentos WHERE id = ?", (orcamento_id,))
        orc = cursor.fetchone()
        if orc:
            pv_base = float(orc["preco_bruto"] or orc["preco_venda"] or 0)
            custo_tot = float(orc["custo_materiais"] or 0) + float(orc["custo_mao_obra"] or 0) + float(orc["custo_frete_montagem"] or 0)
            pv_final = round(pv_base * (1.0 - (desconto_pct / 100.0)))
            lucro_final = round(pv_final - (custo_tot + (pv_final * 0.10)))

            cursor.execute("""
                UPDATE orcamentos SET
                    cliente_nome = ?, cliente_cpf = ?, cliente_rg = ?, cliente_rg_emissor = ?,
                    cliente_nascimento = ?, cliente_pais = ?, cliente_cidade = ?, cliente_email = ?,
                    cliente_telefone = ?, cliente_telefone_2 = ?, cliente_cep_postal = ?, cliente_endereco_postal = ?,
                    cliente_cep_entrega = ?, cliente_endereco_entrega = ?, descricao_manual = ?, desconto_pct = ?,
                    preco_venda = ?, lucro_liquido = ?, forma_pagamento = ?, entrada_valor = ?, num_parcelas = ?
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
    cursor.execute("UPDATE orcamentos SET adendo_descricao = ?, adendo_valor = ?, status = 'Adendo Adicionado' WHERE id = ?", (adendo_descricao, round(adendo_valor), orcamento_id))
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
        writer.writerow([r["id"], r["criado_em"], r["cliente_nome"], r["cliente_cpf"], r["cliente_telefone"], r["cliente_ambiente"], f"{round(float(r['preco_venda'] or 0))}", r["status"]])
    conn.close()
    return Response(content=output.getvalue().encode('utf-8-sig'), media_type="text/csv", headers={"Content-Disposition": f"attachment; filename=relatorio-mvi.csv"})

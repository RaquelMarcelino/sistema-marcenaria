from fastapi import FastAPI, Form, UploadFile, File, Response, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
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
DB_PATH = "mvi_production_v48.db"

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
            nome_empresa TEXT DEFAULT 'MVI Móveis Planejados',
            cnpj TEXT DEFAULT '',
            endereco TEXT DEFAULT '',
            telefone TEXT DEFAULT '',
            email TEXT DEFAULT '',
            pix TEXT DEFAULT '',
            precos_json TEXT DEFAULT '{}',
            chave_mestra TEXT DEFAULT 'MVI2026',
            desconto_max_vendedor REAL DEFAULT 3.0,
            comissao_padrao_pct REAL DEFAULT 4.0
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            email TEXT PRIMARY KEY,
            senha TEXT,
            nome TEXT,
            perfil TEXT, -- 'adm', 'gerente', 'vendedor', 'financeiro', 'liberacao'
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
            vendedor_responsavel TEXT DEFAULT 'Raquel Marcelino',
            vendedor_email TEXT DEFAULT 'raquel@mvi.com',
            cliente_nome TEXT,
            cliente_cpf TEXT DEFAULT '',
            cliente_rg TEXT DEFAULT '',
            cliente_rg_emissor TEXT DEFAULT '',
            cliente_nascimento TEXT DEFAULT '',
            cliente_pais TEXT DEFAULT 'Brasil',
            cliente_cidade TEXT DEFAULT 'São Paulo',
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
            cliente_ambiente TEXT DEFAULT 'Cozinha Planejada',
            descricao_promob TEXT DEFAULT '',
            descricao_manual TEXT DEFAULT '',
            adendo_descricao TEXT DEFAULT '',
            adendo_valor REAL DEFAULT 0,
            prazo_entrega TEXT DEFAULT '25 dias úteis',
            prazo_garantia TEXT DEFAULT '12 (doze) meses',
            data_entrega_prevista TEXT DEFAULT '',
            status TEXT DEFAULT 'Em Negociação',
            potencial_cliente TEXT DEFAULT 'Morno',
            check_dados INTEGER DEFAULT 0,
            check_comercial INTEGER DEFAULT 1,
            check_financeiro INTEGER DEFAULT 0,
            check_contrato INTEGER DEFAULT 0,
            custo_materiais REAL DEFAULT 0,
            custo_mao_obra REAL DEFAULT 0,
            custo_frete_montagem REAL DEFAULT 0,
            imposto_pct REAL DEFAULT 6,
            comissao_pct REAL DEFAULT 4.0,
            comissao_valor REAL DEFAULT 0,
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
            versoes_orcamentos_json TEXT DEFAULT '[]',
            versao_ativa_id INTEGER DEFAULT 1,
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
            INSERT INTO empresas (id, slug, nome_empresa, cnpj, endereco, telefone, email, pix, precos_json, chave_mestra, desconto_max_vendedor, comissao_padrao_pct)
            VALUES (1, 'mvi', 'MVI Móveis Planejados', '', '', '', '', '', ?, 'MVI2026', 3.0, 4.0)
        """, (json.dumps(precos_iniciais),))
        
        cursor.execute("INSERT OR REPLACE INTO usuarios VALUES ('admin@mvi.com', '123456', 'Administrador Geral MVI', 'adm', 1, '', 1, 1)")
        cursor.execute("INSERT OR REPLACE INTO usuarios VALUES ('gerente@mvi.com', '123456', 'Gerente Comercial', 'gerente', 1, '', 1, 1)")
        cursor.execute("INSERT OR REPLACE INTO usuarios VALUES ('raquel@mvi.com', '123456', 'Raquel Marcelino', 'vendedor', 1, '', 1, 1)")
        cursor.execute("INSERT OR REPLACE INTO usuarios VALUES ('financeiro@mvi.com', '123456', 'Auditor Financeiro', 'financeiro', 1, '', 1, 1)")
        cursor.execute("INSERT OR REPLACE INTO usuarios VALUES ('liberacao@mvi.com', '123456', 'Equipe de Liberação & Fábrica', 'liberacao', 1, '', 1, 1)")
        conn.commit()

    conn.close()

init_db()

CURRENT_SESSION = {
    "user_email": "admin@mvi.com",
    "user_nome": "Administrador Geral",
    "user_perfil": "adm",
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
        "cnpj": "", "endereco": "", "telefone": "",
        "email": "", "pix": "", "precos_json": "{}", "chave_mestra": "MVI2026",
        "desconto_max_vendedor": 3.0, "comissao_padrao_pct": 4.0
    }

def get_metricas():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT preco_venda, adendo_valor, lucro_liquido, status, valor_recebido, comissao_valor FROM orcamentos WHERE empresa_id = ?", (CURRENT_SESSION.get("empresa_id", 1),))
    rows = cursor.fetchall()
    conn.close()
    
    total = len(rows)
    fat_total, lucro_total, aprovados, comissao_total = 0.0, 0.0, 0, 0.0
    
    for r in rows:
        st = r["status"] or "Em Negociação"
        pv = float(r["preco_venda"] or 0) + float(r["adendo_valor"] or 0)
        lucro = float(r["lucro_liquido"] or 0)
        com = float(r["comissao_valor"] or (pv * 0.04))
        
        if st in ["Aprovado", "Em Produção", "Entregue", "Liberado para Financeiro & Fábrica", "Contrato Assinado Digitalmente", "Desconto Autorizado pela Diretoria"]:
            fat_total += pv
            lucro_total += lucro
            comissao_total += com
            aprovados += 1

    taxa = (aprovados / total * 100.0) if total > 0 else 0.0
    ticket = (fat_total / aprovados) if aprovados > 0 else 0.0
    
    return {"total": total, "aprovados": aprovados, "faturamento": fat_total, "lucro": lucro_total, "ticket": ticket, "taxa": taxa, "comissoes": comissao_total}

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
    comissao_venda = round(preco_venda * (float(empresa.get("comissao_padrao_pct", 4.0)) / 100.0))
    lucro = round(preco_venda - (total_materiais + custo_mo + custo_frete + (preco_venda * 0.10)))

    return {
        "items": items, "total_mat": total_materiais,
        "custo_mo": custo_mo, "custo_frete": custo_frete,
        "preco_bruto": preco_bruto, "preco_venda": preco_venda, "lucro": lucro,
        "comissao": comissao_venda,
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
# 4. FUNÇÕES DE RENDERIZAÇÃO
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
            <p class="text-xs text-slate-400">Hub Integrador Promob & Gestão Comercial</p>
        </div>
        {erro}
        <form action="/painel" method="post" class="space-y-4">
            <div><label class="block text-xs font-semibold text-slate-300 uppercase mb-1">E-mail Corporativo</label>
            <input type="email" name="username" required placeholder="seuemail@mvi.com" class="w-full px-4 py-3 bg-slate-950 border border-slate-700 rounded-xl text-sm text-white"></div>
            <div><label class="block text-xs font-semibold text-slate-300 uppercase mb-1">Senha</label>
            <input type="password" name="password" required placeholder="••••••••" class="w-full px-4 py-3 bg-slate-950 border border-slate-700 rounded-xl text-sm text-white"></div>
            <button type="submit" class="w-full py-3.5 bg-gradient-to-r from-amber-500 to-amber-600 hover:to-amber-500 text-slate-950 font-bold rounded-xl text-sm shadow-lg">Acessar Painel</button>
        </form>
        <div class="border-t border-slate-800 pt-4 text-center">
            <a href="/solicitar-orcamento" target="_blank" class="text-xs text-amber-400 hover:underline font-semibold block mb-1">🔗 Simulador Público Aberto (Instagram)</a>
            <p class="text-[11px] text-slate-500">Perfis: <b>adm</b>, <b>gerente</b>, <b>vendedor</b>, <b>financeiro</b>, <b>liberacao</b></p>
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
                        </select>
                    </div>

                    <div class="bg-slate-900 p-2.5 rounded-xl border border-slate-800 flex justify-between items-center">
                        <label class="font-semibold text-slate-300">👑 Dorm. Casal / Suíte</label>
                        <select name="qtd_dorm_casal" class="px-2 py-1 bg-slate-950 border border-slate-700 rounded-lg text-white font-bold">
                            <option value="0">0</option>
                            <option value="1" selected>1</option>
                            <option value="2">2</option>
                        </select>
                    </div>

                    <div class="bg-slate-900 p-2.5 rounded-xl border border-slate-800 flex justify-between items-center">
                        <label class="font-semibold text-slate-300">🚿 Banheiro</label>
                        <select name="qtd_banheiro" class="px-2 py-1 bg-slate-950 border border-slate-700 rounded-lg text-white font-bold">
                            <option value="0">0</option>
                            <option value="1">1</option>
                            <option value="2" selected>2</option>
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
                    <textarea name="descricao" rows="2" placeholder="Ex: Iluminação em LED nos aéreos, cava nos gaveteiros..." class="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-xl text-white text-xs"></textarea>
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
    desconto_vista_5 = round(pv_redondo * 0.95)
    tel_limpo = (empresa.get("telefone") or "").replace("-","").replace(" ","").replace("(","").replace(")","")

    return f"""<!DOCTYPE html>
<html lang="pt-br">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{empresa['nome_empresa']} - Pré-Orçamento</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-slate-950 text-slate-100 min-h-screen p-4 sm:p-8 font-sans flex items-center justify-center">
    <div class="max-w-2xl w-full bg-slate-900 border border-amber-500/40 rounded-3xl p-6 sm:p-10 shadow-2xl space-y-6">
        <div class="text-center space-y-2 border-b border-slate-800 pb-4">
            <span class="text-4xl block">✨</span>
            <h1 class="text-xl sm:text-2xl font-bold text-white">Pré-Orçamento Calculado com Sucesso!</h1>
            <p class="text-xs text-slate-400">Olá, <b>{nome}</b>! Estimativa para <b>{cidade} ({area_m2} m²)</b>.</p>
            <p class="text-[11px] text-amber-300 font-semibold">{ambientes_str}</p>
        </div>

        <div class="bg-slate-950 p-6 rounded-2xl border border-amber-500/40 text-center space-y-2">
            <span class="text-xs text-slate-400 font-bold uppercase tracking-wider block">Valor Estimado do Projeto</span>
            <span class="text-3xl sm:text-4xl font-black text-amber-400">R$ {pv_redondo:,.0f}</span>
            <div class="p-3 bg-emerald-950/60 border border-emerald-500/40 rounded-xl inline-block mt-1">
                <span class="text-xs text-emerald-300 font-bold block">⚡ À Vista no PIX (5% de Desconto):</span>
                <span class="text-xl sm:text-2xl font-black text-emerald-400">R$ {desconto_vista_5:,.0f}</span>
            </div>
        </div>

        <div class="pt-2">
            <a href="https://api.whatsapp.com/send?phone=55{tel_limpo}&text=Ol%C3%A1!%20Simulei%20meu%20projeto%20no%20site%20da%20{empresa['nome_empresa']}%20(Projeto%20#{orcamento_id:04d})%20e%20gostaria%20de%20atendimento." target="_blank" class="flex items-center justify-center gap-2 w-full py-4 bg-gradient-to-r from-emerald-500 to-emerald-600 hover:from-emerald-400 hover:to-emerald-500 text-slate-950 font-black rounded-xl text-sm transition-all shadow-xl">
                📲 Enviar Simulação para o WhatsApp da Empresa
            </a>
        </div>
    </div>
</body></html>"""

def render_convite_gerado(nome, email, perfil, telefone, link, senha_temp):
    return f"""<!DOCTYPE html>
<html lang="pt-br"><head><title>Acesso Criado</title><script src="https://cdn.tailwindcss.com"></script></head>
<body class="bg-slate-950 text-slate-100 flex items-center justify-center min-h-screen p-4 font-sans">
    <div class="max-w-md w-full bg-slate-900 border border-amber-500/40 rounded-3xl p-8 shadow-2xl space-y-4 text-center">
        <span class="text-4xl">🔐</span>
        <h2 class="text-xl font-bold text-white">Credenciais Geradas</h2>
        <p class="text-xs text-slate-400">Envie o link ou a senha provisória para o funcionário:</p>
        
        <div class="bg-slate-950 p-4 rounded-2xl border border-slate-800 text-left text-xs space-y-2 font-mono">
            <p><span class="text-slate-500">Nome:</span> <b class="text-white">{nome}</b></p>
            <p><span class="text-slate-500">E-mail:</span> <b class="text-amber-400">{email}</b></p>
            <p><span class="text-slate-500">Perfil:</span> <b class="text-emerald-400 uppercase">{perfil}</b></p>
            <p><span class="text-slate-500">Senha Provisória:</span> <b class="text-rose-400">{senha_temp}</b></p>
        </div>

        <div class="p-3 bg-slate-950 rounded-xl border border-slate-800 text-left">
            <span class="text-[10px] text-slate-500 block uppercase font-bold mb-1">Link de Primeiro Acesso:</span>
            <input type="text" readonly value="{link}" onclick="this.select();" class="w-full p-2 bg-slate-900 border border-slate-700 rounded-lg text-xs text-amber-300 font-mono">
        </div>

        <a href="/painel-get" class="inline-block w-full py-3 bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold rounded-xl text-xs">Voltar ao Painel</a>
    </div>
</body></html>"""

def render_tela_nova_senha(user, token):
    return f"""<!DOCTYPE html>
<html lang="pt-br">
<head><title>Nova Senha - MVI</title><script src="https://cdn.tailwindcss.com"></script></head>
<body class="bg-slate-950 text-slate-100 flex items-center justify-center min-h-screen p-4 font-sans">
    <form action="/salvar-nova-senha" method="post" class="bg-slate-900 border border-amber-500/40 p-8 rounded-3xl space-y-4 max-w-sm w-full shadow-2xl">
        <h1 class="text-lg font-bold text-white text-center">Ativar Acesso & Definir Nova Senha</h1>
        <p class="text-xs text-slate-400 text-center">Olá <b>{user['nome']}</b> ({user['perfil']})</p>
        <input type="hidden" name="token" value="{token}">
        <input type="password" name="nova_senha" required placeholder="Nova Senha Pessoal" class="w-full px-4 py-3 bg-slate-950 border border-slate-700 rounded-xl text-white text-xs">
        <input type="password" name="confirma_senha" required placeholder="Confirme sua Nova Senha" class="w-full px-4 py-3 bg-slate-950 border border-slate-700 rounded-xl text-white text-xs">
        <button type="submit" class="w-full py-3 bg-amber-500 font-bold text-slate-950 rounded-xl text-xs">Salvar Senha e Entrar</button>
    </form>
</body></html>"""

# ==============================================================================
# PAINEL GERAL DO COCKPIT
# ==============================================================================
def render_dashboard_view():
    empresa = get_empresa_dados(1)
    met = get_metricas()
    perfil = CURRENT_SESSION.get("user_perfil", "vendedor")
    
    pode_ver_lucro = (perfil == "adm")
    pode_ver_comissoes_geral = (perfil in ["adm", "gerente", "financeiro"])
    pode_gerenciar_equipe = (perfil == "adm")
    somente_leitura_fabrica = (perfil == "liberacao")
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    if perfil == "financeiro":
        cursor.execute("SELECT * FROM orcamentos WHERE empresa_id = 1 AND status IN ('Aprovado', 'Em Produção', 'Entregue', 'Liberado para Financeiro & Fábrica', 'Contrato Assinado Digitalmente', 'Desconto Autorizado pela Diretoria') ORDER BY id DESC")
    elif perfil == "vendedor":
        cursor.execute("SELECT * FROM orcamentos WHERE empresa_id = 1 AND (vendedor_email = ? OR vendedor_responsavel = ?) ORDER BY id DESC", (CURRENT_SESSION['user_email'], CURRENT_SESSION['user_nome']))
    else:
        cursor.execute("SELECT * FROM orcamentos WHERE empresa_id = 1 ORDER BY id DESC LIMIT 50")
    
    leads = cursor.fetchall()
    cursor.execute("SELECT * FROM usuarios WHERE empresa_id = 1 ORDER BY nome ASC")
    equipe = cursor.fetchall()
    conn.close()

    cliente_ativo = {}
    if CURRENT_SESSION.get("cliente_ativo_id"):
        for h in leads:
            if h["id"] == CURRENT_SESSION["cliente_ativo_id"]:
                cliente_ativo = dict(h)
                break
    if not cliente_ativo and leads:
        cliente_ativo = dict(leads[0])
        CURRENT_SESSION["cliente_ativo_id"] = cliente_ativo.get("id")

    c_id = cliente_ativo.get("id", 0)
    c_nome = cliente_ativo.get("cliente_nome") or "Novo Cliente (Sem Pasta)"
    c_cpf = cliente_ativo.get("cliente_cpf") or "Não informado"
    c_tel = cliente_ativo.get("cliente_telefone") or "—"
    c_cep_post = cliente_ativo.get("cliente_cep_postal") or ""
    c_end_post = cliente_ativo.get("cliente_endereco_postal") or ""
    c_cep_ent = cliente_ativo.get("cliente_cep_entrega") or ""
    c_end_ent = cliente_ativo.get("cliente_endereco_entrega") or ""
    c_vendedor = cliente_ativo.get("vendedor_responsavel") or CURRENT_SESSION["user_nome"]

    c_prazo = cliente_ativo.get("prazo_entrega") or "25 dias úteis"
    c_amb = cliente_ativo.get("cliente_ambiente") or "Cozinha Planejada"
    c_data_venda = cliente_ativo.get("criado_em") or datetime.now().strftime("%d/%m/%Y")
    
    c_p_bruto = round(float(cliente_ativo.get("preco_bruto") or cliente_ativo.get("preco_venda") or 0))
    c_p_venda = round(float(cliente_ativo.get("preco_venda") or 0))
    c_lucro = round(float(cliente_ativo.get("lucro_liquido") or 0))
    c_desc_pct = float(cliente_ativo.get("desconto_pct") or 0)
    c_entrada = round(float(cliente_ativo.get("entrada_valor") or 0))
    c_parc = int(cliente_ativo.get("num_parcelas") or 1)
    c_mod = cliente_ativo.get("modalidade_pagamento") or "Entrada + Cartão de Crédito"
    c_comissao = float(cliente_ativo.get("comissao_valor") or (c_p_venda * (float(empresa.get("comissao_padrao_pct", 4.0)) / 100.0)))
    
    chk_dados = int(cliente_ativo.get("check_dados") or (1 if c_cpf != 'Não informado' else 0))
    chk_comercial = int(cliente_ativo.get("check_comercial") or 1)
    chk_financeiro = int(cliente_ativo.get("check_financeiro") or 0)
    chk_contrato = int(cliente_ativo.get("check_contrato") or 0)

    ambientes_cadastrados = []
    try:
        ambientes_cadastrados = json.loads(cliente_ativo.get("ambientes_json") or "[]")
    except Exception:
        ambientes_cadastrados = []
    
    if not ambientes_cadastrados and c_id > 0:
        ambientes_cadastrados = [{"id": 1, "nome": c_amb, "valor": c_p_venda}]

    versoes_orcamentos = []
    try:
        versoes_orcamentos = json.loads(cliente_ativo.get("versoes_orcamentos_json") or "[]")
    except Exception:
        versoes_orcamentos = []

    if not versoes_orcamentos and c_id > 0:
        versoes_orcamentos = [{"id": 1, "nome": "Orçamento #1 (Principal)", "valor": c_p_venda, "ativo": True}]

    versao_ativa_id = int(cliente_ativo.get("versao_ativa_id") or 1)
    saldo_financiar = max(c_p_venda - c_entrada, 0)
    valor_por_parcela = round(saldo_financiar / c_parc) if c_parc > 0 else 0

    linhas_parcelas = ""
    hoje = date.today()
    for i in range(1, c_parc + 1):
        dt_parc = (hoje + timedelta(days=30 * i)).strftime("%d/%m/%Y")
        linhas_parcelas += f"""
        <tr class="border-b border-slate-800 text-xs hover:bg-slate-800/40">
            <td class="py-2.5 px-3 text-center text-slate-400 font-mono">{i}</td>
            <td class="py-2.5 px-3 text-slate-300">{dt_parc}</td>
            <td class="py-2.5 px-3 font-bold text-amber-400 text-right">R$ {valor_por_parcela:,.2f}</td>
            <td class="py-2.5 px-3 text-slate-300">{c_mod}</td>
            <td class="py-2.5 px-3 text-slate-400">Parcela regular do projeto</td>
        </tr>
        """

    if not linhas_parcelas:
        linhas_parcelas = "<tr><td colspan='5' class='py-4 text-center text-xs text-slate-500'>Nenhuma parcela gerada.</td></tr>"

    lista_ambientes_html = ""
    for amb_item in ambientes_cadastrados:
        val_amb = float(amb_item.get("valor", 0))
        lista_ambientes_html += f"""
        <li class="p-2 bg-slate-950 rounded-xl border border-slate-800 flex justify-between items-center group">
            <div>
                <span class="text-white font-semibold block">📦 {amb_item.get('nome','Ambiente')}</span>
                <span class="text-[11px] font-bold text-amber-400">R$ {val_amb:,.2f}</span>
            </div>
            {f'''<form action="/remover-ambiente-pasta" method="post" class="inline opacity-80 group-hover:opacity-100">
                <input type="hidden" name="orcamento_id" value="{c_id}">
                <input type="hidden" name="ambiente_id" value="{amb_item.get('id')}">
                <button type="submit" class="text-rose-400 hover:text-rose-300 text-xs font-bold px-1">✕</button>
            </form>''' if not somente_leitura_fabrica else ''}
        </li>
        """

    lista_versoes_html = ""
    for v in versoes_orcamentos:
        v_id = v.get("id")
        v_nome = v.get("nome", f"Orçamento #{v_id}")
        v_val = float(v.get("valor", c_p_venda))
        v_ativo = (v_id == versao_ativa_id)
        badge_ativo = "<span class='text-[10px] bg-emerald-950 text-emerald-300 border border-emerald-500/40 px-2 py-0.5 rounded-full font-bold'>Ativo</span>" if v_ativo else ""
        
        lista_versoes_html += f"""
        <li class="p-2.5 bg-slate-950 rounded-xl border {'border-amber-500/60 bg-amber-950/20' if v_ativo else 'border-slate-800'} flex justify-between items-center">
            <div>
                <div class="flex items-center gap-1.5">
                    <span class="text-white font-semibold block">⭐ {v_nome}</span>
                    {badge_ativo}
                </div>
                <span class="text-[11px] font-bold text-amber-400">R$ {v_val:,.2f}</span>
            </div>
            {f'''<form action="/selecionar-versao-orcamento" method="post">
                <input type="hidden" name="orcamento_id" value="{c_id}">
                <input type="hidden" name="versao_id" value="{v_id}">
                <button type="submit" class="px-2 py-1 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg text-[10px] font-bold">Ativar</button>
            </form>''' if not v_ativo else ''}
        </li>
        """

    leads_geral_html = ""
    options_leads = "<option value='0'>📂 Selecionar outra pasta...</option>"
    for h in leads:
        h_d = dict(h)
        pv = round(float(h_d.get("preco_venda") or 0))
        adendo = round(float(h_d.get("adendo_valor") or 0))
        pv_total = pv + adendo
        st = h_d.get("status") or "Em Negociação"
        sel = "selected" if h_d.get("id") == c_id else ""
        options_leads += f"<option value='{h_d['id']}' {sel}>Pasta P{h_d['id']:05d} - {h_d.get('cliente_nome','')} ({h_d.get('cliente_ambiente','')})</option>"

        leads_geral_html += f"""
        <tr class="border-b border-slate-800 text-xs hover:bg-slate-800/40">
            <td class="py-3 px-4 font-mono font-bold text-amber-400">P{h_d['id']:05d}</td>
            <td class="py-3 px-4 text-white font-bold">{h_d.get('cliente_nome','')}<span class="block text-[11px] text-slate-400 font-normal">Vendedor: {h_d.get('vendedor_responsavel','')}</span></td>
            <td class="py-3 px-4 text-slate-300">{h_d.get('cliente_ambiente','')}</td>
            <td class="py-3 px-4 text-amber-400 font-bold text-right">R$ {pv_total:,.2f}</td>
            <td class="py-3 px-4 text-center"><span class="px-2 py-0.5 rounded text-[11px] font-bold bg-amber-950 text-amber-300 border border-amber-500/30">{st}</span></td>
            <td class="py-3 px-4 text-center">
                <form action="/selecionar-cliente-trabalho" method="post" class="inline">
                    <input type="hidden" name="orcamento_id" value="{h_d['id']}">
                    <button type="submit" class="px-3 py-1 bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold rounded text-xs shadow-sm">
                        📂 Abrir Pasta
                    </button>
                </form>
            </td>
        </tr>
        """

    tabela_comissoes_html = ""
    for h in leads:
        h_d = dict(h)
        pv = float(h_d.get("preco_venda") or 0) + float(h_d.get("adendo_valor") or 0)
        vendedor_linha = h_d.get("vendedor_responsavel") or "Raquel Marcelino"
        
        if perfil == "vendedor" and vendedor_linha != CURRENT_SESSION["user_nome"]:
            continue

        pct_com = float(h_d.get("comissao_pct") or 4.0)
        val_com = float(h_d.get("comissao_valor") or (pv * (pct_com / 100.0)))
        st = h_d.get("status") or "Em Negociação"

        tabela_comissoes_html += f"""
        <tr class="border-b border-slate-800 text-xs hover:bg-slate-800/40">
            <td class="py-2.5 px-3 font-mono text-amber-400 font-bold">P{h_d['id']:05d}</td>
            <td class="py-2.5 px-3 text-white font-semibold">{h_d.get('cliente_nome','')}</td>
            <td class="py-2.5 px-3 text-slate-300 font-semibold">{vendedor_linha}</td>
            <td class="py-2.5 px-3 text-right text-slate-300">R$ {pv:,.2f}</td>
            <td class="py-2.5 px-3 text-center text-amber-400 font-bold">{pct_com:.1f}%</td>
            <td class="py-2.5 px-3 text-right font-black text-emerald-400">R$ {val_com:,.2f}</td>
            <td class="py-2.5 px-3 text-center"><span class="px-2 py-0.5 rounded text-[10px] font-bold bg-slate-950 border border-slate-700 text-slate-300">{st}</span></td>
        </tr>
        """

    if not tabela_comissoes_html:
        tabela_comissoes_html = "<tr><td colspan='7' class='py-4 text-center text-xs text-slate-500'>Nenhum lançamento de comissão registrado para esta visualização.</td></tr>"

    tabela_equipe_html = ""
    for u in equipe:
        u_d = dict(u)
        tabela_equipe_html += f"""
        <tr class="border-b border-slate-800 text-xs hover:bg-slate-800/40">
            <td class="py-2.5 px-3 text-white font-bold">{u_d.get('nome')}</td>
            <td class="py-2.5 px-3 text-amber-300 font-mono">{u_d.get('email')}</td>
            <td class="py-2.5 px-3 text-center"><span class="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-950 border border-amber-500/40 text-amber-300 uppercase">{u_d.get('perfil')}</span></td>
            <td class="py-2.5 px-3 text-center"><span class="text-emerald-400 font-bold">{'✓ Ativo' if u_d.get('ativo') else '✕ Inativo'}</span></td>
            <td class="py-2.5 px-3 text-center">
                <form action="/redefinir-senha-funcionario" method="post" class="inline">
                    <input type="hidden" name="email_funcionario" value="{u_d.get('email')}">
                    <button type="submit" class="px-2 py-1 bg-slate-800 hover:bg-slate-700 text-amber-300 rounded text-[11px] font-bold">🔑 Gerar Nova Senha Provisória</button>
                </form>
            </td>
        </tr>
        """

    def cor_bolinha(val):
        if val == 2: return "bg-emerald-500 shadow-emerald-500/50 shadow-md", "✓ Concluído"
        if val == 1: return "bg-amber-400 shadow-amber-400/50 shadow-md", "⚡ Em Análise"
        return "bg-rose-500 shadow-rose-500/50 shadow-md", "✕ Pendente"

    cor_d, txt_d = cor_bolinha(chk_dados)
    cor_c, txt_c = cor_bolinha(chk_comercial)
    cor_f, txt_f = cor_bolinha(chk_financeiro)
    cor_con, txt_con = cor_bolinha(chk_contrato)

    return f"""<!DOCTYPE html>
<html lang="pt-br">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MVI Gestão - CRM Master</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        .tree-item {{ transition: all 0.2s; cursor: pointer; }}
        .tree-item:hover {{ background-color: #1e293b; color: #f59e0b; }}
        .tree-item.active {{ background: linear-gradient(135deg, #f59e0b, #d97706); color: #0f172a; font-weight: bold; }}
        .tab-content {{ display: none; }}
        .tab-content.active {{ display: block; }}
    </style>
</head>
<body class="bg-slate-950 text-slate-100 font-sans min-h-screen">
    
    <header class="bg-slate-900 border-b border-slate-800 px-6 py-3 flex flex-wrap items-center justify-between shadow-lg">
        <div class="flex items-center space-x-6">
            <div class="flex items-center space-x-2 cursor-pointer" onclick="mudarAba('aba-geral')">
                <div class="w-9 h-9 rounded-xl bg-gradient-to-br from-amber-400 to-amber-600 text-slate-950 font-black flex items-center justify-center text-sm shadow">MVI</div>
                <span class="font-bold text-base tracking-wide text-white">{empresa.get('nome_empresa') or 'MVI Sistemas'}</span>
            </div>
            <nav class="flex items-center space-x-3 text-xs font-semibold">
                <button onclick="mudarAba('aba-geral')" class="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700">📂 Pastas</button>
                <button onclick="mudarAba('aba-comissoes')" class="px-3 py-1.5 rounded-lg bg-emerald-950/80 text-emerald-300 hover:bg-emerald-900 border border-emerald-500/40">💰 Extrato de Comissões</button>
                {f'''<button onclick="mudarAba('aba-equipe')" class="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-amber-300 border border-slate-700">👥 Equipe & Acessos</button>
                <button onclick="mudarAba('aba-empresa')" class="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700">🏢 Empresa</button>''' if pode_gerenciar_equipe else ''}
                <a href="/solicitar-orcamento" target="_blank" class="px-3 py-1.5 rounded-lg bg-amber-950 text-amber-300 hover:bg-amber-900 border border-amber-500/40">🔗 Link Público</a>
            </nav>
        </div>

        <div class="flex items-center space-x-4 text-xs">
            <form action="/selecionar-cliente-trabalho" method="post" class="flex items-center gap-1">
                <select name="orcamento_id" onchange="this.form.submit()" class="px-3 py-1.5 rounded-xl bg-slate-950 text-amber-300 font-semibold border border-slate-700 focus:border-amber-500">
                    {options_leads}
                </select>
            </form>
            <span class="bg-amber-500 text-slate-950 px-2.5 py-0.5 rounded-full font-bold uppercase text-[10px]">{perfil}</span>
            <span class="text-slate-300 font-semibold">{CURRENT_SESSION['user_nome']}</span>
            <a href="/" class="bg-slate-800 hover:bg-slate-700 px-3 py-1.5 rounded-xl text-slate-300 border border-slate-700">Sair</a>
        </div>
    </header>

    <div class="max-w-7xl mx-auto p-4 sm:p-6 grid grid-cols-1 lg:grid-cols-12 gap-5">
        
        <!-- MENU LATERAL -->
        <div class="lg:col-span-3 bg-slate-900 border border-slate-800 rounded-3xl p-4 shadow-xl space-y-4 text-xs">
            <div>
                <h3 class="font-bold text-white flex items-center justify-between pb-2 border-b border-slate-800">
                    <span>📁 Pasta P{c_id:05d}</span>
                    <span class="text-[10px] bg-amber-950 text-amber-300 border border-amber-500/40 px-2 py-0.5 rounded-full">Ativa</span>
                </h3>
                <ul class="mt-2 space-y-1">
                    <li><button onclick="mudarAba('aba-resumo')" id="btn-aba-resumo" class="tree-item active w-full text-left flex items-center gap-2 p-2.5 rounded-xl text-white font-semibold">📋 1. Resumo da Venda</button></li>
                    <li><button onclick="mudarAba('aba-cliente')" id="btn-aba-cliente" class="tree-item w-full text-left flex items-center gap-2 p-2.5 rounded-xl text-slate-300 font-medium">👤 2. Dados do Cliente</button></li>
                    {f'''<li><button onclick="mudarAba('aba-mesa')" id="btn-aba-mesa" class="tree-item w-full text-left flex items-center gap-2 p-2.5 rounded-xl text-slate-300 font-medium">💼 3. Mesa de Negociação</button></li>
                    <li><button onclick="mudarAba('aba-promob')" id="btn-aba-promob" class="tree-item w-full text-left flex items-center gap-2 p-2.5 rounded-xl text-slate-300 font-medium">🚀 4. Integrador Promob</button></li>''' if not somente_leitura_fabrica else ''}
                    <li><a href="/minuta-contrato/{c_id}" target="_blank" class="tree-item flex items-center gap-2 p-2.5 rounded-xl text-amber-400 font-bold hover:bg-slate-800">📜 5. Minuta Contrato PDF</a></li>
                    <li><a href="/assinar/{c_id}" target="_blank" class="tree-item flex items-center gap-2 p-2.5 rounded-xl text-emerald-400 font-bold hover:bg-slate-800">✍️ 6. Assinatura Digital</a></li>
                    <li><button onclick="mudarAba('aba-comissoes')" id="btn-aba-comissoes" class="tree-item w-full text-left flex items-center gap-2 p-2.5 rounded-xl text-emerald-300 font-semibold">💰 7. Extrato de Comissões</button></li>
                    {f'''<li><button onclick="mudarAba('aba-equipe')" id="btn-aba-equipe" class="tree-item w-full text-left flex items-center gap-2 p-2.5 rounded-xl text-amber-300 font-semibold">👥 8. Gestão de Equipe</button></li>''' if pode_gerenciar_equipe else ''}
                </ul>
            </div>

            <!-- SEÇÃO DE AMBIENTES -->
            <div>
                <div class="flex justify-between items-center pb-1 border-b border-slate-800 font-bold text-white">
                    <span>🏠 Ambientes</span>
                    {f'''<button onclick="mudarAba('aba-novo-ambiente')" class="text-[11px] px-2 py-0.5 bg-amber-500/20 hover:bg-amber-500/30 text-amber-300 border border-amber-500/40 rounded-lg font-bold">+ Novo</button>''' if not somente_leitura_fabrica else ''}
                </div>
                <ul class="mt-2 space-y-1.5 text-slate-400">{lista_ambientes_html}</ul>
            </div>

            <!-- SEÇÃO DE ORÇAMENTOS -->
            <div>
                <div class="flex justify-between items-center pb-1 border-b border-slate-800 font-bold text-white">
                    <span>⭐ Orçamentos</span>
                    {f'''<button onclick="mudarAba('aba-novo-orcamento-versao')" class="text-[11px] px-2 py-0.5 bg-sky-500/20 hover:bg-sky-500/30 text-sky-300 border border-sky-500/40 rounded-lg font-bold">+ Nova Opção</button>''' if not somente_leitura_fabrica else ''}
                </div>
                <ul class="mt-2 space-y-1.5 text-slate-400">{lista_versoes_html}</ul>
            </div>
        </div>

        <!-- PAINEL CENTRAL -->
        <div class="lg:col-span-6 space-y-4">
            
            <!-- ABA 1: RESUMO DA VENDA -->
            <div id="aba-resumo" class="tab-content active space-y-4">
                <div class="bg-slate-900 border border-slate-800 rounded-3xl p-5 shadow-xl space-y-3">
                    <div class="text-center pb-2 border-b border-slate-800">
                        <h2 class="text-xs font-bold text-amber-400 uppercase tracking-wide">CONTRATO IT{c_id:05d} | Vendedor: {c_vendedor}</h2>
                    </div>

                    <div class="flex flex-wrap gap-2 justify-between items-center">
                        <div class="flex gap-2">
                            <a href="/minuta-contrato/{c_id}" target="_blank" class="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded-xl text-xs font-bold text-slate-200">🖨️ Gerar PDF</a>
                            <a href="/assinar/{c_id}" target="_blank" class="px-3 py-1.5 bg-gradient-to-r from-amber-500 to-amber-600 text-slate-950 font-bold rounded-xl text-xs shadow-lg">✍️ Assinatura</a>
                        </div>
                        <span class="text-[11px] text-slate-400 font-semibold">Comissão: <b class="text-emerald-400">R$ {c_comissao:,.2f}</b></span>
                    </div>

                    <div class="grid grid-cols-2 gap-3 text-xs pt-2">
                        <div><span class="text-slate-500 block text-[11px]">Cliente:</span><span class="font-bold text-white text-sm">{c_nome}</span></div>
                        <div><span class="text-slate-500 block text-[11px]">CPF / CNPJ:</span><span class="font-bold text-slate-300">{c_cpf}</span></div>
                        <div><span class="text-slate-500 block text-[11px]">Prazo de Entrega:</span><span class="font-bold text-slate-300">{c_prazo}</span></div>
                        <div><span class="text-slate-500 block text-[11px]">Telefone:</span><span class="font-bold text-slate-300">{c_tel}</span></div>
                    </div>
                </div>

                <!-- CRONOGRAMA DE PARCELAS -->
                <div class="bg-slate-900 border border-slate-800 rounded-3xl overflow-hidden shadow-xl">
                    <div class="bg-slate-850 px-4 py-2.5 border-b border-slate-800 text-xs font-bold text-amber-400 text-center uppercase tracking-wide">PLANO DE PAGAMENTO & CRONOGRAMA</div>
                    <div class="overflow-x-auto">
                        <table class="w-full text-left text-xs border-collapse">
                            <thead class="bg-slate-950/60 border-b border-slate-800 text-slate-400 font-semibold">
                                <tr>
                                    <th class="py-2.5 px-3 text-center">#</th>
                                    <th class="py-2.5 px-3">Data</th>
                                    <th class="py-2.5 px-3 text-right">Valor</th>
                                    <th class="py-2.5 px-3">Modalidade</th>
                                    <th class="py-2.5 px-3">Status</th>
                                </tr>
                            </thead>
                            <tbody>{linhas_parcelas}</tbody>
                        </table>
                    </div>
                </div>
            </div>

            <!-- ABA 2: DADOS DO CLIENTE -->
            <div id="aba-cliente" class="tab-content bg-slate-900 border border-slate-800 rounded-3xl p-5 shadow-xl space-y-4 text-xs">
                <h3 class="font-bold text-amber-400 uppercase pb-1 border-b border-slate-800">👤 Cadastro de Contratante & Obra</h3>
                <form action="/salvar-dados-completos-cliente" method="post" class="space-y-3">
                    <input type="hidden" name="orcamento_id" value="{c_id}">
                    <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
                        <div class="sm:col-span-2">
                            <label class="block text-slate-400 mb-1">Nome Completo</label>
                            <input type="text" name="cliente_nome" value="{c_nome if c_nome != 'Novo Cliente (Sem Pasta)' else ''}" required class="w-full p-2.5 bg-slate-950 border border-slate-700 rounded-xl text-white font-bold">
                        </div>
                        <div>
                            <label class="block text-slate-400 mb-1">CPF</label>
                            <input type="text" name="cliente_cpf" value="{c_cpf if c_cpf != 'Não informado' else ''}" class="w-full p-2.5 bg-slate-950 border border-slate-700 rounded-xl text-white">
                        </div>
                        <div>
                            <label class="block text-slate-400 mb-1">Telefone WhatsApp</label>
                            <input type="text" name="cliente_telefone" value="{c_tel if c_tel != '—' else ''}" class="w-full p-2.5 bg-slate-950 border border-slate-700 rounded-xl text-white">
                        </div>
                    </div>

                    <div class="border-t border-slate-800 pt-3 grid grid-cols-1 sm:grid-cols-2 gap-4">
                        <div class="bg-slate-950 p-3.5 rounded-2xl border border-slate-800 space-y-2">
                            <label class="font-bold text-amber-400 block">📬 Endereço Postal</label>
                            <input type="text" name="cliente_cep_postal" value="{c_cep_post}" placeholder="CEP" class="w-full p-2 bg-slate-900 border border-slate-700 rounded-xl text-white">
                            <textarea name="cliente_endereco_postal" rows="2" placeholder="Rua, Número, Bairro, Cidade - UF" class="w-full p-2 bg-slate-900 border border-slate-700 rounded-xl text-white">{c_end_post}</textarea>
                        </div>
                        <div class="bg-slate-950 p-3.5 rounded-2xl border border-slate-800 space-y-2">
                            <label class="font-bold text-slate-300 block">🚚 Endereço da Instalação / Obra</label>
                            <input type="text" name="cliente_cep_entrega" value="{c_cep_ent}" placeholder="CEP Obra" class="w-full p-2 bg-slate-900 border border-slate-700 rounded-xl text-white">
                            <textarea name="cliente_endereco_entrega" rows="2" placeholder="Endereço da Montagem..." class="w-full p-2 bg-slate-900 border border-slate-700 rounded-xl text-white">{c_end_ent}</textarea>
                        </div>
                    </div>

                    <button type="submit" class="w-full py-3 bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold rounded-xl shadow-lg">💾 Salvar Ficha Cadastral</button>
                </form>
            </div>

            <!-- ABA 3: MESA DE NEGOCIAÇÃO -->
            <div id="aba-mesa" class="tab-content bg-slate-900 border border-slate-800 rounded-3xl p-5 shadow-xl space-y-4 text-xs">
                <div class="flex justify-between items-center pb-1 border-b border-slate-800">
                    <h3 class="font-bold text-amber-400 uppercase">💼 Mesa de Negociação & Fechamento</h3>
                    <input type="hidden" id="preco_bruto_base" value="{c_p_bruto if c_p_bruto > 0 else c_p_venda}">
                </div>

                <form id="form_mesa_negociacao" action="/salvar-negociacao-mesa" method="post" class="space-y-4">
                    <input type="hidden" name="orcamento_id" value="{c_id}">

                    <div class="grid grid-cols-1 sm:grid-cols-3 gap-3">
                        <div>
                            <label class="block text-slate-400 mb-1 font-semibold">Valor Venda (R$)</label>
                            <input type="number" step="1" name="preco_venda" id="preco_venda_input" value="{c_p_venda}" required class="w-full p-2.5 bg-slate-950 border border-slate-700 rounded-xl font-bold text-amber-400 text-sm">
                        </div>

                        <div>
                            <label class="block text-slate-400 mb-1 font-semibold">Desconto (%)</label>
                            <input type="number" step="0.1" name="desconto_pct" id="desconto_pct_input" value="{c_desc_pct}" class="w-full p-2.5 bg-slate-950 border border-slate-700 rounded-xl font-bold text-white">
                            <span class="text-[10px] text-slate-500 mt-0.5 block">Teto sem autorização: {empresa.get('desconto_max_vendedor', 3.0)}%</span>
                        </div>

                        <div>
                            <label class="block text-slate-400 mb-1 font-semibold">Entrada (R$)</label>
                            <input type="number" step="100" name="entrada_valor" id="entrada_valor_input" value="{c_entrada}" required class="w-full p-2.5 bg-slate-950 border border-slate-700 rounded-xl font-bold text-emerald-400 text-sm">
                        </div>
                    </div>

                    <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                        <div>
                            <label class="block text-slate-400 mb-1 font-semibold">Forma de Pagamento</label>
                            <select name="forma_opcao" class="w-full p-2.5 bg-slate-950 border border-slate-700 rounded-xl font-semibold text-white">
                                <option value="Entrada PIX + Cartão de Crédito">Entrada PIX + Cartão de Crédito</option>
                                <option value="Entrada PIX + Boleto Bancário">Entrada PIX + Boleto Bancário</option>
                                <option value="PIX Integral à Vista">PIX Integral à Vista (5% OFF)</option>
                            </select>
                        </div>
                        <div>
                            <label class="block text-slate-400 mb-1 font-semibold">Parcelas</label>
                            <input type="number" name="num_parcelas" value="{c_parc}" min="1" max="24" class="w-full p-2.5 bg-slate-950 border border-slate-700 rounded-xl font-bold text-white">
                        </div>
                    </div>

                    {f'''<div class="p-4 bg-slate-950 border border-emerald-500/30 rounded-2xl flex justify-between items-center">
                        <div>
                            <span class="font-bold text-slate-400 block text-xs uppercase">Lucro Líquido da Empresa (Restrito ADM):</span>
                            <span class="font-black text-emerald-400 text-lg">R$ {c_lucro:,.2f}</span>
                        </div>
                    </div>''' if pode_ver_lucro else f'''<div class="p-3 bg-slate-950/60 border border-slate-800 rounded-xl text-center text-slate-500 text-[11px]">
                        🔒 Lucro e custos internos protegidos por política de privacidade da empresa.
                    </div>'''}

                    <button type="submit" class="w-full py-3.5 bg-gradient-to-r from-amber-500 to-amber-600 hover:from-amber-400 hover:to-amber-500 text-slate-950 font-bold rounded-xl text-xs shadow-lg">
                        💾 Atualizar Proposta & Salvar
                    </button>
                </form>
            </div>

            <!-- ABA 4: PROMOB -->
            <div id="aba-promob" class="tab-content bg-slate-900 border border-slate-800 rounded-3xl p-5 shadow-xl space-y-4 text-xs">
                <h3 class="font-bold text-amber-400 uppercase pb-1 border-b border-slate-800">🚀 Importação Direta Promob</h3>
                <form action="/importar-promob" method="post" enctype="multipart/form-data" class="space-y-3">
                    <input type="text" name="cliente_nome" value="{c_nome if c_nome != 'Novo Cliente (Sem Pasta)' else ''}" placeholder="Nome do Cliente" required class="w-full p-2.5 bg-slate-950 border border-slate-700 rounded-xl text-white font-bold">
                    <input type="text" name="cliente_telefone" value="{c_tel if c_tel != '—' else ''}" placeholder="WhatsApp" required class="w-full p-2.5 bg-slate-950 border border-slate-700 rounded-xl text-white">
                    <input type="text" name="cliente_ambiente" value="{c_amb}" placeholder="Ambiente" required class="w-full p-2.5 bg-slate-950 border border-slate-700 rounded-xl text-white">
                    <div class="p-4 bg-slate-950 border border-slate-800 rounded-2xl">
                        <label class="block font-bold text-amber-400 mb-1">Arquivo Promob (.xml, .csv, .txt):</label>
                        <input type="file" name="arquivo_promob" accept=".xml,.csv,.txt,.cut" required class="w-full text-slate-400 file:bg-amber-500 file:border-0 file:rounded-xl file:px-3 file:py-1 file:font-bold">
                    </div>
                    <button type="submit" class="w-full py-3.5 bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold rounded-xl shadow-lg">⚡ Processar Peças</button>
                </form>
            </div>

            <!-- ABA 5: EXTRATO DE COMISSÕES -->
            <div id="aba-comissoes" class="tab-content bg-slate-900 border border-slate-800 rounded-3xl p-5 shadow-xl space-y-4 text-xs">
                <div class="flex justify-between items-center pb-2 border-b border-slate-800">
                    <div>
                        <h3 class="font-bold text-emerald-400 uppercase">💰 Extrato de Comissões por Vendedor</h3>
                        <p class="text-[11px] text-slate-400">Auditoria individualizada e fechamento de comissões.</p>
                    </div>
                    {f'''<span class="px-3 py-1 bg-emerald-950 border border-emerald-500/40 text-emerald-300 font-bold rounded-xl text-xs">Total Empresa: R$ {met['comissoes']:,.2f}</span>''' if pode_ver_comissoes_geral else ''}
                </div>

                <div class="overflow-x-auto">
                    <table class="w-full text-left text-xs border-collapse">
                        <thead class="bg-slate-950 border-b border-slate-800 text-slate-400 font-semibold uppercase">
                            <tr>
                                <th class="py-2.5 px-3">Pasta</th>
                                <th class="py-2.5 px-3">Cliente</th>
                                <th class="py-2.5 px-3">Vendedor</th>
                                <th class="py-2.5 px-3 text-right">Valor Venda</th>
                                <th class="py-2.5 px-3 text-center">% Com.</th>
                                <th class="py-2.5 px-3 text-right">Comissão (R$)</th>
                                <th class="py-2.5 px-3 text-center">Status</th>
                            </tr>
                        </thead>
                        <tbody>{tabela_comissoes_html}</tbody>
                    </table>
                </div>
            </div>

            <!-- ABA 6: GESTÃO DE EQUIPE (ADM ONLY) -->
            <div id="aba-equipe" class="tab-content bg-slate-900 border border-slate-800 rounded-3xl p-5 shadow-xl space-y-4 text-xs">
                <div class="flex justify-between items-center pb-2 border-b border-slate-800">
                    <div>
                        <h3 class="font-bold text-amber-400 uppercase">👥 Gestão de Usuários & Senhas Provisórias</h3>
                        <p class="text-[11px] text-slate-400">Cadastre novos funcionários e gere links seguros de primeiro acesso.</p>
                    </div>
                </div>

                <form action="/criar-usuario" method="post" class="bg-slate-950 p-4 rounded-2xl border border-slate-800 grid sm:grid-cols-3 gap-3">
                    <div>
                        <label class="block text-slate-400 mb-1 font-semibold">Nome do Funcionário</label>
                        <input type="text" name="nome" placeholder="Ex: Lucas Vendedor" required class="w-full p-2 bg-slate-900 border border-slate-700 rounded-xl text-white">
                    </div>
                    <div>
                        <label class="block text-slate-400 mb-1 font-semibold">E-mail de Acesso</label>
                        <input type="email" name="email" placeholder="lucas@mvi.com" required class="w-full p-2 bg-slate-900 border border-slate-700 rounded-xl text-white">
                    </div>
                    <div>
                        <label class="block text-slate-400 mb-1 font-semibold">Cargo / Perfil</label>
                        <select name="perfil" class="w-full p-2 bg-slate-900 border border-slate-700 rounded-xl text-white font-bold">
                            <option value="vendedor">Vendedor (Sem acesso a Lucro)</option>
                            <option value="gerente">Gerente (Sem acesso a Lucro)</option>
                            <option value="financeiro">Financeiro (Acesso a Comissões e Pagamentos)</option>
                            <option value="liberacao">Liberação / Fábrica (Projetos e Clientes)</option>
                            <option value="adm">Administrador Geral (Acesso Total)</option>
                        </select>
                    </div>
                    <button type="submit" class="sm:col-span-3 py-2.5 bg-gradient-to-r from-amber-500 to-amber-600 text-slate-950 font-bold rounded-xl shadow-lg mt-1">
                        ➕ Cadastrar Funcionário & Gerar Senha Provisória
                    </button>
                </form>

                <div class="overflow-x-auto">
                    <table class="w-full text-left text-xs border-collapse">
                        <thead class="bg-slate-950 border-b border-slate-800 text-slate-400 font-semibold uppercase">
                            <tr>
                                <th class="py-2.5 px-3">Nome</th>
                                <th class="py-2.5 px-3">E-mail</th>
                                <th class="py-2.5 px-3 text-center">Perfil</th>
                                <th class="py-2.5 px-3 text-center">Status</th>
                                <th class="py-2.5 px-3 text-center">Ações</th>
                            </tr>
                        </thead>
                        <tbody>{tabela_equipe_html}</tbody>
                    </table>
                </div>
            </div>

            <!-- ABA 7: CONFIGURAÇÕES DA EMPRESA -->
            <div id="aba-empresa" class="tab-content bg-slate-900 border border-slate-800 rounded-3xl p-5 shadow-xl space-y-4 text-xs">
                <div class="border-b border-slate-800 pb-2">
                    <h3 class="font-bold text-amber-400 uppercase">🏢 Configuração da Empresa & Parâmetros Comerciais</h3>
                </div>
                <form action="/salvar-empresa" method="post" class="grid sm:grid-cols-2 gap-3">
                    <div class="sm:col-span-2">
                        <label class="block text-slate-400 mb-1 font-semibold">Razão Social / Nome Fantasia</label>
                        <input type="text" name="nome_empresa" value="{empresa.get('nome_empresa','')}" required class="w-full p-2.5 bg-slate-950 border border-slate-700 rounded-xl text-white font-bold">
                    </div>
                    <div>
                        <label class="block text-slate-400 mb-1 font-semibold">CNPJ</label>
                        <input type="text" name="cnpj" value="{empresa.get('cnpj','')}" class="w-full p-2.5 bg-slate-950 border border-slate-700 rounded-xl text-white">
                    </div>
                    <div>
                        <label class="block text-slate-400 mb-1 font-semibold">WhatsApp Comercial</label>
                        <input type="text" name="telefone" value="{empresa.get('telefone','')}" class="w-full p-2.5 bg-slate-950 border border-slate-700 rounded-xl text-white">
                    </div>
                    <div>
                        <label class="block text-slate-400 mb-1 font-semibold">Teto Máx. Desconto Vendedor (%)</label>
                        <input type="number" step="0.5" name="desconto_max_vendedor" value="{empresa.get('desconto_max_vendedor', 3.0)}" class="w-full p-2.5 bg-slate-950 border border-amber-500/50 rounded-xl text-amber-300 font-bold">
                    </div>
                    <div>
                        <label class="block text-slate-400 mb-1 font-semibold">Comissão Padrão da Equipe (%)</label>
                        <input type="number" step="0.5" name="comissao_padrao_pct" value="{empresa.get('comissao_padrao_pct', 4.0)}" class="w-full p-2.5 bg-slate-950 border border-emerald-500/50 rounded-xl text-emerald-300 font-bold">
                    </div>
                    <button type="submit" class="sm:col-span-2 py-3 bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold rounded-xl shadow-lg mt-2">
                        💾 Salvar Parâmetros
                    </button>
                </form>
            </div>

            <!-- ABA ADICIONAR AMBIENTE -->
            <div id="aba-novo-ambiente" class="tab-content bg-slate-900 border border-slate-800 rounded-3xl p-5 shadow-xl space-y-4 text-xs">
                <h3 class="font-bold text-amber-400 uppercase pb-1 border-b border-slate-800">🏠 Adicionar Novo Ambiente</h3>
                <form action="/adicionar-ambiente-pasta" method="post" class="space-y-3">
                    <input type="hidden" name="orcamento_id" value="{c_id}">
                    <div>
                        <label class="block text-slate-400 mb-1 font-semibold">Nome do Ambiente</label>
                        <input type="text" name="nome_ambiente" placeholder="Ex: Suíte Master / Cozinha" required class="w-full p-2.5 bg-slate-950 border border-slate-700 rounded-xl text-white font-bold">
                    </div>
                    <div>
                        <label class="block text-slate-400 mb-1 font-semibold">Valor do Ambiente (R$)</label>
                        <input type="number" step="10" name="valor_ambiente" placeholder="Ex: 8500" required class="w-full p-2.5 bg-slate-950 border border-slate-700 rounded-xl text-amber-400 font-bold">
                    </div>
                    <button type="submit" class="w-full py-3 bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold rounded-xl shadow-lg">➕ Inserir Ambiente na Pasta</button>
                </form>
            </div>

            <!-- ABA ADICIONAR VERSÃO ORÇAMENTO -->
            <div id="aba-novo-orcamento-versao" class="tab-content bg-slate-900 border border-slate-800 rounded-3xl p-5 shadow-xl space-y-4 text-xs">
                <h3 class="font-bold text-sky-400 uppercase pb-1 border-b border-slate-800">⭐ Criar Nova Opção de Orçamento</h3>
                <form action="/adicionar-versao-orcamento" method="post" class="space-y-3">
                    <input type="hidden" name="orcamento_id" value="{c_id}">
                    <div>
                        <label class="block text-slate-400 mb-1 font-semibold">Nome da Versão</label>
                        <input type="text" name="nome_versao" placeholder="Ex: Orçamento #2 - Opção Sem Dormitórios" required class="w-full p-2.5 bg-slate-950 border border-slate-700 rounded-xl text-white font-bold">
                    </div>
                    <div>
                        <label class="block text-slate-400 mb-1 font-semibold">Valor Total (R$)</label>
                        <input type="number" step="10" name="valor_versao" placeholder="Ex: 19500" required class="w-full p-2.5 bg-slate-950 border border-slate-700 rounded-xl text-amber-400 font-bold">
                    </div>
                    <button type="submit" class="w-full py-3 bg-sky-600 hover:bg-sky-500 text-white font-bold rounded-xl shadow-lg">⭐ Salvar Nova Opção</button>
                </form>
            </div>

            <!-- ABA CARTEIRA GERAL DE PASTAS -->
            <div id="aba-geral" class="tab-content bg-slate-900 border border-slate-800 rounded-3xl overflow-hidden shadow-xl space-y-3">
                <div class="bg-slate-850 px-5 py-3 border-b border-slate-800 flex justify-between items-center">
                    <h3 class="font-bold text-xs uppercase text-amber-400 tracking-wide">📂 Carteira de Pastas e Negociações</h3>
                </div>
                <div class="overflow-x-auto p-2">
                    <table class="w-full text-left text-xs border-collapse">
                        <thead class="bg-slate-950 border-b border-slate-800 text-slate-400 font-semibold uppercase">
                            <tr>
                                <th class="py-3 px-4">Pasta</th>
                                <th class="py-3 px-4">Cliente / Vendedor</th>
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

        <!-- RESUMO DA VENDA & QUALIFICAÇÃO -->
        <div class="lg:col-span-3 space-y-4">
            <div class="bg-slate-900 border border-slate-800 rounded-3xl p-5 shadow-xl space-y-3 text-xs">
                <h3 class="font-bold text-amber-400 pb-1 border-b border-slate-800 uppercase tracking-wide">Resumo da Venda</h3>
                <div class="space-y-1 text-slate-400">
                    <div class="flex justify-between"><span>Vendedor:</span> <span class="font-semibold text-white">{c_vendedor}</span></div>
                    <div class="flex justify-between"><span>Comissão:</span> <span class="font-bold text-emerald-400">R$ {c_comissao:,.2f}</span></div>
                    <div class="flex justify-between items-center pt-1"><span class="text-slate-400 font-semibold">Valor Venda:</span> <span class="font-bold text-amber-400 text-sm">R$ {c_p_venda:,.2f}</span></div>
                    <div class="flex justify-between items-center"><span class="text-slate-400 font-semibold">Entrada:</span> <span class="font-bold text-emerald-400 text-sm">R$ {c_entrada:,.2f}</span></div>
                </div>
            </div>

            <div class="bg-slate-900 border border-slate-800 rounded-3xl p-5 shadow-xl space-y-3.5 text-xs">
                <div class="flex justify-between items-center pb-1 border-b border-slate-800">
                    <h3 class="font-bold text-white uppercase tracking-wide">Check List Operacional</h3>
                </div>
                <ul class="space-y-2">
                    <li class="flex justify-between items-center p-1.5 bg-slate-950 rounded-xl border border-slate-800">
                        <span class="font-medium text-slate-300">Dados do Cliente:</span>
                        <span class="text-[10px] font-semibold text-slate-400">{txt_d}</span>
                    </li>
                    <li class="flex justify-between items-center p-1.5 bg-slate-950 rounded-xl border border-slate-800">
                        <span class="font-medium text-slate-300">Aprovação Comercial:</span>
                        <span class="text-[10px] font-semibold text-slate-400">{txt_c}</span>
                    </li>
                    <li class="flex justify-between items-center p-1.5 bg-slate-950 rounded-xl border border-slate-800">
                        <span class="font-medium text-slate-300">Aprovação Financeira:</span>
                        <span class="text-[10px] font-semibold text-slate-400">{txt_f}</span>
                    </li>
                    <li class="flex justify-between items-center p-1.5 bg-slate-950 rounded-xl border border-slate-800">
                        <span class="font-medium text-slate-300">Assinatura Contrato:</span>
                        <span class="text-[10px] font-semibold text-slate-400">{txt_con}</span>
                    </li>
                </ul>
            </div>
        </div>

    </div>

    <script>
        function mudarAba(abaId) {{
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            document.querySelectorAll('.tree-item').forEach(b => b.classList.remove('active'));
            
            var targetAba = document.getElementById(abaId);
            var targetBtn = document.getElementById('btn-' + abaId);
            
            if (targetAba) targetAba.classList.add('active');
            if (targetBtn) targetBtn.classList.add('active');
            window.scrollTo({{ top: 0, behavior: 'smooth' }});
        }}
    </script>
</body></html>"""

# ==============================================================================
# 5. ROTAS FASTAPI
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
    cursor.execute("SELECT * FROM usuarios WHERE email = ? AND senha = ?", (username.strip().lower(), password))
    user = cursor.fetchone()
    conn.close()

    if not user:
        return render_login("E-mail ou senha incorretos. Verifique suas credenciais.")

    if not user["ativo"]:
        return render_login("❌ Este usuário foi desativado pela administração.")

    CURRENT_SESSION["user_email"] = user["email"]
    CURRENT_SESSION["user_nome"] = user["nome"]
    CURRENT_SESSION["user_perfil"] = user["perfil"]
    CURRENT_SESSION["empresa_id"] = user["empresa_id"]

    return render_dashboard_view()

@app.get("/painel", response_class=HTMLResponse)
@app.get("/painel-get", response_class=HTMLResponse)
def painel_get_route():
    return render_dashboard_view()

@app.post("/criar-usuario", response_class=HTMLResponse)
def criar_usuario_route(
    request: Request,
    nome: str = Form(...),
    email: str = Form(...),
    perfil: str = Form("vendedor")
):
    if CURRENT_SESSION.get("user_perfil") != "adm":
        return RedirectResponse(url="/painel-get", status_code=303)

    token = secrets.token_urlsafe(16)
    senha_temp = f"MVI@{secrets.randbelow(8999)+1000}"
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO usuarios (email, senha, nome, perfil, empresa_id, token_primeiro_acesso, primeiro_acesso_concluido, ativo)
        VALUES (?, ?, ?, ?, 1, ?, 0, 1)
    """, (email.strip().lower(), senha_temp, nome.strip(), perfil, token))
    conn.commit()
    conn.close()

    link_ativacao = f"{str(request.base_url).rstrip('/')}/primeiro-acesso/{token}"
    return render_convite_gerado(nome, email, perfil, "", link_ativacao, senha_temp)

@app.get("/primeiro-acesso/{token}", response_class=HTMLResponse)
def tela_primeiro_acesso(token: str):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM usuarios WHERE token_primeiro_acesso = ?", (token,))
    user = cursor.fetchone()
    conn.close()
    if not user:
        return HTMLResponse("Link de ativação inválido ou já utilizado.", status_code=404)
    return render_tela_nova_senha(user, token)

@app.post("/salvar-nova-senha", response_class=HTMLResponse)
def salvar_nova_senha(token: str = Form(...), nova_senha: str = Form(...), confirma_senha: str = Form(...)):
    if nova_senha != confirma_senha:
        return HTMLResponse("<script>alert('As senhas digitadas não coincidem!'); history.back();</script>")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE usuarios SET senha = ?, token_primeiro_acesso = '', primeiro_acesso_concluido = 1, ativo = 1 WHERE token_primeiro_acesso = ?", (nova_senha, token))
    conn.commit()
    conn.close()
    return RedirectResponse(url="/", status_code=303)

@app.post("/redefinir-senha-funcionario", response_class=HTMLResponse)
def redefinir_senha_funcionario(request: Request, email_funcionario: str = Form(...)):
    if CURRENT_SESSION.get("user_perfil") != "adm":
        return RedirectResponse(url="/painel-get", status_code=303)
        
    token = secrets.token_urlsafe(16)
    senha_temp = f"MVI@{secrets.randbelow(8999)+1000}"
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT nome, perfil FROM usuarios WHERE email = ?", (email_funcionario,))
    user = cursor.fetchone()
    if user:
        cursor.execute("UPDATE usuarios SET senha = ?, token_primeiro_acesso = ?, primeiro_acesso_concluido = 0 WHERE email = ?", (senha_temp, token, email_funcionario))
        conn.commit()
        conn.close()
        link_ativacao = f"{str(request.base_url).rstrip('/')}/primeiro-acesso/{token}"
        return render_convite_gerado(user["nome"], email_funcionario, user["perfil"], "", link_ativacao, senha_temp)
    conn.close()
    return RedirectResponse(url="/painel-get", status_code=303)

@app.post("/salvar-negociacao-mesa", response_class=HTMLResponse)
def salvar_negociacao_mesa(
    orcamento_id: int = Form(...),
    preco_venda: float = Form(0.0),
    desconto_pct: float = Form(0.0),
    num_parcelas: int = Form(1),
    entrada_valor: float = Form(0.0),
    forma_opcao: str = Form("Entrada PIX + Cartão de Crédito")
):
    empresa = get_empresa_dados(1)
    desconto_max = float(empresa.get("desconto_max_vendedor", 3.0))
    pct_comissao = float(empresa.get("comissao_padrao_pct", 4.0))

    precisa_aprov = (desconto_pct > desconto_max and CURRENT_SESSION["user_perfil"] == "vendedor")
    desconto_autorizado = 0 if precisa_aprov else 1
    status = "Aguardando Liberação de Desconto" if precisa_aprov else "Em Negociação"

    comissao_calculada = round(preco_venda * (pct_comissao / 100.0))

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT custo_materiais, custo_mao_obra, custo_frete_montagem FROM orcamentos WHERE id = ?", (orcamento_id,))
    orc = cursor.fetchone()
    
    custo_tot = (float(orc["custo_materiais"] or 0) + float(orc["custo_mao_obra"] or 0) + float(orc["custo_frete_montagem"] or 0)) if orc else (preco_venda * 0.5)
    lucro_final = round(preco_venda - (custo_tot + (preco_venda * 0.10) + comissao_calculada))
    saldo = max(preco_venda - entrada_valor, 0.0)
    v_parc = round(saldo / num_parcelas) if num_parcelas > 0 else 0.0

    cursor.execute("""
        UPDATE orcamentos SET
            preco_bruto = ?,
            desconto_pct = ?,
            preco_venda = ?,
            modalidade_pagamento = ?,
            entrada_valor = ?,
            num_parcelas = ?,
            valor_parcela = ?,
            lucro_liquido = ?,
            comissao_pct = ?,
            comissao_valor = ?,
            desconto_autorizado = ?,
            status = ?
        WHERE id = ?
    """, (round(preco_venda), desconto_pct, round(preco_venda), forma_opcao, round(entrada_valor), num_parcelas, v_parc, lucro_final, pct_comissao, comissao_calculada, desconto_autorizado, status, orcamento_id))
    conn.commit()
    conn.close()
    return RedirectResponse(url="/painel-get", status_code=303)

@app.get("/solicitar-orcamento", response_class=HTMLResponse)
@app.get("/solicitar-orcamento/{slug}", response_class=HTMLResponse)
def captacao_route(slug: str = "mvi"):
    empresa = get_empresa_dados(1)
    return render_form_captacao(empresa)

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
    calc = calcular_engenharia(ambientes_selecionados, area_m2_total, espessura_caixa, cor_caixa, espessura_porta, cor_porta, acabamento_porta, espessura_tamponamento, marca_ferragens)

    agora = datetime.now().strftime("%d/%m/%Y %H:%M")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO orcamentos (
            empresa_id, criado_em, vendedor_responsavel, vendedor_email, cliente_nome, cliente_telefone, cliente_ambiente,
            prazo_entrega, data_entrega_prevista, status, custo_materiais,
            custo_mao_obra, custo_frete_montagem, preco_bruto, preco_venda, lucro_liquido, comissao_valor,
            observacoes_tecnicas, descricao_promob
        ) VALUES (1, ?, 'Raquel Marcelino', 'raquel@mvi.com', ?, ?, ?, '25 dias úteis', ?, 'Novo Lead Aberto', ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        agora, nome, whatsapp, ambientes_str, (date.today() + timedelta(days=25)).strftime("%Y-%m-%d"),
        calc["total_mat"], calc["custo_mo"], calc["custo_frete"], calc["preco_bruto"], calc["preco_venda"], calc["lucro"], calc["comissao"],
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
    cliente_telefone: str = Form(""),
    cliente_cep_postal: str = Form(""),
    cliente_endereco_postal: str = Form(""),
    cliente_cep_entrega: str = Form(""),
    cliente_endereco_entrega: str = Form("")
):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE orcamentos SET
            cliente_nome = ?, cliente_cpf = ?, cliente_telefone = ?,
            cliente_cep_postal = ?, cliente_endereco_postal = ?,
            cliente_cep_entrega = ?, cliente_endereco_entrega = ?
        WHERE id = ?
    """, (cliente_nome, cliente_cpf, cliente_telefone, cliente_cep_postal, cliente_endereco_postal, cliente_cep_entrega, cliente_endereco_entrega, orcamento_id))
    conn.commit()
    conn.close()
    return RedirectResponse(url="/painel-get", status_code=303)

@app.post("/adicionar-ambiente-pasta", response_class=HTMLResponse)
def adicionar_ambiente_pasta(orcamento_id: int = Form(...), nome_ambiente: str = Form(...), valor_ambiente: float = Form(0.0)):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT ambientes_json FROM orcamentos WHERE id = ?", (orcamento_id,))
    orc = cursor.fetchone()
    if orc:
        ambientes = []
        try:
            ambientes = json.loads(orc["ambientes_json"] or "[]")
        except Exception:
            ambientes = []
        ambientes.append({"id": len(ambientes) + 1, "nome": nome_ambiente.strip(), "valor": round(valor_ambiente)})
        total_ambientes = sum(float(a.get("valor", 0)) for a in ambientes)
        nomes_amb = " + ".join([a.get("nome", "") for a in ambientes if a.get("nome")])
        cursor.execute("UPDATE orcamentos SET ambientes_json = ?, preco_venda = ?, preco_bruto = ?, cliente_ambiente = ? WHERE id = ?", (json.dumps(ambientes), total_ambientes, total_ambientes, nomes_amb, orcamento_id))
        conn.commit()
    conn.close()
    return RedirectResponse(url="/painel-get", status_code=303)

@app.post("/remover-ambiente-pasta", response_class=HTMLResponse)
def remover_ambiente_pasta(orcamento_id: int = Form(...), ambiente_id: int = Form(...)):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT ambientes_json FROM orcamentos WHERE id = ?", (orcamento_id,))
    orc = cursor.fetchone()
    if orc:
        ambientes = [a for a in json.loads(orc["ambientes_json"] or "[]") if a.get("id") != ambiente_id]
        total_ambientes = sum(float(a.get("valor", 0)) for a in ambientes)
        nomes_amb = " + ".join([a.get("nome", "") for a in ambientes if a.get("nome")]) or "Projeto Sob Medida"
        cursor.execute("UPDATE orcamentos SET ambientes_json = ?, preco_venda = ?, preco_bruto = ?, cliente_ambiente = ? WHERE id = ?", (json.dumps(ambientes), total_ambientes, total_ambientes, nomes_amb, orcamento_id))
        conn.commit()
    conn.close()
    return RedirectResponse(url="/painel-get", status_code=303)

@app.post("/adicionar-versao-orcamento", response_class=HTMLResponse)
def adicionar_versao_orcamento(orcamento_id: int = Form(...), nome_versao: str = Form(...), valor_versao: float = Form(0.0)):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT versoes_orcamentos_json, preco_venda FROM orcamentos WHERE id = ?", (orcamento_id,))
    orc = cursor.fetchone()
    if orc:
        versoes = json.loads(orc["versoes_orcamentos_json"] or "[]")
        novo_id = len(versoes) + 1
        versoes.append({"id": novo_id, "nome": nome_versao.strip(), "valor": round(valor_versao), "ativo": True})
        cursor.execute("UPDATE orcamentos SET versoes_orcamentos_json = ?, versao_ativa_id = ?, preco_venda = ?, preco_bruto = ? WHERE id = ?", (json.dumps(versoes), novo_id, round(valor_versao), round(valor_versao), orcamento_id))
        conn.commit()
    conn.close()
    return RedirectResponse(url="/painel-get", status_code=303)

@app.post("/selecionar-versao-orcamento", response_class=HTMLResponse)
def selecionar_versao_orcamento(orcamento_id: int = Form(...), versao_id: int = Form(...)):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT versoes_orcamentos_json FROM orcamentos WHERE id = ?", (orcamento_id,))
    orc = cursor.fetchone()
    if orc:
        versoes = json.loads(orc["versoes_orcamentos_json"] or "[]")
        val = next((float(v.get("valor", 0)) for v in versoes if v.get("id") == versao_id), 0.0)
        if val > 0:
            cursor.execute("UPDATE orcamentos SET versao_ativa_id = ?, preco_venda = ?, preco_bruto = ? WHERE id = ?", (versao_id, val, val, orcamento_id))
            conn.commit()
    conn.close()
    return RedirectResponse(url="/painel-get", status_code=303)

@app.post("/selecionar-cliente-trabalho", response_class=HTMLResponse)
def selecionar_cliente_trabalho(orcamento_id: int = Form(...)):
    CURRENT_SESSION["cliente_ativo_id"] = None if orcamento_id == 0 else orcamento_id
    return RedirectResponse(url="/painel-get", status_code=303)

@app.post("/salvar-empresa", response_class=HTMLResponse)
def update_empresa(
    nome_empresa: str = Form("MVI Móveis Planejados"),
    cnpj: str = Form(""),
    telefone: str = Form(""),
    desconto_max_vendedor: float = Form(3.0),
    comissao_padrao_pct: float = Form(4.0)
):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE empresas SET
            nome_empresa = ?,
            cnpj = ?,
            telefone = ?,
            desconto_max_vendedor = ?,
            comissao_padrao_pct = ?
        WHERE id = 1
    """, (nome_empresa.strip(), cnpj.strip(), telefone.strip(), desconto_max_vendedor, comissao_padrao_pct))
    conn.commit()
    conn.close()
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
        return HTMLResponse("Contrato não encontrado.", status_code=404)
    empresa = get_empresa_dados(1)
    
    pv_total = float(orc['preco_venda'] or 0) + float(orc['adendo_valor'] or 0)
    return f"""<!DOCTYPE html><html><head><title>Contrato MVI #{orc['id']:04d}</title><script src="https://cdn.tailwindcss.com"></script></head>
    <body class="bg-white text-slate-900 p-10 font-sans leading-relaxed text-sm max-w-4xl mx-auto">
        <h1 class="text-center font-bold text-base border-b pb-3 uppercase">INSTRUMENTO PARTICULAR DE PRESTAÇÃO DE SERVIÇOS DE MARCENARIA</h1>
        <p class="mt-4"><b>CONTRATADA:</b> {empresa['nome_empresa']} (CNPJ: {empresa['cnpj']})</p>
        <p><b>CONTRATANTE:</b> {orc['cliente_nome']} (Tel: {orc['cliente_telefone']})</p>
        <p><b>OBJETO:</b> Fabricação e instalação de móveis sob medida para: <b>{orc['cliente_ambiente']}</b>.</p>
        <p><b>VALOR TOTAL:</b> R$ {pv_total:,.2f} em {orc['modalidade_pagamento']}.</p>
        <p><b>PRAZO:</b> {orc['prazo_entrega']}. <b>GARANTIA:</b> {orc['prazo_garantia']}.</p>
        <div class="mt-12 text-center"><button onclick="window.print()" class="px-4 py-2 bg-amber-500 text-slate-950 font-bold rounded">🖨️ Imprimir / Salvar PDF</button></div>
    </body></html>"""

@app.get("/assinar/{orcamento_id}", response_class=HTMLResponse)
def assinar_contrato_view(orcamento_id: int):
    return HTMLResponse(f"""<!DOCTYPE html><html><head><title>Assinatura Digital</title><script src="https://cdn.tailwindcss.com"></script></head>
    <body class="bg-slate-950 text-slate-100 flex items-center justify-center min-h-screen p-4 font-sans text-center">
        <div class="max-w-md w-full bg-slate-900 border border-emerald-500/40 p-8 rounded-3xl space-y-4">
            <h1 class="font-bold text-emerald-400 text-lg">Assinatura Digital Ativa</h1>
            <p class="text-xs text-slate-400">Contrato #{orcamento_id:04d} autenticado e disponível para assinatura.</p>
            <a href="/painel-get" class="inline-block px-4 py-2 bg-emerald-600 text-slate-950 font-bold rounded-xl text-xs">Voltar ao Painel</a>
        </div>
    </body></html>""")

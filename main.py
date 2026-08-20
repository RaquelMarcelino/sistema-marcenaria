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
DB_PATH = "mvi_production_v49.db"
META_PIXEL_ID = "641231925101582"



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
            imagens_json TEXT DEFAULT '{}',
            arquivo_planta TEXT DEFAULT '',
            arquivo_inspiracao TEXT DEFAULT '',
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

    # Migrações seguras caso o banco já exista
    for col in ["arquivo_planta TEXT DEFAULT ''", "arquivo_inspiracao TEXT DEFAULT ''", "imagens_json TEXT DEFAULT '{}'"]:
        try:
            cursor.execute(f"ALTER TABLE orcamentos ADD COLUMN {col}")
        except Exception:
            pass

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
    <title>{empresa['nome_empresa']} - Simulador</title>
    <script src="https://cdn.tailwindcss.com"></script>
    
    <!-- Meta Pixel Code Oficial -->
    <script>
    !function(f,b,e,v,n,t,s)
    {{if(f.fbq)return;n=f.fbq=function(){{n.callMethod?
    n.callMethod.apply(n,arguments):n.queue.push(arguments)}};
    if(!f._fbq)f._fbq=n;n.push=n;n.loaded=!0;n.version='2.0';
    n.queue=[];t=b.createElement(e);t.async=!0;
    t.src=v;s=b.getElementsByTagName(e)[0];
    s.parentNode.insertBefore(t,s)}}(window, document,'script',
    'https://connect.facebook.net/en_US/fbevents.js');
    fbq('init', '{META_PIXEL_ID}');
    fbq('track', 'PageView');
    fbq('track', 'InitiateCheckout');
    </script>
    <noscript><img height="1" width="1" style="display:none"
    src="https://www.facebook.com/tr?id={META_PIXEL_ID}&ev=PageView&noscript=1"
    /></noscript>
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
                    <label class="font-bold text-amber-400 block">📐 Planta Baixa do Imóvel (PDF ou Imagem)</label>
                    <input type="file" name="planta" class="w-full text-slate-400 file:bg-amber-500 file:border-0 file:rounded-xl file:px-3 file:py-1 file:font-bold text-xs">
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
    
    <script>
    !function(f,b,e,v,n,t,s)
    {{if(f.fbq)return;n=f.fbq=function(){{n.callMethod?
    n.callMethod.apply(n,arguments):n.queue.push(arguments)}};
    if(!f._fbq)f._fbq=n;n.push=n;n.loaded=!0;n.version='2.0';
    n.queue=[];t=b.createElement(e);t.async=!0;
    t.src=v;s=b.getElementsByTagName(e)[0];
    s.parentNode.insertBefore(t,s)}}(window, document,'script',
    'https://connect.facebook.net/en_US/fbevents.js');
    fbq('init', '{META_PIXEL_ID}');
    fbq('track', 'PageView');
    fbq('track', 'Lead', {{
        content_name: '{ambientes_str}',
        value: {pv_redondo},
        currency: 'BRL'
    }});
    </script>
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
<a href="https://wa.me/55{tel_limpo}?text=Ol%C3%A1!%20Simulei%20meu%20projeto%20no%20site%20da%20{empresa['nome_empresa']}%20(Projeto%20%23{orcamento_id:04d})%20e%20gostaria%20de%20atendimento!" target="_blank" class="w-full py-4 bg-emerald-500 hover:bg-emerald-600 text-slate-950 font-bold rounded-2xl flex items-center justify-center space-x-2 shadow-lg shadow-emerald-500/20 transition-all text-sm uppercase tracking-wider block">
                📲 Enviar Simulação para o WhatsApp da Empresa
</a>
        </div>
    </div>
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

    # Recupera imagens e arquivos salvos
    c_imagens = {}
    try:
        c_imagens = json.loads(cliente_ativo.get("imagens_json") or "{}")
    except Exception:
        c_imagens = {}
        
    planta_data = c_imagens.get("planta") or cliente_ativo.get("arquivo_planta") or ""
    planta_nome = c_imagens.get("planta_nome") or "Planta Baixa"
    insp_data = c_imagens.get("inspiracao") or cliente_ativo.get("arquivo_inspiracao") or ""
    insp_nome = c_imagens.get("inspiracao_nome") or "Foto Inspiração"

    tel_lead_limpo = c_tel.replace("-","").replace(" ","").replace("(","").replace(")","")

    anexos_html = f"""
    <div class="bg-slate-900 border border-slate-800 rounded-3xl p-5 shadow-xl space-y-3">
        <h3 class="font-bold text-amber-400 text-xs uppercase tracking-wide flex items-center justify-between pb-1 border-b border-slate-800">
            <span>📁 Arquivos & Anexos do Lead</span>
            <span class="text-[10px] text-slate-400 font-normal">Planta & Referências</span>
        </h3>
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
            <div class="p-3 bg-slate-950 rounded-2xl border border-slate-800 space-y-2">
                <div class="flex items-center justify-between">
                    <span class="font-bold text-slate-300">📐 Planta Baixa:</span>
                    <span class="text-[10px] text-amber-400 font-mono truncate max-w-[120px]">{planta_nome}</span>
                </div>
                {f'''<a href="{planta_data}" target="_blank" download="{planta_nome}" class="block text-center py-2 px-3 bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold rounded-xl transition shadow">👁️ Abrir / Baixar Planta</a>''' if planta_data else '''<span class="block text-center py-2 text-slate-500 bg-slate-900 rounded-xl border border-slate-800">Nenhuma planta anexada</span>'''}
            </div>
            <div class="p-3 bg-slate-950 rounded-2xl border border-slate-800 space-y-2">
                <div class="flex items-center justify-between">
                    <span class="font-bold text-slate-300">🖼️ Foto Inspiração:</span>
                    <span class="text-[10px] text-slate-400 font-mono truncate max-w-[120px]">{insp_nome}</span>
                </div>
                {f'''<a href="{insp_data}" target="_blank" download="{insp_nome}" class="block text-center py-2 px-3 bg-slate-800 hover:bg-slate-700 text-slate-200 font-bold rounded-xl transition border border-slate-700">👁️ Abrir / Baixar Foto</a>''' if insp_data else '''<span class="block text-center py-2 text-slate-500 bg-slate-900 rounded-xl border border-slate-800">Nenhuma foto anexada</span>'''}
            </div>
        </div>
    </div>
    """

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
                <button onclick="mudarAba('aba-comissoes')" class="px-3 py-1.5 rounded-lg bg-emerald-950/80 text-emerald-300 hover:bg-emerald-900 border border-emerald-500/40">💰 Comissões</button>
                {f'''<button onclick="mudarAba('aba-equipe')" class="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-amber-300 border border-slate-700">👥 Equipe</button>
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
                        {f'''<a href="https://api.whatsapp.com/send?phone=55{tel_lead_limpo}&text=Ol%C3%A1%20{c_nome}!%20Recebemos%20sua%20solicita%C3%A7%C3%A3o%20de%20projeto%20(Pasta%20P{c_id:05d})%20na%20{empresa['nome_empresa']}." target="_blank" class="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-slate-950 font-black rounded-xl text-xs shadow flex items-center gap-1">📲 WhatsApp do Lead</a>''' if tel_lead_limpo else ''}
                    </div>

                    <div class="grid grid-cols-2 gap-3 text-xs pt-2">
                        <div><span class="text-slate-500 block text-[11px]">Cliente:</span><span class="font-bold text-white text-sm">{c_nome}</span></div>
                        <div><span class="text-slate-500 block text-[11px]">CPF / CNPJ:</span><span class="font-bold text-slate-300">{c_cpf}</span></div>
                        <div><span class="text-slate-500 block text-[11px]">Prazo de Entrega:</span><span class="font-bold text-slate-300">{c_prazo}</span></div>
                        <div><span class="text-slate-500 block text-[11px]">Telefone:</span><span class="font-bold text-slate-300">{c_tel}</span></div>
                    </div>
                </div>

                <!-- ARQUIVOS E ANEXOS DO LEAD (PLANTA / INSPIRAÇÃO) -->
                {anexos_html}

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
                            <input type="text" name="cliente_cep_entrega" value="{c_cep_ent}" placeholder="CEP Obra" class="w-full p-2 bg-slate-900 border border-slate-700 rounded-xl text-white">{c_end_ent}</textarea>
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
                        <label class="block text-slate-400 mb-1 font-semibold">WhatsApp Comercial (com DDD)</label>
                        <input type="text" name="telefone" value="{empresa.get('telefone','')}" placeholder="Ex: 11999998888" class="w-full p-2.5 bg-slate-950 border border-slate-700 rounded-xl text-white">
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

        </div>

        <!-- RESUMO LATERAL DA VENDA & QUALIFICAÇÃO -->
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
    planta: UploadFile = File(None),
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

    # Conversão dos arquivos para Base64 persistente
    planta_b64, planta_nome = "", ""
    if planta and planta.filename:
        try:
            p_bytes = await planta.read()
            if p_bytes:
                mime_p = planta.content_type or "application/octet-stream"
                planta_b64 = f"data:{mime_p};base64,{base64.b64encode(p_bytes).decode('utf-8')}"
                planta_nome = planta.filename
        except Exception:
            pass

    insp_b64, insp_nome = "", ""
    if inspiracao and inspiracao.filename:
        try:
            i_bytes = await inspiracao.read()
            if i_bytes:
                mime_i = inspiracao.content_type or "image/jpeg"
                insp_b64 = f"data:{mime_i};base64,{base64.b64encode(i_bytes).decode('utf-8')}"
                insp_nome = inspiracao.filename
        except Exception:
            pass

    anexos_payload = json.dumps({
        "planta": planta_b64,
        "planta_nome": planta_nome,
        "inspiracao": insp_b64,
        "inspiracao_nome": insp_nome
    })

    agora = datetime.now().strftime("%d/%m/%Y %H:%M")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO orcamentos (
            empresa_id, criado_em, vendedor_responsavel, vendedor_email, cliente_nome, cliente_telefone, cliente_ambiente,
            prazo_entrega, data_entrega_prevista, status, custo_materiais,
            custo_mao_obra, custo_frete_montagem, preco_bruto, preco_venda, lucro_liquido, comissao_valor,
            observacoes_tecnicas, descricao_promob, imagens_json, arquivo_planta, arquivo_inspiracao
        ) VALUES (1, ?, 'Raquel Marcelino', 'raquel@mvi.com', ?, ?, ?, '25 dias úteis', ?, 'Novo Lead Aberto', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        agora, nome, whatsapp, ambientes_str, (date.today() + timedelta(days=25)).strftime("%Y-%m-%d"),
        calc["total_mat"], calc["custo_mo"], calc["custo_frete"], calc["preco_bruto"], calc["preco_venda"], calc["lucro"], calc["comissao"],
        descricao, calc["desc_promob"], anexos_payload, planta_b64, insp_b64
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

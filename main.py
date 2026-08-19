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
DB_PATH = "mvi_production_v34.db"

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
            prazo_entrega TEXT DEFAULT '30 dias úteis',
            data_entrega_prevista TEXT DEFAULT '',
            status TEXT DEFAULT 'Em Negociação',
            etapa_atual INTEGER DEFAULT 1,
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
# 4. TODAS AS TELAS E FUNÇÕES DE RENDERIZAÇÃO HTML (DECLARADAS ANTES DAS ROTAS)
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

def render_minuta_contrato(orc, empresa):
    pv_total = float(orc.get('preco_venda') or 0) + float(orc.get('adendo_valor') or 0)
    adendo_bloco = f"""
    <div class="p-4 bg-amber-950/40 border border-amber-500/40 rounded-xl space-y-1 my-3">
        <span class="text-amber-400 font-bold block">➕ TERMO ADITIVO / COMPLEMENTO INTEGRANTE:</span>
        <p>{orc.get('adendo_descricao','')}</p>
        <p class="font-bold text-white">Valor Adicional do Adendo: R$ {float(orc.get('adendo_valor') or 0):,.2f}</p>
    </div>
    """ if float(orc.get('adendo_valor') or 0) > 0 else ""

    link_assinar = f"/assinar/{orc.get('id', 1)}"

    return f"""<!DOCTYPE html>
<html lang="pt-br">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Minuta de Contrato #{orc.get('id', 1):04d} - {empresa['nome_empresa']}</title>
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
            <b>CONTRATANTE:</b> <b>{orc.get('cliente_nome','')}</b>, portador do CPF nº <b>{orc.get('cliente_cpf') or 'Pendente'}</b>, RG nº <b>{orc.get('cliente_rg','')} ({orc.get('cliente_rg_emissor') or 'SSP'})</b>, nascido em <b>{orc.get('cliente_nascimento') or '—'}</b>, residente no endereço postal: <b>{orc.get('cliente_endereco_postal') or 'Não informado'} (CEP: {orc.get('cliente_cep_postal') or '—'})</b>, com telefone <b>{orc.get('cliente_telefone','')}</b> e e-mail <b>{orc.get('cliente_email') or 'Não informado'}</b>.</p>

            <p><b>CLÁUSULA 2ª - DO OBJETO:</b><br>
            O presente instrumento tem por objeto a prestação de serviços de marcenaria técnica sob medida para fabricação, transporte e montagem dos móveis planejados destinados aos ambientes: <b>{orc.get('cliente_ambiente','')}</b>, no endereço de entrega da obra: <b>{orc.get('cliente_endereco_entrega') or orc.get('cliente_endereco_postal','')} (CEP: {orc.get('cliente_cep_entrega') or orc.get('cliente_cep_postal','')})</b>.</p>

            <p><b>CLÁUSULA 3ª - DO MEMORIAL DESCRITIVO E ESPECIFICAÇÕES TÉCNICAS:</b><br>
            <b>3.1. Descritivo Promob / Projeto Técnico:</b><br>
            {orc.get('descricao_promob') or 'Conforme projeto executivo 3D aprovado pelo cliente.'}<br><br>
            <b>3.2. Detalhamento e Acabamentos Manuais:</b><br>
            {orc.get('descricao_manual') or 'Caixaria reforçada, portas com alinhamento milimétrico, ferragens com amortecimento slowmotion e tamponamentos inclusos.'}</p>

            {adendo_bloco}

            <p><b>CLÁUSULA 4ª - DO PREÇO E DAS CONDIÇÕES DE PAGAMENTO:</b><br>
            Pelos serviços contratados, o CONTRATANTE pagará à CONTRATADA o valor líquido total de <b>R$ {pv_total:,.2f}</b>, nas seguintes condições:<br>
            • <b>Modalidade:</b> {orc.get('modalidade_pagamento') or orc.get('forma_pagamento','Entrada + Saldo Parcelado')}<br>
            • <b>Valor de Entrada:</b> R$ {float(orc.get('entrada_valor') or 0):,.2f}<br>
            • <b>Saldo Restante:</b> Parcelado em <b>{orc.get('num_parcelas', 1)} parcela(s)</b> de <b>R$ {float(orc.get('valor_parcela') or (pv_total - float(orc.get('entrada_valor') or 0))/max(int(orc.get('num_parcelas') or 1), 1)):,.2f}</b>.</p>

            <p><b>CLÁUSULA 5ª - DOS PRAZOS DE FABRICAÇÃO E INSTALAÇÃO:</b><br>
            O prazo estimado para entrega e finalização da montagem é de <b>{orc.get('prazo_entrega','30 dias úteis')}</b>, contados a partir da aprovação final das medidas no local e confirmação do pagamento da entrada.</p>

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
    pv_total = float(orc.get('preco_venda') or 0) + float(orc.get('adendo_valor') or 0)
    
    adendo_bloco = f"""
    <div class="p-4 bg-amber-950/40 border border-amber-500/40 rounded-xl space-y-1 my-2">
        <span class="text-amber-400 font-bold block">➕ TERMO ADITIVO CONTRATUAL:</span>
        <p>{orc.get('adendo_descricao','')}</p>
        <p class="font-bold text-white">Valor do Adendo: R$ {float(orc.get('adendo_valor') or 0):,.2f}</p>
    </div>
    """ if float(orc.get('adendo_valor') or 0) > 0 else ""

    if orc.get("contrato_assinado"):
        return f"""<!DOCTYPE html>
<html lang="pt-br">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Via Oficial Assinada - Contrato #{orc.get('id', 1):04d}</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-slate-950 text-slate-100 min-h-screen p-4 sm:p-8 font-sans">
    <div class="max-w-4xl mx-auto bg-slate-900 border border-emerald-500/40 rounded-3xl p-6 sm:p-10 shadow-2xl space-y-6">
        <div class="flex flex-wrap justify-between items-center border-b border-slate-800 pb-4 gap-2">
            <div>
                <span class="px-3 py-1 bg-emerald-950 text-emerald-300 border border-emerald-500/40 rounded-xl text-xs font-bold">✓ Contrato Assinado Digitalmente</span>
                <h1 class="text-lg sm:text-xl font-bold text-white mt-1">VIA OFICIAL DO CONTRATO DE PRESTAÇÃO DE SERVIÇOS #{orc.get('id', 1):04d}</h1>
                <p class="text-xs text-slate-400">{empresa['nome_empresa']} | CNPJ: {empresa['cnpj']}</p>
            </div>
            <button onclick="window.print()" class="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-slate-950 font-bold rounded-xl text-xs shadow-lg">
                📥 Imprimir / Salvar PDF
            </button>
        </div>

        <div class="bg-slate-950 p-6 rounded-2xl border border-slate-800 text-xs space-y-4 leading-relaxed text-slate-300">
            <p><b>CONTRATADA:</b> {empresa['nome_empresa']} (CNPJ: {empresa['cnpj']})<br>
            <b>CONTRATANTE:</b> <b>{orc.get('cliente_nome','')}</b> (CPF: {orc.get('cliente_cpf') or 'Pendente'})<br>
            <b>AMBIENTES:</b> {orc.get('cliente_ambiente','')}<br>
            <b>ENDEREÇO DA INSTALAÇÃO:</b> {orc.get('cliente_endereco_entrega') or orc.get('cliente_endereco_postal','')}<br>
            <b>VALOR TOTAL:</b> R$ {pv_total:,.2f} ({orc.get('forma_pagamento','')})<br>
            <b>PRAZO DE MONTAGEM:</b> {orc.get('prazo_entrega','30 dias úteis')}<br>
            <b>GARANTIA:</b> 5 anos em ferragens estruturais e 12 meses em painéis de MDF.</p>
            
            {adendo_bloco}
        </div>

        <div class="bg-slate-950 p-6 rounded-2xl border border-emerald-500/30 space-y-3">
            <h3 class="text-xs font-bold text-emerald-400 uppercase">🛡️ Autenticação & Assinatura Digital do Contratante</h3>
            <p class="text-[11px] text-slate-400">Assinado digitalmente por <b>{orc.get('cliente_nome','')}</b> em <b>{orc.get('assinatura_data','')}</b>.</p>
            
            <div class="p-3 bg-white rounded-xl flex justify-center max-w-sm">
                <img src="{orc.get('assinatura_img','')}" alt="Assinatura do Cliente" class="max-h-24 object-contain">
            </div>
            <p class="text-[10px] text-slate-500">Protocolo de Registro MVI: SHA256-MVI-{orc.get('id', 1):04d}-{orc.get('assinatura_data','')}</p>
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
            <span class="px-3 py-1 bg-amber-950 text-amber-300 border border-amber-500/40 rounded-xl text-xs font-bold">Contrato #{orc.get('id', 1):04d}</span>
        </div>

        <div class="bg-slate-950 p-6 rounded-2xl border border-slate-800 text-xs space-y-4 leading-relaxed text-slate-300 max-h-80 overflow-y-auto">
            <p><b>1. DAS PARTES CONTRATANTES:</b><br>
            <b>CONTRATADA:</b> {empresa['nome_empresa']}, CNPJ: {empresa['cnpj']}, Telefone: {empresa['telefone']}.<br>
            <b>CONTRATANTE:</b> <b>{orc.get('cliente_nome','')}</b>, CPF: <b>{orc.get('cliente_cpf') or 'Pendente'}</b>, Endereço: <b>{orc.get('cliente_endereco_postal') or 'Não informado'}</b>.</p>

            <p><b>2. DO OBJETO E AMBIENTES:</b><br>
            Fabricação e instalação de móveis sob medida para: <b>{orc.get('cliente_ambiente','')}</b>, na obra: <b>{orc.get('cliente_endereco_entrega') or orc.get('cliente_endereco_postal','')}</b>.</p>

            <p><b>3. DO VALOR E CONDIÇÕES:</b><br>
            Valor total de <b>R$ {pv_total:,.2f}</b>, sob as condições: <b>{orc.get('forma_pagamento','')}</b>.</p>

            <p><b>4. DO PRAZO E GARANTIA:</b><br>
            Prazo de entrega de <b>{orc.get('prazo_entrega','30 dias úteis')}</b>. Garantia de 5 anos em ferragens com amortecedores e 12 meses em painéis de MDF.</p>
            
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
                    <input type="hidden" name="orcamento_id" value="{orc.get('id', 1)}">
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
    lucro_final = round(preco_venda - (custo_tot + (preco_venda * 0.10)))
    
    saldo = max(preco_venda - entrada_valor, 0.0)
    v_parc = round(saldo / num_parcelas) if num_parcelas > 0 else 0.0

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
    """, (round(preco_bruto), desconto_pct, round(preco_venda), markup, modalidade_pagamento, round(entrada_valor), num_parcelas, v_parc, lucro_final, desconto_autorizado, status, orcamento_id))
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
        ) VALUES (1, ?, ?, ?, ?, '30 dias úteis', ?, 'Novo Lead Instagram', ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        agora, nome, whatsapp, ambientes_str, (date.today() + timedelta(days=30)).strftime("%Y-%m-%d"),
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
    forma_pagamento: str = Form("Cartão de Crédito até 12x"),
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
                1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Projeto Sob Medida', ?, ?, 1, 'Contrato Pronto para Assinatura',
                ?, ?, ?, ?, ?, ?, '30 dias úteis', ?
            )
        """, (
            agora, cliente_nome, cliente_cpf, cliente_rg, cliente_rg_emissor,
            cliente_nascimento, cliente_pais, cliente_cidade, cliente_email,
            cliente_telefone, cliente_telefone_2, cliente_cep_postal, cliente_endereco_postal,
            cliente_cep_entrega, cliente_endereco_entrega, descricao_manual, desconto_pct,
            pv_base, pv_final, lucro_final, forma_pagamento, round(entrada_valor), num_parcelas,
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
            pv_final = round(pv_base * (1.0 - (desconto_pct / 100.0)))
            lucro_final = round(pv_final - (custo_tot + (pv_final * 0.10)))

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

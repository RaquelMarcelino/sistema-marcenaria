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
DB_PATH = "mvi_production_v45.db"

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
            nome_empresa TEXT DEFAULT '',
            cnpj TEXT DEFAULT '',
            endereco TEXT DEFAULT '',
            telefone TEXT DEFAULT '',
            email TEXT DEFAULT '',
            pix TEXT DEFAULT '',
            precos_json TEXT DEFAULT '{}',
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
            cliente_ambiente TEXT,
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
            INSERT INTO empresas (id, slug, nome_empresa, cnpj, endereco, telefone, email, pix, precos_json, chave_mestra)
            VALUES (1, 'mvi', '', '', '', '', '', '', ?, 'MVI2026')
        """, (json.dumps(precos_iniciais),))
        
        cursor.execute("INSERT OR REPLACE INTO usuarios VALUES ('admin@mvi.com', '123456', 'Administrador Geral MVI', 'admin', 1, '', 1, 1)")
        cursor.execute("INSERT OR REPLACE INTO usuarios VALUES ('vendedor@mvi.com', '123456', 'Consultor Comercial', 'vendedor', 1, '', 1, 1)")
        conn.commit()

    conn.close()

init_db()

CURRENT_SESSION = {
    "user_email": "admin@mvi.com",
    "user_nome": "Administrador Geral",
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
        "id": 1, "slug": "mvi", "nome_empresa": "",
        "cnpj": "", "endereco": "", "telefone": "",
        "email": "", "pix": "", "precos_json": "{}", "chave_mestra": "MVI2026"
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
# 4. TODAS AS FUNÇÕES DE RENDERIZAÇÃO HTML (DECLARADAS ANTES DAS ROTAS)
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
    entrada_val = float(orc.get('entrada_valor') or 0)
    n_parc = int(orc.get('num_parcelas') or 1)
    val_parc = float(orc.get('valor_parcela') or ((pv_total - entrada_val) / max(n_parc, 1)))

    nome_empresa = empresa.get('nome_empresa') or "_____________________________________"
    cnpj_empresa = empresa.get('cnpj') or "00.000.000/0001-00"
    tel_empresa = empresa.get('telefone') or "(00) 00000-0000"
    
    nome_cliente = orc.get('cliente_nome') or "_____________________________________"
    tel_cliente = orc.get('cliente_telefone') or "_____________________"
    ambiente_txt = orc.get('cliente_ambiente') or "Cozinha Planejada"
    prazo_txt = orc.get('prazo_entrega') or "25 dias úteis"
    garantia_txt = orc.get('prazo_garantia') or "12 (doze) meses"
    cidade_txt = orc.get('cliente_cidade') or "São Paulo"
    data_extenso = datetime.now().strftime("%d de %B de %Y")

    if entrada_val > 0:
        condicoes_texto = f"Entrada no valor de R$ {entrada_val:,.2f} mais {n_parc} parcela(s) de R$ {val_parc:,.2f} através de {orc.get('modalidade_pagamento', 'Entrada + Cartão de Crédito')}."
    else:
        condicoes_texto = f"Pagamento integral no valor de R$ {pv_total:,.2f} através de {orc.get('modalidade_pagamento', 'PIX / À Vista')}."

    link_assinar = f"/assinar/{orc.get('id', 1)}"

    return f"""<!DOCTYPE html>
<html lang="pt-br">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Contrato de Prestação de Serviços - {nome_empresa}</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        @media print {{
            .no-print {{ display: none !important; }}
            body {{ background: white !important; color: black !important; padding: 0 !important; }}
            .folha-contrato {{ box-shadow: none !important; border: none !important; max-width: 100% !important; padding: 20mm !important; }}
        }}
    </style>
</head>
<body class="bg-slate-900 text-slate-100 min-h-screen p-4 sm:p-8 font-sans">
    
    <div class="max-w-4xl mx-auto mb-4 flex justify-between items-center no-print">
        <a href="/painel-get" class="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-xl text-xs font-bold border border-slate-700">← Voltar ao Painel</a>
        <div class="flex gap-2">
            <button onclick="window.print()" class="px-4 py-2 bg-amber-500 hover:bg-amber-400 text-slate-950 rounded-xl text-xs font-bold shadow-lg">🖨️ Imprimir / Salvar PDF</button>
            <a href="{link_assinar}" class="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-xl text-xs font-bold shadow-lg">✍️ Assinatura Digital</a>
        </div>
    </div>

    <!-- DOCUMENTO FORMATO PDF / A4 -->
    <div class="folha-contrato max-w-4xl mx-auto bg-white text-slate-900 rounded-2xl p-8 sm:p-14 shadow-2xl space-y-6 text-justify leading-relaxed text-sm">
        
        <div class="text-center border-b border-slate-300 pb-4">
            <h1 class="font-bold text-base sm:text-lg tracking-wide uppercase">INSTRUMENTO PARTICULAR DE PRESTAÇÃO DE SERVIÇOS DE MARCENARIA</h1>
        </div>

        <div class="space-y-4">
            <div>
                <h2 class="font-bold text-sm uppercase text-slate-800">1. IDENTIFICAÇÃO DAS PARTES CONTRATANTES</h2>
                <p class="mt-1">
                    <b>CONTRATADA:</b> {nome_empresa if nome_empresa else '<span class="text-rose-600">[Defina o nome da empresa em Configurações]</span>'}, inscrita no CNPJ sob o nº {cnpj_empresa}, contato {tel_empresa}.<br>
                    <b>CONTRATANTE:</b> <b>{nome_cliente}</b>, telefone/WhatsApp {tel_cliente}.
                </p>
            </div>

            <div>
                <h2 class="font-bold text-sm uppercase text-slate-800">2. OBJETO DO CONTRATO</h2>
                <p class="mt-1">
                    O presente contrato tem por objeto a fabricação, acabamento e instalação de móveis sob medida destinados ao ambiente: <b>{ambiente_txt}</b>, em conformidade com o projeto executivo e relação de insumos aprovados.
                </p>
            </div>

            <div>
                <h2 class="font-bold text-sm uppercase text-slate-800">3. VALOR E FORMA DE PAGAMENTO</h2>
                <p class="mt-1">
                    Pela execução integral dos serviços descritos, o CONTRATANTE pagará à CONTRATADA o valor total de <b>R$ {pv_total:,.2f}</b>, nas seguintes condições: {condicoes_texto}
                </p>
            </div>

            <div>
                <h2 class="font-bold text-sm uppercase text-slate-800">4. PRAZO DE FABRICAÇÃO E INSTALAÇÃO</h2>
                <p class="mt-1">
                    A CONTRATADA compromete-se a entregar e finalizar a montagem dos móveis no prazo estimado de <b>{prazo_txt}</b>, contados a partir da aprovação final das medidas no local e confirmação do pagamento inicial.
                </p>
            </div>

            <div>
                <h2 class="font-bold text-sm uppercase text-slate-800">5. TERMO DE GARANTIA</h2>
                <p class="mt-1">
                    A CONTRATADA concede a garantia de <b>{garantia_txt}</b> a contar da data de entrega, cobrindo eventuais defeitos de fabricação e montagem de ferragens estruturais, não cobrindo danos ocasionados por umidade excessiva, mau uso ou intervenções de terceiros.
                </p>
            </div>
        </div>

        <div class="pt-8 text-right font-medium">
            <p>{cidade_txt}, {data_extenso}.</p>
        </div>

        <div class="pt-12 grid grid-cols-2 gap-8 text-center text-xs">
            <div class="border-t border-slate-900 pt-2 space-y-1">
                <p class="font-bold">{nome_empresa if nome_empresa else 'CONTRATADA'}</p>
                <p class="text-slate-600">CONTRATADA (CNPJ: {cnpj_empresa})</p>
            </div>
            <div class="border-t border-slate-900 pt-2 space-y-1">
                <p class="font-bold">{nome_cliente}</p>
                <p class="text-slate-600">CONTRATANTE</p>
            </div>
        </div>

    </div>

</body></html>"""[cite: 1]

def render_assinatura_online(orc, empresa):
    pv_total = float(orc.get('preco_venda') or 0) + float(orc.get('adendo_valor') or 0)
    entrada_val = float(orc.get('entrada_valor') or 0)
    n_parc = int(orc.get('num_parcelas') or 1)
    val_parc = float(orc.get('valor_parcela') or ((pv_total - entrada_val) / max(n_parc, 1)))

    nome_empresa = empresa.get('nome_empresa') or "MVI Móveis Planejados"
    cnpj_empresa = empresa.get('cnpj') or "00.000.000/0001-00"
    tel_empresa = empresa.get('telefone') or "(00) 00000-0000"
    nome_cliente = orc.get('cliente_nome') or "Cliente"
    tel_cliente = orc.get('cliente_telefone') or "—"
    ambiente_txt = orc.get('cliente_ambiente') or "Projeto Sob Medida"
    prazo_txt = orc.get('prazo_entrega') or "25 dias úteis"
    garantia_txt = orc.get('prazo_garantia') or "12 (doze) meses"

    if entrada_val > 0:
        condicoes_texto = f"Entrada de R$ {entrada_val:,.2f} + {n_parc} parcela(s) de R$ {val_parc:,.2f} ({orc.get('modalidade_pagamento')})."
    else:
        condicoes_texto = f"Pagamento integral no valor de R$ {pv_total:,.2f}."

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
                <h1 class="text-lg sm:text-xl font-bold text-white mt-1">VIA OFICIAL DO CONTRATO #{orc.get('id', 1):04d}</h1>
                <p class="text-xs text-slate-400">{nome_empresa} | CNPJ: {cnpj_empresa}</p>
            </div>
            <a href="/minuta-contrato/{orc.get('id', 1)}" target="_blank" class="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-slate-950 font-bold rounded-xl text-xs shadow-lg">
                📥 Imprimir / Salvar PDF
            </a>
        </div>

        <div class="bg-slate-950 p-6 rounded-2xl border border-slate-800 text-xs space-y-3 leading-relaxed text-slate-300">
            <p><b>CONTRATADA:</b> {nome_empresa} (CNPJ: {cnpj_empresa})<br>
            <b>CONTRATANTE:</b> <b>{nome_cliente}</b> (Tel: {tel_cliente})<br>
            <b>AMBIENTE:</b> {ambiente_txt}<br>
            <b>VALOR TOTAL:</b> R$ {pv_total:,.2f} ({condicoes_texto})<br>
            <b>PRAZO DE MONTAGEM:</b> {prazo_txt}<br>
            <b>GARANTIA:</b> {garantia_txt}.</p>
        </div>

        <div class="bg-slate-950 p-6 rounded-2xl border border-emerald-500/30 space-y-3">
            <h3 class="text-xs font-bold text-emerald-400 uppercase">🛡️ Autenticação & Assinatura Digital do Contratante</h3>
            <p class="text-[11px] text-slate-400">Assinado digitalmente por <b>{nome_cliente}</b> em <b>{orc.get('assinatura_data','')}</b>.</p>
            
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
</body></html>"""[cite: 1]

    return f"""<!DOCTYPE html>
<html lang="pt-br">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Assinatura Digital de Contrato - {nome_empresa}</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdn.jsdelivr.net/npm/signature_pad@4.1.7/dist/signature_pad.umd.min.js"></script>
</head>
<body class="bg-slate-950 text-slate-100 min-h-screen p-4 sm:p-8 font-sans">
    <div class="max-w-4xl mx-auto bg-slate-900 border border-slate-800 rounded-3xl p-6 sm:p-10 shadow-2xl space-y-6">
        <div class="flex justify-between items-center border-b border-slate-800 pb-4">
            <div>
                <h1 class="text-lg sm:text-xl font-bold text-white uppercase">INSTRUMENTO PARTICULAR DE PRESTAÇÃO DE SERVIÇOS DE MARCENARIA</h1>
                <p class="text-xs text-amber-400">{nome_empresa} | CNPJ: {cnpj_empresa}</p>
            </div>
            <span class="px-3 py-1 bg-amber-950 text-amber-300 border border-amber-500/40 rounded-xl text-xs font-bold">Contrato #{orc.get('id', 1):04d}</span>
        </div>

        <div class="bg-slate-950 p-6 rounded-2xl border border-slate-800 text-xs space-y-4 leading-relaxed text-slate-300 max-h-80 overflow-y-auto">
            <p><b>1. IDENTIFICAÇÃO DAS PARTES CONTRATANTES:</b><br>
            <b>CONTRATADA:</b> {nome_empresa}, CNPJ: {cnpj_empresa}, Contato: {tel_empresa}.<br>
            <b>CONTRATANTE:</b> <b>{nome_cliente}</b>, Telefone: <b>{tel_cliente}</b>.</p>

            <p><b>2. OBJETO DO CONTRATO:</b><br>
            Fabricação, acabamento e instalação de móveis sob medida destinados ao ambiente: <b>{ambiente_txt}</b>, em conformidade com o projeto executivo aprovado.</p>

            <p><b>3. VALOR E FORMA DE PAGAMENTO:</b><br>
            Valor total de <b>R$ {pv_total:,.2f}</b> ({condicoes_texto}).</p>

            <p><b>4. PRAZO DE FABRICAÇÃO E INSTALAÇÃO:</b><br>
            Prazo estimado de <b>{prazo_txt}</b>, contados a partir da aprovação final das medidas.</p>

            <p><b>5. TERMO DE GARANTIA:</b><br>
            Garantia de <b>{garantia_txt}</b> para defeitos de fabricação e montagem de ferragens estruturais.</p>
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
</body></html>"""[cite: 1]

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
    if not cliente_ativo and leads:
        cliente_ativo = dict(leads[0])
        CURRENT_SESSION["cliente_ativo_id"] = cliente_ativo.get("id")

    c_id = cliente_ativo.get("id", 0)
    c_nome = cliente_ativo.get("cliente_nome") or "Novo Cliente (Sem Pasta)"
    c_cpf = cliente_ativo.get("cliente_cpf") or "Não informado"
    c_rg = cliente_ativo.get("cliente_rg") or "—"
    c_tel = cliente_ativo.get("cliente_telefone") or "—"
    c_cep_post = cliente_ativo.get("cliente_cep_postal") or ""
    c_end_post = cliente_ativo.get("cliente_endereco_postal") or ""
    c_cep_ent = cliente_ativo.get("cliente_cep_entrega") or ""
    c_end_ent = cliente_ativo.get("cliente_endereco_entrega") or ""
    c_email = cliente_ativo.get("cliente_email") or ""

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
    
    chk_dados = int(cliente_ativo.get("check_dados") or (1 if c_cpf != 'Não informado' else 0))
    chk_comercial = int(cliente_ativo.get("check_comercial") or 1)
    chk_financeiro = int(cliente_ativo.get("check_financeiro") or 0)
    chk_contrato = int(cliente_ativo.get("check_contrato") or 0)
    potencial = cliente_ativo.get("potencial_cliente") or "Morno"

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
            <td class="py-2.5 px-3 text-center text-slate-500">—</td>
            <td class="py-2.5 px-3 text-center text-slate-500">—</td>
            <td class="py-2.5 px-3 text-center text-slate-500">—</td>
            <td class="py-2.5 px-3 text-slate-400">Parcela regular do projeto</td>
            <td class="py-2.5 px-3 text-center"><button class="text-amber-400 hover:underline">📄</button></td>
        </tr>
        """

    if not linhas_parcelas:
        linhas_parcelas = "<tr><td colspan='9' class='py-4 text-center text-xs text-slate-500'>Nenhuma parcela gerada.</td></tr>"

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
            <td class="py-3 px-4 text-white font-bold">{h_d.get('cliente_nome','')}<span class="block text-[11px] text-slate-400 font-normal">CPF: {h_d.get('cliente_cpf') or 'Pendente'}</span></td>
            <td class="py-3 px-4 text-slate-300">{h_d.get('cliente_ambiente','')}</td>
            <td class="py-3 px-4 text-amber-400 font-bold text-right">R$ {pv_total:,.2f}</td>
            <td class="py-3 px-4 text-center"><span class="px-2 py-0.5 rounded text-[11px] font-bold bg-amber-950 text-amber-300 border border-amber-500/30">{st}</span></td>
            <td class="py-3 px-4 text-center">
                <form action="/selecionar-cliente-trabalho" method="post" class="inline">
                    <input type="hidden" name="orcamento_id" value="{h_d['id']}">
                    <button type="submit" class="px-3 py-1 bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold rounded text-xs shadow-sm">
                        📂 Abrir Pasta / Negociar
                    </button>
                </form>
            </td>
        </tr>
        """

    if not leads_geral_html:
        leads_geral_html = "<tr><td colspan='6' class='py-8 text-center text-xs text-slate-500'>Nenhum cliente cadastrado ainda. Use a aba 'Dados do Cliente & CEP'.</td></tr>"

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
    <title>MVI Gestão - Contrato P{c_id:05d}</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        .tree-item {{ transition: all 0.2s; cursor: pointer; }}
        .tree-item:hover {{ background-color: #1e293b; color: #f59e0b; }}
        .tree-item.active {{ background: linear-gradient(135deg, #f59e0b, #d97706); color: #0f172a; font-weight: bold; }}
        .tab-content {{ display: none; }}
        .tab-content.active {{ display: block; }}
        .btn-dot {{ transition: all 0.15s; }}
        .btn-dot:hover {{ transform: scale(1.15); }}
    </style>
</head>
<body class="bg-slate-950 text-slate-100 font-sans min-h-screen">
    
    <!-- HEADER SUPERIOR MVI -->
    <header class="bg-slate-900 border-b border-slate-800 px-6 py-3 flex flex-wrap items-center justify-between shadow-lg">
        <div class="flex items-center space-x-6">
            <div class="flex items-center space-x-2 cursor-pointer" onclick="mudarAba('aba-geral')">
                <div class="w-9 h-9 rounded-xl bg-gradient-to-br from-amber-400 to-amber-600 text-slate-950 font-black flex items-center justify-center text-sm shadow">MVI</div>
                <span class="font-bold text-base tracking-wide text-white">{empresa.get('nome_empresa') or 'MVI Sistemas'}</span>
            </div>
            <nav class="flex items-center space-x-3 text-xs font-semibold">
                <button onclick="mudarAba('aba-geral')" class="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700">📂 Todas as Pastas</button>
                <button onclick="mudarAba('aba-empresa')" class="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-amber-300 border border-slate-700">🏢 Dados da Empresa</button>
                <a href="/solicitar-orcamento" target="_blank" class="px-3 py-1.5 rounded-lg bg-amber-950 text-amber-300 hover:bg-amber-900 border border-amber-500/40">🔗 Simulador Web</a>
                <a href="/exportar-csv" class="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700">📊 Relatório CSV</a>
            </nav>
        </div>

        <div class="flex items-center space-x-4 text-xs">
            <form action="/selecionar-cliente-trabalho" method="post" class="flex items-center gap-1">
                <select name="orcamento_id" onchange="this.form.submit()" class="px-3 py-1.5 rounded-xl bg-slate-950 text-amber-300 font-semibold border border-slate-700 focus:border-amber-500">
                    {options_leads}
                </select>
            </form>
            <span class="bg-amber-500 text-slate-950 px-2.5 py-0.5 rounded-full font-bold">{met['aprovados']} Fechados</span>
            <span class="text-slate-300 font-semibold">{CURRENT_SESSION['user_nome']}</span>
            <a href="/" class="bg-slate-800 hover:bg-slate-700 px-3 py-1.5 rounded-xl text-slate-300 border border-slate-700">Sair</a>
        </div>
    </header>

    <!-- CORPO PRINCIPAL COM ARQUITETURA DE 3 COLUNAS -->
    <div class="max-w-7xl mx-auto p-4 sm:p-6 grid grid-cols-1 lg:grid-cols-12 gap-5">
        
        <!-- COLUNA 1: MENU LATERAL COM TODAS AS ABAS -->
        <div class="lg:col-span-3 bg-slate-900 border border-slate-800 rounded-3xl p-4 shadow-xl space-y-4 text-xs">
            <div>
                <h3 class="font-bold text-white flex items-center justify-between pb-2 border-b border-slate-800">
                    <span>📁 Pasta P{c_id:05d}</span>
                    <span class="text-[10px] bg-amber-950 text-amber-300 border border-amber-500/40 px-2 py-0.5 rounded-full">Ativa</span>
                </h3>
                <ul class="mt-2 space-y-1">
                    <li><button onclick="mudarAba('aba-resumo')" id="btn-aba-resumo" class="tree-item active w-full text-left flex items-center gap-2 p-2.5 rounded-xl text-white font-semibold">📋 1. Resumo Financeiro</button></li>
                    <li><button onclick="mudarAba('aba-cliente')" id="btn-aba-cliente" class="tree-item w-full text-left flex items-center gap-2 p-2.5 rounded-xl text-slate-300 font-medium">👤 2. Dados do Cliente & CEP</button></li>
                    <li><button onclick="mudarAba('aba-mesa')" id="btn-aba-mesa" class="tree-item w-full text-left flex items-center gap-2 p-2.5 rounded-xl text-slate-300 font-medium">💼 3. Mesa de Negociação</button></li>
                    <li><button onclick="mudarAba('aba-promob')" id="btn-aba-promob" class="tree-item w-full text-left flex items-center gap-2 p-2.5 rounded-xl text-slate-300 font-medium">🚀 4. Integrador Promob</button></li>
                    <li><button onclick="mudarAba('aba-empresa')" id="btn-aba-empresa" class="tree-item w-full text-left flex items-center gap-2 p-2.5 rounded-xl text-slate-300 font-medium">🏢 5. Dados da Empresa</button></li>
                    <li><a href="/minuta-contrato/{c_id}" target="_blank" class="tree-item flex items-center gap-2 p-2.5 rounded-xl text-amber-400 font-bold hover:bg-slate-800">📜 6. Gerar Contrato PDF</a></li>
                    <li><a href="/assinar/{c_id}" target="_blank" class="tree-item flex items-center gap-2 p-2.5 rounded-xl text-emerald-400 font-bold hover:bg-slate-800">✍️ 7. Assinatura Digital</a></li>
                </ul>
            </div>

            <div>
                <div class="flex justify-between items-center pb-1 border-b border-slate-800 font-bold text-white">
                    <span>🏠 Ambientes</span>
                    <button onclick="mudarAba('aba-cliente')" class="text-[11px] text-amber-400 hover:underline font-bold">➕ Novo</button>
                </div>
                <ul class="mt-2 space-y-1 text-slate-400">
                    <li class="p-2 bg-slate-950 rounded-xl border border-slate-800 flex justify-between items-center">
                        <span class="text-white font-medium">📦 {c_amb}</span>
                        <span class="font-bold text-amber-400">R$ {c_p_venda:,.2f}</span>
                    </li>
                </ul>
            </div>

            <div>
                <div class="flex justify-between items-center pb-1 border-b border-slate-800 font-bold text-white">
                    <span>⭐ Orçamentos</span>
                    <span class="text-[11px] text-emerald-400 font-bold">Ativo #1</span>
                </div>
                <p class="mt-1 text-slate-500 text-[11px]">Proposta de Fechamento Principal</p>
            </div>
        </div>

        <!-- COLUNA 2: PAINEL CENTRAL DINÂMICO -->
        <div class="lg:col-span-6 space-y-4">
            
            <!-- ABA 1: RESUMO FINANCEIRO (DEFAULT) -->
            <div id="aba-resumo" class="tab-content active space-y-4">
                <div class="bg-slate-900 border border-slate-800 rounded-3xl p-5 shadow-xl space-y-3">
                    <div class="text-center pb-2 border-b border-slate-800">
                        <h2 class="text-xs font-bold text-amber-400 uppercase tracking-wide">CONTRATO IT{c_id:05d} vendido em: {c_data_venda} por {CURRENT_SESSION['user_nome']}</h2>
                    </div>

                    <div class="flex flex-wrap gap-2 justify-between items-center">
                        <div class="flex gap-2">
                            <a href="/minuta-contrato/{c_id}" target="_blank" class="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded-xl text-xs font-bold text-slate-200">🖨️ Gerar / Imprimir PDF</a>
                            <a href="/assinar/{c_id}" target="_blank" class="px-3 py-1.5 bg-gradient-to-r from-amber-500 to-amber-600 text-slate-950 font-bold rounded-xl text-xs shadow-lg">✍️ Assinatura Digital</a>
                        </div>
                        <span class="text-[11px] text-slate-500 font-semibold">MVI Enterprise</span>
                    </div>

                    <div class="grid grid-cols-2 gap-3 text-xs pt-2">
                        <div><span class="text-slate-500 block text-[11px]">Cliente:</span><span class="font-bold text-white text-sm">{c_nome}</span></div>
                        <div><span class="text-slate-500 block text-[11px]">CPF / CNPJ:</span><span class="font-bold text-slate-300">{c_cpf}</span></div>
                        <div><span class="text-slate-500 block text-[11px]">Prazo de Entrega:</span><span class="font-bold text-slate-300">{c_prazo}</span></div>
                        <div><span class="text-slate-500 block text-[11px]">Telefone:</span><span class="font-bold text-slate-300">{c_tel}</span></div>
                    </div>
                </div>

                <!-- TABELA DE ENTRADA -->
                <div class="bg-slate-900 border border-slate-800 rounded-3xl overflow-hidden shadow-xl">
                    <div class="bg-slate-850 px-4 py-2.5 border-b border-slate-800 text-xs font-bold text-amber-400 text-center uppercase tracking-wide">ENTRADA (20% MÍNIMO)</div>
                    <table class="w-full text-left text-xs border-collapse">
                        <thead class="bg-slate-950/60 border-b border-slate-800 text-slate-400 font-semibold">
                            <tr>
                                <th class="py-2.5 px-3 text-center">#</th>
                                <th class="py-2.5 px-3">Data Entrada</th>
                                <th class="py-2.5 px-3 text-right">Valor</th>
                                <th class="py-2.5 px-3">Tipo de Cobrança</th>
                                <th class="py-2.5 px-3 text-center">Banco</th>
                                <th class="py-2.5 px-3 text-center">Agência</th>
                                <th class="py-2.5 px-3 text-center">Conta</th>
                            </tr>
                        </thead>
                        <tbody>
                            <tr class="border-b border-slate-800/60">
                                <td class="py-2.5 px-3 text-center text-slate-500">1</td>
                                <td class="py-2.5 px-3 text-slate-300">{hoje.strftime('%d/%m/%Y')}</td>
                                <td class="py-2.5 px-3 font-bold text-emerald-400 text-right">R$ {c_entrada:,.2f}</td>
                                <td class="py-2.5 px-3 text-amber-300 font-semibold">{c_mod}</td>
                                <td class="py-2.5 px-3 text-center text-slate-500">—</td>
                                <td class="py-2.5 px-3 text-center text-slate-500">—</td>
                                <td class="py-2.5 px-3 text-center text-slate-500">—</td>
                            </tr>
                        </tbody>
                    </table>
                </div>

                <!-- CRONOGRAMA DE PARCELAS -->
                <div class="bg-slate-900 border border-slate-800 rounded-3xl overflow-hidden shadow-xl">
                    <div class="bg-slate-850 px-4 py-2.5 border-b border-slate-800 text-xs font-bold text-amber-400 text-center uppercase tracking-wide">CRONOGRAMA DE PARCELAS</div>
                    <div class="overflow-x-auto">
                        <table class="w-full text-left text-xs border-collapse">
                            <thead class="bg-slate-950/60 border-b border-slate-800 text-slate-400 font-semibold">
                                <tr>
                                    <th class="py-2.5 px-3 text-center">#</th>
                                    <th class="py-2.5 px-3">Data Parcelas</th>
                                    <th class="py-2.5 px-3 text-right">Valor</th>
                                    <th class="py-2.5 px-3">Tipo de Cobrança</th>
                                    <th class="py-2.5 px-3 text-center">Bco</th>
                                    <th class="py-2.5 px-3 text-center">Ag</th>
                                    <th class="py-2.5 px-3 text-center">Conta</th>
                                    <th class="py-2.5 px-3">Observação</th>
                                    <th class="py-2.5 px-3 text-center">Ação</th>
                                </tr>
                            </thead>
                            <tbody>{linhas_parcelas}</tbody>
                        </table>
                    </div>
                </div>
            </div>

            <!-- ABA 2: DADOS DO CLIENTE & BUSCA DE CEP -->
            <div id="aba-cliente" class="tab-content bg-slate-900 border border-slate-800 rounded-3xl p-5 shadow-xl space-y-4 text-xs">
                <h3 class="font-bold text-amber-400 uppercase pb-1 border-b border-slate-800">👤 Ficha Cadastral do Cliente & Endereços</h3>
                <form action="/salvar-dados-completos-cliente" method="post" class="space-y-3">
                    <input type="hidden" name="orcamento_id" value="{c_id}">
                    <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
                        <div class="sm:col-span-2">
                            <label class="block text-slate-400 mb-1">Nome Completo</label>
                            <input type="text" name="cliente_nome" value="{c_nome if c_nome != 'Novo Cliente (Sem Pasta)' else ''}" required placeholder="Nome do Cliente" class="w-full p-2.5 bg-slate-950 border border-slate-700 rounded-xl text-white font-bold">
                        </div>
                        <div>
                            <label class="block text-slate-400 mb-1">CPF</label>
                            <input type="text" name="cliente_cpf" value="{c_cpf if c_cpf != 'Não informado' else ''}" placeholder="000.000.000-00" class="w-full p-2.5 bg-slate-950 border border-slate-700 rounded-xl text-white">
                        </div>
                        <div>
                            <label class="block text-slate-400 mb-1">RG</label>
                            <input type="text" name="cliente_rg" value="{c_rg if c_rg != '—' else ''}" placeholder="RG" class="w-full p-2.5 bg-slate-950 border border-slate-700 rounded-xl text-white">
                        </div>
                        <div>
                            <label class="block text-slate-400 mb-1">Telefone Principal</label>
                            <input type="text" name="cliente_telefone" value="{c_tel if c_tel != '—' else ''}" placeholder="WhatsApp" class="w-full p-2.5 bg-slate-950 border border-slate-700 rounded-xl text-white">
                        </div>
                        <div>
                            <label class="block text-slate-400 mb-1">E-mail</label>
                            <input type="email" name="cliente_email" value="{c_email}" placeholder="E-mail" class="w-full p-2.5 bg-slate-950 border border-slate-700 rounded-xl text-white">
                        </div>
                    </div>

                    <div class="border-t border-slate-800 pt-3 grid grid-cols-1 sm:grid-cols-2 gap-4">
                        <div class="bg-slate-950 p-3.5 rounded-2xl border border-slate-800 space-y-2">
                            <label class="font-bold text-amber-400 block">📬 Endereço Postal</label>
                            <div class="flex gap-2">
                                <input type="text" id="cep_postal" name="cliente_cep_postal" value="{c_cep_post}" placeholder="CEP" class="w-1/2 p-2 bg-slate-900 border border-slate-700 rounded-xl text-white">
                                <button type="button" onclick="buscarCep('postal')" class="w-1/2 px-2 py-1 bg-amber-500 font-bold text-slate-950 rounded-xl">🔍 Buscar CEP</button>
                            </div>
                            <textarea id="end_postal" name="cliente_endereco_postal" rows="2" placeholder="Rua, Número, Bairro, Cidade - UF" class="w-full p-2 bg-slate-900 border border-slate-700 rounded-xl text-white">{c_end_post}</textarea>
                        </div>
                        <div class="bg-slate-950 p-3.5 rounded-2xl border border-slate-800 space-y-2">
                            <label class="font-bold text-slate-300 block">🚚 Endereço da Obra</label>
                            <div class="flex gap-2">
                                <input type="text" id="cep_entrega" name="cliente_cep_entrega" value="{c_cep_ent}" placeholder="CEP Obra" class="w-1/2 p-2 bg-slate-900 border border-slate-700 rounded-xl text-white">
                                <button type="button" onclick="buscarCep('entrega')" class="w-1/2 px-2 py-1 bg-amber-500 font-bold text-slate-950 rounded-xl">🔍 Buscar CEP</button>
                            </div>
                            <textarea id="end_entrega" name="cliente_endereco_entrega" rows="2" placeholder="Endereço da Instalação..." class="w-full p-2 bg-slate-900 border border-slate-700 rounded-xl text-white">{c_end_ent}</textarea>
                        </div>
                    </div>

                    <button type="submit" class="w-full py-3 bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold rounded-xl shadow-lg">💾 Salvar Dados do Cliente</button>
                </form>
            </div>

            <!-- ABA 3: MESA DE NEGOCIAÇÃO E FECHAMENTO -->
            <div id="aba-mesa" class="tab-content bg-slate-900 border border-slate-800 rounded-3xl p-5 shadow-xl space-y-4 text-xs">
                <div class="flex justify-between items-center pb-1 border-b border-slate-800">
                    <h3 class="font-bold text-amber-400 uppercase">💼 Mesa de Negociação & Fechamento Financeiro</h3>
                    <input type="hidden" id="preco_bruto_base" value="{c_p_bruto if c_p_bruto > 0 else c_p_venda}">
                </div>

                <form id="form_mesa_negociacao" action="/salvar-negociacao-mesa" method="post" class="space-y-4" onkeydown="impedirEnterSubmit(event)">
                    <input type="hidden" name="orcamento_id" value="{c_id}">

                    <div class="grid grid-cols-1 sm:grid-cols-3 gap-3">
                        <div>
                            <label class="block text-slate-400 mb-1 font-semibold">Valor Venda (R$)</label>
                            <input type="number" step="1" name="preco_venda" id="preco_venda_input" value="{c_p_venda}" required oninput="calcularDescontoPorValorVenda()" class="w-full p-2.5 bg-slate-950 border border-slate-700 rounded-xl font-bold text-amber-400 text-sm focus:border-amber-500">
                        </div>

                        <div>
                            <label class="block text-slate-400 mb-1 font-semibold">Desconto (%)</label>
                            <div class="flex gap-1.5">
                                <input type="number" step="0.1" name="desconto_pct" id="desconto_pct_input" value="{c_desc_pct}" oninput="calcularValorVendaPorDesconto()" class="w-2/3 p-2.5 bg-slate-950 border border-slate-700 rounded-xl font-bold text-white">
                                <button type="button" onclick="calcularValorVendaPorDesconto()" class="w-1/3 px-2 py-1 bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold rounded-xl text-[11px]">
                                    ⚡ Simular
                                </button>
                            </div>
                        </div>

                        <div>
                            <label class="block text-slate-400 mb-1 font-semibold">Entrada (R$)</label>
                            <input type="number" step="100" name="entrada_valor" id="entrada_valor_input" value="{c_entrada}" required oninput="recalcularLucroEMesa()" class="w-full p-2.5 bg-slate-950 border border-slate-700 rounded-xl font-bold text-emerald-400 text-sm">
                        </div>
                    </div>

                    <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                        <div>
                            <label class="block text-slate-400 mb-1 font-semibold">Forma de Pagamento</label>
                            <select name="forma_opcao" id="forma_opcao_select" onchange="atualizarFormaPagamento()" class="w-full p-2.5 bg-slate-950 border border-slate-700 rounded-xl font-semibold text-white">
                                <option value="Entrada PIX + 3 à Vista" {"selected" if "3 à Vista" in c_mod or "PIX + 3" in c_mod else ""}>Entrada PIX + 3 à Vista (PIX/TED)</option>
                                <option value="Entrada + Cartão de Crédito" {"selected" if "Cartão" in c_mod and "3 à Vista" not in c_mod else ""}>Entrada + Cartão de Crédito</option>
                                <option value="Entrada + Boleto Bancário" {"selected" if "Boleto" in c_mod else ""}>Entrada + Boleto Bancário</option>
                                <option value="PIX Integral à Vista" {"selected" if "PIX Integral" in c_mod else ""}>PIX Integral à Vista (5% OFF)</option>
                            </select>
                            <input type="hidden" name="modalidade_pagamento" id="modalidade_pagamento_hidden" value="{c_mod}">
                        </div>

                        <div id="box_parcelas_dinamico">
                            <label class="block text-slate-400 mb-1 font-semibold" id="label_vezes">Quantidade de Parcelas</label>
                            <select name="num_parcelas" id="num_parcelas_select" class="w-full p-2.5 bg-slate-950 border border-slate-700 rounded-xl font-bold text-white">
                                <!-- Preenchido dinamicamente via JS -->
                            </select>
                        </div>
                    </div>

                    <div class="p-4 bg-slate-950 border border-emerald-500/30 rounded-2xl flex justify-between items-center">
                        <div>
                            <span class="font-bold text-slate-400 block text-xs uppercase">Lucro Líquido da Operação:</span>
                            <span id="valor_lucro_operacao" data-real="R$ {c_lucro:,.2f}" class="font-black text-emerald-400 text-lg">R$ {c_lucro:,.2f}</span>
                        </div>
                        <button type="button" onclick="alternarOlhoLucro()" id="btn_olho_lucro" title="Ocultar / Revelar Lucro" class="p-2 bg-slate-900 hover:bg-slate-800 border border-slate-700 rounded-xl text-slate-300 text-sm font-bold shadow">
                            👁️
                        </button>
                    </div>

                    <button type="submit" class="w-full py-3.5 bg-gradient-to-r from-amber-500 to-amber-600 hover:from-amber-400 hover:to-amber-500 text-slate-950 font-bold rounded-xl text-xs shadow-lg">
                        💾 Atualizar Negociação & Salvar
                    </button>
                </form>
            </div>

            <!-- ABA 4: PROMOB INTEGRADOR -->
            <div id="aba-promob" class="tab-content bg-slate-900 border border-slate-800 rounded-3xl p-5 shadow-xl space-y-4 text-xs">
                <h3 class="font-bold text-amber-400 uppercase pb-1 border-b border-slate-800">🚀 Importação Direta de Arquivo Promob</h3>
                <form action="/importar-promob" method="post" enctype="multipart/form-data" class="space-y-3">
                    <input type="text" name="cliente_nome" value="{c_nome if c_nome != 'Novo Cliente (Sem Pasta)' else ''}" placeholder="Nome do Cliente" required class="w-full p-2.5 bg-slate-950 border border-slate-700 rounded-xl text-white font-bold">
                    <input type="text" name="cliente_telefone" value="{c_tel if c_tel != '—' else ''}" placeholder="WhatsApp" required class="w-full p-2.5 bg-slate-950 border border-slate-700 rounded-xl text-white">
                    <input type="text" name="cliente_ambiente" value="{c_amb}" placeholder="Ambiente" required class="w-full p-2.5 bg-slate-950 border border-slate-700 rounded-xl text-white">
                    <div class="p-4 bg-slate-950 border border-slate-800 rounded-2xl">
                        <label class="block font-bold text-amber-400 mb-1">Selecione o arquivo exportado (.xml, .csv, .txt, .cut):</label>
                        <input type="file" name="arquivo_promob" accept=".xml,.csv,.txt,.cut" required class="w-full text-slate-400 file:bg-amber-500 file:border-0 file:rounded-xl file:px-3 file:py-1 file:font-bold">
                    </div>
                    <button type="submit" class="w-full py-3.5 bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold rounded-xl shadow-lg">⚡ Processar Peças & Gerar Orçamento</button>
                </form>
            </div>

            <!-- ABA 5: CONFIGURAÇÃO DOS DADOS DA EMPRESA (PREENCHIMENTO AUTOMÁTICO DO CONTRATO) -->
            <div id="aba-empresa" class="tab-content bg-slate-900 border border-slate-800 rounded-3xl p-5 shadow-xl space-y-4 text-xs">
                <div class="border-b border-slate-800 pb-2">
                    <h3 class="font-bold text-amber-400 uppercase">🏢 Configuração da Empresa Contratada</h3>
                    <p class="text-[11px] text-slate-400">Esses dados serão inseridos automaticamente nas cláusulas do contrato em PDF e na via digital.</p>
                </div>

                <form action="/salvar-empresa" method="post" class="grid sm:grid-cols-2 gap-3">
                    <div class="sm:col-span-2">
                        <label class="block text-slate-400 mb-1 font-semibold">Razão Social / Nome Fantasia da Empresa</label>
                        <input type="text" name="nome_empresa" value="{empresa.get('nome_empresa','')}" placeholder="Ex: Marcenaria Pro Móveis Planejados" required class="w-full p-2.5 bg-slate-950 border border-slate-700 rounded-xl text-white font-bold">
                    </div>
                    <div>
                        <label class="block text-slate-400 mb-1 font-semibold">CNPJ</label>
                        <input type="text" name="cnpj" value="{empresa.get('cnpj','')}" placeholder="00.000.000/0001-00" required class="w-full p-2.5 bg-slate-950 border border-slate-700 rounded-xl text-white">
                    </div>
                    <div>
                        <label class="block text-slate-400 mb-1 font-semibold">Telefone / WhatsApp Comercial</label>
                        <input type="text" name="telefone" value="{empresa.get('telefone','')}" placeholder="(11) 98888-7777" required class="w-full p-2.5 bg-slate-950 border border-slate-700 rounded-xl text-white">
                    </div>
                    <div class="sm:col-span-2">
                        <label class="block text-slate-400 mb-1 font-semibold">Endereço Completo da Sede / Loja</label>
                        <input type="text" name="endereco" value="{empresa.get('endereco','')}" placeholder="Rua, Número, Bairro, Cidade - UF" class="w-full p-2.5 bg-slate-950 border border-slate-700 rounded-xl text-white">
                    </div>
                    <div>
                        <label class="block text-slate-400 mb-1 font-semibold">E-mail Comercial</label>
                        <input type="email" name="email" value="{empresa.get('email','')}" placeholder="contato@marcenaria.com.br" class="w-full p-2.5 bg-slate-950 border border-slate-700 rounded-xl text-white">
                    </div>
                    <div>
                        <label class="block text-slate-400 mb-1 font-semibold">Chave Mestra Admin (PIN)</label>
                        <input type="text" name="chave_mestra" value="{empresa.get('chave_mestra','MVI2026')}" required class="w-full p-2.5 bg-slate-950 border border-amber-500/50 rounded-xl text-amber-300 font-bold">
                    </div>
                    <button type="submit" class="sm:col-span-2 py-3 bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold rounded-xl shadow-lg mt-2">
                        💾 Salvar Dados da Empresa & Atualizar Contratos
                    </button>
                </form>
            </div>

            <!-- ABA 6: CARTEIRA GERAL DE CLIENTES -->
            <div id="aba-geral" class="tab-content bg-slate-900 border border-slate-800 rounded-3xl overflow-hidden shadow-xl space-y-3">
                <div class="bg-slate-850 px-5 py-3 border-b border-slate-800 flex justify-between items-center">
                    <h3 class="font-bold text-xs uppercase text-amber-400 tracking-wide">📂 Carteira Geral de Contratos e Negociações</h3>
                    <button onclick="mudarAba('aba-cliente')" class="px-3 py-1.5 bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold rounded-xl text-xs shadow-sm">
                        ➕ Novo Cadastro
                    </button>
                </div>
                <div class="overflow-x-auto p-2">
                    <table class="w-full text-left text-xs border-collapse">
                        <thead class="bg-slate-950 border-b border-slate-800 text-slate-400 font-semibold uppercase">
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

        <!-- COLUNA 3: RESUMO DA VENDA & CHECKLIST CLICÁVEL -->
        <div class="lg:col-span-3 space-y-4">
            
            <div class="bg-slate-900 border border-slate-800 rounded-3xl p-5 shadow-xl space-y-3 text-xs">
                <h3 class="font-bold text-amber-400 pb-1 border-b border-slate-800 uppercase tracking-wide">Resumo da Venda</h3>
                
                <div class="space-y-1.5 text-slate-400">
                    <div class="flex justify-between"><span>Responsável:</span> <span class="font-semibold text-white">{CURRENT_SESSION['user_nome']}</span></div>
                    <div class="flex justify-between"><span>Orçamento:</span> <span class="font-semibold text-white">#1</span></div>
                    <div class="flex justify-between"><span>Tipo de Venda:</span> <span class="font-semibold text-white">Normal</span></div>
                </div>

                <div class="pt-2 border-t border-slate-800 space-y-1">
                    <div class="flex justify-between items-center"><span class="text-slate-400 font-semibold">Valor da Venda:</span> <span class="font-bold text-amber-400 text-sm">R$ {c_p_venda:,.2f}</span></div>
                    <div class="flex justify-between items-center"><span class="text-slate-400 font-semibold">Valor da Entrada:</span> <span class="font-bold text-emerald-400 text-sm">R$ {c_entrada:,.2f}</span></div>
                    <div class="flex justify-between items-center"><span class="text-slate-500">Opção de Pagto:</span> <span class="font-semibold text-slate-300">{c_mod}</span></div>
                    <div class="flex justify-between items-center"><span class="text-slate-500">Parcelas:</span> <span class="font-semibold text-slate-300">1 + {c_parc}x</span></div>
                </div>

                <div class="pt-2 border-t border-slate-800">
                    <span class="text-[11px] font-bold text-slate-400 block mb-1">Ambientes Vendidos</span>
                    <div class="flex justify-between text-[11px] font-medium text-slate-300 bg-slate-950 p-2.5 rounded-xl border border-slate-800">
                        <span>{c_amb}</span>
                        <span class="font-bold text-amber-400">R$ {c_p_venda:,.2f}</span>
                    </div>
                </div>
            </div>

            <!-- CHECK LIST & POTENCIAL DO CLIENTE COM BOTÕES CLICÁVEIS -->
            <div class="bg-slate-900 border border-slate-800 rounded-3xl p-5 shadow-xl space-y-3.5 text-xs">
                <div class="flex justify-between items-center pb-1 border-b border-slate-800">
                    <h3 class="font-bold text-white uppercase tracking-wide">Qualificação & Check List</h3>
                    <span class="text-[10px] text-slate-500">Clique para mudar</span>
                </div>
                
                <!-- SELETOR DE POTENCIAL DO CLIENTE (TERMÔMETRO DE VENDAS) -->
                <div class="bg-slate-950 p-3 rounded-2xl border border-slate-800 space-y-1.5">
                    <span class="text-[11px] font-bold text-amber-400 block uppercase">Potencial do Cliente:</span>
                    <div class="grid grid-cols-3 gap-1.5 text-center font-bold text-[10px]">
                        <button type="button" onclick="alterarPotencial('Quente')" class="p-1.5 rounded-lg border {'bg-rose-950 border-rose-500 text-rose-300' if potencial == 'Quente' else 'bg-slate-900 border-slate-800 text-slate-400'}">🔥 Quente</button>
                        <button type="button" onclick="alterarPotencial('Morno')" class="p-1.5 rounded-lg border {'bg-amber-950 border-amber-500 text-amber-300' if potencial == 'Morno' else 'bg-slate-900 border-slate-800 text-slate-400'}">⚡ Morno</button>
                        <button type="button" onclick="alterarPotencial('Frio')" class="p-1.5 rounded-lg border {'bg-sky-950 border-sky-500 text-sky-300' if potencial == 'Frio' else 'bg-slate-900 border-slate-800 text-slate-400'}">❄️ Frio</button>
                    </div>
                </div>

                <!-- BOLINHAS DO CHECKLIST CLICÁVEIS (VERDE/AMARELO/VERMELHO) -->
                <ul class="space-y-2.5">
                    <li class="flex justify-between items-center p-1.5 bg-slate-950 rounded-xl border border-slate-800">
                        <span class="font-medium text-slate-300">Dados do Cliente:</span>
                        <button type="button" onclick="toggleCheckItem('check_dados')" title="Clique para alterar status" class="flex items-center gap-1.5 btn-dot">
                            <span class="w-3.5 h-3.5 rounded-full {cor_d}"></span>
                            <span class="text-[10px] text-slate-400 font-semibold">{txt_d}</span>
                        </button>
                    </li>

                    <li class="flex justify-between items-center p-1.5 bg-slate-950 rounded-xl border border-slate-800">
                        <span class="font-medium text-slate-300">Aprovação Comercial:</span>
                        <button type="button" onclick="toggleCheckItem('check_comercial')" title="Clique para alterar status" class="flex items-center gap-1.5 btn-dot">
                            <span class="w-3.5 h-3.5 rounded-full {cor_c}"></span>
                            <span class="text-[10px] text-slate-400 font-semibold">{txt_c}</span>
                        </button>
                    </li>

                    <li class="flex justify-between items-center p-1.5 bg-slate-950 rounded-xl border border-slate-800">
                        <span class="font-medium text-slate-300">Aprovação Financeira:</span>
                        <button type="button" onclick="toggleCheckItem('check_financeiro')" title="Clique para alterar status" class="flex items-center gap-1.5 btn-dot">
                            <span class="w-3.5 h-3.5 rounded-full {cor_f}"></span>
                            <span class="text-[10px] text-slate-400 font-semibold">{txt_f}</span>
                        </button>
                    </li>

                    <li class="flex justify-between items-center p-1.5 bg-slate-950 rounded-xl border border-slate-800">
                        <span class="font-medium text-slate-300">Assinatura do Contrato:</span>
                        <button type="button" onclick="toggleCheckItem('check_contrato')" title="Clique para alterar status" class="flex items-center gap-1.5 btn-dot">
                            <span class="w-3.5 h-3.5 rounded-full {cor_con}"></span>
                            <span class="text-[10px] text-slate-400 font-semibold">{txt_con}</span>
                        </button>
                    </li>
                </ul>
            </div>

        </div>

    </div>

    <!-- RODAPÉ ERP -->
    <footer class="text-center py-4 text-[11px] text-slate-500">
        Copyright © 2026 - MVI Sistemas de Marcenaria Sob Medida. Todos os direitos reservados.
    </footer>

    <!-- JAVASCRIPT DE CONTROLE DAS ABAS, SIMULAÇÃO E OLHO -->
    <script>
        var parcelasSalvas = {c_parc};
        var idOrcamentoAtivo = {c_id};

        function mudarAba(abaId) {{
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            document.querySelectorAll('.tree-item').forEach(b => b.classList.remove('active'));
            
            var targetAba = document.getElementById(abaId);
            var targetBtn = document.getElementById('btn-' + abaId);
            
            if (targetAba) targetAba.classList.add('active');
            if (targetBtn) targetBtn.classList.add('active');
            window.scrollTo({{ top: 0, behavior: 'smooth' }});
        }}

        function toggleCheckItem(campo) {{
            if (idOrcamentoAtivo === 0) {{
                alert("Selecione um cliente para alterar o check list.");
                return;
            }}
            fetch('/atualizar-checklist-item?orcamento_id=' + idOrcamentoAtivo + '&campo=' + campo, {{ method: 'POST' }})
                .then(() => window.location.reload());
        }}

        function alterarPotencial(valor) {{
            if (idOrcamentoAtivo === 0) {{
                alert("Selecione um cliente para classificar o potencial.");
                return;
            }}
            fetch('/atualizar-potencial-cliente?orcamento_id=' + idOrcamentoAtivo + '&potencial=' + encodeURIComponent(valor), {{ method: 'POST' }})
                .then(() => window.location.reload());
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

            var valorSelecionadoAnterior = selectParc.value || parcelasSalvas;
            selectParc.innerHTML = "";

            if (opcao === "Entrada PIX + 3 à Vista") {{
                boxParc.style.display = "block";
                selectParc.innerHTML = `
                    <option value="1">1x (À Vista)</option>
                    <option value="2">2x (30/60 dias)</option>
                    <option value="3">3x (30/60/90 dias)</option>
                `;
                hiddenMod.value = "Entrada PIX + 3 à Vista";
            }} else if (opcao === "Entrada + Cartão de Crédito") {{
                boxParc.style.display = "block";
                for (var i = 1; i <= 12; i++) {{
                    selectParc.innerHTML += `<option value="` + i + `">` + i + `x no Cartão</option>`;
                }}
                hiddenMod.value = "Entrada + Cartão de Crédito";
            }} else if (opcao === "Entrada + Boleto Bancário") {{
                boxParc.style.display = "block";
                for (var i = 1; i <= 24; i++) {{
                    selectParc.innerHTML += `<option value="` + i + `">` + i + `x no Boleto</option>`;
                }}
                hiddenMod.value = "Entrada + Boleto Bancário";
            }} else {{
                boxParc.style.display = "none";
                selectParc.innerHTML = `<option value="1" selected>1x (Integral)</option>`;
                hiddenMod.value = "PIX Integral à Vista (5% OFF)";
            }}

            if (valorSelecionadoAnterior) {{
                selectParc.value = valorSelecionadoAnterior;
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

@app.post("/atualizar-checklist-item")
def atualizar_checklist_item(orcamento_id: int, campo: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(f"SELECT {campo} FROM orcamentos WHERE id = ?", (orcamento_id,))
    row = cursor.fetchone()
    if row:
        val_atual = row[0] or 0
        novo_val = (val_atual + 1) % 3
        cursor.execute(f"UPDATE orcamentos SET {campo} = ? WHERE id = ?", (novo_val, orcamento_id))
        conn.commit()
    conn.close()
    return JSONResponse({"status": "ok"})

@app.post("/atualizar-potencial-cliente")
def atualizar_potencial_cliente(orcamento_id: int, potencial: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE orcamentos SET potencial_cliente = ? WHERE id = ?", (potencial, orcamento_id))
    conn.commit()
    conn.close()
    return JSONResponse({"status": "ok"})

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
        ) VALUES (1, ?, ?, ?, ?, '25 dias úteis', ?, 'Importado Promob', ?, ?, ?, ?, ?)
    """, (agora, cliente_nome, cliente_telefone, cliente_ambiente, (date.today() + timedelta(days=25)).strftime("%Y-%m-%d"), calc["total_mat"], calc["preco_bruto"], calc["preco_venda"], calc["lucro"], desc_auto))
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
        ) VALUES (1, ?, ?, ?, ?, '25 dias úteis', ?, 'Novo Lead Instagram', ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        agora, nome, whatsapp, ambientes_str, (date.today() + timedelta(days=25)).strftime("%Y-%m-%d"),
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
    cliente_cidade: str = Form("São Paulo"),
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
                1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Cozinha Planejada', ?, ?, 1, 'Em Negociação',
                ?, ?, ?, ?, ?, ?, '25 dias úteis', ?
            )
        """, (
            agora, cliente_nome, cliente_cpf, cliente_rg, cliente_rg_emissor,
            cliente_nascimento, cliente_pais, cliente_cidade, cliente_email,
            cliente_telefone, cliente_telefone_2, cliente_cep_postal, cliente_endereco_postal,
            cliente_cep_entrega, cliente_endereco_entrega, descricao_manual, desconto_pct,
            pv_base, pv_final, lucro_final, forma_pagamento, round(entrada_valor), num_parcelas,
            (date.today() + timedelta(days=25)).strftime("%Y-%m-%d")
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
def update_empresa(
    nome_empresa: str = Form(""),
    cnpj: str = Form(""),
    endereco: str = Form(""),
    telefone: str = Form(""),
    email: str = Form(""),
    chave_mestra: str = Form("MVI2026")
):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE empresas SET
            nome_empresa = ?,
            cnpj = ?,
            endereco = ?,
            telefone = ?,
            email = ?,
            chave_mestra = ?
        WHERE id = 1
    """, (nome_empresa.strip(), cnpj.strip(), endereco.strip(), telefone.strip(), email.strip(), chave_mestra.strip()))
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

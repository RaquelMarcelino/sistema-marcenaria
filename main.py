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
DB_PATH = "mvi_production_v9.db"

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

# ROTAS FASTAPI

@app.get("/", response_class=HTMLResponse)
def root():
    return render_login()

@app.post("/painel", response_class=HTMLResponse)
def login(username: str = Form(...), password: str = Form(...)):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM usuarios WHERE email = ? AND senha = ?", (username, password))
    user = cursor.fetchone()
    conn.close()

    if not user:
        return render_login("E-mail ou senha incorretos. Tente novamente.")

    CURRENT_SESSION["user_email"] = user["email"]
    CURRENT_SESSION["user_nome"] = user["nome"]
    CURRENT_SESSION["user_perfil"] = user["perfil"]
    CURRENT_SESSION["empresa_id"] = user["empresa_id"]

    return render_dashboard_view()

@app.get("/painel", response_class=HTMLResponse)
@app.get("/painel-get", response_class=HTMLResponse)
def painel_view():
    return render_dashboard_view()

@app.get("/solicitar-orcamento", response_class=HTMLResponse)
@app.get("/solicitar-orcamento/{slug}", response_class=HTMLResponse)
def captacao_view(slug: str = "mvi"):
    empresa = get_empresa_dados(1)
    return render_form_captacao(empresa)

@app.post("/importar-promob", response_class=HTMLResponse)
async def importar_promob(
    cliente_nome: str = Form(...),
    cliente_telefone: str = Form(...),
    cliente_ambiente: str = Form(...),
    arquivo_promob: UploadFile = File(...)
):
    empresa = get_empresa_dados(1)
    conteudo_bytes = await arquivo_promob.read()
    conteudo_texto = conteudo_bytes.decode("utf-8", errors="ignore")
    
    calc = processar_arquivo_promob(conteudo_texto, arquivo_promob.filename)
    agora = datetime.now().strftime("%d/%m/%Y %H:%M")
    
    desc_auto = f"Projeto importado do Promob ({arquivo_promob.filename}). {len(calc['items'])} componentes detectados com plano de corte e ferragens."

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO orcamentos (
            empresa_id, criado_em, cliente_nome, cliente_telefone, cliente_ambiente,
            prazo_entrega, data_entrega_prevista, status, custo_materiais,
            custo_mao_obra, custo_frete_montagem, imposto_pct, comissao_pct,
            markup, preco_venda, lucro_liquido, entrada_valor, num_parcelas,
            forma_pagamento, valor_recebido, imagens_json, ambientes_json,
            observacoes_tecnicas, items_json, descricao_promob, liberado_financeiro
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
    """, (
        1, agora, cliente_nome, cliente_telefone, cliente_ambiente,
        "25 dias úteis", (date.today() + timedelta(days=25)).strftime("%Y-%m-%d"),
        "Importado do Promob (CRM)", calc["total_mat"], calc["custo_mo"], calc["custo_frete"],
        6.0, 4.0, 2.2, calc["preco_venda"], calc["lucro"], calc["preco_venda"] * 0.3, 3,
        "Entrada + 3x Cartão", 0.0, "[]", json.dumps([cliente_ambiente]),
        desc_auto, json.dumps(calc["items"]), desc_auto
    ))
    conn.commit()
    conn.close()

    return RedirectResponse(url="/painel-get", status_code=303)

@app.post("/enviar-solicitacao-lead", response_class=HTMLResponse)
async def submit_lead(
    nome: str = Form(...),
    whatsapp: str = Form(...),
    area_m2_total: float = Form(180.0),
    espessura_caixa: str = Form("MDF 18mm"),
    espessura_tamponamento: str = Form("Tamponamento 25mm"),
    fabricante_mdf: str = Form("Duratex"),
    cor_mdf: str = Form("Freijó"),
    modelo_portas: str = Form("Perfil Gola em Alumínio"),
    marca_ferragens: str = Form("Blum (Linha Blumotion Áustria)"),
    ambientes_check: List[str] = Form(["Cozinha c/ Ilha", "Suíte Master c/ Closet"]),
    cidade: str = Form(...),
    descricao: str = Form(""),
    planta: UploadFile = File(...),
    inspiracao: UploadFile = File(None)
):
    empresa = get_empresa_dados(1)
    calc = calcular_engenharia(
        ambientes_check, area_m2_total, espessura_caixa, espessura_tamponamento,
        fabricante_mdf, cor_mdf, modelo_portas, marca_ferragens
    )

    agora = datetime.now().strftime("%d/%m/%Y %H:%M")
    imagens = []
    
    content_planta = await planta.read()
    if content_planta:
        imagens.append(base64.b64encode(content_planta).decode("utf-8"))

    if inspiracao:
        try:
            content_insp = await inspiracao.read()
            if content_insp:
                imagens.append(base64.b64encode(content_insp).decode("utf-8"))
        except Exception:
            pass

    nome_amb_str = " + ".join(ambientes_check)
    obs = f"Lead {area_m2_total}m² ({cidade}) | MDF: {fabricante_mdf} ({cor_mdf}) | Ferragens: {marca_ferragens} | Portas: {modelo_portas}"
    if descricao:
        obs += f" | Obs: {descricao}"

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO orcamentos (
            empresa_id, criado_em, cliente_nome, cliente_telefone, cliente_ambiente,
            prazo_entrega, data_entrega_prevista, status, custo_materiais,
            custo_mao_obra, custo_frete_montagem, imposto_pct, comissao_pct,
            markup, preco_venda, lucro_liquido, entrada_valor, num_parcelas,
            forma_pagamento, valor_recebido, imagens_json, ambientes_json,
            observacoes_tecnicas, items_json, descricao_promob, liberado_financeiro
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
    """, (
        1, agora, nome, whatsapp, nome_amb_str,
        "30 dias úteis", (date.today() + timedelta(days=30)).strftime("%Y-%m-%d"),
        "Novo Lead Instagram", calc["total_mat"], calc["custo_mo"], calc["custo_frete"],
        6.0, 4.0, 2.2, calc["preco_venda"], calc["lucro"], calc["preco_venda"] * 0.3, 3,
        "Entrada + 3x Cartão", 0.0, json.dumps(imagens), json.dumps(ambientes_check),
        obs, json.dumps(calc["items"]), calc["desc_promob"]
    ))
    conn.commit()
    novo_id = cursor.lastrowid
    conn.close()

    msg_zap = f"""Olá! Meu nome é *{nome}*.
Simulei meu projeto na *{empresa['nome_empresa']}* (Projeto #{novo_id:04d}).

📋 *RESUMO DO PROJETO:*
• *Cidade:* {cidade}
• *Metragem:* {area_m2_total} m²
• *Ambientes:* {nome_amb_str}
• *MDF:* {fabricante_mdf} ({cor_mdf})
• *Ferragens:* {marca_ferragens}
• *Portas:* {modelo_portas}
• *Caixaria/Tamponamento:* {espessura_caixa} / {espessura_tamponamento}
• *Estimativa:* R$ {calc['preco_venda']:,.2f}

Enviei a foto da planta pelo simulador e gostaria de atendimento!"""

    tel_limpo = empresa["telefone"].replace("(", "").replace(")", "").replace("-", "").replace(" ", "")
    zap_url = f"https://api.whatsapp.com/send?phone=55{tel_limpo}&text={urllib.parse.quote(msg_zap)}"

    return render_sucesso(empresa, calc["preco_venda"], zap_url)

@app.post("/salvar-dados-completos-cliente", response_class=HTMLResponse)
def salvar_dados_completos_cliente(
    orcamento_id: int = Form(...),
    cliente_nome: str = Form(...),
    cliente_cpf: str = Form(...),
    cliente_rg: str = Form(...),
    cliente_rg_emissor: str = Form(...),
    cliente_nascimento: str = Form(...),
    cliente_pais: str = Form("Brasil"),
    cliente_cidade: str = Form(...),
    cliente_email: str = Form(...),
    cliente_telefone: str = Form(...),
    cliente_telefone_2: str = Form(""),
    cliente_cep_postal: str = Form(""),
    cliente_endereco_postal: str = Form(""),
    cliente_cep_entrega: str = Form(""),
    cliente_endereco_entrega: str = Form(""),
    cliente_banco: str = Form(""),
    cliente_agencia: str = Form(""),
    cliente_conta: str = Form(""),
    cliente_renda: str = Form(""),
    ref_nome_1: str = Form(""),
    ref_tel_1: str = Form(""),
    ref_nome_2: str = Form(""),
    ref_tel_2: str = Form(""),
    descricao_manual: str = Form(""),
    desconto_pct: float = Form(0.0),
    forma_pagamento: str = Form("Entrada + Cartão"),
    entrada_valor: float = Form(0.0),
    num_parcelas: int = Form(1)
):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT preco_venda, custo_materiais, custo_mao_obra, custo_frete_montagem FROM orcamentos WHERE id = ?", (orcamento_id,))
    orc = cursor.fetchone()
    
    if orc:
        pv_orig = float(orc["preco_venda"] or 0)
        custo_tot = float(orc["custo_materiais"] or 0) + float(orc["custo_mao_obra"] or 0) + float(orc["custo_frete_montagem"] or 0)
        
        precisa_aprov = (desconto_pct > 3.0 and CURRENT_SESSION["user_perfil"] == "vendedor")
        desconto_autorizado = 0 if precisa_aprov else 1
        status = "Aguardando Liberação de Desconto" if precisa_aprov else "Contrato Pronto para Assinatura"
        
        pv_final = pv_orig * (1.0 - (desconto_pct / 100.0))
        lucro_final = pv_final - (custo_tot + (pv_final * 0.10))

        cursor.execute("""
            UPDATE orcamentos SET
                cliente_nome = ?, cliente_cpf = ?, cliente_rg = ?, cliente_rg_emissor = ?,
                cliente_nascimento = ?, cliente_pais = ?, cliente_cidade = ?, cliente_email = ?,
                cliente_telefone = ?, cliente_telefone_2 = ?, cliente_cep_postal = ?, cliente_endereco_postal = ?,
                cliente_cep_entrega = ?, cliente_endereco_entrega = ?, cliente_banco = ?, cliente_agencia = ?,
                cliente_conta = ?, cliente_renda = ?, ref_nome_1 = ?, ref_tel_1 = ?, ref_nome_2 = ?, ref_tel_2 = ?,
                descricao_manual = ?, desconto_pct = ?, desconto_autorizado = ?, status = ?, preco_venda = ?,
                lucro_liquido = ?, forma_pagamento = ?, entrada_valor = ?, num_parcelas = ?
            WHERE id = ?
        """, (
            cliente_nome, cliente_cpf, cliente_rg, cliente_rg_emissor,
            cliente_nascimento, cliente_pais, cliente_cidade, cliente_email,
            cliente_telefone, cliente_telefone_2, cliente_cep_postal, cliente_endereco_postal,
            cliente_cep_entrega, cliente_endereco_entrega, cliente_banco, cliente_agencia,
            cliente_conta, cliente_renda, ref_nome_1, ref_tel_1, ref_nome_2, ref_tel_2,
            descricao_manual, desconto_pct, desconto_autorizado, status, pv_final,
            lucro_final, forma_pagamento, entrada_valor, num_parcelas, orcamento_id
        ))
        conn.commit()
    conn.close()
    return RedirectResponse(url="/painel-get", status_code=303)

@app.post("/salvar-adendo", response_class=HTMLResponse)
def salvar_adendo(
    orcamento_id: int = Form(...),
    adendo_descricao: str = Form(...),
    adendo_valor: float = Form(0.0)
):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE orcamentos SET
            adendo_descricao = ?,
            adendo_valor = ?,
            status = 'Contrato com Adendo Adicionado'
        WHERE id = ?
    """, (adendo_descricao, adendo_valor, orcamento_id))
    conn.commit()
    conn.close()
    return RedirectResponse(url="/painel-get", status_code=303)

@app.post("/autorizar-com-chave", response_class=HTMLResponse)
def autorizar_com_chave(
    orcamento_id: int = Form(...),
    chave_digitada: str = Form(...),
    tipo_acao: str = Form(...)
):
    empresa = get_empresa_dados(CURRENT_SESSION.get("empresa_id", 1))
    chave_oficial = empresa.get("chave_mestra", "MVI2026")
    
    if chave_digitada.strip() != chave_oficial.strip():
        return HTMLResponse("""
        <div style="background:#0f172a; color:#f8fafc; font-family:sans-serif; text-align:center; padding:50px; min-height:100vh;">
            <h1 style="color:#ef4444; font-size:26px;">❌ Chave Mestra Incorreta</h1>
            <p style="color:#94a3b8; font-size:14px; margin-top:10px;">Apenas o Administrador possui a chave de liberação.</p>
            <a href="/painel" style="display:inline-block; margin-top:20px; padding:10px 25px; background:#f59e0b; color:#0f172a; font-weight:bold; border-radius:10px; text-decoration:none;">Voltar ao Painel</a>
        </div>
        """, status_code=403)

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
        return HTMLResponse("Contrato não encontrado.", status_code=404)
        
    empresa = get_empresa_dados(orc["empresa_id"])
    return render_assinatura_online(orc, empresa)

@app.post("/confirmar-assinatura", response_class=HTMLResponse)
def confirmar_assinatura(orcamento_id: int = Form(...), assinatura_base64: str = Form(...)):
    agora = datetime.now().strftime("%d/%m/%Y às %H:%M:%S")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE orcamentos SET
            contrato_assinado = 1,
            assinatura_data = ?,
            assinatura_img = ?,
            status = 'Contrato Assinado Digitalmente'
        WHERE id = ?
    """, (agora, assinatura_base64, orcamento_id))
    conn.commit()
    conn.close()
    return HTMLResponse(f"""
    <div style="background:#0f172a; color:#f8fafc; font-family:sans-serif; text-align:center; padding:50px; min-height:100vh;">
        <h1 style="color:#10b981; font-size:28px;">🎉 Contrato Assinado Digitalmente com Sucesso!</h1>
        <p style="color:#94a3b8; font-size:14px; margin-top:10px;">Protocolado no sistema da MVI Móveis Planejados em {agora}.</p>
    </div>
    """)

@app.post("/criar-usuario", response_class=HTMLResponse)
def criar_usuario_com_convite(request: Request, nome: str = Form(...), email: str = Form(...), perfil: str = Form(...), telefone: str = Form("")):
    if CURRENT_SESSION.get("user_perfil") != "admin":
        return RedirectResponse(url="/painel-get", status_code=303)
        
    token_convite = secrets.token_urlsafe(16)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO usuarios (email, senha, nome, perfil, empresa_id, token_primeiro_acesso, primeiro_acesso_concluido)
        VALUES (?, '', ?, ?, 1, ?, 0)
    """, (email.strip().lower(), nome, perfil, token_convite))
    conn.commit()
    conn.close()

    base_url = str(request.base_url).rstrip("/")
    link_primeiro_acesso = f"{base_url}/primeiro-acesso/{token_convite}"
    return render_convite_gerado(nome, email, perfil, telefone, link_primeiro_acesso)

@app.get("/primeiro-acesso/{token}", response_class=HTMLResponse)
def tela_primeiro_acesso(token: str):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM usuarios WHERE token_primeiro_acesso = ?", (token,))
    user = cursor.fetchone()
    conn.close()

    if not user:
        return HTMLResponse("Link inválido ou já utilizado.", status_code=404)
    return render_tela_nova_senha(user, token)

@app.post("/salvar-nova-senha", response_class=HTMLResponse)
def salvar_nova_senha(token: str = Form(...), nova_senha: str = Form(...), confirma_senha: str = Form(...)):
    if nova_senha != confirma_senha or len(nova_senha) < 6:
        return HTMLResponse("<script>alert('As senhas não coincidem ou possuem menos de 6 caracteres!'); history.back();</script>")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE usuarios SET senha = ?, token_primeiro_acesso = '', primeiro_acesso_concluido = 1 WHERE token_primeiro_acesso = ?", (nova_senha, token))
    conn.commit()
    conn.close()

    return HTMLResponse("""
    <div style="background:#0f172a; color:#f8fafc; font-family:sans-serif; text-align:center; padding:50px; min-height:100vh;">
        <h1 style="color:#10b981; font-size:28px;">🎉 Senha Criada com Sucesso!</h1>
        <p style="color:#94a3b8; font-size:14px; margin-top:10px;">Sua conta foi ativada. Você já pode acessar o painel.</p>
        <a href="/" style="display:inline-block; margin-top:20px; padding:12px 30px; background:#f59e0b; color:#0f172a; font-weight:bold; border-radius:10px; text-decoration:none;">Acessar o Painel Agora</a>
    </div>
    """)

@app.post("/salvar-empresa", response_class=HTMLResponse)
def update_empresa(nome_empresa: str = Form(...), cnpj: str = Form(...), telefone: str = Form(...), pix: str = Form(...), chave_mestra: str = Form("MVI2026")):
    if CURRENT_SESSION.get("user_perfil") != "admin":
        return RedirectResponse(url="/painel-get", status_code=303)
        
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
    
    return Response(
        content=output.getvalue().encode('utf-8-sig'),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=relatorio-mvi.csv"}
    )

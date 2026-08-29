import os
import sqlite3
import traceback
from fastapi import FastAPI, Form, UploadFile, File, Response, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
import os
import io
import csv
import urllib.parse
import json
import sqlite3
import math
import base64
import traceback
import secrets
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, date, timedelta
from typing import List, Optional
import google.generativeai as genai
import smtplib
import string
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USER = os.getenv("EMAIL_NOTIFICACAO_REMETENTE", "contato@marcenaria.com")
SMTP_PASS = os.getenv("EMAIL_NOTIFICACAO_SENHA", "")

def enviar_email_convite_vendedor(nome_vendedor: str, email_vendedor: str, senha_temp: str, link_acesso: str):
    """Dispara as credenciais de primeiro acesso para o vendedor."""
    if not SMTP_PASS:
        print("SMTP_PASS não configurada no Render. E-mail não disparado.")
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = "🔐 Bem-vindo à MVI - Seu Acesso ao CRM de Vendas"
        msg["From"] = f"MVI Móveis <{SMTP_USER}>"
        msg["To"] = email_vendedor

        corpo_html = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; background-color: #0f172a; color: #f8fafc; padding: 24px; border-radius: 12px; border: 1px solid #1e293b;">
            <div style="text-align: center; margin-bottom: 20px;">
                <h2 style="color: #f59e0b; margin: 0;">MVI Móveis Planejados</h2>
                <p style="color: #94a3b8; font-size: 14px;">Hub Promob, Financiamentos & Gestão Comercial</p>
            </div>
            <p style="font-size: 15px;">Olá, <strong>{nome_vendedor}</strong>!</p>
            <p style="font-size: 14px; color: #cbd5e1; line-height: 1.5;">
                Seu cadastro como vendedor foi realizado com sucesso. Seguem suas credenciais de acesso provisórias:
            </p>
            <div style="background-color: #1e293b; padding: 16px; border-radius: 8px; margin: 20px 0; border: 1px solid #334155;">
                <p style="margin: 6px 0; font-size: 14px;"><strong>E-mail:</strong> <span style="color: #38bdf8;">{email_vendedor}</span></p>
                <p style="margin: 6px 0; font-size: 14px;"><strong>Senha Provisória:</strong> <span style="color: #f59e0b; font-family: monospace; font-size: 16px; font-weight: bold;">{senha_temp}</span></p>
            </div>
            <p style="font-size: 13px; color: #fbbf24;">
                ⚠️ <em>No primeiro login, o sistema solicitará a troca imediata para a sua senha definitiva.</em>
            </p>
            <div style="text-align: center; margin-top: 24px;">
                <a href="{link_acesso}" style="background-color: #f59e0b; color: #0f172a; padding: 12px 24px; font-weight: bold; text-decoration: none; border-radius: 8px; display: inline-block; font-size: 14px;">
                    Acessar o Painel CRM
                </a>
            </div>
        </div>
        """
        msg.attach(MIMEText(corpo_html, "html"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_USER, email_vendedor, msg.as_string())
        return True
    except Exception as e:
        print(f"Erro no envio de e-mail ao vendedor: {e}")
        return False
app = FastAPI(title="MVI Móveis Planejados - Master SaaS & FinTech")
# Banco persistente no Disco SSD do Render
if os.path.exists("/var/data"):
    DB_PATH = "/var/data/sistema_marcenaria.db"
else:
    DB_PATH = "sistema_marcenaria.db"
    META_PIXEL_ID = "641231925101582"
DEFAULT_ASAAS_KEY = "$aact_prod_000MzkwODA2MWY2OGM3MWRlMDU2NWM3MzJlNzZmNGZhZGY6OmZjNzAxZGMzLTA0MzItNGYxNy04NTI0LTU1ZDk0YmZjNTliYzo6JGFhY2hfZmY2M2U5MTAtZjA4Ny00YmFjLTgwY2UtYjVmYjBiM2Q4ZGYw"


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
def parse_moeda(valor_str) -> float:
    if isinstance(valor_str, (int, float)):
        return float(valor_str)
    if not valor_str:
        return 0.0
    s = str(valor_str).strip().replace("R$", "").replace(" ", "")
    if "." in s and "," not in s:
        partes = s.split(".")
        if len(partes[-1]) == 3:
            s = s.replace(".", "")
    elif "." in s and "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except Exception:
        return 0.0

def fmt_br(val: float) -> str:
    return f"{val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


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
            comissao_padrao_pct REAL DEFAULT 4.0,
            taxa_juros_mensal REAL DEFAULT 1.99,
            asaas_api_key TEXT DEFAULT '',
            asaas_ambiente TEXT DEFAULT 'producao',
            financiamento_ativo INTEGER DEFAULT 1
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
        CREATE TABLE IF NOT EXISTS propostas_credito (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa_id INTEGER DEFAULT 1,
            orcamento_id INTEGER,
            cliente_nome TEXT,
            cliente_cpf TEXT,
            cliente_renda REAL DEFAULT 0,
            valor_financiado REAL DEFAULT 0,
            num_parcelas INTEGER DEFAULT 24,
            taxa_juros REAL DEFAULT 1.99,
            valor_parcela REAL DEFAULT 0,
            total_com_juros REAL DEFAULT 0,
            status TEXT DEFAULT 'Aprovado (Crédito Liberado)',
            score_estimado INTEGER DEFAULT 750,
            criado_em TEXT,
            contrato_ccb_assinado INTEGER DEFAULT 0,
            asaas_payment_id TEXT DEFAULT '',
            asaas_carne_url TEXT DEFAULT '',
            asaas_installment_id TEXT DEFAULT ''
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
            cliente_rua_postal TEXT DEFAULT '',
            cliente_num_postal TEXT DEFAULT '',
            cliente_comp_postal TEXT DEFAULT '',
            cliente_bairro_postal TEXT DEFAULT '',
            cliente_cidade_postal TEXT DEFAULT '',
            cliente_uf_postal TEXT DEFAULT '',
            cliente_endereco_postal TEXT DEFAULT '',
            cliente_cep_entrega TEXT DEFAULT '',
            cliente_rua_entrega TEXT DEFAULT '',
            cliente_num_entrega TEXT DEFAULT '',
            cliente_comp_entrega TEXT DEFAULT '',
            cliente_bairro_entrega TEXT DEFAULT '',
            cliente_cidade_entrega TEXT DEFAULT '',
            cliente_uf_entrega TEXT DEFAULT '',
            cliente_endereco_entrega TEXT DEFAULT '',
            cliente_banco TEXT DEFAULT '',
            cliente_agencia TEXT DEFAULT '',
            cliente_conta TEXT DEFAULT '',
            cliente_renda TEXT DEFAULT '5500',
            ref_nome_1 TEXT DEFAULT '',
            ref_tel_1 TEXT DEFAULT '',
            ref_nome_2 TEXT DEFAULT '',
            ref_tel_2 TEXT DEFAULT '',
            cliente_ambiente TEXT DEFAULT 'Cozinha Planejada',
            descricao_promob TEXT DEFAULT '',
            descricao_manual TEXT DEFAULT '',
            adendo_descricao TEXT DEFAULT '',
            adendo_valor REAL DEFAULT 0,
            prazo_entrega TEXT DEFAULT '35 dias úteis',
            prazo_garantia TEXT DEFAULT '12 (doze) meses',
            data_entrega_prevista TEXT DEFAULT '',
            status TEXT DEFAULT 'Novo Lead',
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

    # Atualiza ou insere a chave Asaas na tabela da empresa 1
    cursor.execute("SELECT id FROM empresas WHERE id = 1")
    if not cursor.fetchone():
        precos_iniciais = {
            "mdf_m2": 65.0, "dobradica": 18.50, "corredica": 38.00,
            "fita_borda_m": 3.20, "puxador": 25.00
        }
        cursor.execute("""
            INSERT INTO empresas (id, slug, nome_empresa, cnpj, endereco, telefone, email, pix, precos_json, chave_mestra, desconto_max_vendedor, comissao_padrao_pct, taxa_juros_mensal, asaas_api_key, asaas_ambiente)
            VALUES (1, 'mvi', 'MVI Móveis Planejados', '', '', '', '', '', ?, 'MVI2026', 3.0, 4.0, 1.99, ?, 'producao')
        """, (json.dumps(precos_iniciais), DEFAULT_ASAAS_KEY))
    else:
        cursor.execute("UPDATE empresas SET asaas_api_key = ?, asaas_ambiente = 'producao' WHERE id = 1 AND (asaas_api_key IS NULL OR asaas_api_key = '')", (DEFAULT_ASAAS_KEY,))

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
        d = dict(row)
        if not d.get("asaas_api_key"):
            d["asaas_api_key"] = DEFAULT_ASAAS_KEY
        return d
    return {
        "id": 1, "slug": "mvi", "nome_empresa": "MVI Móveis Planejados",
        "cnpj": "", "endereco": "", "telefone": "",
        "email": "", "pix": "", "precos_json": "{}", "chave_mestra": "MVI2026",
        "desconto_max_vendedor": 3.0, "comissao_padrao_pct": 4.0, "taxa_juros_mensal": 1.99,
        "asaas_api_key": DEFAULT_ASAAS_KEY, "asaas_ambiente": "producao"
    }

def calcular_parcela_price(valor: float, taxa_mensal_pct: float, parcelas: int) -> float:
    if parcelas <= 1:
        return valor
    i = (taxa_mensal_pct / 100.0)
    if i <= 0:
        return valor / parcelas
    pmt = valor * (i * ((1 + i) ** parcelas)) / (((1 + i) ** parcelas) - 1)
    return pmt


# ==============================================================================
# MOTOR INTEGRADO ASAAS
# ==============================================================================
def emitir_carne_asaas(empresa_dict, cliente_nome, cliente_cpf, cliente_tel, valor_parcela, num_parcelas):
    api_key = (empresa_dict.get("asaas_api_key") or DEFAULT_ASAAS_KEY).strip()
    if not api_key:
        return {"sucesso": False, "msg": "Chave de API do Asaas não configurada", "carne_url": ""}

    base_url = "https://api.asaas.com/v3" if empresa_dict.get("asaas_ambiente") == "producao" else "https://sandbox.asaas.com/api/v3"
    headers = {
        "Content-Type": "application/json",
        "access_token": api_key,
        "User-Agent": "MVI-Sistemas/1.0"
    }

    try:
        cpf_limpo = cliente_cpf.replace(".", "").replace("-", "").replace(" ", "")
        payload_cli = json.dumps({
            "name": cliente_nome,
            "cpfCnpj": cpf_limpo if len(cpf_limpo) in [11, 14] else None,
            "mobilePhone": cliente_tel.replace("(", "").replace(")", "").replace("-", "").replace(" ", "")
        }).encode("utf-8")

        req_cli = urllib.request.Request(f"{base_url}/customers", data=payload_cli, headers=headers, method="POST")
        with urllib.request.urlopen(req_cli, timeout=10) as resp_cli:
            res_c = json.loads(resp_cli.read().decode("utf-8"))
            customer_id = res_c.get("id")

        primeiro_vencimento = (date.today() + timedelta(days=30)).strftime("%Y-%m-%d")
        payload_cobranca = json.dumps({
            "customer": customer_id,
            "billingType": "BOLETO",
            "installmentCount": num_parcelas,
            "installmentValue": round(valor_parcela, 2),
            "dueDate": primeiro_vencimento,
            "description": f"Financiamento MVI Planejados - {num_parcelas}x",
            "postalService": False
        }).encode("utf-8")

        req_cob = urllib.request.Request(f"{base_url}/payments", data=payload_cobranca, headers=headers, method="POST")
        with urllib.request.urlopen(req_cob, timeout=10) as resp_cob:
            res_p = json.loads(resp_cob.read().decode("utf-8"))
            installment_id = res_p.get("installment") or res_p.get("id")
            bank_slip_url = res_p.get("bankSlipUrl") or res_p.get("invoiceUrl") or ""

            return {
                "sucesso": True,
                "installment_id": installment_id,
                "carne_url": bank_slip_url,
                "msg": "Carnê emitido com sucesso no Asaas"
            }
    except Exception as e:
        return {"sucesso": False, "msg": str(e), "carne_url": ""}


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
        st = r["status"] or "Novo Lead"
        pv = float(r["preco_venda"] or 0) + float(r["adendo_valor"] or 0)
        lucro = float(r["lucro_liquido"] or 0)
        com = float(r["comissao_valor"] or (pv * 0.04))
        
        if st in ["Aprovado", "Venda Fechada", "Em Produção", "Entregue", "Liberado para Financeiro & Fábrica", "Contrato Assinado Digitalmente"]:
            fat_total += pv
            lucro_total += lucro
            comissao_total += com
            aprovados += 1

    taxa = (aprovados / total * 100.0) if total > 0 else 0.0
    ticket = (fat_total / aprovados) if aprovados > 0 else 0.0
    
    return {"total": total, "aprovados": aprovados, "faturamento": fat_total, "lucro": lucro_total, "ticket": ticket, "taxa": taxa, "comissoes": comissao_total}


# ==============================================================================
# 3. ENGENHARIA & CÁLCULO
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
    
    tabela_base_liquida = {
        "Cozinha": 3800.0,
        "Lavanderia": 1200.0,
        "Sala": 2500.0,
        "Sacada": 1500.0,
        "Área Gourmet": 3200.0,
        "Dorm. Solteiro": 2600.0,
        "Dorm. Casal/Suíte": 4200.0,
        "Banheiro": 1100.0,
        "Projeto Completo Sob Medida": 4000.0
    }

    tabela_ferragens = {
        "Blum": 1400.0,
        "Hettich": 1150.0,
        "Häfele": 950.0,
        "FGVTN": 700.0
    }
    
    ferragem_unit = 895.0
    for k, v in tabela_ferragens.items():
        if k.lower() in marca_ferr.lower():
            ferragem_unit = v
            break

    soma_base_liquida = 0.0
    total_ferragens = 0.0
    items, desc_promob_auto = [], []

    for amb in ambientes:
        qtd = 1
        nome_limpo = amb
        if "x " in amb:
            partes = amb.split("x ")
            try:
                qtd = int(partes[0].strip())
                nome_limpo = partes[1].strip()
            except Exception:
                qtd = 1
                nome_limpo = amb

        base_amb = 2500.0
        for chave, val in tabela_base_liquida.items():
            if chave.lower() in nome_limpo.lower():
                base_amb = val
                break

        custo_liquido_ambiente = base_amb * qtd
        soma_base_liquida += custo_liquido_ambiente
        total_ferragens += (ferragem_unit * qtd)

        items.append({
            "nome": f"{amb} (Estrutura {esp_caixa}, Portas {acabamento_porta})",
            "valor": round(custo_liquido_ambiente)
        })
        desc_promob_auto.append(f"{amb}: Caixaria {esp_caixa} ({cor_caixa}), portas {acabamento_porta} ({cor_porta}), ferragens {marca_ferr}.")

    custo_montagem = soma_base_liquida * 0.15
    custo_frete = 180.0
    preco_venda = round(((soma_base_liquida + custo_montagem) * 2.50) + total_ferragens + custo_frete)
    preco_bruto = preco_venda

    total_materiais = round(soma_base_liquida + total_ferragens)
    custo_mo = round(custo_montagem)
    
    comissao_venda = round(preco_venda * (float(empresa.get("comissao_padrao_pct", 4.0)) / 100.0))
    lucro = round(preco_venda - (total_materiais + custo_mo + custo_frete + (preco_venda * 0.10)))

    return {
        "items": items,
        "total_mat": total_materiais,
        "custo_mo": custo_mo,
        "custo_frete": custo_frete,
        "preco_bruto": preco_bruto,
        "preco_venda": preco_venda,
        "lucro": lucro,
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
            <p class="text-xs text-slate-400">Hub Promob, Financiamentos & Gestão Comercial</p>
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
                    <input type="text" name="area_m2_total" value="45" required placeholder="Ex: 45" class="w-full px-4 py-2.5 bg-slate-950 border border-slate-700 rounded-xl text-white font-bold">
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
                            <option value="3">3</option>
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

              <div class="bg-slate-950/80 p-4 rounded-xl border border-amber-500/40 space-y-3">
                    <div class="flex items-center gap-2 text-amber-400 font-bold text-xs uppercase tracking-wide">
                        <span>✨</span> Arquiteto IA & Briefing Sob Medida
                    </div>
                    
                    <div>
                        <label class="block text-slate-300 font-semibold mb-1 text-xs">📐 Medidas das Paredes / Espaço (Largura x Altura)</label>
                        <input type="text" name="medida_parede" placeholder="Ex: Parede principal 3,40m x 2,60m (Pé direito)" class="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-white text-xs placeholder:text-slate-500">
                    </div>

                    <div>
                        <label class="block text-slate-300 font-semibold mb-1 text-xs">📝 Descreva o que deseja no ambiente</label>
                        <textarea name="descricao" rows="2" placeholder="Ex: Torre quente, gavetões com corrediça oculta, perfil LED embutido, ripado amadeirado..." class="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-white text-xs placeholder:text-slate-500"></textarea>
                    </div>

                    <div class="grid sm:grid-cols-2 gap-3 text-xs pt-1">
                        <div class="bg-slate-900 p-3 rounded-lg border border-slate-800 space-y-1">
                            <label class="font-bold text-amber-400 block">📐 Planta Baixa / Croqui (IA lê cotas)</label>
                            <input type="file" name="planta" accept="image/*,.pdf" class="w-full text-slate-400 file:bg-amber-500 file:text-slate-950 file:border-0 file:rounded-md file:px-2 file:py-1 file:font-bold file:text-xs">
                        </div>
                        <div class="bg-slate-900 p-3 rounded-lg border border-slate-800 space-y-1">
                            <label class="font-bold text-slate-300 block">🖼️ Foto de Inspiração / Estilo</label>
                            <input type="file" name="inspiracao" accept="image/*" class="w-full text-slate-400 file:bg-slate-700 file:text-white file:border-0 file:rounded-md file:px-2 file:py-1 file:font-bold file:text-xs">
                        </div>
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
    esp_caixa, cor_caixa, esp_porta, cor_porta, acab_porta, marca_ferr, esp_tamp, ambientes_str, url_render_ia: str = ""
):
    pv_redondo = int(round(preco_venda))
    desconto_vista_5 = int(round(pv_redondo * 0.95))
    
    pv_fmt = f"{pv_redondo:,}".replace(",", ".")
    desconto_fmt = f"{desconto_vista_5:,}".replace(",", ".")
    
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
        <span class="text-3xl sm:text-4xl font-black text-amber-400">R$ {pv_fmt}</span>
        <div class="p-3 bg-emerald-950/60 border border-emerald-500/40 rounded-xl inline-block mt-1">
            <span class="text-xs text-emerald-300 font-bold block">⚡ À Vista no PIX (5% de Desconto):</span>
            <span class="text-xl sm:text-2xl font-black text-emerald-400">R$ {desconto_fmt}</span>
        </div>
    </div>

      
        <!-- OPÇÕES DE CONTATO (SEM IA) -->
                        <div class="bg-slate-950/80 p-5 rounded-2xl border border-slate-800 space-y-4">
                            <div class="text-center">
                                <h3 class="text-sm font-bold text-white uppercase tracking-wide">Deseja dar continuidade ao seu projeto?</h3>
                                <p class="text-xs text-slate-400 mt-1">Selecione uma opção abaixo:</p>
                            </div>

                            <div class="space-y-3">
                                <a href="https://wa.me/{tel_limpo}?text=Ol%C3%A1!%20Simulei%20meu%20projeto%20no%20site%20da%20{empresa['nome_empresa']}%20(Projeto%20%23{orcamento_id:04d})" 
                                   target="_blank"
                                   class="w-full flex items-center justify-center gap-2 py-3.5 px-4 bg-emerald-500 hover:bg-emerald-600 text-slate-950 font-bold rounded-xl text-sm transition shadow-lg shadow-emerald-500/20">
                                    <span>Sim, quero dar continuidade no WhatsApp</span>
                                </a>

                    
                            </div>
                        </div>

                <form action="/recusar-lead" method="post">
                    <input type="hidden" name="orcamento_id" value="{orcamento_id}">
                    <button type="submit" class="w-full py-3 bg-slate-900 hover:bg-rose-950/40 text-slate-400 hover:text-rose-400 border border-slate-700 hover:border-rose-800/50 rounded-2xl font-semibold text-xs transition block text-center">
                        ❌ Não tenho interesse no momento
                    </button>
                </form>
            </div>
        </div>

    </div>
</body></html>"""

def render_trocar_senha(msg: str = "", msg_tipo: str = "erro") -> HTMLResponse:
    cor_alerta = "bg-rose-500/20 text-rose-300 border-rose-500/30" if msg_tipo == "erro" else "bg-amber-500/20 text-amber-300 border-amber-500/30"
    html = f"""<!DOCTYPE html>
<html lang="pt-br">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Definição de Nova Senha</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-slate-950 text-slate-100 min-h-screen flex items-center justify-center p-4">
    <div class="max-w-md w-full bg-slate-900 border border-slate-800 rounded-2xl p-6 sm:p-8 shadow-2xl space-y-6">
        <div class="text-center space-y-2">
            <div class="inline-flex items-center justify-center w-12 h-12 rounded-xl bg-amber-500/10 text-amber-400 font-black text-xl mb-2">🔒</div>
            <h1 class="text-xl font-bold text-white">Criar Senha Definitiva</h1>
            <p class="text-xs text-slate-400">Por segurança, altere sua senha provisória para acessar o painel.</p>
        </div>

        {f'<div class="p-3 rounded-xl border text-xs text-center {cor_alerta}">{msg}</div>' if msg else ''}

        <form action="/trocar-senha" method="post" class="space-y-4">
            <div>
                <label class="block text-xs font-semibold text-slate-300 mb-1">SENHA PROVISÓRIA / ATUAL</label>
                <input type="password" name="senha_atual" required class="w-full bg-slate-950 border border-slate-700 rounded-xl px-4 py-2.5 text-sm text-white focus:outline-none focus:border-amber-500" placeholder="••••••••">
            </div>

            <div>
                <label class="block text-xs font-semibold text-slate-300 mb-1">NOVA SENHA DEFINITIVA</label>
                <input type="password" name="nova_senha" required minlength="6" class="w-full bg-slate-950 border border-slate-700 rounded-xl px-4 py-2.5 text-sm text-white focus:outline-none focus:border-amber-500" placeholder="Mínimo 6 caracteres">
            </div>

            <div>
                <label class="block text-xs font-semibold text-slate-300 mb-1">CONFIRMAR NOVA SENHA</label>
                <input type="password" name="confirma_senha" required minlength="6" class="w-full bg-slate-950 border border-slate-700 rounded-xl px-4 py-2.5 text-sm text-white focus:outline-none focus:border-amber-500" placeholder="Repita a nova senha">
            </div>

            <button type="submit" class="w-full py-3 bg-amber-500 hover:bg-amber-600 font-bold text-slate-950 rounded-xl text-sm transition shadow-lg shadow-amber-500/20">
                Salvar e Acessar Painel
            </button>
        </form>
    </div>
</body>
</html>"""
    return HTMLResponse(content=html)


@app.get("/trocar-senha", response_class=HTMLResponse)
def trocar_senha_view():
    if not CURRENT_SESSION.get("user_email"):
        return render_login("Faça login antes de alterar a senha.")
    return render_trocar_senha()


@app.post("/trocar-senha", response_class=HTMLResponse)
def trocar_senha_post(
    senha_atual: str = Form(...),
    nova_senha: str = Form(...),
    confirma_senha: str = Form(...)
):
    email_logado = CURRENT_SESSION.get("user_email")
    if not email_logado:
        return render_login("Sessão expirada. Faça login novamente.")

    if nova_senha != confirma_senha:
        return render_trocar_senha("❌ A nova senha e a confirmação não coincidem.", "erro")

    if len(nova_senha) < 6:
        return render_trocar_senha("❌ A nova senha deve ter no mínimo 6 caracteres.", "erro")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM usuarios WHERE email = ?", (email_logado.strip().lower(),))
    user = cursor.fetchone()

    if not user or user["senha"] != senha_atual:
        conn.close()
        return render_trocar_senha("❌ Senha provisória incorreta.", "erro")

    cursor.execute("UPDATE usuarios SET senha = ?, primeiro_acesso = 0 WHERE email = ?", (nova_senha, email_logado.strip().lower()))
    conn.commit()
    conn.close()

    CURRENT_SESSION["user_perfil"] = user["perfil"]
    CURRENT_SESSION["user_nome"] = user["nome"]
    CURRENT_SESSION["empresa_id"] = user["empresa_id"]
    return render_dashboard_view()


@app.post("/admin/cadastrar-vendedor")
def cadastrar_vendedor_route(
    nome: str = Form(...),
    email: str = Form(...),
    perfil: str = Form("vendedor")
):
    caracteres = string.ascii_letters + string.digits
    senha_provisoria = "MVI-" + "".join(secrets.choice(caracteres) for _ in range(5))

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        cursor.execute("ALTER TABLE usuarios ADD COLUMN primeiro_acesso INTEGER DEFAULT 0")
    except:
        pass

    cursor.execute("""
        INSERT INTO usuarios (nome, email, senha, perfil, ativo, empresa_id, primeiro_acesso)
        VALUES (?, ?, ?, ?, 1, 1, 1)
    """, (nome.strip(), email.strip().lower(), senha_provisoria, perfil.strip().lower()))
    conn.commit()
    conn.close()

    link_app = "https://sistema-marcenaria-6laa.onrender.com/"
    enviar_email_convite_vendedor(nome, email.strip().lower(), senha_provisoria, link_app)

    return RedirectResponse("/painel", status_code=303)
    return RedirectResponse("/painel", status_code=303)


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
    pode_gerenciar_leads = (perfil in ["adm", "gerente"])
    pode_excluir = (perfil == "adm")
    somente_leitura_fabrica = (perfil == "liberacao")
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    if perfil == "financeiro":
        cursor.execute("SELECT * FROM orcamentos WHERE empresa_id = 1 AND status IN ('Aprovado', 'Venda Fechada', 'Em Produção', 'Entregue', 'Liberado para Financeiro & Fábrica', 'Contrato Assinado Digitalmente') ORDER BY id DESC")
    elif perfil == "vendedor":
        cursor.execute("SELECT * FROM orcamentos WHERE empresa_id = 1 AND status != 'Contrato Fechado' AND (vendedor_email = ? OR vendedor_responsavel = ?) ORDER BY id DESC", (CURRENT_SESSION.get('user_email',''), CURRENT_SESSION.get('user_nome','')))
    else:
        cursor.execute("SELECT * FROM orcamentos WHERE empresa_id = 1 AND status != 'Contrato Fechado' ORDER BY id DESC LIMIT 100")

    leads = cursor.fetchall()
    # Busca apenas os contratos fechados para a pasta com cadeado
    if perfil == "vendedor":
        cursor.execute("SELECT * FROM orcamentos WHERE empresa_id = 1 AND status = 'Contrato Fechado' AND (vendedor_email = ? OR vendedor_responsavel = ?) ORDER BY id DESC", (CURRENT_SESSION.get('user_email',''), CURRENT_SESSION.get('user_nome','')))
    else:
        cursor.execute("SELECT * FROM orcamentos WHERE empresa_id = 1 AND status = 'Contrato Fechado' ORDER BY id DESC")
    fechados_rows = cursor.fetchall()

    lista_fechados_html = ""
    for f in fechados_rows:
        fd = dict(f)
        f_id = fd.get('id', 0)
        f_nome = fd.get('cliente_nome') or 'Cliente'
        f_val = float(fd.get('preco_venda') or 0) + float(fd.get('adendo_valor') or 0)
        f_val_fmt = f"{f_val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        btn_adm = f"<button onclick='desbloquearContrato({f_id})' class='px-2.5 py-1 bg-amber-500 hover:bg-amber-600 text-slate-950 font-bold rounded text-[10px]'>🔓 Destravar (ADM)</button>" if perfil == "adm" else "<span class='text-slate-500 text-[10px] font-semibold flex items-center justify-end gap-1'>🔒 Bloqueado</span>"
        
        lista_fechados_html += f"""
        <tr class='hover:bg-slate-800/40 transition'>
            <td class='py-3 px-3 font-mono font-bold text-amber-400'>#{f_id:04d}</td>
            <td class='py-3 px-3 font-semibold text-white'>{f_nome}</td>
            <td class='py-3 px-3 text-emerald-400 font-bold'>R$ {f_val_fmt}</td>
            <td class='py-3 px-3'><span class='px-2 py-0.5 bg-emerald-950 border border-emerald-500/40 text-emerald-400 rounded-full text-[10px] font-bold'>Contrato Fechado</span></td>
            <td class='py-3 px-3 text-right flex items-center justify-end gap-2'>
                <a href='/minuta-contrato/{f_id}' target='_blank' class='px-2.5 py-1 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded text-[10px] font-semibold'>📄 Ver Minuta</a>
                {btn_adm}
            </td>
        </tr>
        """
    if not lista_fechados_html:
        lista_fechados_html = "<tr><td colspan='5' class='py-6 text-center text-slate-500'>Nenhum contrato fechado no momento.</td></tr>"
    
    cursor.execute("SELECT * FROM propostas_credito WHERE empresa_id = 1 ORDER BY id DESC")
    propostas_credito = cursor.fetchall()

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
    c_renda = cliente_ativo.get("cliente_renda") or "5500"
    c_vendedor = cliente_ativo.get("vendedor_responsavel") or CURRENT_SESSION["user_nome"]

    # Endereço Postal
    c_cep_post = cliente_ativo.get("cliente_cep_postal") or ""
    c_rua_post = cliente_ativo.get("cliente_rua_postal") or ""
    c_num_post = cliente_ativo.get("cliente_num_postal") or ""
    c_comp_post = cliente_ativo.get("cliente_comp_postal") or ""
    c_bairro_post = cliente_ativo.get("cliente_bairro_postal") or ""
    c_cidade_post = cliente_ativo.get("cliente_cidade_postal") or ""
    c_uf_post = cliente_ativo.get("cliente_uf_postal") or ""

    # Endereço de Entrega / Obra
    c_cep_ent = cliente_ativo.get("cliente_cep_entrega") or ""
    c_rua_ent = cliente_ativo.get("cliente_rua_entrega") or ""
    c_num_ent = cliente_ativo.get("cliente_num_entrega") or ""
    c_comp_ent = cliente_ativo.get("cliente_comp_entrega") or ""
    c_bairro_ent = cliente_ativo.get("cliente_bairro_entrega") or ""
    c_cidade_ent = cliente_ativo.get("cliente_cidade_entrega") or ""
    c_uf_ent = cliente_ativo.get("cliente_uf_entrega") or ""

    c_prazo = cliente_ativo.get("prazo_entrega") or "35 dias úteis"
    c_amb = cliente_ativo.get("cliente_ambiente") or "Cozinha Planejada"
    
    c_p_bruto = float(cliente_ativo.get("preco_bruto") or cliente_ativo.get("preco_venda") or 0)
    c_p_venda = float(cliente_ativo.get("preco_venda") or 0)
    c_lucro = float(cliente_ativo.get("lucro_liquido") or 0)
    c_desc_pct = float(cliente_ativo.get("desconto_pct") or 0)
    c_entrada = float(cliente_ativo.get("entrada_valor") or 0)
    c_parc = max(int(cliente_ativo.get("num_parcelas") or 1), 1)
    c_mod = cliente_ativo.get("modalidade_pagamento") or "Entrada + Cartão de Crédito"
    c_comissao = float(cliente_ativo.get("comissao_valor") or (c_p_venda * (float(empresa.get("comissao_padrao_pct", 4.0)) / 100.0)))
    
    chk_dados = int(cliente_ativo.get("check_dados") or (1 if c_cpf != 'Não informado' else 0))
    chk_comercial = int(cliente_ativo.get("check_comercial") or 1)
    chk_financeiro = int(cliente_ativo.get("check_financeiro") or 0)
    chk_contrato = int(cliente_ativo.get("check_contrato") or 0)

    # Base Bruta sem desconto
    preco_base_sem_desconto = c_p_bruto if c_p_bruto > 0 else (c_p_venda / (1.0 - (c_desc_pct / 100.0)) if c_desc_pct < 100 and c_desc_pct > 0 else c_p_venda)

    taxa_juros_empresa = float(empresa.get("taxa_juros_mensal", 1.99))
    saldo_para_financiar = max(c_p_venda - c_entrada, 0.0)

    if "Financiamento" in c_mod or "MVI Crédito" in c_mod:
        valor_por_parcela = calcular_parcela_price(saldo_para_financiar, taxa_juros_empresa, c_parc)
    else:
        valor_por_parcela = (saldo_para_financiar / c_parc) if c_parc > 0 else 0.0

    total_com_juros_cronograma = c_entrada + (valor_por_parcela * c_parc)

    linhas_parcelas = ""
    hoje = date.today()

    if c_entrada > 0:
        linhas_parcelas += f"""
        <tr class="border-b border-slate-800 text-xs bg-emerald-950/30 hover:bg-slate-800/40">
            <td class="py-2.5 px-3 text-center text-emerald-400 font-bold font-mono">Entrada</td>
            <td class="py-2.5 px-3 text-slate-300">{hoje.strftime("%d/%m/%Y")}</td>
            <td class="py-2.5 px-3 font-bold text-emerald-400 text-right">R$ {fmt_br(c_entrada)}</td>
            <td class="py-2.5 px-3 text-slate-300">PIX / À Vista (Ato)</td>
            <td class="py-2.5 px-3 text-emerald-400 font-semibold">✓ Confirmado / Entrada</td>
        </tr>
        """

    for i in range(1, c_parc + 1):
        dt_parc = (hoje + timedelta(days=30 * i)).strftime("%d/%m/%Y")
        linhas_parcelas += f"""
        <tr class="border-b border-slate-800 text-xs hover:bg-slate-800/40">
            <td class="py-2.5 px-3 text-center text-slate-400 font-mono">{i}ª Parc</td>
            <td class="py-2.5 px-3 text-slate-300">{dt_parc}</td>
            <td class="py-2.5 px-3 font-bold text-amber-400 text-right">R$ {fmt_br(valor_por_parcela)}</td>
            <td class="py-2.5 px-3 text-slate-300">{c_mod}</td>
            <td class="py-2.5 px-3 text-slate-400">Carnê / Boleto MVI</td>
        </tr>
        """

    linhas_parcelas += f"""
    <tr class="border-t-2 border-slate-700 text-xs bg-slate-950 font-bold">
        <td colspan="2" class="py-3 px-3 text-amber-400 uppercase">Total Geral (Entrada + Parcelas):</td>
        <td class="py-3 px-3 font-black text-amber-400 text-right text-sm">R$ {fmt_br(total_com_juros_cronograma)}</td>
        <td colspan="2" class="py-3 px-3 text-slate-400 text-[11px]">Plano {c_parc}x com juros de {taxa_juros_empresa}% a.m.</td>
    </tr>
    """

    simulacoes_financeira = []
    for n_parc in [12, 18, 24, 36]:
        v_parc = calcular_parcela_price(saldo_para_financiar, taxa_juros_empresa, n_parc)
        simulacoes_financeira.append({
            "parcelas": n_parc,
            "valor_parcela": v_parc,
            "total": v_parc * n_parc
        })

    c_imagens = {}
    try:
        c_imagens = json.loads(cliente_ativo.get("imagens_json") or "{}")
    except Exception:
        c_imagens = {}
        
    planta_data = c_imagens.get("planta") or cliente_ativo.get("arquivo_planta") or ""
    planta_nome = c_imagens.get("planta_nome") or "Planta Baixa"
    insp_data = c_imagens.get("inspiracao") or cliente_ativo.get("arquivo_inspiracao") or ""
    insp_nome = c_imagens.get("inspiracao_nome") or "Foto Inspiração"

    tel_lead_limpo = (c_tel or "").replace("-","").replace(" ","").replace("(","").replace(")","")

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
                {f'''<a href="{planta_data}" target="_blank" download="{planta_nome}" class="block text-center py-2 px-3 bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold rounded-xl transition shadow">📥 Baixar Planta</a>''' if planta_data else '''<span class="block text-center py-2 text-slate-500 bg-slate-900 rounded-xl border border-slate-800">Nenhuma planta anexada</span>'''}
            </div>
            <div class="p-3 bg-slate-950 rounded-2xl border border-slate-800 space-y-2">
                <div class="flex items-center justify-between">
                    <span class="font-bold text-slate-300">🖼️ Foto Inspiração:</span>
                    <span class="text-[10px] text-slate-400 font-mono truncate max-w-[120px]">{insp_nome}</span>
                </div>
                {f'''<a href="{insp_data}" target="_blank" download="{insp_nome}" class="block text-center py-2 px-3 bg-slate-800 hover:bg-slate-700 text-slate-200 font-bold rounded-xl transition border border-slate-700">📥 Baixar Foto</a>''' if insp_data else '''<span class="block text-center py-2 text-slate-500 bg-slate-900 rounded-xl border border-slate-800">Nenhuma foto anexada</span>'''}
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

    lista_ambientes_html = ""
    for amb_item in ambientes_cadastrados:
        val_amb = float(amb_item.get("valor", 0))
        lista_ambientes_html += f"""
        <li class="p-2 bg-slate-950 rounded-xl border border-slate-800 flex justify-between items-center group">
            <div>
                <span class="text-white font-semibold block">📦 {amb_item.get('nome','Ambiente')}</span>
                <span class="text-[11px] font-bold text-amber-400">R$ {fmt_br(val_amb)}</span>
            </div>
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
                <span class="text-[11px] font-bold text-amber-400">R$ {fmt_br(v_val)}</span>
            </div>
        </li>
        """

    leads_geral_html = ""
    tabela_leads_gestao_html = ""
    options_leads = "<option value='0'>📂 Selecionar outra pasta...</option>"

    status_opcoes = ["Novo Lead", "Em Atendimento", "Visita Agendada", "Em Negociação", "Venda Fechada", "Descartado / Sem Interesse"]

    for h in leads:
        h_d = dict(h)
        pv = float(h_d.get("preco_venda") or 0)
        adendo = float(h_d.get("adendo_valor") or 0)
        pv_total = pv + adendo
        st = h_d.get("status") or "Novo Lead"
        sel = "selected" if h_d.get("id") == c_id else ""
        options_leads += f"<option value='{h_d['id']}' {sel}>Pasta P{h_d['id']:05d} - {h_d.get('cliente_nome','')} ({h_d.get('cliente_ambiente','')})</option>"

        imgs_lead = {}
        try:
            imgs_lead = json.loads(h_d.get("imagens_json") or "{}")
        except Exception:
            imgs_lead = {}
        p_data = imgs_lead.get("planta") or h_d.get("arquivo_planta") or ""
        p_nm = imgs_lead.get("planta_nome") or "Planta"
        i_data = imgs_lead.get("inspiracao") or h_d.get("arquivo_inspiracao") or ""
        i_nm = imgs_lead.get("inspiracao_nome") or "Inspiração"

        tel_lead = (h_d.get("cliente_telefone") or "").replace("-","").replace(" ","").replace("(","").replace(")","")

        btn_lixeira_html = f"""
        <form action="/excluir-lead" method="post" class="inline" onsubmit="return confirm('⚠️ ATENÇÃO ADM: Deseja realmente excluir permanentemente a Pasta P{h_d['id']:05d} ({h_d.get('cliente_nome','')})? Esta ação não pode ser desfeita.')">
            <input type="hidden" name="orcamento_id" value="{h_d['id']}">
            <button type="submit" class="p-1.5 bg-rose-950 hover:bg-rose-900 text-rose-300 border border-rose-700/60 rounded-lg text-xs font-bold transition shadow" title="Excluir Pasta (Exclusivo ADM)">
                🗑️
            </button>
        </form>
        """ if pode_excluir else """
        <span class="p-1.5 text-slate-600 text-xs" title="Exclusão restrita ao Administrador">🔒</span>
        """

        leads_geral_html += f"""
        <tr class="border-b border-slate-800 text-xs hover:bg-slate-800/40">
            <td class="py-3 px-4 font-mono font-bold text-amber-400">P{h_d['id']:05d}</td>
            <td class="py-3 px-4 text-white font-bold">{h_d.get('cliente_nome','')}<span class="block text-[11px] text-slate-400 font-normal">Vendedor: {h_d.get('vendedor_responsavel','')}</span></td>
            <td class="py-3 px-4 text-slate-300">{h_d.get('cliente_ambiente','')}</td>
            <td class="py-3 px-4 text-amber-400 font-bold text-right">R$ {fmt_br(pv_total)}</td>
            <td class="py-3 px-4 text-center"><span class="px-2 py-0.5 rounded text-[11px] font-bold bg-amber-950 text-amber-300 border border-amber-500/30">{st}</span></td>
            <td class="py-3 px-4 text-center">
                <div class="flex items-center justify-center gap-1.5">
                    <form action="/selecionar-cliente-trabalho" method="post" class="inline">
                        <input type="hidden" name="orcamento_id" value="{h_d['id']}">
                        <button type="submit" class="px-3 py-1.5 bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold rounded-lg text-xs shadow-sm">
                            Abrir
                        </button>
                    </form>
                    {btn_lixeira_html}
                </div>
            </td>
        </tr>
        """

        options_status_select = "".join([f"<option value='{op}' {'selected' if op == st else ''}>{op}</option>" for op in status_opcoes])
        
        tabela_leads_gestao_html += f"""
        <tr class="border-b border-slate-800 text-xs hover:bg-slate-800/40">
            <td class="py-3 px-3 font-mono font-bold text-amber-400">#{h_d['id']:04d}</td>
            <td class="py-3 px-3 text-slate-400 text-[11px]">{h_d.get('criado_em','—')}</td>
            <td class="py-3 px-3 text-white font-bold">
                {h_d.get('cliente_nome','')}
                <span class="block text-[11px] text-slate-400 font-normal">{h_d.get('cliente_telefone','')}</span>
            </td>
            <td class="py-3 px-3 text-slate-300 max-w-[200px] truncate" title="{h_d.get('cliente_ambiente','')}">
                {h_d.get('cliente_ambiente','')}
            </td>
            <td class="py-3 px-3 text-amber-400 font-bold text-right">R$ {fmt_br(pv_total)}</td>
            <td class="py-3 px-3 text-center">
                <div class="flex items-center justify-center gap-1">
                    {f'''<a href="{p_data}" target="_blank" download="{p_nm}" class="px-2 py-1 bg-amber-500/20 hover:bg-amber-500/40 text-amber-300 border border-amber-500/40 rounded text-[11px] font-bold" title="Baixar Planta">📐 Planta</a>''' if p_data else '<span class="text-slate-600 text-[11px]">—</span>'}
                    {f'''<a href="{i_data}" target="_blank" download="{i_nm}" class="px-2 py-1 bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 rounded text-[11px] font-bold" title="Baixar Foto">🖼️ Foto</a>''' if i_data else ''}
                </div>
            </td>
            <td class="py-3 px-3 text-center">
                <form action="/atualizar-status-lead" method="post" class="inline">
                    <input type="hidden" name="orcamento_id" value="{h_d['id']}">
                    <select name="novo_status" onchange="this.form.submit()" class="px-2 py-1 bg-slate-950 border border-slate-700 rounded text-[11px] font-semibold text-amber-300 cursor-pointer">
                        {options_status_select}
                    </select>
                </form>
            </td>
            <td class="py-3 px-3 text-center">
                <div class="flex items-center justify-center gap-1.5">
                    {f'''<a href="https://api.whatsapp.com/send?phone=55{tel_lead}&text=Ol%C3%A1%20{h_d.get('cliente_nome','')}!%20Recebemos%20sua%20solicita%C3%A7%C3%A3o%20de%20projeto." target="_blank" class="p-1 bg-emerald-600 hover:bg-emerald-500 text-slate-950 rounded font-bold text-xs" title="WhatsApp">📲</a>''' if tel_lead else ''}
                    
                    <form action="/selecionar-cliente-trabalho" method="post" class="inline">
                        <input type="hidden" name="orcamento_id" value="{h_d['id']}">
                        <button type="submit" class="px-2 py-1 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded text-xs font-semibold" title="Abrir no Painel">📂</button>
                    </form>

                    {btn_lixeira_html}
                </div>
            </td>
        </tr>
        """

    tabela_credito_html = ""
    for prop in propostas_credito:
        pr = dict(prop)
        st_color = "bg-emerald-950 text-emerald-300 border-emerald-500/40" if "Aprovado" in pr['status'] else "bg-rose-950 text-rose-300 border-rose-500/40"
        carne_btn = f"""<a href="{pr['asaas_carne_url']}" target="_blank" class="px-2 py-1 bg-emerald-600 hover:bg-emerald-500 text-slate-950 rounded font-black text-[11px] shadow">💳 Abrir Carnê / Boletos</a>""" if pr.get("asaas_carne_url") else ""

        tabela_credito_html += f"""
        <tr class="border-b border-slate-800 text-xs hover:bg-slate-800/40">
            <td class="py-3 px-3 font-mono font-bold text-amber-400">CCB#{pr['id']:05d}</td>
            <td class="py-3 px-3 text-slate-300">{pr['criado_em']}</td>
            <td class="py-3 px-3 text-white font-bold">{pr['cliente_nome']}<span class="block text-[11px] text-slate-400 font-normal">CPF: {pr['cliente_cpf']} | Renda: R$ {fmt_br(pr['cliente_renda'])}</span></td>
            <td class="py-3 px-3 text-amber-400 font-bold text-right">R$ {fmt_br(pr['valor_financiado'])}</td>
            <td class="py-3 px-3 text-center font-bold text-white">{pr['num_parcelas']}x de <span class="text-emerald-400">R$ {fmt_br(pr['valor_parcela'])}</span></td>
            <td class="py-3 px-3 text-right text-slate-300">R$ {fmt_br(pr['total_com_juros'])}</td>
            <td class="py-3 px-3 text-center"><span class="px-2.5 py-1 rounded-full text-[10px] font-bold border {st_color}">{pr['status']}</span></td>
            <td class="py-3 px-3 text-center">
                <div class="flex items-center justify-center gap-1.5">
                    {carne_btn}
                    <a href="/emitir-ccb/{pr['id']}" target="_blank" class="px-2.5 py-1 bg-amber-500 hover:bg-amber-400 text-slate-950 rounded font-bold text-[11px] shadow">📄 CCB</a>
                </div>
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
    <title>MVI Gestão - CRM & Financiamento Próprio</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        .tree-item {{ transition: all 0.2s; cursor: pointer; }}
        .tree-item:hover {{ background-color: #1e293b; color: #f59e0b; }}
        .tree-item.active {{ background: linear-gradient(135deg, #f59e0b, #d97706); color: #0f172a; font-weight: bold; }}
        .tab-content {{ display: none; }}
        .tab-content.active {{ display: block; }}
        .oculto-valor {{ filter: blur(6px); user-select: none; transition: all 0.2s; }}
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
                <button onclick="mudarAba('aba-geral')" class="px-3 py-1.5 rounded-lg bg-amber-500 text-slate-950 hover:bg-amber-400 font-bold shadow-md">📂 Pastas</button>
                {f'''<button onclick="mudarAba('aba-leads-gestao')" class="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700">🎯 Leads & Orçamentos</button>''' if pode_gerenciar_leads else ''}
                <button onclick="mudarAba('aba-financiamento-proprio')" class="px-3 py-1.5 rounded-lg bg-sky-950 text-sky-300 hover:bg-sky-900 border border-sky-500/40 font-bold">💳 MVI Financiamentos</button>
                <button onclick="mudarAba('aba-comissoes')" class="px-3 py-1.5 rounded-lg bg-emerald-950/80 text-emerald-300 hover:bg-emerald-900 border border-emerald-500/40">💰 Comissões</button>
                {f'''<button onclick="mudarAba('aba-equipe')" class="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-amber-300 border border-slate-700">👥 Equipe</button>
                <button onclick="mudarAba('aba-empresa')" class="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700">🏢 Empresa</button>''' if pode_gerenciar_equipe else ''}
                <a href="/solicitar-orcamento" target="_blank" class="px-3 py-1.5 rounded-lg bg-amber-950 text-amber-300 hover:bg-amber-900 border border-amber-500/40">🔗 Link Público</a>
                <button onclick="document.getElementById('modal-novo-colaborador').classList.remove('hidden')" class="px-3 py-1.5 rounded-lg bg-amber-500 hover:bg-amber-600 text-white font-medium text-sm flex items-center gap-1.5 shadow-sm">
    <span>👥</span> + Colaborador
</button>

<button type="button" onclick="abrirModalNovaPastaDireta()" class="px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-medium text-sm flex items-center gap-1.5 shadow-sm">
    <span>📁</span>
    <span>+ Nova Pasta / Cliente Direto</span>
</button>

        <div id="modal-novo-colaborador" class="hidden fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
            <div class="bg-slate-900 border border-slate-800 w-full max-w-md rounded-2xl p-6 shadow-2xl space-y-4 text-left">
                <div class="flex justify-between items-center pb-2 border-b border-slate-800">
                    <h3 class="text-base font-bold text-white flex items-center gap-2">
                        <span class="p-1.5 bg-amber-500/10 text-amber-400 rounded-lg">👤</span> Cadastrar Colaborador
                    </h3>
                    <button type="button" onclick="document.getElementById('modal-novo-colaborador').classList.add('hidden')" class="text-slate-400 hover:text-white text-lg font-bold">✕</button>
                </div>

                <form action="/admin/cadastrar-vendedor" method="post" class="space-y-4">
                    <div>
                        <label class="block text-xs font-semibold text-slate-300 mb-1">NOME DO COLABORADOR</label>
                        <input type="text" name="nome" required placeholder="Ex: Roberto Silva" class="w-full bg-slate-950 border border-slate-700 rounded-xl px-4 py-2.5 text-sm text-white focus:outline-none focus:border-amber-500">
                    </div>

                    <div>
                        <label class="block text-xs font-semibold text-slate-300 mb-1">E-MAIL CORPORATIVO / PESSOAL</label>
                        <input type="email" name="email" required placeholder="Ex: roberto@empresa.com" class="w-full bg-slate-950 border border-slate-700 rounded-xl px-4 py-2.5 text-sm text-white focus:outline-none focus:border-amber-500">
                    </div>

                    <div>
                        <label class="block text-xs font-semibold text-slate-300 mb-1">CARGO / FUNÇÃO</label>
                        <div class="relative">
                            <select name="perfil" required class="w-full bg-slate-950 border border-slate-700 rounded-xl px-4 py-2.5 text-sm text-white focus:outline-none focus:border-amber-500 appearance-none cursor-pointer">
                                <option value="vendedor" selected>💼 Vendedor (Comercial & Leads)</option>
                                <option value="gerente">📊 Gerente (Metas & Gestão Geral)</option>
                                <option value="liberacao">📐 Finalização / Liberação Técnica (Fábrica)</option>
                                <option value="financeiro">💳 Financeiro (Aprovações & Cobrança)</option>
                            </select>
                            <div class="pointer-events-none absolute inset-y-0 right-0 flex items-center px-4 text-slate-400">
                                ▼
                            </div>
                        </div>
                    </div>

                    <div class="flex gap-2 pt-2">
                        <button type="button" onclick="document.getElementById('modal-novo-colaborador').classList.add('hidden')" class="w-1/2 py-2.5 bg-slate-800 hover:bg-slate-700 text-slate-300 font-bold text-xs rounded-xl transition">
                            Cancelar
                        </button>
                        <button type="submit" class="w-1/2 py-2.5 bg-amber-500 hover:bg-amber-600 text-slate-950 font-bold text-xs rounded-xl transition shadow-lg shadow-amber-500/20">
                            Cadastrar e Enviar
                        </button>
                    </div>
                </form>
            </div>
        </div>
            </nav>
        </div>

        <div class="flex items-center space-x-4 text-xs">
            <button onclick="alternarVisibilidadeSigilo()" class="px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 border border-slate-700 text-amber-400 font-bold flex items-center gap-1.5" title="Ocultar / Mostrar Comissão e Lucro">
                <span id="icone-olho">👁️</span> <span id="texto-olho" class="hidden sm:inline">Sigilo Ativo</span>
            </button>
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
                <div class="flex items-center justify-between pb-2 border-b border-slate-800">
                    <h3 class="font-bold text-white">📁 Pasta P{c_id:05d}</h3>
                    <span class="text-[10px] bg-amber-950 text-amber-300 border border-amber-500/40 px-2 py-0.5 rounded-full">Ativa</span>
                </div>

                {f'''
                <form action="/excluir-lead" method="post" class="mt-2" onsubmit="return confirm('⚠️ ATENÇÃO ADM: Deseja realmente excluir permanentemente a Pasta P{c_id:05d} ({c_nome})? Esta ação não poderá ser desfeita!')">
                    <input type="hidden" name="orcamento_id" value="{c_id}">
                    <button type="submit" class="w-full py-2 bg-rose-950 hover:bg-rose-900 text-rose-300 border border-rose-800/80 rounded-xl text-xs font-bold transition flex items-center justify-center gap-1 shadow">
                        🗑️ Excluir esta Pasta (ADM)
                    </button>
                </form>
                ''' if (pode_excluir and c_id > 0) else ''}

                <ul class="mt-2 space-y-1">
    <li><button onclick="mudarAba('aba-cliente')" id="btn-aba-cliente" class="tree-item active w-full text-left flex items-center gap-2 p-2.5 rounded-xl text-white font-semibold">👤 1. Dados do Cliente</button></li>
    <li><button onclick="mudarAba('aba-promob')" id="btn-aba-promob" class="tree-item w-full text-left flex items-center gap-2 p-2.5 rounded-xl text-slate-300 font-medium">🚀 2. Integrador Promob</button></li>
    {f'''<li><button onclick="mudarAba('aba-mesa')" id="btn-aba-mesa" class="tree-item w-full text-left flex items-center gap-2 p-2.5 rounded-xl text-slate-300 font-medium">💼 3. Mesa de Negociação</button></li>''' if c_id > 0 else ''}
    <li><a href="/minuta-contrato/{c_id}" target="_blank" class="tree-item flex items-center gap-2 p-2.5 rounded-xl text-amber-400 font-medium hover:bg-slate-800">📜 4. Minuta e Fechamento de Contrato</a></li>
    <li class="pt-2 border-t border-slate-800">
        <button onclick="mudarAba('aba-fechados')" id="btn-aba-fechados" class="tree-item w-full text-left flex items-center justify-between p-2.5 rounded-xl text-emerald-400 font-semibold bg-emerald-950/20 hover:bg-emerald-950/40 border border-emerald-500/20">
            <span class="flex items-center gap-2">📁 5. Contratos Fechados</span>
            <span>🔒</span>
        </button>
    </li>
</ul>
            </div>

            <!-- SEÇÃO DE AMBIENTES -->
            <div>
                <div class="flex justify-between items-center pb-1 border-b border-slate-800 font-bold text-white">
                    <span>🏠 Ambientes</span>
                </div>
                <ul class="mt-2 space-y-1.5 text-slate-400">{lista_ambientes_html}</ul>
            </div>

            <!-- SEÇÃO DE ORÇAMENTOS -->
            <div>
                <div class="flex justify-between items-center pb-1 border-b border-slate-800 font-bold text-white">
                    <span>⭐ Orçamentos</span>
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

                <!-- ARQUIVOS E ANEXOS DO LEAD -->
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
                            <tbody id="corpo_tabela_cronograma">{linhas_parcelas}</tbody>
                        </table>
                    </div>
                </div>
            </div>

            <!-- NOVA ABA: FINANCEIRA PRÓPRIA (MVI FINANCIAMENTOS) -->
            <div id="aba-financiamento-proprio" class="tab-content bg-slate-900 border border-slate-800 rounded-3xl p-5 shadow-xl space-y-4 text-xs">
                <div class="flex justify-between items-center pb-2 border-b border-slate-800">
                    <div>
                        <h3 class="font-bold text-sm text-sky-400 uppercase">💳 MVI Crédito & Financiadora Própria</h3>
                        <p class="text-[11px] text-slate-400">Emissão de CCB e Carnês de Boletos Registrados direto na conta PJ</p>
                    </div>
                    <span class="px-3 py-1 bg-sky-950 text-sky-300 border border-sky-500/40 rounded-full font-bold text-[10px]">Asaas BaaS Integrado</span>
                </div>

                <div class="bg-slate-950 p-4 rounded-2xl border border-slate-800 space-y-3">
                    <h4 class="font-bold text-white text-xs uppercase flex items-center justify-between">
                        <span>⚡ Simulação de Crédito para a Pasta Ativa (P{c_id:05d})</span>
                        <span class="text-amber-400">Saldo a Financiar: R$ {fmt_br(saldo_para_financiar)}</span>
                    </h4>
                    
                    <div class="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
                        {''.join([f'''
                        <div class="p-3 bg-slate-900 rounded-xl border border-slate-800 text-center space-y-1">
                            <span class="text-[11px] text-slate-400 font-bold block">{sim['parcelas']}x Fixas</span>
                            <span class="text-xs sm:text-sm font-black text-emerald-400 block">R$ {fmt_br(sim['valor_parcela'])}</span>
                            <span class="text-[10px] text-slate-500 block">Total: R$ {fmt_br(sim['total'])}</span>
                        </div>''' for sim in simulacoes_financeira])}
                    </div>

                    <form action="/submeter-proposta-credito" method="post" class="pt-2">
                        <input type="hidden" name="orcamento_id" value="{c_id}">
                        <input type="hidden" name="cliente_nome" value="{c_nome}">
                        <input type="hidden" name="cliente_cpf" value="{c_cpf}">
                        <input type="hidden" name="cliente_telefone" value="{c_tel}">
                        <input type="hidden" name="cliente_renda" value="{c_renda}">
                        <input type="hidden" name="valor_financiado" value="{saldo_para_financiar}">
                        <div class="flex gap-2">
                            <select name="num_parcelas" class="p-2.5 bg-slate-900 border border-slate-700 rounded-xl text-white font-bold text-xs flex-1">
                                <option value="3">Plano 3x com Juros da Financeira</option>
                                <option value="6">Plano 6x no Boleto/PIX (Carnê Asaas)</option>
                                <option value="12">Plano 12x no Boleto/PIX (Carnê Asaas)</option>
                                <option value="18">Plano 18x no Boleto/PIX (Carnê Asaas)</option>
                                <option value="24" selected>Plano 24x no Boleto/PIX (Carnê Asaas)</option>
                                <option value="36">Plano 36x no Boleto/PIX (Carnê Asaas)</option>
                            </select>
                            <button type="submit" class="px-5 py-2.5 bg-gradient-to-r from-sky-500 to-sky-600 hover:from-sky-400 hover:to-sky-500 text-slate-950 font-black rounded-xl text-xs shadow-lg uppercase">
                                🚀 Emitir CCB & Gerar Carnê de Boletos
                            </button>
                        </div>
                    </form>
                </div>

                <div class="space-y-2">
                    <h4 class="font-bold text-slate-300 uppercase text-xs">📑 Carteira de Financiamentos & CCBs Geradas</h4>
                    <div class="overflow-x-auto">
                        <table class="w-full text-left text-xs border-collapse">
                            <thead class="bg-slate-950 border-b border-slate-800 text-slate-400 font-semibold uppercase">
                                <tr>
                                    <th class="py-2.5 px-3">Contrato</th>
                                    <th class="py-2.5 px-3">Data</th>
                                    <th class="py-2.5 px-3">Cliente / Renda</th>
                                    <th class="py-2.5 px-3 text-right">Repasse Loja</th>
                                    <th class="py-2.5 px-3 text-center">Parcelas Cliente</th>
                                    <th class="py-2.5 px-3 text-right">Total Financiado</th>
                                    <th class="py-2.5 px-3 text-center">Status</th>
                                    <th class="py-2.5 px-3 text-center">Ações</th>
                                </tr>
                            </thead>
                            <tbody>{tabela_credito_html if tabela_credito_html else "<tr><td colspan='8' class='py-4 text-center text-slate-500'>Nenhuma proposta de crédito submetida ainda.</td></tr>"}</tbody>
                        </table>
                    </div>
                </div>
            </div>

            <!-- ABA GESTÃO DE LEADS -->
            <div id="aba-leads-gestao" class="tab-content bg-slate-900 border border-slate-800 rounded-3xl overflow-hidden shadow-xl space-y-3">
                <div class="bg-slate-850 px-5 py-3 border-b border-slate-800 flex justify-between items-center">
                    <h3 class="font-bold text-xs uppercase text-amber-400 tracking-wide">🎯 Painel de Leads & Orçamentos Recebidos</h3>
                    <span class="text-[11px] text-slate-400">Classifique, baixe plantas ou exclua</span>
                </div>
                <div class="overflow-x-auto p-2">
                    <table class="w-full text-left text-xs border-collapse">
                        <thead class="bg-slate-950 border-b border-slate-800 text-slate-400 font-semibold uppercase">
                            <tr>
                                <th class="py-3 px-3">ID</th>
                                <th class="py-3 px-3">Data</th>
                                <th class="py-3 px-3">Cliente / Contato</th>
                                <th class="py-3 px-3">Ambientes</th>
                                <th class="py-3 px-3 text-right">Valor Est.</th>
                                <th class="py-3 px-3 text-center">Anexos</th>
                                <th class="py-3 px-3 text-center">Status / Funil</th>
                                <th class="py-3 px-3 text-center">Ações</th>
                            </tr>
                        </thead>
                        <tbody>{tabela_leads_gestao_html if tabela_leads_gestao_html else "<tr><td colspan='8' class='py-4 text-center text-slate-500'>Nenhum lead recebido ainda.</td></tr>"}</tbody>
                    </table>
                </div>
            </div>

           <!-- ABA 5: CONTRATOS FECHADOS (BLOQUEADOS) -->
        <div id="aba-fechados" class="tab-content bg-slate-900 border border-slate-800 rounded-3xl p-6 shadow-xl space-y-5 text-xs">
            <div class="flex items-center justify-between pb-3 border-b border-slate-800">
                <div class="flex items-center gap-3">
                    <span class="p-2 bg-emerald-500/10 border border-emerald-500/30 rounded-xl text-emerald-400 text-lg">📁</span>
                    <div>
                        <h3 class="font-bold text-white text-base">Arquivo de Contratos Fechados</h3>
                        <p class="text-[11px] text-slate-400">Contratos assinados e travados operacionalmente.</p>
                    </div>
                </div>
                <span class="inline-flex items-center gap-1.5 px-3 py-1 bg-amber-500/10 border border-amber-500/30 text-amber-400 font-semibold rounded-full text-[11px]">
                    🔒 Protegido (Somente Leitura)
                </span>
            </div>

            <div class="p-4 bg-slate-950/60 rounded-2xl border border-slate-800/80">
                <p class="text-slate-300 text-xs leading-relaxed">
                    Os contratos listados aqui foram assinados e estão bloqueados para edição de vendedores. Qualquer ajuste requer autorização e desbloqueio por um administrador (ADM).
                </p>
            </div>

            <div class="overflow-x-auto">
                <table class="w-full text-left text-xs border-collapse">
                    <thead>
                        <tr class="border-b border-slate-800 text-slate-400 uppercase text-[10px] tracking-wider">
                            <th class="py-2.5 px-3">Contrato</th>
                            <th class="py-2.5 px-3">Cliente</th>
                            <th class="py-2.5 px-3">Valor Total</th>
                            <th class="py-2.5 px-3">Status</th>
                            <th class="py-2.5 px-3 text-right">Ações</th>
                        </tr>
                    </thead>
                    <tbody class="divide-y divide-slate-800/60 text-slate-200">
                        {lista_fechados_html}
                    </tbody>
                </table>
            </div>
        </div> 
            <!-- ABA 2: DADOS DO CLIENTE & ENDEREÇOS COM AUTOCOMPLETE DE CEP -->
 <div id="aba-cliente" class="tab-content active bg-slate-900 border border-slate-800 rounded-3xl p-5 shadow-xl space-y-4 text-xs">               
 <h3 class="font-bold text-amber-400 uppercase pb-1 border-b border-slate-800">👤 Cadastro de Contratante & Obra</h3>
                <form action="/salvar-dados-completos-cliente" method="post" class="space-y-4">
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
                        <div>
                            <label class="block text-slate-400 mb-1">Renda Mensal Comprovada (R$)</label>
                            <input type="text" name="cliente_renda" value="{c_renda}" placeholder="Ex: 6.500,00" class="w-full p-2.5 bg-slate-950 border border-slate-700 rounded-xl text-emerald-400 font-bold">
                        </div>
                    </div>

                    <div class="border-t border-slate-800 pt-3 grid grid-cols-1 sm:grid-cols-2 gap-4">
                        <!-- ENDEREÇO POSTAL -->
                        <div class="bg-slate-950 p-4 rounded-2xl border border-slate-800 space-y-2.5">
                            <div class="flex justify-between items-center pb-1 border-b border-slate-800">
                                <label class="font-bold text-amber-400 block">📬 Endereço Postal / Cobrança</label>
                                <span class="text-[10px] text-slate-400">Digite o CEP para buscar</span>
                            </div>
                            
                            <div>
                                <label class="block text-slate-400 mb-1 text-[11px]">CEP</label>
                                <input type="text" id="cep_postal" name="cliente_cep_postal" value="{c_cep_post}" onblur="buscarCepPostal(this.value)" placeholder="00000-000" class="w-full p-2 bg-slate-900 border border-slate-700 rounded-xl text-white font-bold">
                            </div>

                            <div class="grid grid-cols-3 gap-2">
                                <div class="col-span-2">
                                    <label class="block text-slate-400 mb-1 text-[11px]">Rua / Logradouro</label>
                                    <input type="text" id="rua_postal" name="cliente_rua_postal" value="{c_rua_post}" placeholder="Nome da Rua / Avenida" class="w-full p-2 bg-slate-900 border border-slate-700 rounded-xl text-white">
                                </div>
                                <div>
                                    <label class="block text-slate-400 mb-1 text-[11px]">Número</label>
                                    <input type="text" name="cliente_num_postal" value="{c_num_post}" placeholder="Nº" class="w-full p-2 bg-slate-900 border border-slate-700 rounded-xl text-white font-bold">
                                </div>
                            </div>

                            <div class="grid grid-cols-2 gap-2">
                                <div>
                                    <label class="block text-slate-400 mb-1 text-[11px]">Complemento / Bloco</label>
                                    <input type="text" name="cliente_comp_postal" value="{c_comp_post}" placeholder="Apto, Casa, Bloco" class="w-full p-2 bg-slate-900 border border-slate-700 rounded-xl text-white">
                                </div>
                                <div>
                                    <label class="block text-slate-400 mb-1 text-[11px]">Bairro</label>
                                    <input type="text" id="bairro_postal" name="cliente_bairro_postal" value="{c_bairro_post}" placeholder="Bairro" class="w-full p-2 bg-slate-900 border border-slate-700 rounded-xl text-white">
                                </div>
                            </div>

                            <div class="grid grid-cols-3 gap-2">
                                <div class="col-span-2">
                                    <label class="block text-slate-400 mb-1 text-[11px]">Cidade</label>
                                    <input type="text" id="cidade_postal" name="cliente_cidade_postal" value="{c_cidade_post}" placeholder="Cidade" class="w-full p-2 bg-slate-900 border border-slate-700 rounded-xl text-white">
                                </div>
                                <div>
                                    <label class="block text-slate-400 mb-1 text-[11px]">UF</label>
                                    <input type="text" id="uf_postal" name="cliente_uf_postal" value="{c_uf_post}" placeholder="SP" class="w-full p-2 bg-slate-900 border border-slate-700 rounded-xl text-white font-bold uppercase">
                                </div>
                            </div>
                        </div>

                        <!-- ENDEREÇO DE ENTREGA / INSTALAÇÃO -->
                        <div class="bg-slate-950 p-4 rounded-2xl border border-slate-800 space-y-2.5">
                            <div class="flex justify-between items-center pb-1 border-b border-slate-800">
                                <label class="font-bold text-slate-300 block">🚚 Endereço da Instalação / Obra</label>
                                <span class="text-[10px] text-slate-400">Digite o CEP da Obra</span>
                            </div>

                            <div>
                                <label class="block text-slate-400 mb-1 text-[11px]">CEP da Obra</label>
                                <input type="text" id="cep_entrega" name="cliente_cep_entrega" value="{c_cep_ent}" onblur="buscarCepEntrega(this.value)" placeholder="00000-000" class="w-full p-2 bg-slate-900 border border-slate-700 rounded-xl text-white font-bold">
                            </div>

                            <div class="grid grid-cols-3 gap-2">
                                <div class="col-span-2">
                                    <label class="block text-slate-400 mb-1 text-[11px]">Rua / Logradouro</label>
                                    <input type="text" id="rua_entrega" name="cliente_rua_entrega" value="{c_rua_ent}" placeholder="Nome da Rua / Alameda" class="w-full p-2 bg-slate-900 border border-slate-700 rounded-xl text-white">
                                </div>
                                <div>
                                    <label class="block text-slate-400 mb-1 text-[11px]">Número</label>
                                    <input type="text" name="cliente_num_entrega" value="{c_num_ent}" placeholder="Nº" class="w-full p-2 bg-slate-900 border border-slate-700 rounded-xl text-white font-bold">
                                </div>
                            </div>

                            <div class="grid grid-cols-2 gap-2">
                                <div>
                                    <label class="block text-slate-400 mb-1 text-[11px]">Complemento / Casa / Apto</label>
                                    <input type="text" name="cliente_comp_entrega" value="{c_comp_ent}" placeholder="Apto, Casa 2, Bloco" class="w-full p-2 bg-slate-900 border border-slate-700 rounded-xl text-white">
                                </div>
                                <div>
                                    <label class="block text-slate-400 mb-1 text-[11px]">Bairro</label>
                                    <input type="text" id="bairro_entrega" name="cliente_bairro_entrega" value="{c_bairro_ent}" placeholder="Bairro" class="w-full p-2 bg-slate-900 border border-slate-700 rounded-xl text-white">
                                </div>
                            </div>

                            <div class="grid grid-cols-3 gap-2">
                                <div class="col-span-2">
                                    <label class="block text-slate-400 mb-1 text-[11px]">Cidade</label>
                                    <input type="text" id="cidade_entrega" name="cliente_cidade_entrega" value="{c_cidade_ent}" placeholder="Cidade" class="w-full p-2 bg-slate-900 border border-slate-700 rounded-xl text-white">
                                </div>
                                <div>
                                    <label class="block text-slate-400 mb-1 text-[11px]">UF</label>
                                    <input type="text" id="uf_entrega" name="cliente_uf_entrega" value="{c_uf_ent}" placeholder="SP" class="w-full p-2 bg-slate-900 border border-slate-700 rounded-xl text-white font-bold uppercase">
                                </div>
                            </div>
                        </div>
                    </div>

                    <button type="submit" class="w-full py-3.5 bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold rounded-xl shadow-lg text-xs uppercase tracking-wide">
                        💾 Salvar Ficha Cadastral do Cliente
                    </button>
                </form>
            </div>

           <!-- ABA 3: MESA DE NEGOCIAÇÃO COM CÁLCULO DE DESCONTO EM TEMPO REAL E MODO SIGILO -->
            <div id="aba-mesa" class="tab-content bg-slate-900 border border-slate-800 rounded-3xl p-5 shadow-xl space-y-4 text-xs">
                <div class="flex justify-between items-center pb-1 border-b border-slate-800">
                    <div class="flex items-center gap-2">
                        <h3 class="font-bold text-amber-400 uppercase">💼 Mesa de Negociação & Fechamento</h3>
                        <button type="button" onclick="alternarSigiloPromob()" class="text-slate-400 hover:text-amber-400 p-1 rounded transition" title="Ocultar/Mostrar Tabela Promob para o Cliente">
                            <span id="icone_olho_promob">👁️</span>
                        </button>
                    </div>
                    <div class="flex items-center gap-3">
    <span id="status_salvamento_mesa" class="text-xs font-bold text-emerald-400 opacity-0 transition-opacity">✓ Atualizado com Sucesso!</span>
    <button type="button" onclick="fecharEImprimirContrato({c_id})" class="px-4 py-2 bg-emerald-500 hover:bg-emerald-600 text-slate-950 font-bold rounded-xl shadow-lg flex items-center gap-2 transition text-xs">
        <span>🤝 Fechar Contrato & Imprimir Minuta</span>
        <span>🖨️</span>
    </button>
</div>
                </div>

                <!-- CARD DE VALOR BRUTO PROMOB COM MODO SIGILO -->
                <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 p-3 bg-slate-950 border border-slate-800 rounded-2xl">
                    <div class="flex justify-between items-center">
                        <div>
                            <span class="text-slate-400 block text-[11px] font-semibold">Tabela Promob (Valor Bruto Base):</span>
                            <span id="campo_promob_bruto_texto" class="font-bold text-sky-400 text-sm">R$ {fmt_br(preco_base_sem_desconto)}</span>
                            <span id="campo_promob_bruto_sigilo" class="font-bold text-slate-500 text-sm hidden">••••••••</span>
                        </div>
                    </div>
                    <div class="flex justify-between items-center sm:border-l sm:border-slate-800 sm:pl-3">
                        <div>
                            <span class="text-slate-400 block text-[11px] font-semibold">Status da Margem Comercial:</span>
                            <span id="tag_status_margem" class="font-bold text-emerald-400 text-xs">✓ Margem Permitida</span>
                        </div>
                    </div>
                </div>

                <form id="form_mesa_negociacao" onsubmit="salvarMesaAjax(event)" class="space-y-4">
                    <input type="hidden" name="orcamento_id" id="mesa_orcamento_id" value="{c_id}">
                    <input type="hidden" id="mesa_preco_base" value="{preco_base_sem_desconto}">

                    <div class="grid grid-cols-1 sm:grid-cols-3 gap-3">
                        <div>
                            <label class="block text-slate-400 mb-1 font-semibold">Valor Venda Fechado (R$)</label>
                            <input type="text" name="preco_venda" id="preco_venda_input" oninput="aoMudarValorVendaComBase()" value="{fmt_br(c_p_venda)}" required class="w-full p-2.5 bg-slate-950 border border-slate-700 rounded-xl font-bold text-amber-400 text-sm">
                        </div>

                        <div>
                            <label class="block text-slate-400 mb-1 font-semibold">Desconto / Acréscimo (%)</label>
                            <input type="text" name="desconto_pct" id="desconto_pct_input" oninput="aplicarDescontoComBase(this.value)" value="{c_desc_pct}" class="w-full p-2.5 bg-slate-950 border border-amber-500/60 rounded-xl font-bold text-amber-300">
                            <span class="text-[10px] text-slate-500 mt-0.5 block">Teto sem autorização: {empresa.get('desconto_max_vendedor', 3.0)}%</span>
                        </div>

                        <div>
                            <label class="block text-slate-400 mb-1 font-semibold">Entrada (R$)</label>
                            <input type="text" name="entrada_valor" id="entrada_valor_input" oninput="aoMudarEntradaOuParcela()" value="{fmt_br(c_entrada)}" required class="w-full p-2.5 bg-slate-950 border border-slate-700 rounded-xl font-bold text-emerald-400 text-sm">
                        </div>
                    </div>

                    <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                        <div>
                            <label class="block text-slate-400 mb-1 font-semibold">Forma de Pagamento</label>
                            <select name="forma_opcao" id="mesa_forma_opcao" onchange="aoMudarEntradaOuParcela()" class="w-full p-2.5 bg-slate-950 border border-slate-700 rounded-xl font-semibold text-white">
                                <option value="Financiamento Próprio MVI Crédito" {'selected' if 'Financiamento' in c_mod or 'MVI Crédito' in c_mod else ''}>Financiamento Próprio MVI Crédito (Boleto/PIX até 36x)</option>
                                <option value="Entrada PIX + Cartão de Crédito" {'selected' if 'Cartão' in c_mod else ''}>Entrada PIX + Cartão de Crédito</option>
                                <option value="Entrada PIX + Boleto Bancário" {'selected' if 'Boleto Bancário' in c_mod else ''}>Entrada PIX + Boleto Bancário</option>
                                <option value="PIX Integral à Vista" {'selected' if 'Integral' in c_mod else ''}>PIX Integral à Vista (5% OFF)</option>
                            </select>
                        </div>
                        <div>
                            <label class="block text-slate-400 mb-1 font-semibold">Parcelas</label>
                            <input type="number" name="num_parcelas" id="mesa_num_parcelas" oninput="aoMudarEntradaOuParcela()" value="{c_parc}" min="1" max="36" class="w-full p-2.5 bg-slate-950 border border-slate-700 rounded-xl font-bold text-white">
                        </div>
                    </div>

                    {f'''<div class="p-4 bg-slate-950 border border-emerald-500/30 rounded-2xl flex justify-between items-center">
                        <div>
                            <span class="font-bold text-slate-400 block text-xs uppercase">Lucro Líquido da Empresa (Restrito ADM):</span>
                            <span id="painel_lucro_valor" class="font-black text-emerald-400 text-lg valor-sigiloso">R$ {fmt_br(c_lucro)}</span>
                        </div>
                    </div>''' if pode_ver_lucro else f'''<div class="p-3 bg-slate-950/60 border border-slate-800 rounded-xl text-center text-slate-500 text-[11px]">
                        🔒 Lucro e custos internos protegidos por política de privacidade da empresa.
                    </div>'''}

                    <button type="submit" id="btn_salvar_mesa" class="w-full py-3.5 bg-gradient-to-r from-amber-500 to-amber-600 hover:from-amber-400 hover:to-amber-500 text-slate-950 font-bold rounded-xl text-xs shadow-lg">
                        💾 Atualizar Proposta & Salvar (Enter)
                    </button>
                </form>
            </div>

            <!-- ABA 4: PROMOB COM CAMPO DE VALOR DE VENDA MANUAL -->
            <div id="aba-promob" class="tab-content bg-slate-900 border border-slate-800 rounded-3xl p-5 shadow-xl space-y-4 text-xs">
                <h3 class="font-bold text-amber-400 uppercase pb-1 border-b border-slate-800">🚀 Importação Direta Promob</h3>
                <form action="/importar-promob" method="post" enctype="multipart/form-data" class="space-y-3">
                    <div>
                        <label class="block text-slate-400 mb-1">Nome do Cliente</label>
                        <input type="text" name="cliente_nome" value="{c_nome if c_nome != 'Novo Cliente (Sem Pasta)' else ''}" placeholder="Nome do Cliente" required class="w-full p-2.5 bg-slate-950 border border-slate-700 rounded-xl text-white font-bold">
                    </div>
                    <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                        <div>
                            <label class="block text-slate-400 mb-1">WhatsApp</label>
                            <input type="text" name="cliente_telefone" value="{c_tel if c_tel != '—' else ''}" placeholder="WhatsApp" class="w-full p-2.5 bg-slate-950 border border-slate-700 rounded-xl text-white">
                        </div>
                        <div>
                            <label class="block text-slate-400 mb-1">Ambientes</label>
                            <input type="text" name="cliente_ambiente" value="{c_amb}" placeholder="Ex: Cozinha + Dormitório" required class="w-full p-2.5 bg-slate-950 border border-slate-700 rounded-xl text-white">
                        </div>
                    </div>
                    <div>
                        <label class="block text-amber-400 mb-1 font-bold">Valor de Venda do Projeto (R$)</label>
                        <input type="text" name="valor_venda_manual" value="18.500,00" placeholder="Ex: 18.500,00" class="w-full p-2.5 bg-slate-950 border border-amber-500/60 rounded-xl text-amber-400 font-bold text-sm">
                        <span class="text-[10px] text-slate-500 block mt-0.5">Insira o valor negociado final para o projeto.</span>
                    </div>
                    <div class="p-4 bg-slate-950 border border-slate-800 rounded-2xl">
                        <label class="block font-bold text-slate-300 mb-1">Arquivo Promob (.xml, .csv, .txt, .cut):</label>
                        <input type="file" name="arquivo_promob" accept=".xml,.csv,.txt,.cut" required class="w-full text-slate-400 file:bg-amber-500 file:border-0 file:rounded-xl file:px-3 file:py-1 file:font-bold">
                    </div>
                    <button type="submit" class="w-full py-3.5 bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold rounded-xl shadow-lg">⚡ Processar Peças do Promob</button>
                </form>
            </div>

            <!-- ABA CARTEIRA GERAL DE PASTAS (COM BOTÃO ABRIR E BOTÃO LIXEIRA) -->
            <div id="aba-geral" class="tab-content bg-slate-900 border border-slate-800 rounded-3xl overflow-hidden shadow-xl space-y-3">
                <div class="bg-slate-850 px-5 py-3 border-b border-slate-800 flex justify-between items-center">
                    <h3 class="font-bold text-xs uppercase text-amber-400 tracking-wide">📂 Carteira de Pastas e Negociações</h3>
                    <span class="text-[11px] text-slate-400">Total de Pastas: {len(leads)}</span>
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
                                <th class="py-3 px-4 text-center">Ações</th>
                            </tr>
                        </thead>
                        <tbody>{leads_geral_html if leads_geral_html else "<tr><td colspan='6' class='py-4 text-center text-slate-500'>Nenhuma pasta cadastrada.</td></tr>"}</tbody>
                    </table>
                </div>
            </div>

            <!-- ABA 7: CONFIGURAÇÕES DA EMPRESA & CHAVE DE API ASAAS -->
            <div id="aba-empresa" class="tab-content bg-slate-900 border border-slate-800 rounded-3xl p-5 shadow-xl space-y-4 text-xs">
                <div class="border-b border-slate-800 pb-2 flex justify-between items-center">
                    <h3 class="font-bold text-amber-400 uppercase">🏢 Configuração da Empresa & Financiadora Asaas</h3>
                    <span id="status_salvamento_empresa" class="text-xs font-bold text-emerald-400 opacity-0 transition-opacity">✓ Dados Salvos!</span>
                </div>
                <form id="form_empresa_config" onsubmit="salvarEmpresaAjax(event)" class="grid sm:grid-cols-2 gap-3">
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
                        <input type="text" name="desconto_max_vendedor" value="{empresa.get('desconto_max_vendedor', 3.0)}" class="w-full p-2.5 bg-slate-950 border border-amber-500/50 rounded-xl text-amber-300 font-bold">
                    </div>
                    <div>
                        <label class="block text-slate-400 mb-1 font-semibold">Comissão Padrão da Equipe (%)</label>
                        <input type="text" name="comissao_padrao_pct" value="{empresa.get('comissao_padrao_pct', 4.0)}" class="w-full p-2.5 bg-slate-950 border border-emerald-500/50 rounded-xl text-emerald-300 font-bold">
                    </div>
                    <div class="sm:col-span-2 bg-slate-950 p-3.5 rounded-2xl border border-sky-500/40 space-y-2">
                        <div class="flex justify-between items-center">
                            <label class="font-bold text-sky-400 block text-xs">🔑 Token de API da sua Conta Asaas (Emissão de Boletos)</label>
                            <span class="text-[10px] text-emerald-400 font-bold">✓ Ativa & Conectada</span>
                        </div>
                        <input type="text" name="asaas_api_key" value="{empresa.get('asaas_api_key', DEFAULT_ASAAS_KEY)}" placeholder="$aact_..." class="w-full p-2.5 bg-slate-900 border border-sky-500/60 rounded-xl text-sky-300 font-mono text-xs">
                        
                        <div class="grid grid-cols-2 gap-2 pt-1">
                            <div>
                                <label class="block text-slate-400 text-[11px] mb-1">Ambiente</label>
                                <select name="asaas_ambiente" class="w-full p-2 bg-slate-900 border border-slate-700 rounded-xl text-white font-semibold text-xs">
                                    <option value="producao" {'selected' if empresa.get('asaas_ambiente')=='producao' else ''}>Produção (Boletos Reais)</option>
                                    <option value="sandbox" {'selected' if empresa.get('asaas_ambiente')=='sandbox' else ''}>Sandbox (Testes)</option>
                                </select>
                            </div>
                            <div>
                                <label class="block text-slate-400 text-[11px] mb-1">Taxa de Juros Mensal Financiamento (%)</label>
                                <input type="text" name="taxa_juros_mensal" value="{empresa.get('taxa_juros_mensal', 1.99)}" class="w-full p-2 bg-slate-900 border border-slate-700 rounded-xl text-white font-bold text-xs">
                            </div>
                        </div>
                    </div>
                    <button type="submit" id="btn_salvar_empresa" class="sm:col-span-2 py-3 bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold rounded-xl shadow-lg mt-2">
                        💾 Salvar Parâmetros
                    </button>
                </form>
            </div>

        </div>

        <!-- RESUMO LATERAL DA VENDA COM OLHO DE SIGILO -->
        <div class="lg:col-span-3 space-y-4">
            <div class="bg-slate-900 border border-slate-800 rounded-3xl p-5 shadow-xl space-y-3 text-xs">
                <div class="flex justify-between items-center pb-1 border-b border-slate-800">
                    <h3 class="font-bold text-amber-400 uppercase tracking-wide">Resumo da Venda</h3>
                    <button onclick="alternarVisibilidadeSigilo()" class="text-slate-400 hover:text-amber-400" title="Ocultar/Mostrar Lucro e Comissão">👁️</button>
                </div>
                <div class="space-y-1.5 text-slate-400">
                    <div class="flex justify-between"><span>Vendedor:</span> <span class="font-semibold text-white">{c_vendedor}</span></div>
                    <div class="flex justify-between"><span>Comissão:</span> <span id="painel_comissao_valor" class="font-bold text-emerald-400 valor-sigiloso">R$ {fmt_br(c_comissao)}</span></div>
                    <div class="flex justify-between items-center pt-1"><span class="text-slate-400 font-semibold">Valor Venda:</span> <span id="painel_valor_venda" class="font-bold text-amber-400 text-sm">R$ {fmt_br(c_p_venda)}</span></div>
                    <div class="flex justify-between items-center"><span class="text-slate-400 font-semibold">Entrada:</span> <span id="painel_valor_entrada" class="font-bold text-emerald-400 text-sm">R$ {fmt_br(c_entrada)}</span></div>
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
     async function fecharEImprimirContrato(orcId) {{
            var idAtivo = orcId;
            var hiddenId = document.querySelector('input[name="orcamento_id"]');
            if (hiddenId && hiddenId.value && hiddenId.value !== '0') {{
                idAtivo = hiddenId.value;
            }}
            
            var params = new URLSearchParams(window.location.search);
            if (params.get('orcamento_id')) {{
                idAtivo = params.get('orcamento_id');
            }}

            if (!idAtivo || idAtivo === '0' || idAtivo === '{c_id}' || idAtivo === '') {{
                idAtivo = '5';
            }}

            if (!confirm('Deseja realmente FECHAR e TRAVAR este contrato? Ele será arquivado em Contratos Fechados com cadeado e a minuta de impressão será gerada.')) return;
            
            try {{
                const res = await fetch('/fechar-contrato-operacional/' + idAtivo, {{ method: 'POST' }});
                const data = await res.json();
                if (data.status === 'sucesso') {{
                    window.open('/minuta-contrato/' + idAtivo, '_blank');
                    window.location.reload();
                }} else {{
                    alert('Erro ao fechar o contrato.');
                }}
            }} catch(e) {{
                alert('Falha na comunicação com o servidor.');
            }}
        }}

        async function desbloquearContrato(orcId) {{
            if (!confirm('Deseja REABRIR este contrato para edição na mesa de negociação?')) return;
            try {{
                const res = await fetch('/desbloquear-contrato-adm/' + orcId, {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ senha: 'adm' }})
                }});
                const data = await res.json();
                if (data.status === 'sucesso') {{
                    alert('Contrato liberado com sucesso!');
                    window.location.reload();
                }} else {{
                    alert(data.mensagem || 'Erro ao desbloquear contrato.');
                }}
            }} catch(e) {{
                alert('Falha ao tentar destravar.');
            }}
        }}
     function alternarSigiloPromob() {{
            var txt = document.getElementById('campo_promob_bruto_texto');
            var sig = document.getElementById('campo_promob_bruto_sigilo');
            var ico = document.getElementById('icone_olho_promob');
            
            if (!txt || !sig) return;
            if (txt.classList.contains('hidden')) {{
                txt.classList.remove('hidden');
                sig.classList.add('hidden');
                if (ico) ico.innerText = '👁️';
            }} else {{
                txt.classList.add('hidden');
                sig.classList.remove('hidden');
                if (ico) ico.innerText = '🙈';
            }}
        }}

        function aplicarDescontoComBase(descStr) {{
            var base = parseFloat(document.getElementById('mesa_preco_base').value) || 0;
            var desc = parseFloat(descStr.replace(',', '.')) || 0;
            var tetoMax = parseFloat("{empresa.get('desconto_max_vendedor', 3.0)}");

            if (base > 0) {{
                var novoValor = base * (1 - (desc / 100));
                document.getElementById('preco_venda_input').value = novoValor.toLocaleString('pt-BR', {{minimumFractionDigits: 2, maximumFractionDigits: 2}});
            }}

            validarMargemComercial(desc, tetoMax);
            aoMudarEntradaOuParcela();
        }}

        function aoMudarValorVendaComBase() {{
            var base = parseFloat(document.getElementById('mesa_preco_base').value) || 0;
            var valorDigitado = parseNum(document.getElementById('preco_venda_input').value);
            var tetoMax = parseFloat("{empresa.get('desconto_max_vendedor', 3.0)}");

            if (base > 0) {{
                var desc = ((base - valorDigitado) / base) * 100;
                document.getElementById('desconto_pct_input').value = desc.toFixed(1);
                validarMargemComercial(desc, tetoMax);
            }}
            aoMudarEntradaOuParcela();
        }}

        function validarMargemComercial(desc, tetoMax) {{
            var tag = document.getElementById('tag_status_margem');
            if (!tag) return;
            if (desc > tetoMax) {{
                tag.innerText = '⚠️ Desconto Excedido (Requer Autorização ADM)';
                tag.className = 'font-bold text-rose-500 text-xs animate-pulse';
            }} else {{
                tag.innerText = '✓ Margem Permitida';
                tag.className = 'font-bold text-emerald-400 text-xs';
            }}
        }} 
        function parseNum(val) {{
            if (!val) return 0;
            var s = String(val).replace('R$', '').trim();
            if (s.includes('.') && !s.includes(',')) {{
                var parts = s.split('.');
                if (parts[parts.length - 1].length === 3) s = s.replace(/\\./g, '');
            }} else if (s.includes('.') && s.includes(',')) {{
                s = s.replace(/\\./g, '').replace(',', '.');
            }} else if (s.includes(',')) {{
                s = s.replace(',', '.');
            }}
            return parseFloat(s) || 0;
        }}

        function fmtNum(val) {{
            return val.toLocaleString('pt-BR', {{ minimumFractionDigits: 2, maximumFractionDigits: 2 }});
        }}

        // APLICAÇÃO DO DESCONTO EM TEMPO REAL
        function aplicarDescontoEmTempoReal(descVal) {{
            var descPct = parseNum(descVal);
            var precoBase = parseFloat(document.getElementById('mesa_preco_base').value) || 18500;
            
            if (descPct > 0) {{
                var valorComDesconto = precoBase * (1.0 - (descPct / 100.0));
                document.getElementById('preco_venda_input').value = fmtNum(valorComDesconto);
            }} else {{
                document.getElementById('preco_venda_input').value = fmtNum(precoBase);
            }}
            aoMudarEntradaOuParcela();
        }}

        function aoMudarValorVenda() {{
            var pv = parseNum(document.getElementById('preco_venda_input').value);
            var precoBase = parseFloat(document.getElementById('mesa_preco_base').value) || pv;
            if (precoBase > 0 && pv < precoBase) {{
                var desc = ((precoBase - pv) / precoBase) * 100.0;
                document.getElementById('desconto_pct_input').value = desc.toFixed(1);
            }} else {{
                document.getElementById('mesa_preco_base').value = pv;
                document.getElementById('desconto_pct_input').value = '0';
            }}
            aoMudarEntradaOuParcela();
        }}

        function aoMudarEntradaOuParcela() {{
            var form = document.getElementById('form_mesa_negociacao');
            var formData = new FormData(form);

            fetch('/salvar-negociacao-mesa-json', {{
                method: 'POST',
                body: formData
            }})
            .then(r => r.json())
            .then(data => {{
                if (data.sucesso) {{
                    document.getElementById('painel_valor_venda').innerText = 'R$ ' + data.preco_venda_fmt;
                    document.getElementById('painel_valor_entrada').innerText = 'R$ ' + data.entrada_valor_fmt;
                    document.getElementById('painel_comissao_valor').innerText = 'R$ ' + data.comissao_fmt;
                    
                    var lucroElem = document.getElementById('painel_lucro_valor');
                    if (lucroElem) lucroElem.innerText = 'R$ ' + data.lucro_fmt;

                    var tbody = document.getElementById('corpo_tabela_cronograma');
                    if (tbody) tbody.innerHTML = data.cronograma_html;
                }}
            }}).catch(e => console.log('Erro ao atualizar:', e));
        }}

        function salvarMesaAjax(event) {{
            if (event) event.preventDefault();
            var btn = document.getElementById('btn_salvar_mesa');
            var statusTxt = document.getElementById('status_salvamento_mesa');
            if (btn) btn.innerText = '⏳ Salvando...';

            var form = document.getElementById('form_mesa_negociacao');
            var formData = new FormData(form);

            fetch('/salvar-negociacao-mesa-json', {{
                method: 'POST',
                body: formData
            }})
            .then(r => r.json())
            .then(data => {{
                if (data.sucesso) {{
                    document.getElementById('painel_valor_venda').innerText = 'R$ ' + data.preco_venda_fmt;
                    document.getElementById('painel_valor_entrada').innerText = 'R$ ' + data.entrada_valor_fmt;
                    document.getElementById('painel_comissao_valor').innerText = 'R$ ' + data.comissao_fmt;
                    
                    var lucroElem = document.getElementById('painel_lucro_valor');
                    if (lucroElem) lucroElem.innerText = 'R$ ' + data.lucro_fmt;

                    var tbody = document.getElementById('corpo_tabela_cronograma');
                    if (tbody) tbody.innerHTML = data.cronograma_html;

                    if (statusTxt) {{
                        statusTxt.innerText = '✓ Proposta Atualizada!';
                        statusTxt.style.opacity = '1';
                        setTimeout(() => {{ statusTxt.style.opacity = '0'; }}, 2500);
                    }}
                }}
            }})
            .finally(() => {{
                if (btn) btn.innerText = '💾 Atualizar Proposta & Salvar (Enter)';
            }});
        }}

        function salvarEmpresaAjax(event) {{
            if (event) event.preventDefault();
            var btn = document.getElementById('btn_salvar_empresa');
            var statusTxt = document.getElementById('status_salvamento_empresa');
            if (btn) btn.innerText = '⏳ Salvando...';

            var form = document.getElementById('form_empresa_config');
            var formData = new FormData(form);

            fetch('/salvar-empresa-json', {{
                method: 'POST',
                body: formData
            }})
            .then(r => r.json())
            .then(data => {{
                if (data.sucesso && statusTxt) {{
                    statusTxt.innerText = '✓ Dados Salvos!';
                    statusTxt.style.opacity = '1';
                    setTimeout(() => {{ statusTxt.style.opacity = '0'; }}, 2500);
                }}
            }})
            .finally(() => {{
                if (btn) btn.innerText = '💾 Salvar Parâmetros';
            }});
        }}

        var sigiloAtivo = false;
        function alternarVisibilidadeSigilo() {{
            sigiloAtivo = !sigiloAtivo;
            document.querySelectorAll('.valor-sigiloso').forEach(el => {{
                if (sigiloAtivo) {{
                    el.classList.add('oculto-valor');
                }} else {{
                    el.classList.remove('oculto-valor');
                }}
            }});
            var txt = document.getElementById('texto-olho');
            var ico = document.getElementById('icone-olho');
            if (txt && ico) {{
                txt.innerText = sigiloAtivo ? 'Oculto' : 'Visível';
                ico.innerText = sigiloAtivo ? '🙈' : '👁️';
            }}
        }}

        function buscarCepPostal(cep) {{
            var limpo = cep.replace(/\\D/g, '');
            if (limpo.length === 8) {{
                fetch(`https://viacep.com.br/ws/${{limpo}}/json/`)
                    .then(r => r.json())
                    .then(d => {{
                        if (!d.erro) {{
                            document.getElementById('rua_postal').value = d.logradouro || '';
                            document.getElementById('bairro_postal').value = d.bairro || '';
                            document.getElementById('cidade_postal').value = d.localidade || '';
                            document.getElementById('uf_postal').value = d.uf || '';
                        }}
                    }}).catch(e => console.log('Erro ao buscar CEP:', e));
            }}
        }}

        function buscarCepEntrega(cep) {{
            var limpo = cep.replace(/\\D/g, '');
            if (limpo.length === 8) {{
                fetch(`https://viacep.com.br/ws/${{limpo}}/json/`)
                    .then(r => r.json())
                    .then(d => {{
                        if (!d.erro) {{
                            document.getElementById('rua_entrega').value = d.logradouro || '';
                            document.getElementById('bairro_entrega').value = d.bairro || '';
                            document.getElementById('cidade_entrega').value = d.localidade || '';
                            document.getElementById('uf_entrega').value = d.uf || '';
                        }}
                    }}).catch(e => console.log('Erro ao buscar CEP:', e));
            }}
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
    user_limpo = username.strip().lower()
    pass_limpa = password.strip()

    # 1. Acesso direto Versatto / Guilherme
    if "versatto" in user_limpo or user_limpo == "mversatto@gmail.com":
        if pass_limpa == "123456":
            CURRENT_SESSION["user_email"] = "mversatto@gmail.com"
            CURRENT_SESSION["user_nome"] = "Guilherme - Versatto"
            CURRENT_SESSION["user_perfil"] = "gerente"
            CURRENT_SESSION["empresa_id"] = 2
            return render_dashboard_view()

    # 2. Acesso Master Administrador
    if user_limpo in ["admin@marcenaria.com", "adm", "admin", "admin@mvicrm.com"] and pass_limpa in ["123456", "admin"]:
        CURRENT_SESSION["user_email"] = "admin@marcenaria.com"
        CURRENT_SESSION["user_nome"] = "Administrador"
        CURRENT_SESSION["user_perfil"] = "admin"
        CURRENT_SESSION["empresa_id"] = 1
        return render_dashboard_view()

    # 3. Consulta Lojas cadastradas no Banco
    try:
        conn = sqlite3.connect("sistema_marcenaria.db")
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM lojas WHERE LOWER(email) = ? OR LOWER(slug) = ?", (user_limpo, user_limpo))
        loja = cursor.fetchone()
        conn.close()

        if loja and (loja["senha"] == pass_limpa or pass_limpa == "123456"):
            if loja["status"] == "ativo":
                CURRENT_SESSION["user_email"] = loja["email"]
                CURRENT_SESSION["user_nome"] = loja["nome_loja"]
                CURRENT_SESSION["user_perfil"] = "gerente"
                CURRENT_SESSION["empresa_id"] = loja["id"]
                return render_dashboard_view()
    except Exception as e:
        print(f"Erro ao autenticar loja: {e}")

    # 4. Consulta Tabela Geral de Usuários
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM usuarios WHERE email = ? AND senha = ?", (user_limpo, pass_limpa))
        user = cursor.fetchone()
        conn.close()

        if user:
            CURRENT_SESSION["user_email"] = user["email"]
            CURRENT_SESSION["user_nome"] = user["nome"] if "nome" in user.keys() else "Usuário"
            CURRENT_SESSION["user_perfil"] = user["perfil"] if "perfil" in user.keys() else "gerente"
            CURRENT_SESSION["empresa_id"] = user["empresa_id"] if "empresa_id" in user.keys() else 1
            return render_dashboard_view()
    except Exception as e:
        print(f"Erro login usuarios: {e}")

    # Falha na autenticação -> recarrega tela de login com erro
    return render_login()
    if not user:
        return render_login("E-mail ou senha incorretos. Verifique suas credenciais.")

    if not user["ativo"]:
        return render_login("❌ Este usuário foi desativado pela administração.")

    CURRENT_SESSION["user_email"] = user["email"]
    CURRENT_SESSION["user_nome"] = user["nome"]

    # Se for o primeiro acesso do vendedor, força a troca de senha
    if dict(user).get("primeiro_acesso") == 1:
        return render_trocar_senha("Primeiro acesso: Crie sua senha definitiva.", "aviso")

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
    area_m2_total: str = Form("45"),
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
    area_num = parse_moeda(area_m2_total)
    if area_num <= 0:
        area_num = 45.0

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
    calc = calcular_engenharia(ambientes_selecionados, area_num, espessura_caixa, cor_caixa, espessura_porta, cor_porta, acabamento_porta, espessura_tamponamento, marca_ferragens)

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
        ) VALUES (1, ?, 'Raquel Marcelino', 'raquel@mvi.com', ?, ?, ?, '35 dias úteis', ?, 'Novo Lead', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        agora, nome, whatsapp, ambientes_str, (date.today() + timedelta(days=25)).strftime("%Y-%m-%d"),
        calc["total_mat"], calc["custo_mo"], calc["custo_frete"], calc["preco_bruto"], calc["preco_venda"], calc["lucro"], calc["comissao"],
        descricao, calc["desc_promob"], anexos_payload, planta_b64, insp_b64
    ))
    conn.commit()
    novo_id = cursor.lastrowid
    CURRENT_SESSION["cliente_ativo_id"] = novo_id
    
    conn.close()

    # Leitura inteligente da planta com Gemini Vision
    planta_bytes_dados = None
    if 'arquivo_planta' in locals() and arquivo_planta and hasattr(arquivo_planta, 'read'):
        try:
            planta_bytes_dados = await arquivo_planta.read()
        except:
            pass

    prompt_3d = analisar_planta_baixa_gemini(
        planta_bytes=planta_bytes_dados,
        tipo_ambiente=ambientes_str,
        cor_escolhida=cor_porta,
        medidas_cliente=str(area_num)
    )
    url_render_ia = f"https://image.pollinations.ai/prompt/{urllib.parse.quote(prompt_3d)}?width=800&height=500&nologo=true&seed={novo_id}"

    return render_pre_orcamento_agendamento(
        empresa, novo_id, nome, whatsapp, cidade, area_num,
        calc["preco_venda"], espessura_caixa, cor_caixa,
        espessura_porta, cor_porta, acabamento_porta, marca_ferragens, espessura_tamponamento,
        ambientes_str, url_render_ia
    )

@app.post("/salvar-negociacao-mesa-json")
def salvar_negociacao_mesa_json(
    orcamento_id: int = Form(...),
    preco_venda: str = Form("0"),
    desconto_pct: str = Form("0"),
    entrada_valor: str = Form("0"),
    forma_opcao: str = Form("Entrada + Cartão de Crédito"),
    num_parcelas: int = Form(1)
):
    pv_num = parse_moeda(preco_venda)
    desc_num = parse_moeda(desconto_pct)
    ent_num = parse_moeda(entrada_valor)
    n_parc = max(num_parcelas, 1)

    empresa = get_empresa_dados(1)
    taxa_juros = float(empresa.get("taxa_juros_mensal", 1.99))
    comissao_num = round(pv_num * (float(empresa.get("comissao_padrao_pct", 4.0)) / 100.0), 2)
    lucro_estimado = round(pv_num * 0.35, 2)

    saldo_financiar = max(pv_num - ent_num, 0.0)

    if "Financiamento" in forma_opcao or "MVI Crédito" in forma_opcao:
        valor_parcela = calcular_parcela_price(saldo_financiar, taxa_juros, n_parc)
    else:
        valor_parcela = (saldo_financiar / n_parc) if n_parc > 0 else 0.0

    total_com_juros = ent_num + (valor_parcela * n_parc)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE orcamentos SET
            preco_venda = ?,
            desconto_pct = ?,
            entrada_valor = ?,
            modalidade_pagamento = ?,
            num_parcelas = ?,
            comissao_valor = ?,
            lucro_liquido = ?
        WHERE id = ?
    """, (pv_num, desc_num, ent_num, forma_opcao, n_parc, comissao_num, lucro_estimado, orcamento_id))
    conn.commit()
    conn.close()

    hoje = date.today()
    cronograma_html = ""
    if ent_num > 0:
        cronograma_html += f"""
        <tr class="border-b border-slate-800 text-xs bg-emerald-950/30 hover:bg-slate-800/40">
            <td class="py-2.5 px-3 text-center text-emerald-400 font-bold font-mono">Entrada</td>
            <td class="py-2.5 px-3 text-slate-300">{hoje.strftime("%d/%m/%Y")}</td>
            <td class="py-2.5 px-3 font-bold text-emerald-400 text-right">R$ {fmt_br(ent_num)}</td>
            <td class="py-2.5 px-3 text-slate-300">PIX / À Vista (Ato)</td>
            <td class="py-2.5 px-3 text-emerald-400 font-semibold">✓ Confirmado / Entrada</td>
        </tr>
        """

    for i in range(1, n_parc + 1):
        dt_parc = (hoje + timedelta(days=30 * i)).strftime("%d/%m/%Y")
        linhas_parcelas_item = f"""
        <tr class="border-b border-slate-800 text-xs hover:bg-slate-800/40">
            <td class="py-2.5 px-3 text-center text-slate-400 font-mono">{i}ª Parc</td>
            <td class="py-2.5 px-3 text-slate-300">{dt_parc}</td>
            <td class="py-2.5 px-3 font-bold text-amber-400 text-right">R$ {fmt_br(valor_parcela)}</td>
            <td class="py-2.5 px-3 text-slate-300">{forma_opcao}</td>
            <td class="py-2.5 px-3 text-slate-400">Carnê / Boleto MVI</td>
        </tr>
        """
        cronograma_html += linhas_parcelas_item

    cronograma_html += f"""
    <tr class="border-t-2 border-slate-700 text-xs bg-slate-950 font-bold">
        <td colspan="2" class="py-3 px-3 text-amber-400 uppercase">Total Geral (Entrada + Parcelas):</td>
        <td class="py-3 px-3 font-black text-amber-400 text-right text-sm">R$ {fmt_br(total_com_juros)}</td>
        <td colspan="2" class="py-3 px-3 text-slate-400 text-[11px]">Plano {n_parc}x com juros de {taxa_juros}% a.m.</td>
    </tr>
    """

    return {
        "sucesso": True,
        "preco_venda_fmt": fmt_br(pv_num),
        "entrada_valor_fmt": fmt_br(ent_num),
        "comissao_fmt": fmt_br(comissao_num),
        "lucro_fmt": fmt_br(lucro_estimado),
        "cronograma_html": cronograma_html
    }

@app.post("/salvar-empresa-json")
def salvar_empresa_json(
    nome_empresa: str = Form("MVI Móveis Planejados"),
    cnpj: str = Form(""),
    telefone: str = Form(""),
    desconto_max_vendedor: str = Form("3.0"),
    comissao_padrao_pct: str = Form("4.0"),
    taxa_juros_mensal: str = Form("1.99"),
    asaas_api_key: str = Form(""),
    asaas_ambiente: str = Form("producao")
):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE empresas SET
            nome_empresa = ?,
            cnpj = ?,
            telefone = ?,
            desconto_max_vendedor = ?,
            comissao_padrao_pct = ?,
            taxa_juros_mensal = ?,
            asaas_api_key = ?,
            asaas_ambiente = ?
        WHERE id = 1
    """, (nome_empresa.strip(), cnpj.strip(), telefone.strip(), parse_moeda(desconto_max_vendedor), parse_moeda(comissao_padrao_pct), parse_moeda(taxa_juros_mensal), asaas_api_key.strip(), asaas_ambiente.strip()))
    conn.commit()
    conn.close()
    return {"sucesso": True}

@app.post("/submeter-proposta-credito", response_class=HTMLResponse)
def submeter_proposta_credito_route(
    orcamento_id: int = Form(...),
    cliente_nome: str = Form(...),
    cliente_cpf: str = Form(...),
    cliente_telefone: str = Form(""),
    cliente_renda: str = Form("5500"),
    valor_financiado: str = Form("0"),
    num_parcelas: int = Form(24)
):
    v_fin = parse_moeda(valor_financiado)
    r_cli = parse_moeda(cliente_renda)
    empresa = get_empresa_dados(1)
    taxa = float(empresa.get("taxa_juros_mensal", 1.99))
    
    v_parc = calcular_parcela_price(v_fin, taxa, num_parcelas)
    tot_juros = v_parc * num_parcelas
    agora = datetime.now().strftime("%d/%m/%Y %H:%M")

    res_asaas = emitir_carne_asaas(empresa, cliente_nome, cliente_cpf, cliente_telefone, v_parc, num_parcelas)
    carne_url = res_asaas.get("carne_url", "")
    inst_id = res_asaas.get("installment_id", "")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO propostas_credito (
            empresa_id, orcamento_id, cliente_nome, cliente_cpf, cliente_renda,
            valor_financiado, num_parcelas, taxa_juros, valor_parcela, total_com_juros,
            status, score_estimado, criado_em, contrato_ccb_assinado, asaas_carne_url, asaas_installment_id
        ) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Aprovado (Crédito Liberado)', 780, ?, 1, ?, ?)
    """, (orcamento_id, cliente_nome, cliente_cpf, r_cli, v_fin, num_parcelas, taxa, v_parc, tot_juros, agora, carne_url, inst_id))
    
    cursor.execute("UPDATE orcamentos SET modalidade_pagamento = ?, num_parcelas = ?, status = 'Crédito Aprovado / CCB Emitida' WHERE id = ?", (f"MVI Crédito ({num_parcelas}x no Boleto/PIX)", num_parcelas, orcamento_id))
    conn.commit()
    conn.close()

    return RedirectResponse(url="/painel-get", status_code=303)

@app.get("/emitir-ccb/{proposta_id}", response_class=HTMLResponse)
def emitir_ccb_route(proposta_id: int):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM propostas_credito WHERE id = ?", (proposta_id,))
    prop = cursor.fetchone()
    conn.close()

    if not prop:
        return HTMLResponse("Proposta de Crédito não encontrada.", status_code=404)

    empresa = get_empresa_dados(1)
    carne_btn = f"""<a href="{prop['asaas_carne_url']}" target="_blank" class="px-4 py-2 bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-black rounded text-xs inline-block">💳 Visualizar / Imprimir Carnê de Boletos</a>""" if prop.get("asaas_carne_url") else ""

    return f"""<!DOCTYPE html>
<html lang="pt-br">
<head>
    <meta charset="UTF-8"><title>Cédula de Crédito Bancário - CCB #{prop['id']:05d}</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-white text-slate-900 p-8 font-sans text-xs max-w-4xl mx-auto leading-relaxed">
    <div class="border-b-2 border-slate-900 pb-3 text-center mb-4">
        <h1 class="font-black text-sm uppercase">CÉDULA DE CRÉDITO BANCÁRIO (CCB) Nº {prop['id']:05d}</h1>
        <p class="text-[11px] text-slate-600">Financiamento Direto ao Consumidor (CDC) - Lei Federal nº 10.931/2004</p>
    </div>

    <div class="border p-3 rounded-lg bg-slate-50 space-y-1 mb-4">
        <p><b>CREDOR ORIGINAL / EMISSOR:</b> {empresa['nome_empresa']} (CNPJ: {empresa['cnpj']})</p>
        <p><b>EMITENTE / DEVEDOR:</b> {prop['cliente_nome']} (CPF: {prop['cliente_cpf']})</p>
        <p><b>VALOR PRINCIPAL FINANCIADO (Repasse da Compra):</b> R$ {fmt_br(prop['valor_financiado'])}</p>
        <p><b>PLANO DE PAGAMENTO:</b> {prop['num_parcelas']} parcelas mensais de <b>R$ {fmt_br(prop['valor_parcela'])}</b></p>
        <p><b>TAXA DE JUROS:</b> {prop['taxa_juros']}% ao mês (Tabela Price) | <b>VALOR TOTAL:</b> R$ {fmt_br(prop['total_com_juros'])}</p>
    </div>

    <p class="mb-3">Pelo presente instrumento, o EMITENTE confessa a dívida e se obriga a pagar ao CREDOR a quantia líquida, certa e exigível acima estipulada, mediante liquidação pontual dos boletos ou chaves PIX emitidos sob sua titularidade.</p>

    <div class="mt-8 pt-4 border-t flex justify-between text-center">
        <div class="w-1/2">______________________________________<br><b>{prop['cliente_nome']}</b><br>Devedor / Emitente</div>
        <div class="w-1/2">______________________________________<br><b>{empresa['nome_empresa']}</b><br>Credor / Operador</div>
    </div>

    <div class="mt-8 text-center flex items-center justify-center gap-3">
        <button onclick="window.print()" class="px-4 py-2 bg-sky-500 text-slate-950 font-bold rounded">🖨️ Imprimir Cédula de Crédito (PDF)</button>
        {carne_btn}
    </div>
</body></html>"""

@app.post("/importar-promob", response_class=HTMLResponse)
async def importar_promob_route(
    cliente_nome: str = Form(...),
    cliente_telefone: str = Form(""),
    cliente_ambiente: str = Form("Ambiente Promob"),
    valor_venda_manual: str = Form(""),
    arquivo_promob: UploadFile = File(...)
):
    conteudo = ""
    try:
        bytes_arquivo = await arquivo_promob.read()
        conteudo = bytes_arquivo.decode("utf-8", errors="ignore")
    except Exception:
        pass

    pv_num = 0.0

    if conteudo.strip():
        import re
        padroes = [
            r"TOTALORCADO\s*=\s*[\"']?([0-9\.\,]+)[\"']?",
            r"VALORTOTAL\s*=\s*[\"']?([0-9\.\,]+)[\"']?",
            r"PRECOTOTAL\s*=\s*[\"']?([0-9\.\,]+)[\"']?",
            r"<TOTALORCADO[^>]*>([0-9\.\,]+)<\/TOTALORCADO>",
            r"<VALORTOTAL[^>]*>([0-9\.\,]+)<\/VALORTOTAL>",
            r"<PRECOTOTAL[^>]*>([0-9\.\,]+)<\/PRECOTOTAL>",
            r"Total\s*or[cç]ado\s*[:=]?\s*([0-9\.\,]+)",
            r"Valor\s*Total\s*[:=]?\s*([0-9\.\,]+)",
            r"TOTAL\s*[:=]?\s*([0-9\.\,]+)"
        ]
        for padrao in padroes:
            matches = re.findall(padrao, conteudo, re.IGNORECASE)
            for m in matches:
                v = parse_moeda(m)
                if v > pv_num:
                    pv_num = v

        if pv_num <= 0:
            try:
                root = ET.fromstring(conteudo)
                tags_alvo = ["TOTALORCADO", "TOTAL_ORCADO", "VALORTOTAL", "VALOR_TOTAL", "TOTAL", "TOTALGERAL", "PRECOTOTAL", "VALOR", "PRECO"]
                for elem in root.iter():
                    tag_limpa = elem.tag.upper().replace("_", "")
                    for alvo in tags_alvo:
                        if alvo.replace("_", "") in tag_limpa and elem.text:
                            val = parse_moeda(elem.text)
                            if val > pv_num:
                                pv_num = val
                    for attr_k, attr_v in elem.attrib.items():
                        attr_limpo = attr_k.upper().replace("_", "")
                        for alvo in tags_alvo:
                            if alvo.replace("_", "") in attr_limpo:
                                val = parse_moeda(attr_v)
                                if val > pv_num:
                                    pv_num = val
            except Exception:
                pass

    if valor_venda_manual and valor_venda_manual.strip():
        v_digitado = parse_moeda(valor_venda_manual)
        if v_digitado > 0:
            pv_num = v_digitado

    if pv_num <= 0:
        pv_num = 0.0

    comissao_pct = 4.0
    comissao_num = (pv_num * comissao_pct) / 100.0
    custo_estimado = pv_num * 0.65
    lucro_estimado = pv_num - custo_estimado - comissao_num
    agora = datetime.now().strftime("%d/%m/%Y %H:%M")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO orcamentos (
            empresa_id, criado_em, vendedor_responsavel, vendedor_email,
            cliente_nome, cliente_telefone, cliente_ambiente,
            prazo_entrega, status, preco_venda, preco_bruto,
            comissao_valor, lucro_liquido,
            observacoes_tecnicas, descricao_promob
        ) VALUES (1, ?, 'Raquel Marcelino', 'raquel@mvi.com', ?, ?, ?, '35 dias úteis', 'Em Negociação', ?, ?, ?, ?, ?, ?)
    """, (
        agora, cliente_nome, cliente_telefone, cliente_ambiente,
        pv_num, pv_num, comissao_num, lucro_estimado,
        f"Arquivo: {arquivo_promob.filename}", conteudo[:1000]
    ))
    
    conn.commit()
    novo_id = cursor.lastrowid
    CURRENT_SESSION["cliente_ativo_id"] = novo_id
    conn.close()
    nome = cliente_nome
    whatsapp = cliente_telefone
    cidade = "Não informada"
    area_m2_total = 45
    espessura_caixa = "15mm"
    cor_caixa = "Branco TX"
    espessura_porta = "18mm"
    cor_porta = "Madeirado"
    acabamento_porta = "MDF Texturizado"
    marca_ferragens = "Hettich"
    espessura_tamponamento = "18mm"
    empresa_dados = get_empresa_dados()
    ambientes_str = "Cozinha Planejada"
    return HTMLResponse(render_pre_orcamento_agendamento(
        empresa_dados, novo_id, nome, whatsapp, cidade, float(area_m2_total or 45), pv_num,
        espessura_caixa, cor_caixa, espessura_porta, cor_porta, acabamento_porta, marca_ferragens, espessura_tamponamento, ambientes_str
    ))
@app.post("/recusar-lead", response_class=HTMLResponse)
def recusar_lead_route(orcamento_id: int = Form(...)):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE orcamentos SET status = 'Descartado / Sem Interesse' WHERE id = ?", (orcamento_id,))
    conn.commit()
    conn.close()
    
    return HTMLResponse(f"""<!DOCTYPE html>
<html lang="pt-br">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Agradecemos seu contato</title><script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-slate-950 text-slate-100 flex items-center justify-center min-h-screen p-4 font-sans text-center">
    <div class="max-w-md w-full bg-slate-900 border border-slate-800 p-8 rounded-3xl space-y-4 shadow-2xl">
        <span class="text-4xl block">🤝</span>
        <h1 class="font-bold text-white text-lg">Agradecemos sua simulação!</h1>
        <p class="text-xs text-slate-400">Suas preferências foram registradas. Quando desejar retomar o projeto dos seus móveis planejados, estaremos à disposição!</p>
        <a href="/solicitar-orcamento" class="inline-block px-5 py-2.5 bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold rounded-xl text-xs transition">Fazer Nova Simulação</a>
    </div>
</body></html>""")

@app.post("/atualizar-status-lead", response_class=HTMLResponse)
def atualizar_status_lead_route(orcamento_id: int = Form(...), novo_status: str = Form(...)):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE orcamentos SET status = ? WHERE id = ?", (novo_status, orcamento_id))
    conn.commit()
    conn.close()
    return RedirectResponse(url="/painel-get", status_code=303)

@app.post("/excluir-lead", response_class=HTMLResponse)
def excluir_lead_route(orcamento_id: int = Form(...)):
    if CURRENT_SESSION.get("user_perfil") != "adm":
        return HTMLResponse("<script>alert('Acesso negado: Apenas Administradores podem excluir clientes/pastas.'); window.location.href='/painel-get';</script>")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM orcamentos WHERE id = ?", (orcamento_id,))
    cursor.execute("DELETE FROM propostas_credito WHERE orcamento_id = ?", (orcamento_id,))
    conn.commit()
    conn.close()

    if CURRENT_SESSION.get("cliente_ativo_id") == orcamento_id:
        CURRENT_SESSION["cliente_ativo_id"] = None

    return RedirectResponse(url="/painel-get", status_code=303)

@app.post("/salvar-dados-completos-cliente", response_class=HTMLResponse)
def salvar_dados_completos_cliente_route(
    orcamento_id: int = Form(0),
    cliente_nome: str = Form(""),
    cliente_cpf: str = Form(""),
    cliente_telefone: str = Form(""),
    cliente_renda: str = Form("5500"),
    cliente_cep_postal: str = Form(""),
    cliente_rua_postal: str = Form(""),
    cliente_num_postal: str = Form(""),
    cliente_comp_postal: str = Form(""),
    cliente_bairro_postal: str = Form(""),
    cliente_cidade_postal: str = Form(""),
    cliente_uf_postal: str = Form(""),
    cliente_cep_entrega: str = Form(""),
    cliente_rua_entrega: str = Form(""),
    cliente_num_entrega: str = Form(""),
    cliente_comp_entrega: str = Form(""),
    cliente_bairro_entrega: str = Form(""),
    cliente_cidade_entrega: str = Form(""),
    cliente_uf_entrega: str = Form("")
):
    end_postal_completo = f"{cliente_rua_postal}, {cliente_num_postal} - {cliente_comp_postal}, {cliente_bairro_postal}, {cliente_cidade_postal} - {cliente_uf_postal}".strip(" ,-")
    end_entrega_completo = f"{cliente_rua_entrega}, {cliente_num_entrega} - {cliente_comp_entrega}, {cliente_bairro_entrega}, {cliente_cidade_entrega} - {cliente_uf_entrega}".strip(" ,-")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE orcamentos SET
            cliente_nome = ?, cliente_cpf = ?, cliente_telefone = ?, cliente_renda = ?,
            cliente_cep_postal = ?, cliente_rua_postal = ?, cliente_num_postal = ?,
            cliente_comp_postal = ?, cliente_bairro_postal = ?, cliente_cidade_postal = ?, cliente_uf_postal = ?,
            cliente_endereco_postal = ?,
            cliente_cep_entrega = ?, cliente_rua_entrega = ?, cliente_num_entrega = ?,
            cliente_comp_entrega = ?, cliente_bairro_entrega = ?, cliente_cidade_entrega = ?, cliente_uf_entrega = ?,
            cliente_endereco_entrega = ?
        WHERE id = ?
    """, (
        cliente_nome, cliente_cpf, cliente_telefone, cliente_renda,
        cliente_cep_postal, cliente_rua_postal, cliente_num_postal, cliente_comp_postal, cliente_bairro_postal, cliente_cidade_postal, cliente_uf_postal,
        end_postal_completo,
        cliente_cep_entrega, cliente_rua_entrega, cliente_num_entrega, cliente_comp_entrega, cliente_bairro_entrega, cliente_cidade_entrega, cliente_uf_entrega,
        end_entrega_completo,
        orcamento_id
    ))
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
    desconto_max_vendedor: str = Form("3.0"),
    comissao_padrao_pct: str = Form("4.0"),
    taxa_juros_mensal: str = Form("1.99"),
    asaas_api_key: str = Form(""),
    asaas_ambiente: str = Form("producao")
):
    key_final = asaas_api_key.strip() if asaas_api_key.strip() else DEFAULT_ASAAS_KEY
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE empresas SET
            nome_empresa = ?,
            cnpj = ?,
            telefone = ?,
            desconto_max_vendedor = ?,
            comissao_padrao_pct = ?,
            taxa_juros_mensal = ?,
            asaas_api_key = ?,
            asaas_ambiente = ?
        WHERE id = 1
    """, (nome_empresa.strip(), cnpj.strip(), telefone.strip(), parse_moeda(desconto_max_vendedor), parse_moeda(comissao_padrao_pct), parse_moeda(taxa_juros_mensal), key_final, asaas_ambiente.strip()))
    conn.commit()
    conn.close()
    return RedirectResponse(url="/painel-get", status_code=303)

@app.get("/minuta-contrato/{orcamento_id}", response_class=HTMLResponse)
def minuta_contrato_route(orcamento_id: int):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    if orcamento_id == 0:
        sess_id = CURRENT_SESSION.get("cliente_ativo_id")
        if sess_id:
            cursor.execute("SELECT * FROM orcamentos WHERE id = ?", (sess_id,))
        else:
            cursor.execute("SELECT * FROM orcamentos ORDER BY id DESC LIMIT 1")
    else:
        cursor.execute("SELECT * FROM orcamentos WHERE id = ?", (orcamento_id,))
        
    row = cursor.fetchone()
    conn.close()
    if not row:
        return HTMLResponse("Nenhum contrato ativo encontrado no sistema.", status_code=404)

    orc = dict(row)
    empresa = get_empresa_dados(1) if "get_empresa_dados" in globals() else {}
    
    pv_total = float(orc.get("preco_venda") or 0) + float(orc.get("adendo_valor") or 0)
    end_ent = orc.get("cliente_endereco_entrega") or orc.get("cliente_endereco_postal") or orc.get("cliente_endereco") or "A combinar"
    cpf_cli = orc.get("cliente_cpf") or orc.get("cpf") or "Não informado"
    rg_cli = orc.get("cliente_rg") or orc.get("rg") or "Não informado"
    email_cli = orc.get("cliente_email") or orc.get("email") or "Não informado"
    tel_cli = orc.get("cliente_telefone") or orc.get("telefone") or "Não informado"
    
    nome_emp = empresa.get("nome_empresa", "MVI Móveis Planejados")
    cnpj_emp = empresa.get("cnpj", "Consulte a Administração")
    end_emp = empresa.get("endereco", "Endereço da Fábrica / Showroom")
    
    forma_pag = orc.get("modalidade_pagamento") or orc.get("forma_pagamento") or "A combinar"
    parcelas = orc.get("num_parcelas") or orc.get("parcelas_qtd") or orc.get("qtd_parcelas") or orc.get("parcelas") or orc.get("condicao_parcelas") or 1    
    entrada = float(orc.get("entrada_valor") or 0)
    try:
        parcelas_int = int(parcelas) if int(parcelas) > 0 else 1
    except:
        parcelas_int = 1
    saldo_devedor = max(0.0, pv_total - entrada)
    valor_parcela = saldo_devedor / parcelas_int
    texto_parcelamento = f"{parcelas_int}x de R$ {valor_parcela:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    cliente_nome = orc.get("cliente_nome", "Cliente")
    ambiente = orc.get("cliente_ambiente", "Móveis Planejados")
    prazo = orc.get("prazo_entrega", "35 dias úteis")
    criado_em = orc.get("criado_em", "")
    contrato_id = orc.get("id", 1)

    html_code = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <title>Contrato de Prestação de Serviços - {cliente_nome}</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        @media print {{
            .no-print {{ display: none !important; }}
            body {{ padding: 0; background: white; }}
            @page {{ margin: 15mm 20mm 15mm 20mm; }}
        }}
    </style>
</head>
<body class="bg-slate-100 text-slate-800 font-sans text-xs leading-relaxed p-6">
    <div class="max-w-4xl mx-auto bg-white p-8 md:p-12 shadow-md rounded-sm border border-slate-200">
        
        <div class="no-print flex justify-between items-center bg-slate-900 text-white p-4 rounded mb-6">
            <div>
                <h3 class="font-bold text-sm">Visualização de Minuta Contratual</h3>
                <p class="text-xs text-slate-400">Pronto para impressão em A4 ou exportação para PDF.</p>
            </div>
            <button onclick="window.print()" class="bg-amber-500 hover:bg-amber-600 text-slate-950 font-bold px-4 py-2 rounded flex items-center gap-2 text-xs transition">
                🖨️ Imprimir / Salvar PDF
            </button>
        </div>

        <div class="text-center border-b pb-4 mb-6">
        <div style="display: flex; justify-content: center; margin-bottom: 12px;">
            <div style="background-color: #0d0d0d; border: 1.5px solid #d4af37; padding: 12px 24px; border-radius: 6px; text-align: center;">
                <div style="font-family: serif; font-size: 26px; font-weight: bold; color: #d4af37; line-height: 1; margin-bottom: 2px;">V</div>
                <div style="font-family: serif; font-size: 18px; font-weight: bold; letter-spacing: 4px; color: #d4af37; text-transform: uppercase;">VERSATTO</div>
                <div style="font-size: 8px; letter-spacing: 2.5px; color: #e5c365; text-transform: uppercase; margin-top: 2px;">MÓVEIS PLANEJADOS</div>
            </div>
        </div>
        <h1 class="text-base font-bold uppercase tracking-wider text-slate-900">INSTRUMENTO PARTICULAR DE PRESTAÇÃO DE SERVIÇOS E FORNECIMENTO DE MÓVEIS SOB MEDIDA</h1>
        <p class="text-xs text-slate-500 mt-1">Contrato Referência: #{contrato_id:04d} | Emissão: {criado_em}</p>
    </div>

        <div class="space-y-4">
            <div>
                <h2 class="font-bold text-slate-900 uppercase border-b pb-1 mb-2">1. DAS PARTES</h2>
                <p><b>CONTRATADA:</b> <span class="uppercase">{nome_emp}</span>, pessoa jurídica de direito privado, inscrita no CNPJ sob o nº <b>{cnpj_emp}</b>, com sede em {end_emp}.</p>
                <p class="mt-1"><b>CONTRATANTE:</b> <b>{cliente_nome}</b>, CPF nº <b>{cpf_cli}</b>, RG nº <b>{rg_cli}</b>, Telefone: <b>{tel_cli}</b>, E-mail: <b>{email_cli}</b>, com endereço de entrega/instalação em: <b>{end_ent}</b>.</p>
            </div>

            <div>
                <h2 class="font-bold text-slate-900 uppercase border-b pb-1 mb-2">2. DO OBJETO</h2>
                <p>O presente contrato tem por objeto a fabricação, fornecimento e montagem dos móveis planejados sob medida para o(s) seguinte(s) ambiente(s): <b>{ambiente}</b>, em conformidade estrita com o projeto 3D e memorial descritivo aprovados pelo CONTRATANTE.</p>
            </div>

            <div>
                <h2 class="font-bold text-slate-900 uppercase border-b pb-1 mb-2">3. DO VALOR E FORMA DE PAGAMENTO</h2>
                <p>Pela prestação dos serviços e fornecimento dos materiais, o CONTRATANTE pagará à CONTRATADA o valor total fechado de <b>R$ {fmt_br(pv_total)}</b>.</p>
                <p class="mt-1"><b>Condição comercial acordada:</b> {forma_pag}.</p>
            <p class="mt-1"><b>Valor de Entrada:</b> R$ {fmt_br(entrada)} | <b>Parcelamento:</b> {texto_parcelamento}.</p>           
            </div>

            <div>
                <h2 class="font-bold text-slate-900 uppercase border-b pb-1 mb-2">4. DO PRAZO DE FABRICAÇÃO E INSTALAÇÃO</h2>
<p>O prazo estimado para entrega e início da montagem é de <b>35 dias úteis</b>, contados a partir da conclusão da medição técnica final no local e aprovação definitiva do projeto executivo por ambas as partes.</p>
            <p class="mt-1 text-slate-600"><i>Parágrafo Único:</i> O CONTRATANTE compromete-se a deixar o ambiente civilmente preparado (alvenaria, hidráulica, elétrica e pisos concluídos) para o início da montagem.</p>
        </div>
            <div>
                <h2 class="font-bold text-slate-900 uppercase border-b pb-1 mb-2">5. DA GARANTIA E ASSISTÊNCIA TÉCNICA</h2>
 <p>A CONTRATADA oferece garantia legal e contratual de <b>05 (cinco) anos para marcenaria/madeira</b> e <b>12 (doze) meses para ferragens e acessórios</b> contra eventuais defeitos de fabricação e montagem, excetuando-se danos decorrentes de umidade excessiva, mau uso, impacto mecânico ou intervenção de terceiros não autorizados.</p>           
 </div>

            <div>
                <h2 class="font-bold text-slate-900 uppercase border-b pb-1 mb-2">6. DO FORO</h2>
                <p>Para dirimir quaisquer controvérsias oriundas do presente instrumento, as partes elegem o foro da Comarca de domicílio da CONTRATADA, com renúncia expressa a qualquer outro.</p>
            </div>
        </div>

        <div class="mt-12 pt-8 border-t border-slate-300">
            <p class="text-center mb-10 text-slate-600">E, por estarem justas e acordadas, as partes assinam o presente contrato em 02 (duas) vias de igual teor.</p>
            
            <div class="grid grid-cols-2 gap-12 text-center text-xs">
                <div>
                    <div class="border-b border-slate-900 pb-1 mb-1 font-bold uppercase">{cliente_nome}</div>
                    <span class="text-slate-500">CONTRATANTE</span>
                </div>
                <div>
                    <div class="border-b border-slate-900 pb-1 mb-1 font-bold uppercase">{nome_emp}</div>
                    <span class="text-slate-500">CONTRATADA</span>
                </div>
            </div>

            <div class="grid grid-cols-2 gap-12 text-center text-xs mt-8">
                <div>
                    <div class="border-b border-slate-400 pb-1 mb-1 text-slate-400">Assinatura Testemunha 1</div>
                    <span class="text-slate-500">CPF: ______________________</span>
                </div>
                <div>
                    <div class="border-b border-slate-400 pb-1 mb-1 text-slate-400">Assinatura Testemunha 2</div>
                    <span class="text-slate-500">CPF: ______________________</span>
                </div>
            </div>
        </div>
    </div>
</body>
</html>"""
    return HTMLResponse(content=html_code)

# ==========================================
# MÓDULO ARQUITETO IA - LEITURA DE PLANTA E MEMORIAL
# ==========================================
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")
if GEMINI_KEY:
    try:
        genai.configure(api_key=GEMINI_KEY)
    except Exception:
        pass

@app.post("/api/analisar-planta-ia")
async def analisar_planta_ia(
    cliente_nome: str = Form(...),
    telefone: str = Form(...),
    ambiente: str = Form(...),
    descricao_cliente: str = Form(...),
    medida_parede: str = Form(""),
    foto_planta: UploadFile = File(None)
):
    briefing_tecnico = ""
    
    if GEMINI_KEY:
        try:
            model = genai.GenerativeModel("gemini-1.5-flash")
            prompt_analise = f"""
            Você é um Arquiteto e Engenheiro de Produção especialista em Marcenaria Sob Medida de Alto Padrão.
            Analise os dados enviados pelo cliente:
            - Cliente: {cliente_nome}
            - Ambiente: {ambiente}
            - Parede / Medida informada: {medida_parede}
            - O que o cliente deseja detalhadamente: {descricao_cliente}

            Gere uma análise estruturada para o cliente e para a marcenaria contendo:
            1. Sugestão de Paginação e Distribuição dos Módulos (inferiores, aéreos, torres).
            2. Combinação de Cores e Padrões de MDF recomendados.
            3. Ferragens e Acessórios indicados (corrediças ocultas, amortecedores, iluminação LED).
            4. Estimativa aproximada de consumo de chapas com base na medida da parede.
            """
            
            if foto_planta and foto_planta.filename:
                contents = await foto_planta.read()
                image_parts = [{"mime_type": foto_planta.content_type or "image/jpeg", "data": contents}]
                response = model.generate_content([prompt_analise, image_parts[0]])
            else:
                response = model.generate_content(prompt_analise)
                
            briefing_tecnico = response.text if hasattr(response, "text") else "Análise concluída."
        except Exception as e:
            briefing_tecnico = f"Briefing preliminar registrado. Detalhe técnico: {str(e)}"
    else:
        briefing_tecnico = f"Ambiente: {ambiente} | Parede: {medida_parede} | Briefing: {descricao_cliente}"

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO orcamentos (cliente_nome, cliente_telefone, cliente_ambiente, status_lead, criado_em)
        VALUES (?, ?, ?, 'Novo Lead IA', datetime('now', 'localtime'))
    """, (cliente_nome, telefone, f"{ambiente} ({medida_parede}) - {descricao_cliente[:100]}"))
    conn.commit()
    novo_id = cursor.lastrowid
    conn.close()

    return JSONResponse({
        "status": "success",
        "orcamento_id": novo_id,
        "briefing": briefing_tecnico
    })

def analisar_planta_baixa_gemini(planta_bytes: bytes, tipo_ambiente: str, cor_escolhida: str, medidas_cliente: str) -> str:
    """Usa o Gemini Vision para ler a planta baixa e forçar a tipologia real (linear vs L)."""
    try:
        if not GEMINI_KEY or not planta_bytes:
            return f"photorealistic 3d interior render modern bespoke joinery narrow linear straight single wall kitchen cabinetry width {medidas_cliente}m {cor_escolhida} no island no L-shape built-in appliances modern led lighting 8k"
        
        genai.configure(api_key=GEMINI_KEY)
        model = genai.GenerativeModel("gemini-1.5-flash")
        
        prompt_instrucao = (
            f"Você é um arquiteto técnico especialista em marcenaria sob medida e leitura técnica de plantas baixas brasileiras. "
            f"Analise detalhadamente a imagem da planta baixa anexada com foco no ambiente de {tipo_ambiente} ({medidas_cliente} m²). "
            f"REGRAS DE LAYOUT ESTRITAS: "
            f"1. Se a planta for uma cozinha corredor/estreita com bancada em apenas uma parede, descreva OBRIGATORIAMENTE como 'narrow linear straight galley single-wall kitchen, straight cabinetry run along one single wall, perfectly straight countertop, NO L-shape, NO island, NO corner cabinet'. "
            f"2. Se e somente se a planta tiver bancada contínua virando a quina em 90 graus, descreva como 'L-shaped corner kitchen'. "
            f"3. Inclua acabamento dos armários em {cor_escolhida}, cuba inox, cooktop embutido, armários aéreos superiores alinhados e iluminação LED. "
            f"Retorne APENAS um prompt em INGLÊS com até 40 palavras para renderização arquitetônica fotorrealista 8k."
        )
        
        conteudo = [
            prompt_instrucao,
            {"mime_type": "image/jpeg", "data": planta_bytes}
        ]
        
        resposta = model.generate_content(conteudo)
        prompt_gerado = resposta.text.strip().replace("\n", " ")
        return prompt_gerado
    except Exception as e:
        print(f"Erro na leitura da planta com Gemini: {e}")
        return f"photorealistic 3d interior render narrow linear straight single wall kitchen cabinetry width {medidas_cliente}m {cor_escolhida} no island no L-shape built-in appliances 8k"

# ==========================================================
# --- PÁGINA PÚBLICA DE PLANOS & ASSINATURA (MVI CRM) ---
# ==========================================================

PLANOS_MVI = {
    "starter": {
        "id": "starter",
        "nome": "Individual",
        "badge": "Individual",
        "usuarios": "1 Operador",
        "setup": 0.0,
        "mensalidade": 49.97,
    },
    "professional": {
        "id": "professional",
        "nome": "Profissional",
        "badge": "Mais Escolhido",
        "usuarios": "Até 5 Operadores",
        "setup": 197.0,
        "mensalidade": 97.90,
        "destaque": True
    },
    "enterprise": {
        "id": "enterprise",
        "nome": "Ilimitado",
        "badge": "Enterprise",
        "usuarios": "Usuários Ilimitados",
        "setup": 497.0,
        "mensalidade": 179.90,
        }
}

@app.get("/planos")
async def rota_pagina_planos(request: Request):
    caminho = os.path.join(os.path.dirname(__file__), "templates", "templates", "planos_checkout.html")
    if not os.path.exists(caminho):
        caminho = os.path.join(os.path.dirname(__file__), "templates", "planos_checkout.html")
    
    if os.path.exists(caminho):
        with open(caminho, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h2>Template não encontrado</h2>", status_code=404)

@app.post("/api/assinar-plano")
async def api_assinar_plano_mvi(request: Request):
    try:
        dados = await request.json()
    except Exception:
        dados = {}

    plano_info = PLANOS_MVI.get(dados.get("plano_id"))
    if not plano_info:
        return JSONResponse(status_code=400, content={"status": "erro", "mensagem": "Plano inválido"})

    asaas_key = os.getenv("ASAAS_API_KEY", "")
    asaas_url = os.getenv("ASAAS_API_URL", "https://api.asaas.com/v3")
    chave_pix = os.getenv("CHAVE_PIX", "suachavepix@mvicrm.com.br")

    headers = {
        "access_token": asaas_key,
        "Content-Type": "application/json"
    }

    customer_id = None
    if asaas_key:
        payload_cliente = {
            "name": dados.get("nome_empresa"),
            "cpfCnpj": dados.get("cpf_cnpj"),
            "email": dados.get("email"),
            "mobilePhone": dados.get("whatsapp"),
            "notificationDisabled": False
        }
        try:
            req = urllib.request.Request(
                f"{asaas_url}/customers",
                data=json.dumps(payload_cliente).encode("utf-8"),
                headers=headers,
                method="POST"
            )
            with urllib.request.urlopen(req) as resp:
                res_cliente = json.loads(resp.read().decode())
                customer_id = res_cliente.get("id")
        except Exception as e:
            print(f"Erro Asaas Cliente: {e}")

        if customer_id:
            data_vencimento = (date.today() + timedelta(days=30)).strftime("%Y-%m-%d")
            payload_sub = {
                "customer": customer_id,
                "billingType": "UNDEFINED",
                "value": plano_info["mensalidade"],
                "nextDueDate": data_vencimento,
                "cycle": "MONTHLY",
                "description": f"Mensalidade MVI CRM - Plano {plano_info['nome']}"
            }
            try:
                req_sub = urllib.request.Request(
                    f"{asaas_url}/subscriptions",
                    data=json.dumps(payload_sub).encode("utf-8"),
                    headers=headers,
                    method="POST"
                )
                with urllib.request.urlopen(req_sub) as resp_sub:
                    pass
            except Exception as e:
                print(f"Erro Asaas Subscrição: {e}")

    return JSONResponse(content={
        "status": "sucesso",
        "plano": plano_info["nome"],
        "setup_valor": plano_info["setup"],
        "chave_pix": chave_pix
    })
# ==========================================================
# --- SISTEMA MULTI-LOJAS, LOGIN UNIVERSAL & ADMIN CRM ---
# ==========================================================

def inicializar_tabelas_multiloja():
    conn = sqlite3.connect("sistema_marcenaria.db")
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS lojas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT UNIQUE,
            nome_loja TEXT,
            email TEXT UNIQUE,
            whatsapp TEXT,
            senha TEXT,
            plano TEXT,
            status TEXT DEFAULT 'ativo',
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Inserir loja padrão
    cursor.execute("""
        INSERT OR IGNORE INTO lojas (slug, nome_loja, email, whatsapp, senha, plano, status)
        VALUES ('padrao', 'Marcenaria Principal (MVI)', 'admin@mvicrm.com', '5511999999999', '123456', 'Enterprise', 'ativo')
    """)

    # Garantir que a Versatto já venha cadastrada e ativa
    cursor.execute("""
        INSERT OR REPLACE INTO lojas (slug, nome_loja, email, whatsapp, senha, plano, status)
        VALUES ('guilherme', 'Versatto Moveis Planejados', 'mversatto@gmail.com', '11966556933', '123456', 'Starter', 'ativo')
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS leads_orcamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            loja_slug TEXT,
            cliente_nome TEXT,
            cliente_whats TEXT,
            status_chaves TEXT,
            ambientes TEXT,
            valor_estimado TEXT,
            especificacoes TEXT,
            data_envio TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

try:
    inicializar_tabelas_multiloja()
except Exception as e:
    print(f"Erro tabelas multiloja: {e}")

# Autenticação de Login que aceita Form, JSON e AJAX
@app.post("/login")
@app.post("/api/login")
async def rota_login_unificada(request: Request):
    email = ""
    senha = ""
    
    # Tenta ler como JSON ou como FormData
    try:
        dados_json = await request.json()
        email = dados_json.get("email", "")
        senha = dados_json.get("senha", "")
    except Exception:
        try:
            dados_form = await request.form()
            email = dados_form.get("email", "")
            senha = dados_form.get("senha", "")
        except Exception:
            pass

    email_limpo = str(email).strip().lower()
    senha_limpa = str(senha).strip()

    conn = sqlite3.connect("sistema_marcenaria.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # 1. Busca na tabela de lojas
    cursor.execute("SELECT * FROM lojas WHERE LOWER(email) = ?", (email_limpo,))
    loja = cursor.fetchone()
    
    if loja:
        if loja["status"] != "ativo":
            conn.close()
            return JSONResponse(content={"status": "erro", "mensagem": "Assinatura inativa ou bloqueada."}, status_code=403)
        
        # Senha correta ou senha padrão '123456'
        if loja["senha"] == senha_limpa or senha_limpa == "123456":
            conn.close()
            resposta = JSONResponse(content={"status": "sucesso", "redirect": f"/painel?loja={loja['slug']}"})
            resposta.set_cookie(key="loja_logada", value=loja["slug"], max_age=86400)
            resposta.set_cookie(key="usuario_email", value=loja["email"], max_age=86400)
            return resposta

    # 2. Busca na tabela tradicional de usuários
    try:
        cursor.execute("SELECT * FROM usuarios WHERE LOWER(email) = ? AND senha = ?", (email_limpo, senha_limpa))
        usuario = cursor.fetchone()
        if usuario:
            conn.close()
            resposta = JSONResponse(content={"status": "sucesso", "redirect": "/painel"})
            resposta.set_cookie(key="usuario_email", value=usuario["email"], max_age=86400)
            return resposta
    except Exception:
        pass

    conn.close()
    return JSONResponse(content={"status": "erro", "mensagem": "E-mail ou senha incorretos."}, status_code=401)

@app.get("/solicitar-orcamento")
@app.get("/orcamento-multi")
async def rota_solicitar_orcamento(request: Request, loja: Optional[str] = None):
    if loja and loja.lower() != "padrao":
        conn = sqlite3.connect("sistema_marcenaria.db")
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM lojas WHERE slug = ?", (loja.lower(),))
        row = cursor.fetchone()
        conn.close()
        
        if not row or row[0] != "ativo":
            return HTMLResponse(
                content="<body style='background:#020617;color:#fff;font-family:sans-serif;text-align:center;padding:50px;'>"
                        "<h2 style='color:#f59e0b;'>⚠️ Assinatura Inativa ou Nao Encontrada</h2>"
                        "<p style='color:#94a3b8;'>Esta marcenaria nao possui uma conta ativa no MVI CRM.</p>"
                        "<a href='/planos' style='display:inline-block;margin-top:20px;padding:12px 24px;background:#f59e0b;color:#000;font-weight:bold;text-decoration:none;border-radius:8px;'>Contratar Plano</a>"
                        "</body>",
                status_code=403
            )

    caminhos = [
        "templates/templates/templates/solicitar_orcamento.html",
        "templates/templates/solicitar_orcamento.html",
        "templates/solicitar_orcamento.html",
        "solicitar_orcamento.html"
    ]
    for c in caminhos:
        for base in [os.path.dirname(__file__), os.getcwd()]:
            p = os.path.join(base, c)
            if os.path.exists(p):
                with open(p, "r", encoding="utf-8") as f:
                    return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h2>Template de orcamento nao encontrado</h2>", status_code=404)

@app.get("/admin-lojas")
async def rota_admin_lojas(request: Request):
    caminhos = [
        "templates/templates/templates/admin_lojas.html",
        "templates/templates/admin_lojas.html",
        "templates/admin_lojas.html",
        "admin_lojas.html"
    ]
    for c in caminhos:
        for base in [os.path.dirname(__file__), os.getcwd()]:
            p = os.path.join(base, c)
            if os.path.exists(p):
                with open(p, "r", encoding="utf-8") as f:
                    return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h2>Template admin nao encontrado</h2>", status_code=404)

@app.get("/api/admin/listar-lojas-leads")
async def api_admin_listar_lojas_leads():
    try:
        conn = sqlite3.connect("sistema_marcenaria.db")
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM lojas ORDER BY id DESC")
        lojas = [dict(row) for row in cursor.fetchall()]
        
        cursor.execute("SELECT * FROM leads_orcamentos ORDER BY id DESC LIMIT 50")
        leads = [dict(row) for row in cursor.fetchall()]
        
        conn.close()
        return JSONResponse(content={"status": "sucesso", "lojas": lojas, "leads": leads})
    except Exception as e:
        return JSONResponse(content={"status": "erro", "detalhes": str(e)}, status_code=500)

@app.post("/api/admin/cadastrar-loja")
async def api_admin_cadastrar_loja(
    nome_loja: str = Form(...),
    slug: str = Form(...),
    whatsapp: str = Form(...),
    email: str = Form(...),
    plano: str = Form("Pro")
):
    try:
        conn = sqlite3.connect("sistema_marcenaria.db")
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO lojas (slug, nome_loja, email, whatsapp, senha, plano, status)
            VALUES (?, ?, ?, ?, '123456', ?, 'ativo')
        """, (slug.lower(), nome_loja, email.strip().lower(), whatsapp, plano))
        conn.commit()
        conn.close()
        return JSONResponse(content={"status": "sucesso", "mensagem": "Loja cadastrada com sucesso!"})
    except Exception as e:
        return JSONResponse(content={"status": "erro", "mensagem": f"Erro: {e}"}, status_code=400)

@app.post("/api/admin/alterar-status-loja")
async def api_admin_alterar_status_loja(
    slug: str = Form(...),
    status: str = Form(...)
):
    try:
        conn = sqlite3.connect("sistema_marcenaria.db")
        cursor = conn.cursor()
        cursor.execute("UPDATE lojas SET status = ? WHERE slug = ?", (status, slug.lower()))
        conn.commit()
        conn.close()
        return JSONResponse(content={"status": "sucesso"})
    except Exception as e:
        return JSONResponse(content={"status": "erro", "detalhes": str(e)}, status_code=500)

@app.post("/api/salvar-lead-loja")
async def api_salvar_lead_loja(
    loja_slug: str = Form("padrao"),
    cliente_nome: str = Form(...),
    cliente_whats: str = Form(...),
    status_chaves: str = Form(""),
    ambientes: str = Form(""),
    valor_estimado: str = Form(""),
    especificacoes: str = Form("")
):
    try:
        conn = sqlite3.connect("sistema_marcenaria.db")
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO leads_orcamentos (loja_slug, cliente_nome, cliente_whats, status_chaves, ambientes, valor_estimado, especificacoes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (loja_slug.lower(), cliente_nome, cliente_whats, status_chaves, ambientes, valor_estimado, especificacoes))
        conn.commit()
        conn.close()
        return JSONResponse(content={"status": "sucesso"})
    except Exception as e:
        return JSONResponse(content={"status": "erro", "detalhes": str(e)}, status_code=500)
@app.get("/assinar/{contrato_id}", response_class=HTMLResponse)
def assinar_digital_view(contrato_id: int):
    cliente = "Julian Barbosa Filho"
    pv_total_str = "18.500,00"
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM orcamentos WHERE id = ?", (contrato_id,))
        row = cursor.fetchone()
        conn.close()
        if row:
            orc = dict(row)
            cliente = orc.get("cliente_nome") or cliente
            val = float(orc.get("preco_venda") or 0) + float(orc.get("adendo_valor") or 0)
            if val > 0:
                pv_total_str = f"{val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        pass

    return HTMLResponse(f"""
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Assinatura Digital - Versatto Móveis</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <style>
            canvas {{ touch-action: none; }}
        </style>
    </head>
    <body class="bg-slate-900 text-slate-100 min-h-screen flex items-center justify-center p-4">
        <div class="max-w-md w-full bg-slate-800 p-6 rounded-2xl shadow-2xl border border-slate-700 text-center">
            <div class="mb-4">
                <span class="inline-block px-3 py-1 bg-amber-500/20 text-amber-400 text-xs font-semibold rounded-full uppercase tracking-wider border border-amber-500/30">Versatto Móveis Planejados</span>
            </div>
            
            <h1 class="text-xl font-bold text-white mb-1">Assinatura do Contrato #{contrato_id:04d}</h1>
            <p class="text-sm text-slate-400 mb-4">Contratante: <strong class="text-slate-200">{cliente}</strong> | Valor: <strong class="text-emerald-400">R$ {pv_total_str}</strong></p>
            
            <div class="text-left mb-2 text-xs text-slate-400 flex justify-between items-center">
                <span>Desenhe sua assinatura abaixo:</span>
                <button type="button" onclick="limparCanvas()" class="text-amber-400 hover:text-amber-300 underline text-xs">Limpar</button>
            </div>
            
            <div class="border-2 border-dashed border-slate-600 rounded-xl bg-white overflow-hidden mb-4">
                <canvas id="pad" class="w-full h-48 block cursor-crosshair"></canvas>
            </div>

            <p class="text-[11px] text-slate-400 leading-tight mb-6">
                Ao clicar em "Confirmar e Assinar", você declara concordar integralmente com as cláusulas, prazos e condições comerciais descritas na minuta contratual.
            </p>

            <button type="button" onclick="salvarAssinatura()" id="btnAssinar" class="w-full bg-amber-500 hover:bg-amber-600 text-slate-950 font-bold py-3 px-4 rounded-xl shadow-lg transition active:scale-95 text-sm">
                Confirmar e Assinar Documento
            </button>
            
            <div id="sucesso" class="hidden mt-4 p-4 bg-emerald-950/80 border border-emerald-500 text-emerald-200 rounded-xl text-xs font-semibold">
                ✓ Contrato Assinado Digitalmente com Sucesso!
            </div>
        </div>

        <script>
            const canvas = document.getElementById('pad');
            const ctx = canvas.getContext('2d');
            let desenhando = false;

            function redimensionar() {{
                const rect = canvas.getBoundingClientRect();
                canvas.width = rect.width;
                canvas.height = rect.height;
                ctx.lineWidth = 2.5;
                ctx.lineCap = 'round';
                ctx.strokeStyle = '#0f172a';
            }}
            redimensionar();
            window.addEventListener('resize', redimensionar);

            function pos(e) {{
                const rect = canvas.getBoundingClientRect();
                const clientX = e.touches ? e.touches[0].clientX : e.clientX;
                const clientY = e.touches ? e.touches[0].clientY : e.clientY;
                return {{ x: clientX - rect.left, y: clientY - rect.top }};
            }}

            function iniciar(e) {{ desenhando = true; ctx.beginPath(); const p = pos(e); ctx.moveTo(p.x, p.y); }}
            function mover(e) {{ if (!desenhando) return; const p = pos(e); ctx.lineTo(p.x, p.y); ctx.stroke(); }}
            function parar() {{ desenhando = false; }}

            canvas.addEventListener('mousedown', iniciar);
            canvas.addEventListener('mousemove', mover);
            window.addEventListener('mouseup', parar);

            canvas.addEventListener('touchstart', (e) => {{ e.preventDefault(); iniciar(e); }}, {{ passive: false }});
            canvas.addEventListener('touchmove', (e) => {{ e.preventDefault(); mover(e); }}, {{ passive: false }});
            canvas.addEventListener('touchend', parar);

            function limparCanvas() {{
                ctx.clearRect(0, 0, canvas.width, canvas.height);
            }}

            function salvarAssinatura() {{
                document.getElementById('btnAssinar').style.display = 'none';
                document.getElementById('sucesso').classList.remove('hidden');
            }}
        </script>
    </body>
    </html>
    """)
@app.post("/fechar-contrato-operacional/{contrato_id}")
@app.post("/fechar-contrato-operacional/{contrato_id}")
async def fechar_contrato_operacional_route(contrato_id: int):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("UPDATE orcamentos SET status = 'Contrato Fechado' WHERE id = ? OR lead_id = ?", (contrato_id, contrato_id))
        conn.commit()
        conn.close()
        return JSONResponse({"status": "sucesso"})
    except Exception as e:
        return JSONResponse({"status": "erro", "mensagem": str(e)}, status_code=500)

@app.post("/desbloquear-contrato-adm/{contrato_id}")
async def desbloquear_contrato_adm_route(contrato_id: int, request: Request):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("UPDATE orcamentos SET status = 'Em Negociação' WHERE id = ? OR lead_id = ?", (contrato_id, contrato_id))
        conn.commit()
        conn.close()
        return JSONResponse({"status": "sucesso"})
    except Exception as e:
        return JSONResponse({"status": "erro", "mensagem": str(e)}, status_code=500)
@app.post("/criar-pasta-direta-crm")
async def criar_pasta_direta_crm(request: Request):
    try:
        data = await request.json()
        nome = data.get("nome", "Cliente Balcão").strip()
        telefone = data.get("telefone", "").strip()
        ambientes = data.get("ambientes", "Móveis Planejados").strip()
        vendedor_nome = CURRENT_SESSION.get("user_nome", "Vendedor")
        vendedor_email = CURRENT_SESSION.get("user_email", "")

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO orcamentos (
                empresa_id, nome, telefone, ambiente, status, 
                vendedor_responsavel, vendedor_email, preco_final, entrada, parcelas
            ) VALUES (1, ?, ?, ?, 'Em Aberto', ?, ?, 0.0, 0.0, 1)
        """, (nome, telefone, ambientes, vendedor_nome, vendedor_email))
        
        novo_id = cursor.lastrowid
        conn.commit()
        conn.close()

        return JSONResponse({"status": "sucesso", "id": novo_id})
    except Exception as e:
        return JSONResponse({"status": "erro", "mensagem": str(e)}, status_code=500)

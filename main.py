from fastapi import FastAPI, Form, UploadFile, File, Response
from fastapi.responses import HTMLResponse, RedirectResponse
import xml.etree.ElementTree as ET
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
from datetime import datetime, date, timedelta
from typing import List

app = FastAPI(title="Sistema Marcenaria Inteligente")
DB_PATH = "marcenaria.db"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (
                email TEXT PRIMARY KEY,
                senha TEXT,
                nome TEXT,
                perfil TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS configuracoes (
                chave TEXT PRIMARY KEY,
                valor TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS estoque (
                codigo TEXT PRIMARY KEY,
                descricao TEXT,
                quantidade REAL,
                qtd_minima REAL,
                unidade TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS orcamentos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                criado_em TEXT,
                cliente_nome TEXT,
                cliente_telefone TEXT,
                cliente_ambiente TEXT,
                prazo_entrega TEXT,
                data_entrega_prevista TEXT,
                status TEXT DEFAULT 'Em Negociação',
                custo_materiais REAL,
                custo_mao_obra REAL,
                custo_frete_montagem REAL,
                imposto_pct REAL,
                comissao_pct REAL,
                markup REAL,
                preco_venda REAL,
                lucro_liquido REAL,
                entrada_valor REAL DEFAULT 0.0,
                num_parcelas INTEGER DEFAULT 1,
                forma_pagamento TEXT DEFAULT 'PIX / Transferência',
                estoque_baixado INTEGER DEFAULT 0,
                valor_recebido REAL DEFAULT 0.0,
                imagens_json TEXT,
                ambientes_json TEXT,
                observacoes_tecnicas TEXT DEFAULT '',
                items_json TEXT
            )
        """)
        
        colunas = [
            ("status", "TEXT"),
            ("entrada_valor", "REAL"),
            ("num_parcelas", "INTEGER"),
            ("forma_pagamento", "TEXT"),
            ("estoque_baixado", "INTEGER"),
            ("data_entrega_prevista", "TEXT"),
            ("valor_recebido", "REAL"),
            ("imagens_json", "TEXT"),
            ("ambientes_json", "TEXT"),
            ("observacoes_tecnicas", "TEXT"),
            ("items_json", "TEXT")
        ]
        for col, tipo in colunas:
            try:
                cursor.execute(f"ALTER TABLE orcamentos ADD COLUMN {col} {tipo}")
            except Exception:
                pass

        cursor.execute("SELECT codigo FROM estoque WHERE codigo = 'mdf'")
        if not cursor.fetchone():
            itens_padrao = [
                ('mdf', 'Chapas de MDF 18mm / 15mm', 15.0, 5.0, 'chapas'),
                ('fita', 'Fita de Borda PVC 22mm', 250.0, 50.0, 'metros'),
                ('dobradica', 'Dobradiças com Amortecedor 35mm', 80.0, 20.0, 'unidades'),
                ('corredica', 'Corrediças Telescópicas 450mm', 24.0, 6.0, 'pares'),
                ('puxador', 'Puxadores Perfil Alumínio / Pontos', 30.0, 10.0, 'unidades')
            ]
            cursor.executemany("INSERT INTO estoque VALUES (?, ?, ?, ?, ?)", itens_padrao)

        cursor.execute("SELECT email FROM usuarios WHERE email = 'admin@marcenaria.com'")
        if not cursor.fetchone():
            cursor.execute("INSERT INTO usuarios VALUES ('admin@marcenaria.com', '123456', 'Administrador', 'admin')")
            cursor.execute("INSERT INTO usuarios VALUES ('vendedor@marcenaria.com', '123456', 'Vendedor da Loja', 'vendedor')")

        cursor.execute("SELECT valor FROM configuracoes WHERE chave = 'precos'")
        if not cursor.fetchone():
            default_precos = {
                "mdf_m2": 65.0,
                "dobradica": 18.50,
                "corredica": 38.00,
                "fita_borda_m": 3.20,
                "puxador": 25.00,
                "outros_insumos": 15.00
            }
            cursor.execute("INSERT INTO configuracoes (chave, valor) VALUES ('precos', ?)", (json.dumps(default_precos),))

        cursor.execute("SELECT valor FROM configuracoes WHERE chave = 'dados_empresa'")
        if not cursor.fetchone():
            default_empresa = {
                "nome_empresa": "Marcenaria Pro Móveis Planejados",
                "cnpj": "00.000.000/0001-00",
                "telefone_empresa": "(11) 98888-7777",
                "pix": "contato@marcenaria.com"
            }
            cursor.execute("INSERT INTO configuracoes (chave, valor) VALUES ('dados_empresa', ?)", (json.dumps(default_empresa),))
        conn.commit()

init_db()

def get_precos_config():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT valor FROM configuracoes WHERE chave = 'precos'")
        row = cursor.fetchone()
        if row:
            return json.loads(row["valor"])
    return {
        "mdf_m2": 65.0, "dobradica": 18.50, "corredica": 38.00,
        "fita_borda_m": 3.20, "puxador": 25.00, "outros_insumos": 15.00
    }

def set_precos_config(precos: dict):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO configuracoes (chave, valor) VALUES ('precos', ?)", (json.dumps(precos),))
        conn.commit()

def get_empresa_config():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT valor FROM configuracoes WHERE chave = 'dados_empresa'")
        row = cursor.fetchone()
        if row:
            return json.loads(row["valor"])
    return {
        "nome_empresa": "Marcenaria Pro Móveis Planejados",
        "cnpj": "00.000.000/0001-00",
        "telefone_empresa": "(11) 98888-7777",
        "pix": "contato@marcenaria.com"
    }

def get_estoque_atual():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM estoque")
        return cursor.fetchall()

def get_metricas_financeiras():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT preco_venda, lucro_liquido, status, valor_recebido FROM orcamentos")
        rows = cursor.fetchall()
        
        total_orcamentos = len(rows)
        faturamento_total = 0.0
        lucro_acumulado = 0.0
        total_recebido = 0.0
        aprovados = 0
        
        for r in rows:
            st = r["status"] or "Em Negociação"
            pv = float(r["preco_venda"] or 0.0)
            lucro = float(r["lucro_liquido"] or 0.0)
            rec = float(r["valor_recebido"] or 0.0)
            
            if st in ["Aprovado", "Em Produção", "Entregue"]:
                faturamento_total += pv
                lucro_acumulado += lucro
                total_recebido += rec
                aprovados += 1

        taxa_conversao = (aprovados / total_orcamentos * 100.0) if total_orcamentos > 0 else 0.0
        ticket_medio = (faturamento_total / aprovados) if aprovados > 0 else 0.0
        saldo_a_receber = max(faturamento_total - total_recebido, 0.0)
        
        return {
            "total_orcamentos": total_orcamentos,
            "aprovados": aprovados,
            "faturamento_total": faturamento_total,
            "lucro_acumulado": lucro_acumulado,
            "total_recebido": total_recebido,
            "saldo_a_receber": saldo_a_receber,
            "ticket_medio": ticket_medio,
            "taxa_conversao": taxa_conversao
        }

CURRENT_DATA = {
    "user": "admin@marcenaria.com",
    "user_perfil": "admin",
    "user_nome": "Administrador",
    "orcamento_id": None,
    "status": "Em Negociação",
    "cliente_nome": "Cliente Exemplo",
    "cliente_telefone": "11999998888",
    "cliente_ambiente": "Casa Completa / Múltiplos Ambientes",
    "prazo_entrega": "25 dias úteis",
    "data_entrega_prevista": (date.today() + timedelta(days=25)).strftime("%Y-%m-%d"),
    "entrada_valor": 1000.0,
    "num_parcelas": 3,
    "forma_pagamento": "Entrada + Cartão de Crédito",
    "estoque_baixado": 0,
    "valor_recebido": 1000.0,
    "imagens": [],
    "ambientes": ["Cozinha Planejada"],
    "observacoes_tecnicas": "",
    "custo_materiais": 0.0,
    "dias_producao": 3,
    "valor_diaria": 180.0,
    "custo_frete": 250.0,
    "custo_montagem": 350.0,
    "imposto_pct": 6.0,
    "comissao_pct": 4.0,
    "markup": 2.2,
    "items": []
}

def numero_extenso_reais(valor: float) -> str:
    inteiro = int(valor)
    centavos = int(round((valor - inteiro) * 100))
    unidades = ["", "um", "dois", "três", "quatro", "cinco", "seis", "sete", "oito", "nove"]
    de_10_a_19 = ["dez", "onze", "doze", "treze", "quatorze", "quinze", "dezesseis", "dezessete", "dezoito", "dezenove"]
    dezenas = ["", "", "vinte", "trinta", "quarenta", "cinquenta", "sessenta", "setenta", "oitenta", "noventa"]
    centenas = ["", "cento", "duzentos", "trezentos", "quatrocentos", "quinhentos", "seiscentos", "setecentos", "oitocentos", "novecentos"]

    def converter_grupo(n):
        if n == 100:
            return "cem"
        c = n // 100
        d = (n % 100) // 10
        u = n % 10
        partes = []
        if c > 0:
            partes.append(centenas[c])
        if d == 1:
            partes.append(de_10_a_19[u])
        else:
            if d > 1:
                partes.append(dezenas[d])
            if u > 0:
                partes.append(unidades[u])
        return " e ".join(partes)

    if inteiro == 0:
        texto = "zero reais"
    elif inteiro == 1:
        texto = "um real"
    else:
        milhares = inteiro // 1000
        resto = inteiro % 1000
        partes_mil = []
        if milhares > 0:
            partes_mil.append("mil" if milhares == 1 else f"{converter_grupo(milhares)} mil")
        if resto > 0:
            partes_mil.append(converter_grupo(resto))
        texto = " e ".join(partes_mil) + " reais"

    if centavos > 0:
        texto += f" e {centavos}/100 centavos"
    return texto.capitalize()

def calcular_engenharia_avancada(
    ambientes_selecionados: list,
    area_m2_total: float,
    espessura_caixa: str,
    espessura_tamponamento: str,
    cor_mdf: str,
    modelo_portas: str,
    nivel_ferragens: str,
    precos: dict
):
    items = []
    fator_caixa = 1.0 if "15mm" in espessura_caixa else 1.15

    if "Sem Tamponamento" in espessura_tamponamento:
        fator_tamp = 1.0
    elif "18mm" in espessura_tamponamento:
        fator_tamp = 1.18
    elif "25mm" in espessura_tamponamento:
        fator_tamp = 1.30
    else:
        fator_tamp = 1.45

    if "Branco" in cor_mdf:
        fator_cor = 1.0
    elif "Madeirado" in cor_mdf:
        fator_cor = 1.30
    elif "Grafite" in cor_mdf or "Matt" in cor_mdf:
        fator_cor = 1.40
    else:
        fator_cor = 1.60

    if "Lisa Tradicional" in modelo_portas:
        fator_portas = 1.0
    elif "Cava Usinada" in modelo_portas:
        fator_portas = 1.20
    elif "Perfil Gola" in modelo_portas:
        fator_portas = 1.25
    else:
        fator_portas = 1.55

    preco_dob = precos["dobradica"] * (1.8 if "Premium" in nivel_ferragens else 1.0)
    preco_corr = precos["corredica"] * (2.2 if "Premium" in nivel_ferragens else 1.0)
    custo_m2_mdf_base = precos["mdf_m2"] * fator_caixa * fator_tamp * fator_cor * fator_portas

    area_val = max(area_m2_total, 5.0)
    qtd_ambientes = max(len(ambientes_selecionados), 1)
    area_por_comodo = area_val / qtd_ambientes

    for amb in ambientes_selecionados:
        if "Cozinha" in amb or "Gourmet" in amb:
            m_lin = max(area_por_comodo * 0.35, 2.5)
            num_modulos = max(int(math.ceil(m_lin / 0.8)), 2)
            
            for i in range(1, num_modulos + 1):
                items.append({
                    "nome": f"Balcão Inferior #{i} ({espessura_caixa}) - {amb}", "tipo": "Chapa MDF / Painel", "ambiente": amb,
                    "largura": 800, "altura": 720, "dimensoes": "800 x 720 x 580 mm", "qtd": 1,
                    "valor": 1.25 * custo_m2_mdf_base
                })
                items.append({
                    "nome": f"Portas Balcão #{i} ({modelo_portas})", "tipo": "Chapa MDF / Painel", "ambiente": amb,
                    "largura": 395, "altura": 700, "dimensoes": "395 x 700 x 18 mm", "qtd": 2,
                    "valor": 0.58 * custo_m2_mdf_base
                })
                items.append({
                    "nome": f"Armário Aéreo #{i} ({amb})", "tipo": "Chapa MDF / Painel", "ambiente": amb,
                    "largura": 800, "altura": 700, "dimensoes": "800 x 700 x 350 mm", "qtd": 1,
                    "valor": 0.98 * custo_m2_mdf_base
                })
            
            items.append({
                "nome": f"Gaveteiro Triplo ({nivel_ferragens})", "tipo": "Ferragem (Corrediça)", "ambiente": amb,
                "largura": 600, "altura": 720, "dimensoes": "600 mm", "qtd": 3,
                "valor": (3 * preco_corr) + (1.4 * custo_m2_mdf_base)
            })
            qtd_dob = (num_modulos * 4) + 4
            items.append({"nome": f"Dobradiças ({nivel_ferragens})", "tipo": "Ferragem (Dobradiça)", "ambiente": amb, "largura": 0, "altura": 0, "dimensoes": "Ø35mm", "qtd": qtd_dob, "valor": qtd_dob * preco_dob})
            items.append({"nome": f"Puxadores ({modelo_portas})", "tipo": "Acessório (Puxador)", "ambiente": amb, "largura": 0, "altura": 0, "dimensoes": "Kit", "qtd": qtd_dob // 2, "valor": (qtd_dob // 2) * precos["puxador"]})
            items.append({"nome": f"Fita de Borda PVC 22mm ({amb})", "tipo": "Fita de Borda", "ambiente": amb, "largura": 0, "altura": 0, "dimensoes": "-", "qtd": int(m_lin * 20), "valor": (m_lin * 20) * precos["fita_borda_m"]})

        elif "Dormitório" in amb or "Suíte" in amb or "Closet" in amb:
            m_lin = max(area_por_comodo * 0.28, 2.0)
            num_portas = max(int(round(m_lin / 0.5)), 2)
            
            items.append({"nome": f"Laterais Roupeiro ({espessura_caixa}) - {amb}", "tipo": "Chapa MDF / Painel", "ambiente": amb, "largura": 2600, "altura": 600, "dimensoes": "2600 x 600 x 18 mm", "qtd": num_portas + 1, "valor": (num_portas + 1) * (2.6 * 0.6 * custo_m2_mdf_base)})
            items.append({"nome": f"Portas Armário ({modelo_portas})", "tipo": "Chapa MDF / Painel", "ambiente": amb, "largura": 2500, "altura": 500, "dimensoes": "2500 x 500 x 18 mm", "qtd": num_portas, "valor": num_portas * (2.5 * 0.5 * custo_m2_mdf_base)})
            items.append({"nome": f"Divisórias e Maleiros ({amb})", "tipo": "Chapa MDF / Painel", "ambiente": amb, "largura": 900, "altura": 550, "dimensoes": "900 x 550 x 18 mm", "qtd": num_portas * 2, "valor": (num_portas * 2) * (0.9 * 0.55 * custo_m2_mdf_base)})
            items.append({"nome": f"Gavetas Internas ({nivel_ferragens})", "tipo": "Ferragem (Corrediça)", "ambiente": amb, "largura": 0, "altura": 0, "dimensoes": "450 mm", "qtd": 4, "valor": 4 * preco_corr})
            items.append({"nome": f"Dobradiças ({nivel_ferragens})", "tipo": "Ferragem (Dobradiça)", "ambiente": amb, "largura": 0, "altura": 0, "dimensoes": "Ø35mm", "qtd": num_portas * 4, "valor": (num_portas * 4) * preco_dob})
            items.append({"nome": f"Fita de Borda PVC ({amb})", "tipo": "Fita de Borda", "ambiente": amb, "largura": 0, "altura": 0, "dimensoes": "-", "qtd": int(m_lin * 22), "valor": (m_lin * 22) * precos["fita_borda_m"]})

        elif "Banheiro" in amb or "Lavabo" in amb:
            items.append({"nome": f"Gabinete Sob Medida c/ Gavetas ({amb})", "tipo": "Chapa MDF / Painel", "ambiente": amb, "largura": 900, "altura": 650, "dimensoes": "900 x 650 x 500 mm", "qtd": 1, "valor": 1.4 * custo_m2_mdf_base})
            items.append({"nome": f"Espelheira / Aéreo ({amb})", "tipo": "Chapa MDF / Painel", "ambiente": amb, "largura": 900, "altura": 800, "dimensoes": "900 x 800 x 150 mm", "qtd": 1, "valor": 0.85 * custo_m2_mdf_base})
            items.append({"nome": f"Corrediças e Dobradiças ({nivel_ferragens})", "tipo": "Ferragem (Corrediça)", "ambiente": amb, "largura": 0, "altura": 0, "dimensoes": "Kit", "qtd": 2, "valor": 2 * preco_corr})

        else:
            items.append({"nome": f"Painel Ripado / Rack ({espessura_tamponamento}) - {amb}", "tipo": "Chapa MDF / Painel", "ambiente": amb, "largura": 2200, "altura": 1800, "dimensoes": "2200 x 1800 x 18 mm", "qtd": 1, "valor": (2.2 * 1.8 * custo_m2_mdf_base)})
            items.append({"nome": f"Bancada Suspensa c/ Portas Basculantes ({amb})", "tipo": "Chapa MDF / Painel", "ambiente": amb, "largura": 2200, "altura": 400, "dimensoes": "2200 x 400 x 400 mm", "qtd": 1, "valor": 1.2 * custo_m2_mdf_base})
            items.append({"nome": f"Pistões e Articulações ({nivel_ferragens})", "tipo": "Ferragem (Dobradiça)", "ambiente": amb, "largura": 0, "altura": 0, "dimensoes": "Kit", "qtd": 4, "valor": 4 * preco_dob})

    total_mat = sum(i["valor"] for i in items)
    return items, total_mat

def render_login_page(msg_erro=""):
    erro_tag = f"<p class='text-rose-400 text-xs text-center bg-rose-950/60 border border-rose-800 p-2 rounded-lg'>{msg_erro}</p>" if msg_erro else ""
    return f"""
    <!DOCTYPE html>
    <html lang="pt-br">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Marcenaria SaaS - Login</title>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-slate-900 text-slate-100 flex items-center justify-center min-h-screen p-4 font-sans">
        <div class="max-w-md w-full bg-slate-800 border border-slate-700 rounded-2xl p-8 shadow-2xl space-y-6">
            <div class="text-center space-y-2">
                <h1 class="text-2xl font-bold tracking-tight text-white">Marcenaria Pro SaaS</h1>
                <p class="text-xs text-slate-400">Painel de Gestão e Captação de Projetos</p>
            </div>
            {erro_tag}
            <form action="/painel" method="post" class="space-y-4">
                <div>
                    <label class="block text-xs font-semibold text-slate-300 uppercase mb-1">E-mail</label>
                    <input type="email" name="username" required value="admin@marcenaria.com" class="w-full px-4 py-2.5 bg-slate-900 border border-slate-700 rounded-lg text-sm focus:outline-none focus:border-sky-500 text-slate-200">
                </div>
                <div>
                    <label class="block text-xs font-semibold text-slate-300 uppercase mb-1">Senha</label>
                    <input type="password" name="password" required value="123456" class="w-full px-4 py-2.5 bg-slate-900 border border-slate-700 rounded-lg text-sm focus:outline-none focus:border-sky-500 text-slate-200">
                </div>
                <button type="submit" class="w-full py-3 bg-sky-600 hover:bg-sky-500 text-white font-semibold rounded-lg text-sm transition-colors shadow-lg shadow-sky-600/30">
                    Acessar Painel de Controle
                </button>
            </form>
            <div class="border-t border-slate-700/60 pt-4 text-center">
                <a href="/solicitar-orcamento" target="_blank" class="text-xs text-emerald-400 hover:underline font-medium block mb-2">🔗 Ver Formulário de Captação (Instagram)</a>
                <p class="text-[11px] text-slate-400">Admin: <b>admin@marcenaria.com</b> | Senha: <b>123456</b></p>
            </div>
        </div>
    </body>
    </html>
    """

def render_pagina_captacao(sucesso=False, orc_id=None, estimativa=0.0):
    empresa = get_empresa_config()
    msg_sucesso = f"""
    <div class="bg-emerald-950/90 border border-emerald-600 p-6 rounded-2xl text-center space-y-4 shadow-2xl">
        <span class="text-5xl block animate-bounce">✨</span>
        <h2 class="text-xl font-bold text-white">Planta, Especificações & Estimativa Geradas!</h2>
        <div class="bg-slate-950 p-4 rounded-xl border border-emerald-800 inline-block text-left space-y-1">
            <p class="text-xs text-slate-400">Estimativa Orçamentária Inicial:</p>
            <p class="text-2xl font-bold text-emerald-400">R$ {estimativa:,.2f}</p>
            <p class="text-[11px] text-slate-400">Entrada + Parcelamento facilitado em até 12x</p>
        </div>
        <p class="text-xs text-slate-300">Nossa equipe de engenharia da <b>{empresa['nome_empresa']}</b> já recebeu sua solicitação.</p>
        <a href="https://api.whatsapp.com/send?phone=55{empresa['telefone_empresa'].replace('(', '').replace(')', '').replace('-', '').replace(' ', '')}&text=Olá! Enviei minha planta e especificações no site (Projeto #{orc_id}) e gostaria de dar andamento!" target="_blank" class="inline-block px-6 py-3 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold rounded-xl shadow-lg transition-colors">
            💬 Falar com Projetista no WhatsApp
        </a>
    </div>
    """ if sucesso else ""

    formulario = f"""
    <form action="/enviar-solicitacao-lead" method="post" enctype="multipart/form-data" class="space-y-4 bg-slate-900 border border-slate-800 p-6 sm:p-8 rounded-2xl shadow-2xl">
        <div class="space-y-1 border-b border-slate-800 pb-3">
            <h2 class="text-lg font-bold text-white">✨ Simulador Completo de Marcenaria Sob Medida</h2>
            <p class="text-xs text-slate-400">Envie a planta baixa, selecione os ambientes e escolha os materiais para receber o orçamento instantâneo.</p>
        </div>

        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
                <label class="block text-xs font-semibold text-slate-300 uppercase mb-1">Seu Nome Completo</label>
                <input type="text" name="nome" required placeholder="Ex: Mariana Silva" class="w-full px-4 py-2.5 bg-slate-950 border border-slate-700 rounded-xl text-sm text-white focus:outline-none focus:border-sky-500">
            </div>
            <div>
                <label class="block text-xs font-semibold text-slate-300 uppercase mb-1">Seu WhatsApp (com DDD)</label>
                <input type="text" name="whatsapp" required placeholder="Ex: (11) 99999-8888" class="w-full px-4 py-2.5 bg-slate-950 border border-slate-700 rounded-xl text-sm text-white focus:outline-none focus:border-sky-500">
            </div>
        </div>

        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
                <label class="block text-xs font-semibold text-slate-300 uppercase mb-1">Área Total do Imóvel ou Espaço (m²)</label>
                <input type="number" step="any" min="5.0" max="2000.0" name="area_m2_total" value="68.5" placeholder="Ex: 68.5" required class="w-full px-4 py-2.5 bg-slate-950 border border-slate-700 rounded-xl text-sm text-white focus:outline-none focus:border-sky-500">
                <span class="text-[10px] text-slate-500 block mt-1">Ex: 68.5 m² (Apartamento/Casa) ou 14.2 m² (Cômodo único).</span>
            </div>
            <div>
                <label class="block text-xs font-semibold text-slate-300 uppercase mb-1">Cidade / Bairro da Obra</label>
                <input type="text" name="cidade" required placeholder="Ex: São Paulo / Moema" class="w-full px-4 py-2.5 bg-slate-950 border border-slate-700 rounded-xl text-sm text-white focus:outline-none focus:border-sky-500">
            </div>
        </div>

        <div>
            <label class="block text-xs font-semibold text-slate-300 uppercase mb-2">Ambientes a Serem Mobiliados (Marque todos):</label>
            <div class="grid grid-cols-2 sm:grid-cols-3 gap-2 text-xs">
                <label class="flex items-center space-x-2 bg-slate-950 p-2.5 rounded-lg border border-slate-800 cursor-pointer hover:border-sky-600">
                    <input type="checkbox" name="ambientes_check" value="Cozinha Planejada" checked class="rounded text-sky-600">
                    <span>🍳 Cozinha</span>
                </label>
                <label class="flex items-center space-x-2 bg-slate-950 p-2.5 rounded-lg border border-slate-800 cursor-pointer hover:border-sky-600">
                    <input type="checkbox" name="ambientes_check" value="Lavanderia" checked class="rounded text-sky-600">
                    <span>🧺 Lavanderia</span>
                </label>
                <label class="flex items-center space-x-2 bg-slate-950 p-2.5 rounded-lg border border-slate-800 cursor-pointer hover:border-sky-600">
                    <input type="checkbox" name="ambientes_check" value="Dormitório Casal / Closet" checked class="rounded text-sky-600">
                    <span>🛏️ Suíte Casal</span>
                </label>
                <label class="flex items-center space-x-2 bg-slate-950 p-2.5 rounded-lg border border-slate-800 cursor-pointer hover:border-sky-600">
                    <input type="checkbox" name="ambientes_check" value="Dormitório 2 / Infantil" class="rounded text-sky-600">
                    <span>🧸 Quarto 2 / Office</span>
                </label>
                <label class="flex items-center space-x-2 bg-slate-950 p-2.5 rounded-lg border border-slate-800 cursor-pointer hover:border-sky-600">
                    <input type="checkbox" name="ambientes_check" value="Banheiros" checked class="rounded text-sky-600">
                    <span>🚿 Banheiros</span>
                </label>
                <label class="flex items-center space-x-2 bg-slate-950 p-2.5 rounded-lg border border-slate-800 cursor-pointer hover:border-sky-600">
                    <input type="checkbox" name="ambientes_check" value="Sala / Painel Home TV" class="rounded text-sky-600">
                    <span>📺 Sala / Home</span>
                </label>
            </div>
        </div>

        <div class="bg-slate-950 p-4 rounded-xl border border-slate-800 space-y-3">
            <h3 class="text-xs font-bold text-sky-400 uppercase tracking-wide">⚙️ Especificações Técnicas de Marcenaria</h3>
            
            <div class="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
                <div>
                    <label class="block text-slate-300 font-medium mb-1">Espessura da Caixa</label>
                    <select name="espessura_caixa" class="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-white">
                        <option value="MDF 15mm">MDF 15mm (Padrão)</option>
                        <option value="MDF 18mm">MDF 18mm (Reforçado)</option>
                    </select>
                </div>
                <div>
                    <label class="block text-slate-300 font-medium mb-1">Tamponamento</label>
                    <select name="espessura_tamponamento" class="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-white">
                        <option value="Tamponamento 18mm">Tamponamento 18mm</option>
                        <option value="Tamponamento 25mm">Tamponamento 25mm</option>
                        <option value="Tamponamento 36mm Engrossado">Tamponamento 36mm Engrossado</option>
                        <option value="Sem Tamponamento">Sem Tamponamento</option>
                    </select>
                </div>
                <div>
                    <label class="block text-slate-300 font-medium mb-1">Cor / Padrão MDF</label>
                    <select name="cor_mdf" class="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-white">
                        <option value="Branco TX Essencial">Branco TX Essencial</option>
                        <option value="Madeirado Nobre (Freijó / Carvalho)">Madeirado Nobre</option>
                        <option value="Cores Unicolores (Grafite / Preto)">Cinza Grafite / Preto Matt</option>
                    </select>
                </div>
            </div>

            <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                <div>
                    <label class="block text-slate-300 font-medium mb-1">Modelo das Portas</label>
                    <select name="modelo_portas" class="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-white">
                        <option value="Lisa Tradicional com Puxador Externo">Lisa Tradicional</option>
                        <option value="Cava Usinada na Madeira (Usinado)">Cava Usinada na Madeira</option>
                        <option value="Perfil Gola em Alumínio">Perfil Gola em Alumínio</option>
                        <option value="Perfil Slim com Vidro Reflecta">Perfil Slim com Vidro Reflecta</option>
                    </select>
                </div>
                <div>
                    <label class="block text-slate-300 font-medium mb-1">Nível das Ferragens</label>
                    <select name="nivel_ferragens" class="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-white">
                        <option value="Padrão c/ Amortecedor Slowmotion">Padrão com Amortecimento</option>
                        <option value="Linha Premium Oculta (Extração Total)">Linha Premium Oculta</option>
                    </select>
                </div>
            </div>
        </div>

        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div class="bg-slate-950 p-3.5 rounded-xl border border-slate-800 space-y-1">
                <label class="block text-xs font-bold text-sky-400 uppercase">📐 1. Planta Baixa Completa</label>
                <input type="file" name="planta" accept="image/*" required class="block w-full text-xs text-slate-400 file:mr-3 file:py-1.5 file:px-3 file:rounded-lg file:border-0 file:text-xs file:font-semibold file:bg-sky-900 file:text-white hover:file:bg-sky-800 cursor-pointer">
            </div>
            <div class="bg-slate-950 p-3.5 rounded-xl border border-slate-800 space-y-1">
                <label class="block text-xs font-bold text-purple-400 uppercase">🖼️ 2. Inspiração / Estilo (Opcional)</label>
                <input type="file" name="inspiracao" accept="image/*" class="block w-full text-xs text-slate-400 file:mr-3 file:py-1.5 file:px-3 file:rounded-lg file:border-0 file:text-xs file:font-semibold file:bg-purple-900 file:text-white hover:file:bg-purple-800 cursor-pointer">
            </div>
        </div>

        <div>
            <label class="block text-xs font-semibold text-slate-300 uppercase mb-1">Observações e Detalhes Especiais (Opcional)</label>
            <textarea name="descricao" rows="2" placeholder="Ex: Iluminação em fita LED nos aéreos, torre quente na cozinha, portas de espelho no dormitório..." class="w-full px-4 py-2.5 bg-slate-950 border border-slate-700 rounded-xl text-sm text-white focus:outline-none focus:border-sky-500"></textarea>
        </div>

        <button type="submit" class="w-full py-3.5 bg-sky-600 hover:bg-sky-500 text-white font-bold rounded-xl text-sm transition-colors shadow-lg shadow-sky-600/30 flex items-center justify-center space-x-2">
            <span>⚡ Calcular Engenharia & Gerar Estimativa Instantânea</span>
        </button>
    </form>
    """ if not sucesso else ""

    return f"""
    <!DOCTYPE html>
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
                <div class="w-9 h-9 rounded-xl bg-sky-600 flex items-center justify-center font-bold text-white shadow-md">M</div>
                <span class="font-bold text-base sm:text-lg text-white tracking-wide">{empresa['nome_empresa']}</span>
            </div>
            <span class="text-xs text-sky-400 font-medium">Marcenaria Sob Medida</span>
        </header>

        <main class="max-w-3xl w-full mx-auto p-4 sm:p-6 my-auto">
            {msg_sucesso}
            {formulario}
        </main>

        <footer class="bg-slate-900 border-t border-slate-800 p-4 text-center text-xs text-slate-500">
            <p>{empresa['nome_empresa']} | Atendimento WhatsApp: {empresa['telefone_empresa']}</p>
        </footer>
    </body>
    </html>
    """

@app.get("/", response_class=HTMLResponse)
def home():
    return render_login_page()

@app.get("/solicitar-orcamento", response_class=HTMLResponse)
def solicitar_orcamento():
    return render_pagina_captacao()

@app.get("/painel", response_class=HTMLResponse)
def painel_direto():
    return render_dashboard(data=CURRENT_DATA)

@app.get("/painel-get", response_class=HTMLResponse)
def painel_get():
    return render_dashboard(data=CURRENT_DATA)

@app.post("/painel", response_class=HTMLResponse)
def login(username: str = Form(...), password: str = Form(...)):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM usuarios WHERE email = ? AND senha = ?", (username, password))
        user_row = cursor.fetchone()
        
        if not user_row:
            return render_login_page("E-mail ou senha incorretos. Tente novamente.")

        CURRENT_DATA["user"] = user_row["email"]
        CURRENT_DATA["user_nome"] = user_row["nome"]
        CURRENT_DATA["user_perfil"] = user_row["perfil"]

    return render_dashboard(data=CURRENT_DATA)

@app.post("/enviar-solicitacao-lead", response_class=HTMLResponse)
async def enviar_solicitacao_lead(
    nome: str = Form(...),
    whatsapp: str = Form(...),
    area_m2_total: float = Form(68.5),
    espessura_caixa: str = Form("MDF 15mm"),
    espessura_tamponamento: str = Form("Tamponamento 18mm"),
    cor_mdf: str = Form("Branco TX Essencial"),
    modelo_portas: str = Form("Perfil Gola em Alumínio"),
    nivel_ferragens: str = Form("Padrão c/ Amortecedor Slowmotion"),
    ambientes_check: List[str] = Form(["Cozinha Planejada"]),
    cidade: str = Form(...),
    descricao: str = Form(""),
    planta: UploadFile = File(...),
    inspiracao: UploadFile = File(None)
):
    agora = datetime.now().strftime("%d/%m/%Y %H:%M")
    imagens_lead = []
    
    contents_planta = await planta.read()
    if contents_planta:
        img_b64 = base64.b64encode(contents_planta).decode("utf-8")
        imagens_lead.append(img_b64)

    if inspiracao:
        try:
            contents_insp = await inspiracao.read()
            if contents_insp:
                img_insp_b64 = base64.b64encode(contents_insp).decode("utf-8")
                imagens_lead.append(img_insp_b64)
        except Exception:
            pass

    precos = get_precos_config()
    items_auto, total_mat = calcular_engenharia_avancada(
        ambientes_check, area_m2_total, espessura_caixa, espessura_tamponamento,
        cor_mdf, modelo_portas, nivel_ferragens, precos
    )
    
    qtd_comodos = max(len(ambientes_check), 1)
    dias_prod = max(int(math.ceil(qtd_comodos * 2.5)), 3)
    custo_mo = dias_prod * 180.0
    custo_frete_mont = max(qtd_comodos * 350.0, 600.0)
    markup = 2.2
    
    pv_estimado = (total_mat + custo_mo + custo_frete_mont) * markup
    lucro_estimado = pv_estimado - (total_mat + custo_mo + custo_frete_mont + (pv_estimado * 0.10))

    nome_ambientes_str = " + ".join(ambientes_check)
    obs_completa = f"Lead {area_m2_total}m² ({cidade}) | Caixa: {espessura_caixa} | Tamp: {espessura_tamponamento} | Cor: {cor_mdf} | Portas: {modelo_portas} | Ferragens: {nivel_ferragens}"
    if descricao:
        obs_completa += f" | Detalhes: {descricao}"

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO orcamentos (
                criado_em, cliente_nome, cliente_telefone, cliente_ambiente,
                prazo_entrega, data_entrega_prevista, status, custo_materiais,
                custo_mao_obra, custo_frete_montagem, imposto_pct, comissao_pct,
                markup, preco_venda, lucro_liquido, entrada_valor, num_parcelas,
                forma_pagamento, valor_recebido, imagens_json, ambientes_json,
                observacoes_tecnicas, items_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            agora,
            nome,
            whatsapp,
            nome_ambientes_str,
            "25 dias úteis",
            (date.today() + timedelta(days=25)).strftime("%Y-%m-%d"),
            "Novo Lead Instagram",
            total_mat, custo_mo, custo_frete_mont, 6.0, 4.0, markup,
            pv_estimado, lucro_estimado, pv_estimado * 0.3, 3,
            "Entrada + 3x no Cartão", 0.0, json.dumps(imagens_lead), json.dumps(ambientes_check),
            obs_completa, json.dumps(items_auto)
        ))
        conn.commit()
        novo_id = cursor.lastrowid

    return render_pagina_captacao(sucesso=True, orc_id=novo_id, estimativa=pv_estimado)

@app.post("/adicionar-ambiente", response_class=HTMLResponse)
def adicionar_ambiente(novo_ambiente: str = Form(...)):
    if "ambientes" not in CURRENT_DATA:
        CURRENT_DATA["ambientes"] = []
    if novo_ambiente and novo_ambiente not in CURRENT_DATA["ambientes"]:
        CURRENT_DATA["ambientes"].append(novo_ambiente)
        CURRENT_DATA["cliente_ambiente"] = " + ".join(CURRENT_DATA["ambientes"])
    return RedirectResponse(url="/painel-get", status_code=303)

@app.post("/remover-ambiente", response_class=HTMLResponse)
def remover_ambiente(ambiente_nome: str = Form(...)):
    if "ambientes" in CURRENT_DATA and ambiente_nome in CURRENT_DATA["ambientes"]:
        CURRENT_DATA["ambientes"].remove(ambiente_nome)
        CURRENT_DATA["cliente_ambiente"] = " + ".join(CURRENT_DATA["ambientes"]) if CURRENT_DATA["ambientes"] else "Geral"
    return RedirectResponse(url="/painel-get", status_code=303)

@app.post("/upload-imagem", response_class=HTMLResponse)
async def upload_imagem(foto: UploadFile = File(...)):
    contents = await foto.read()
    if contents:
        img_b64 = base64.b64encode(contents).decode("utf-8")
        if "imagens" not in CURRENT_DATA:
            CURRENT_DATA["imagens"] = []
        CURRENT_DATA["imagens"].append(img_b64)
    return RedirectResponse(url="/painel-get", status_code=303)

@app.post("/remover-imagem", response_class=HTMLResponse)
def remover_imagem(img_index: int = Form(...)):
    if "imagens" in CURRENT_DATA and 0 <= img_index < len(CURRENT_DATA["imagens"]):
        CURRENT_DATA["imagens"].pop(img_index)
    return RedirectResponse(url="/painel-get", status_code=303)

@app.get("/exportar-csv")
def exportar_csv():
    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')
    
    writer.writerow([
        "ID", "Data/Hora", "Cliente", "Telefone", "Ambiente", "Prazo Entrega", "Data Prevista",
        "Status", "Custo Materiais (R$)", "Mao de Obra (R$)", "Frete e Montagem (R$)",
        "Impostos (%)", "Comissao (%)", "Markup", "Preco Venda (R$)", "Lucro Liquido (R$)",
        "Entrada (R$)", "Num Parcelas", "Valor Recebido (R$)", "Forma Pagamento", "Estoque Baixado"
    ])
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM orcamentos ORDER BY id DESC")
        for r in cursor.fetchall():
            writer.writerow([
                r["id"], r["criado_em"], r["cliente_nome"], r["cliente_telefone"], r["cliente_ambiente"],
                r["prazo_entrega"], r["data_entrega_prevista"] or "-", r["status"], f"{r['custo_materiais']:.2f}",
                f"{r['custo_mao_obra']:.2f}", f"{r['custo_frete_montagem']:.2f}", r["imposto_pct"],
                r["comissao_pct"], r["markup"], f"{r['preco_venda']:.2f}", f"{r['lucro_liquido']:.2f}",
                f"{r['entrada_valor'] or 0.0:.2f}", r["num_parcelas"] or 1, f"{r['valor_recebido'] or 0.0:.2f}",
                r["forma_pagamento"] or "PIX", "Sim" if r["estoque_baixado"] else "Nao"
            ])
            
    output.seek(0)
    nome_arquivo = f"relatorio-financeiro-marcenaria-{date.today().strftime('%d-%m-%Y')}.csv"
    return Response(
        content=output.getvalue().encode('utf-8-sig'),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={nome_arquivo}"}
    )

@app.post("/salvar-empresa", response_class=HTMLResponse)
def salvar_empresa(nome_empresa: str = Form(...), cnpj: str = Form(...), telefone_empresa: str = Form(...), pix: str = Form(...)):
    if CURRENT_DATA.get("user_perfil") == "admin":
        dados = {
            "nome_empresa": nome_empresa,
            "cnpj": cnpj,
            "telefone_empresa": telefone_empresa,
            "pix": pix
        }
        set_empresa_config(dados)
    return RedirectResponse(url="/painel-get", status_code=303)

@app.post("/adicionar-estoque", response_class=HTMLResponse)
def adicionar_estoque(codigo: str = Form(...), quantidade: float = Form(...)):
    if CURRENT_DATA.get("user_perfil") == "admin":
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE estoque SET quantidade = quantidade + ? WHERE codigo = ?", (quantidade, codigo))
            conn.commit()
    return RedirectResponse(url="/painel-get", status_code=303)

@app.post("/dar-baixa-estoque", response_class=HTMLResponse)
def dar_baixa_estoque(orcamento_id: int = Form(...)):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT items_json, estoque_baixado FROM orcamentos WHERE id = ?", (orcamento_id,))
        row = cursor.fetchone()
        if row and not row["estoque_baixado"]:
            items = json.loads(row["items_json"]) if row["items_json"] else []
            compras = consolidar_compras_e_nesting(items)
            
            cursor.execute("UPDATE estoque SET quantidade = MAX(quantidade - ?, 0) WHERE codigo = 'mdf'", (compras["chapas_mdf"],))
            cursor.execute("UPDATE estoque SET quantidade = MAX(quantidade - ?, 0) WHERE codigo = 'fita'", (compras["fita_metros"],))
            cursor.execute("UPDATE estoque SET quantidade = MAX(quantidade - ?, 0) WHERE codigo = 'dobradica'", (compras["dobradicas"],))
            cursor.execute("UPDATE estoque SET quantidade = MAX(quantidade - ?, 0) WHERE codigo = 'corredica'", (compras["corredicas"],))
            cursor.execute("UPDATE estoque SET quantidade = MAX(quantidade - ?, 0) WHERE codigo = 'puxador'", (compras["puxadores"],))
            
            cursor.execute("UPDATE orcamentos SET estoque_baixado = 1 WHERE id = ?", (orcamento_id,))
            conn.commit()
            
    return RedirectResponse(url="/painel-get", status_code=303)

@app.post("/salvar-pagamento", response_class=HTMLResponse)
def salvar_pagamento(entrada_valor: float = Form(0.0), num_parcelas: int = Form(1), valor_recebido: float = Form(0.0), forma_pagamento: str = Form("PIX")):
    CURRENT_DATA["entrada_valor"] = entrada_valor
    CURRENT_DATA["num_parcelas"] = num_parcelas
    CURRENT_DATA["valor_recebido"] = valor_recebido
    CURRENT_DATA["forma_pagamento"] = forma_pagamento
    return RedirectResponse(url="/painel-get", status_code=303)

@app.post("/atualizar-status", response_class=HTMLResponse)
def atualizar_status(orcamento_id: int = Form(...), novo_status: str = Form(...)):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE orcamentos SET status = ? WHERE id = ?", (novo_status, orcamento_id))
        conn.commit()
    if CURRENT_DATA.get("orcamento_id") == orcamento_id:
        CURRENT_DATA["status"] = novo_status
    return RedirectResponse(url="/painel-get", status_code=303)

@app.post("/criar-usuario", response_class=HTMLResponse)
def criar_usuario(nome: str = Form(...), email: str = Form(...), senha: str = Form(...), perfil: str = Form(...)):
    if CURRENT_DATA.get("user_perfil") == "admin":
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO usuarios (email, senha, nome, perfil) VALUES (?, ?, ?, ?)", (email, senha, nome, perfil))
            conn.commit()
    return RedirectResponse(url="/painel-get", status_code=303)

@app.get("/novo-orcamento", response_class=HTMLResponse)
def novo_orcamento():
    CURRENT_DATA["orcamento_id"] = None
    CURRENT_DATA["status"] = "Em Negociação"
    CURRENT_DATA["cliente_nome"] = "Novo Cliente"
    CURRENT_DATA["cliente_telefone"] = ""
    CURRENT_DATA["cliente_ambiente"] = "Apartamento Completo"
    CURRENT_DATA["prazo_entrega"] = "20 dias úteis"
    CURRENT_DATA["data_entrega_prevista"] = (date.today() + timedelta(days=20)).strftime("%Y-%m-%d")
    CURRENT_DATA["entrada_valor"] = 0.0
    CURRENT_DATA["num_parcelas"] = 1
    CURRENT_DATA["valor_recebido"] = 0.0
    CURRENT_DATA["forma_pagamento"] = "PIX / Transferência"
    CURRENT_DATA["estoque_baixado"] = 0
    CURRENT_DATA["imagens"] = []
    CURRENT_DATA["ambientes"] = ["Cozinha", "Dormitório Casal"]
    CURRENT_DATA["observacoes_tecnicas"] = ""
    CURRENT_DATA["custo_materiais"] = 0.0
    CURRENT_DATA["dias_producao"] = 3
    CURRENT_DATA["valor_diaria"] = 180.0
    CURRENT_DATA["custo_frete"] = 250.0
    CURRENT_DATA["custo_montagem"] = 350.0
    CURRENT_DATA["imposto_pct"] = 6.0
    CURRENT_DATA["comissao_pct"] = 4.0
    CURRENT_DATA["markup"] = 2.2
    CURRENT_DATA["items"] = []
    return RedirectResponse(url="/painel-get", status_code=303)

@app.post("/salvar-operacionais", response_class=HTMLResponse)
def salvar_operacionais(
    dias_producao: int = Form(3),
    valor_diaria: float = Form(180.0),
    custo_frete: float = Form(250.0),
    custo_montagem: float = Form(350.0),
    imposto_pct: float = Form(6.0)
):
    if CURRENT_DATA.get("user_perfil") == "admin":
        CURRENT_DATA["dias_producao"] = dias_producao
        CURRENT_DATA["valor_diaria"] = valor_diaria
        CURRENT_DATA["custo_frete"] = custo_frete
        CURRENT_DATA["custo_montagem"] = custo_montagem
        CURRENT_DATA["imposto_pct"] = imposto_pct
    return RedirectResponse(url="/painel-get", status_code=303)

@app.post("/salvar-banco", response_class=HTMLResponse)
def salvar_banco():
    dre = calcular_dre_completa(CURRENT_DATA)
    agora = datetime.now().strftime("%d/%m/%Y %H:%M")
    
    with get_db() as conn:
        cursor = conn.cursor()
        if CURRENT_DATA["orcamento_id"]:
            cursor.execute("""
                UPDATE orcamentos SET
                    criado_em = ?,
                    cliente_nome = ?,
                    cliente_telefone = ?,
                    cliente_ambiente = ?,
                    prazo_entrega = ?,
                    data_entrega_prevista = ?,
                    status = ?,
                    custo_materiais = ?,
                    custo_mao_obra = ?,
                    custo_frete_montagem = ?,
                    imposto_pct = ?,
                    comissao_pct = ?,
                    markup = ?,
                    preco_venda = ?,
                    lucro_liquido = ?,
                    entrada_valor = ?,
                    num_parcelas = ?,
                    forma_pagamento = ?,
                    valor_recebido = ?,
                    imagens_json = ?,
                    ambientes_json = ?,
                    observacoes_tecnicas = ?,
                    items_json = ?
                WHERE id = ?
            """, (
                agora,
                CURRENT_DATA["cliente_nome"],
                CURRENT_DATA["cliente_telefone"],
                CURRENT_DATA["cliente_ambiente"],
                CURRENT_DATA["prazo_entrega"],
                CURRENT_DATA.get("data_entrega_prevista"),
                CURRENT_DATA.get("status", "Em Negociação"),
                dre["custo_mat"],
                dre["custo_mo"],
                dre["custo_frete_mont"],
                CURRENT_DATA["imposto_pct"],
                CURRENT_DATA["comissao_pct"],
                CURRENT_DATA["markup"],
                dre["pv"],
                dre["lucro_liquido"],
                CURRENT_DATA.get("entrada_valor", 0.0),
                CURRENT_DATA.get("num_parcelas", 1),
                CURRENT_DATA.get("forma_pagamento", "PIX"),
                CURRENT_DATA.get("valor_recebido", 0.0),
                json.dumps(CURRENT_DATA.get("imagens", [])),
                json.dumps(CURRENT_DATA.get("ambientes", [])),
                CURRENT_DATA.get("observacoes_tecnicas", ""),
                json.dumps(CURRENT_DATA["items"]),
                CURRENT_DATA["orcamento_id"]
            ))
        else:
            cursor.execute("""
                INSERT INTO orcamentos (criado_em, cliente_nome, cliente_telefone, cliente_ambiente, prazo_entrega, data_entrega_prevista, status, custo_materiais, custo_mao_obra, custo_frete_montagem, imposto_pct, comissao_pct, markup, preco_venda, lucro_liquido, entrada_valor, num_parcelas, forma_pagamento, valor_recebido, imagens_json, ambientes_json, observacoes_tecnicas, items_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                agora,
                CURRENT_DATA["cliente_nome"],
                CURRENT_DATA["cliente_telefone"],
                CURRENT_DATA["cliente_ambiente"],
                CURRENT_DATA["prazo_entrega"],
                CURRENT_DATA.get("data_entrega_prevista"),
                CURRENT_DATA.get("status", "Em Negociação"),
                dre["custo_mat"],
                dre["custo_mo"],
                dre["custo_frete_mont"],
                CURRENT_DATA["imposto_pct"],
                CURRENT_DATA["comissao_pct"],
                CURRENT_DATA["markup"],
                dre["pv"],
                dre["lucro_liquido"],
                CURRENT_DATA.get("entrada_valor", 0.0),
                CURRENT_DATA.get("num_parcelas", 1),
                CURRENT_DATA.get("forma_pagamento", "PIX"),
                CURRENT_DATA.get("valor_recebido", 0.0),
                json.dumps(CURRENT_DATA.get("imagens", [])),
                json.dumps(CURRENT_DATA.get("ambientes", [])),
                CURRENT_DATA.get("observacoes_tecnicas", ""),
                json.dumps(CURRENT_DATA["items"])
            ))
            CURRENT_DATA["orcamento_id"] = cursor.lastrowid
        conn.commit()

    return RedirectResponse(url="/painel-get", status_code=303)

@app.post("/carregar-orcamento", response_class=HTMLResponse)
def carregar_orcamento(orcamento_id: int = Form(...)):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM orcamentos WHERE id = ?", (orcamento_id,))
        row = cursor.fetchone()
        if row:
            CURRENT_DATA["orcamento_id"] = row["id"]
            CURRENT_DATA["status"] = row["status"] or "Em Negociação"
            CURRENT_DATA["cliente_nome"] = row["cliente_nome"]
            CURRENT_DATA["cliente_telefone"] = row["cliente_telefone"]
            CURRENT_DATA["cliente_ambiente"] = row["cliente_ambiente"]
            CURRENT_DATA["prazo_entrega"] = row["prazo_entrega"]
            CURRENT_DATA["data_entrega_prevista"] = row["data_entrega_prevista"] or (date.today() + timedelta(days=20)).strftime("%Y-%m-%d")
            CURRENT_DATA["custo_materiais"] = row["custo_materiais"]
            CURRENT_DATA["imposto_pct"] = row["imposto_pct"] or 6.0
            CURRENT_DATA["comissao_pct"] = row["comissao_pct"] or 4.0
            CURRENT_DATA["markup"] = row["markup"] or 2.2
            try:
                CURRENT_DATA["entrada_valor"] = float(row["entrada_valor"] or 0.0)
                CURRENT_DATA["num_parcelas"] = int(row["num_parcelas"] or 1)
                CURRENT_DATA["forma_pagamento"] = row["forma_pagamento"] or "PIX"
                CURRENT_DATA["valor_recebido"] = float(row["valor_recebido"] or 0.0)
                CURRENT_DATA["estoque_baixado"] = int(row["estoque_baixado"] or 0)
                CURRENT_DATA["imagens"] = json.loads(row["imagens_json"]) if row["imagens_json"] else []
                CURRENT_DATA["ambientes"] = json.loads(row["ambientes_json"]) if row["ambientes_json"] else [row["cliente_ambiente"]]
                CURRENT_DATA["observacoes_tecnicas"] = row["observacoes_tecnicas"] or ""
            except Exception:
                pass
            CURRENT_DATA["items"] = json.loads(row["items_json"]) if row["items_json"] else []

    return RedirectResponse(url="/painel-get", status_code=303)

@app.post("/excluir-orcamento", response_class=HTMLResponse)
def excluir_orcamento(orcamento_id: int = Form(...)):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM orcamentos WHERE id = ?", (orcamento_id,))
        conn.commit()
    if CURRENT_DATA["orcamento_id"] == orcamento_id:
        CURRENT_DATA["orcamento_id"] = None
    return RedirectResponse(url="/painel-get", status_code=303)

@app.post("/salvar-cliente", response_class=HTMLResponse)
def salvar_cliente(
    cliente_nome: str = Form(...),
    cliente_telefone: str = Form(...),
    cliente_ambiente: str = Form(...),
    prazo_entrega: str = Form(...),
    data_entrega_prevista: str = Form(...),
    observacoes_tecnicas: str = Form(""),
    status: str = Form("Em Negociação")
):
    CURRENT_DATA["cliente_nome"] = cliente_nome
    CURRENT_DATA["cliente_telefone"] = cliente_telefone
    CURRENT_DATA["cliente_ambiente"] = cliente_ambiente
    CURRENT_DATA["prazo_entrega"] = prazo_entrega
    CURRENT_DATA["data_entrega_prevista"] = data_entrega_prevista
    CURRENT_DATA["observacoes_tecnicas"] = observacoes_tecnicas
    CURRENT_DATA["status"] = status
    return RedirectResponse(url="/painel-get", status_code=303)

@app.post("/salvar-precos", response_class=HTMLResponse)
def salvar_precos(
    mdf_m2: float = Form(65.0),
    dobradica: float = Form(18.50),
    corredica: float = Form(38.00),
    fita_borda_m: float = Form(3.20),
    puxador: float = Form(25.00)
):
    if CURRENT_DATA.get("user_perfil") == "admin":
        precos = {
            "mdf_m2": mdf_m2,
            "dobradica": dobradica,
            "corredica": corredica,
            "fita_borda_m": fita_borda_m,
            "puxador": puxador,
            "outros_insumos": 15.00
        }
        set_precos_config(precos)

        novo_mat = 0.0
        for it in CURRENT_DATA["items"]:
            valor_item = it.get("valor", 0.0)
            novo_mat += valor_item

        CURRENT_DATA["custo_materiais"] = novo_mat
    return RedirectResponse(url="/painel-get", status_code=303)

@app.post("/recalcular", response_class=HTMLResponse)
def recalcular(markup: float = Form(2.2)):
    if CURRENT_DATA.get("user_perfil") == "admin":
        CURRENT_DATA["markup"] = markup
    return RedirectResponse(url="/painel-get", status_code=303)

@app.get("/gerar-os")
def gerar_os(id: int = None):
    empresa = get_empresa_config()
    ambientes_list = []
    if id:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM orcamentos WHERE id = ?", (id,))
            row = cursor.fetchone()
            if row:
                c_nome = row["cliente_nome"]
                c_tel = row["cliente_telefone"]
                c_amb = row["cliente_ambiente"]
                orc_id = row["id"]
                c_prazo = row["prazo_entrega"]
                c_data = row["data_entrega_prevista"] or date.today().strftime("%Y-%m-%d")
                obs = row["observacoes_tecnicas"] or "Sem observações especiais."
                ambientes_list = json.loads(row["ambientes_json"]) if row["ambientes_json"] else [c_amb]
                items = json.loads(row["items_json"]) if row["items_json"] else []
            else:
                return Response(content="Orçamento não encontrado", status_code=404)
    else:
        c_nome = CURRENT_DATA['cliente_nome']
        c_tel = CURRENT_DATA['cliente_telefone']
        c_amb = CURRENT_DATA['cliente_ambiente']
        orc_id = CURRENT_DATA['orcamento_id'] or 1
        c_prazo = CURRENT_DATA['prazo_entrega']
        c_data = CURRENT_DATA.get('data_entrega_prevista', date.today().strftime("%Y-%m-%d"))
        obs = CURRENT_DATA.get('observacoes_tecnicas', 'Sem observações especiais.')
        ambientes_list = CURRENT_DATA.get("ambientes", [c_amb])
        items = CURRENT_DATA["items"]

    compras = consolidar_compras_e_nesting(items)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    styles = getSampleStyleSheet()
    elements = []

    title_style = ParagraphStyle(name='TitleStyle', parent=styles['Heading1'], fontSize=16, textColor=colors.HexColor('#0f172a'), spaceAfter=2)
    sub_empresa = ParagraphStyle(name='SubEmpresa', parent=styles['Normal'], fontSize=9, textColor=colors.HexColor('#475569'), spaceAfter=10)
    section_title = ParagraphStyle(name='SecTitle', parent=styles['Heading2'], fontSize=11, textColor=colors.HexColor('#0284c7'), spaceBefore=8, spaceAfter=4)
    body_style = ParagraphStyle(name='BodyStyle', parent=styles['Normal'], fontSize=9, leading=13, textColor=colors.HexColor('#1e293b'))

    elements.append(Paragraph(f"<b>{empresa['nome_empresa']}</b>", title_style))
    elements.append(Paragraph(f"ORDEM DE SERVIÇO & FICHA TÉCNICA DE PRODUÇÃO - O.S. #{orc_id:04d}", sub_empresa))

    meta_data = [
        ["Cliente:", c_nome, "Data Emissão:", date.today().strftime("%d/%m/%Y")],
        ["Telefone:", c_tel, "Data Prevista Montagem:", c_data],
        ["Ambientes:", ", ".join(ambientes_list), "Prazo:", c_prazo]
    ]
    meta_table = Table(meta_data, colWidths=[110, 160, 120, 150])
    meta_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#e0f2fe')),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#0369a1')),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#93c5fd')),
    ]))
    elements.append(meta_table)
    elements.append(Spacer(1, 8))

    elements.append(Paragraph("<b>1. Separação de Ferragens & Insumos para Montagem</b>", section_title))
    ferragens_data = [
        ["Insumo / Ferragem", "Quantidade", "Status Separação Oficina"],
        ["Dobradiças Slowmotion", f"{compras['dobradicas']} un", "[  ] Separado e Conferido"],
        ["Corrediças Telescópicas", f"{compras['corredicas']} pares", "[  ] Separado e Conferido"],
        ["Puxadores / Perfis", f"{compras['puxadores']} un", "[  ] Separado e Conferido"],
        ["Fita de Borda PVC", f"{compras['fita_metros']} metros", "[  ] Separado e Conferido"],
        ["Chapas MDF Estimadas", f"{compras['chapas_mdf']} chapas", "[  ] Cortado na Seccionadora"]
    ]
    ferragens_table = Table(ferragens_data, colWidths=[200, 140, 200])
    ferragens_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0284c7')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
    ]))
    elements.append(ferragens_table)
    elements.append(Spacer(1, 8))

    elements.append(Paragraph("<b>2. Relação de Peças a Cortar & Fitamento</b>", section_title))
    pecas_data = [["Peça / Descrição", "Ambiente", "Dimensões", "Qtd"]]
    for it in (items or [{"nome": "Módulo Geral", "ambiente": "Geral", "dimensoes": "-", "qtd": 1}]):
        pecas_data.append([
            it.get("nome", "Peça"),
            it.get("ambiente", "Geral"),
            it.get("dimensoes", "-"),
            str(it.get("qtd", 1))
        ])

    pecas_table = Table(pecas_data, colWidths=[220, 130, 140, 50])
    pecas_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#334155')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (3, 0), (3, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
    ]))
    elements.append(pecas_table)
    elements.append(Spacer(1, 8))

    elements.append(Paragraph("<b>3. Observações Técnicas & Detalhes da Planta</b>", section_title))
    elements.append(Paragraph(f"<b>Instruções:</b> {obs}", body_style))
    elements.append(Spacer(1, 16))

    sign_data = [
        ["_____________________________________________", "_____________________________________________"],
        ["Marceneiro Responsável (Oficina)", "Montador Responsável (Obra)"]
    ]
    sign_table = Table(sign_data, colWidths=[270, 270])
    sign_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#0f172a')),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    elements.append(sign_table)

    doc.build(elements)
    buffer.seek(0)
    nome_arquivo = f"ordem-servico-{c_nome.replace(' ', '_')}.pdf"
    return Response(content=buffer.getvalue(), media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename={nome_arquivo}"})

@app.get("/gerar-pdf")
def gerar_pdf(id: int = None):
    empresa = get_empresa_config()
    imagens = []
    ambientes_list = []
    if id:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM orcamentos WHERE id = ?", (id,))
            row = cursor.fetchone()
            if row:
                c_nome = row["cliente_nome"]
                c_tel = row["cliente_telefone"]
                c_amb = row["cliente_ambiente"]
                c_prazo = row["prazo_entrega"]
                c_status = row["status"] or "Em Negociação"
                pv = row["preco_venda"]
                entrada = float(row["entrada_valor"] or 0.0)
                n_parc = int(row["num_parcelas"] or 1)
                forma_pgto = row["forma_pagamento"] or "PIX"
                imagens = json.loads(row["imagens_json"]) if row["imagens_json"] else []
                ambientes_list = json.loads(row["ambientes_json"]) if row["ambientes_json"] else [c_amb]
                items = json.loads(row["items_json"]) if row["items_json"] else []
            else:
                return Response(content="Orçamento não encontrado", status_code=404)
    else:
        dre = calcular_dre_completa(CURRENT_DATA)
        c_nome = CURRENT_DATA['cliente_nome']
        c_tel = CURRENT_DATA['cliente_telefone']
        c_amb = CURRENT_DATA['cliente_ambiente']
        c_prazo = CURRENT_DATA['prazo_entrega']
        c_status = CURRENT_DATA.get('status', 'Em Negociação')
        pv = dre["pv"]
        entrada = dre["entrada"]
        n_parc = dre["n_parc"]
        forma_pgto = CURRENT_DATA.get("forma_pagamento", "PIX")
        imagens = CURRENT_DATA.get("imagens", [])
        ambientes_list = CURRENT_DATA.get("ambientes", [c_amb])
        items = CURRENT_DATA["items"]

    v_parc = (pv - entrada) / n_parc if n_parc > 0 else 0.0

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    styles = getSampleStyleSheet()
    elements = []

    title_style = ParagraphStyle(name='TitleStyle', parent=styles['Heading1'], fontSize=18, textColor=colors.HexColor('#0f172a'), spaceAfter=2)
    sub_empresa = ParagraphStyle(name='SubEmpresa', parent=styles['Normal'], fontSize=9, textColor=colors.HexColor('#475569'), spaceAfter=10)
    
    elements.append(Paragraph(f"{empresa['nome_empresa']}", title_style))
    elements.append(Paragraph(f"CNPJ: {empresa['cnpj']} | Contato: {empresa['telefone_empresa']} | PIX: {empresa['pix']}", sub_empresa))
    elements.append(Spacer(1, 4))

    cliente_data = [
        ["Cliente:", c_nome, "Data da Proposta:", date.today().strftime("%d/%m/%Y")],
        ["WhatsApp/Tel:", c_tel, "Prazo de Entrega:", c_prazo],
        ["Ambientes Inclusos:", ", ".join(ambientes_list), "Status:", c_status]
    ]
    cliente_table = Table(cliente_data, colWidths=[110, 160, 120, 150])
    cliente_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f1f5f9')),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#334155')),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
    ]))
    elements.append(cliente_table)
    elements.append(Spacer(1, 10))

    if imagens:
        try:
            img_bytes = io.BytesIO(base64.b64decode(imagens[0]))
            img_render = RLImage(img_bytes, width=540, height=220)
            elements.append(img_render)
            elements.append(Spacer(1, 10))
        except Exception:
            pass

    cond_texto = f"Entrada de R$ {entrada:,.2f} + {n_parc}x de R$ {v_parc:,.2f} ({forma_pgto})" if n_parc > 1 else f"À vista: R$ {pv:,.2f} ({forma_pgto})"

    dre_data = [
        ["Ambientes do Projeto", f"{', '.join(ambientes_list)}"],
        ["Prazo de Fabricação e Instalação", f"{c_prazo}"],
        ["Condições de Pagamento", cond_texto],
        ["Garantia Estrutural e Ferragens", "12 meses contra defeitos de fabricação"],
        ["VALOR TOTAL DO INVESTIMENTO (GLOBAL)", f"R$ {pv:,.2f}"]
    ]
    dre_table = Table(dre_data, colWidths=[240, 300])
    dre_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 3), colors.HexColor('#f8fafc')),
        ('BACKGROUND', (0, 4), (-1, 4), colors.HexColor('#dbeafe')),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#0f172a')),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
    ]))
    elements.append(dre_table)
    elements.append(Spacer(1, 12))

    sum_title = ParagraphStyle(name='SumTitle', parent=styles['Heading2'], fontSize=12, textColor=colors.HexColor('#0284c7'), spaceAfter=6)
    elements.append(Paragraph("Especificação dos Módulos e Componentes", sum_title))

    items = items or [{"nome": "Módulo Planejado", "dimensoes": "-", "qtd": 1, "ambiente": "Geral"}]
    table_data = [["Descrição do Componente", "Ambiente", "Dimensões", "Qtd"]]
    for it in items:
        table_data.append([
            it.get("nome", "Peça"),
            it.get("ambiente", "Geral"),
            it.get("dimensoes", "-"),
            str(it.get("qtd", 1))
        ])

    items_table = Table(table_data, colWidths=[220, 130, 140, 50])
    items_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0284c7')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (3, 0), (3, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
    ]))
    elements.append(items_table)

    doc.build(elements)
    buffer.seek(0)
    nome_arquivo = f"proposta-{c_nome.replace(' ', '_')}.pdf"
    return Response(content=buffer.getvalue(), media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename={nome_arquivo}"})

@app.get("/gerar-recibo")
def gerar_recibo(id: int = None):
    empresa = get_empresa_config()
    if id:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM orcamentos WHERE id = ?", (id,))
            row = cursor.fetchone()
            if row:
                c_nome = row["cliente_nome"]
                c_tel = row["cliente_telefone"]
                c_amb = row["cliente_ambiente"]
                orc_id = row["id"]
                pv = row["preco_venda"]
                rec = float(row["valor_recebido"] or row["entrada_valor"] or row["preco_venda"])
                forma_pgto = row["forma_pagamento"] or "PIX"
            else:
                return Response(content="Orçamento não encontrado", status_code=404)
    else:
        dre = calcular_dre_completa(CURRENT_DATA)
        c_nome = CURRENT_DATA['cliente_nome']
        c_tel = CURRENT_DATA['cliente_telefone']
        c_amb = CURRENT_DATA['cliente_ambiente']
        orc_id = CURRENT_DATA['orcamento_id'] or 1
        pv = dre["pv"]
        rec = float(CURRENT_DATA.get('valor_recebido', 0.0) or dre['entrada'] or pv)
        forma_pgto = CURRENT_DATA.get("forma_pagamento", "PIX")

    extenso = numero_extenso_reais(rec)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    styles = getSampleStyleSheet()
    elements = []

    title_style = ParagraphStyle(name='TitleStyle', parent=styles['Heading1'], fontSize=16, alignment=1, textColor=colors.HexColor('#0f172a'), spaceAfter=4)
    sub_empresa = ParagraphStyle(name='SubEmpresa', parent=styles['Normal'], fontSize=9, alignment=1, textColor=colors.HexColor('#475569'), spaceAfter=14)
    body_style = ParagraphStyle(name='BodyStyle', parent=styles['Normal'], fontSize=10, leading=15, textColor=colors.HexColor('#1e293b'))
    recibo_val_style = ParagraphStyle(name='ValStyle', parent=styles['Normal'], fontSize=12, alignment=1, textColor=colors.HexColor('#0369a1'), fontName="Helvetica-Bold")

    elements.append(Paragraph(f"<b>{empresa['nome_empresa']}</b>", title_style))
    elements.append(Paragraph(f"CNPJ: {empresa['cnpj']} | Telefone: {empresa['telefone_empresa']} | Chave PIX: {empresa['pix']}", sub_empresa))

    val_box_data = [[
        Paragraph(f"<b>RECIBO DE PAGAMENTO Nº #{orc_id:04d}</b>", recibo_val_style),
        Paragraph(f"<b>VALOR: R$ {rec:,.2f}</b>", recibo_val_style)
    ]]
    val_box = Table(val_box_data, colWidths=[270, 270])
    val_box.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#e0f2fe')),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#0284c7')),
        ('PADDING', (0, 0), (-1, -1), 8),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
    ]))
    elements.append(val_box)
    elements.append(Spacer(1, 16))

    texto_recibo = f"""
    Recebemos de <b>{c_nome}</b> (Telefone: {c_tel}) a importância de <b>R$ {rec:,.2f} ({extenso})</b>, referente ao pagamento (entrada / quitação) da fabricação e instalação de móveis planejados sob medida para o projeto/ambiente: <b>{c_amb}</b>.<br/><br/>
    <b>Forma de Liquidação:</b> {forma_pgto}.<br/>
    <b>Valor Total Contratado da Obra:</b> R$ {pv:,.2f}.<br/>
    Para clareza e firmeza do que foi recebido, firmamos o presente recibo dando plena e geral quitação da quantia paga.
    """
    elements.append(Paragraph(texto_recibo, body_style))
    elements.append(Spacer(1, 24))

    data_extenso = date.today().strftime("%d de %B de %Y")
    elements.append(Paragraph(f"Emitido em {data_extenso}.", body_style))
    elements.append(Spacer(1, 30))

    sign_data = [
        ["________________________________________________________"],
        [f"<b>{empresa['nome_empresa']}</b>\nCNPJ: {empresa['cnpj']}\nRepresentante / Financeiro"]
    ]
    sign_table = Table(sign_data, colWidths=[400])
    sign_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#0f172a')),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    elements.append(sign_table)

    doc.build(elements)
    buffer.seek(0)
    nome_arquivo = f"recibo-pagamento-{c_nome.replace(' ', '_')}.pdf"
    return Response(content=buffer.getvalue(), media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename={nome_arquivo}"})

@app.get("/gerar-vistoria")
def gerar_vistoria(id: int = None):
    empresa = get_empresa_config()
    ambientes_list = []
    if id:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM orcamentos WHERE id = ?", (id,))
            row = cursor.fetchone()
            if row:
                c_nome = row["cliente_nome"]
                c_tel = row["cliente_telefone"]
                c_amb = row["cliente_ambiente"]
                ambientes_list = json.loads(row["ambientes_json"]) if row["ambientes_json"] else [c_amb]
                c_data = row["data_entrega_prevista"] or date.today().strftime("%Y-%m-%d")
            else:
                return Response(content="Orçamento não encontrado", status_code=404)
    else:
        c_nome = CURRENT_DATA['cliente_nome']
        c_tel = CURRENT_DATA['cliente_telefone']
        c_amb = CURRENT_DATA['cliente_ambiente']
        ambientes_list = CURRENT_DATA.get("ambientes", [c_amb])
        c_data = CURRENT_DATA.get('data_entrega_prevista', date.today().strftime("%Y-%m-%d"))

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    styles = getSampleStyleSheet()
    elements = []

    title_style = ParagraphStyle(name='TitleStyle', parent=styles['Heading1'], fontSize=15, alignment=1, textColor=colors.HexColor('#0f172a'), spaceAfter=2)
    sub_empresa = ParagraphStyle(name='SubEmpresa', parent=styles['Normal'], fontSize=9, alignment=1, textColor=colors.HexColor('#475569'), spaceAfter=12)
    body_style = ParagraphStyle(name='BodyStyle', parent=styles['Normal'], fontSize=9, leading=13, textColor=colors.HexColor('#1e293b'))
    section_title = ParagraphStyle(name='SecTitle', parent=styles['Heading2'], fontSize=11, textColor=colors.HexColor('#6b21a8'), spaceBefore=8, spaceAfter=4)

    elements.append(Paragraph(f"<b>{empresa['nome_empresa']}</b>", title_style))
    elements.append(Paragraph("TERMO DE VISTORIA, ENTREGA E ACEITE FINAL DE MONTAGEM", sub_empresa))

    meta_data = [
        ["Cliente:", c_nome, "Data da Vistoria:", date.today().strftime("%d/%m/%Y")],
        ["WhatsApp/Tel:", c_tel, "Ambientes Montados:", ", ".join(ambientes_list)]
    ]
    meta_table = Table(meta_data, colWidths=[110, 160, 120, 150])
    meta_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f3e8ff')),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#581c87')),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#d8b4fe')),
    ]))
    elements.append(meta_table)
    elements.append(Spacer(1, 10))

    elements.append(Paragraph("<b>1. Checklist de Vistoria de Campo e Qualidade</b>", section_title))
    
    check_data = [
        ["Item de Verificação Técnica", "Status de Inspeção", "Rubrica Cliente / Observações"],
        ["Alinhamento e folgas de portas e gavetas", "[  ] Conforme  [  ] Ajustado", "Sem atritos estruturais"],
        ["Amortecedores (Slowmotion) e Corrediças", "[  ] Conforme  [  ] Ajustado", "Abertura e fechamento suaves"],
        ["Acabamento de fitas de borda e tapa-furos", "[  ] Conforme  [  ] Ajustado", "Refilamento perfeito"],
        ["Fixações em alvenaria e prumo dos módulos", "[  ] Conforme  [  ] Ajustado", "Fixação reforçada"],
        ["Limpeza geral e ausência de riscos nos painéis", "[  ] Conforme  [  ] Ajustado", "Higienizado para entrega"]
    ]
    check_table = Table(check_data, colWidths=[240, 130, 170])
    check_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#7e22ce')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
    ]))
    elements.append(check_table)
    elements.append(Spacer(1, 10))

    elements.append(Paragraph("<b>2. Declaração de Aceite e Quitação de Entrega</b>", section_title))
    p_aceite = """
    Pelo presente instrumento, o <b>CONTRATANTE</b> declara que acompanhou a vistoria técnica final dos móveis sob medida instalados nos ambientes supracitados, constatando que os serviços foram integralmente executados de acordo com o projeto contratado, encontrando-se em perfeito estado de funcionamento, acabamento e limpeza, dando por <b>RECEBIDA E APROVADA A OBRA</b>.
    """
    elements.append(Paragraph(p_aceite, body_style))
    elements.append(Spacer(1, 24))

    sign_data = [
        ["_____________________________________________", "_____________________________________________"],
        [f"<b>{empresa['nome_empresa']}</b>\nResponsável Técnico / Montador", f"<b>{c_nome}</b>\nAssinatura do Cliente (Aceite)"]
    ]
    sign_table = Table(sign_data, colWidths=[270, 270])
    sign_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#0f172a')),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    elements.append(sign_table)

    doc.build(elements)
    buffer.seek(0)
    nome_arquivo = f"termo-vistoria-{c_nome.replace(' ', '_')}.pdf"
    return Response(content=buffer.getvalue(), media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename={nome_arquivo}"})

@app.get("/gerar-etiquetas")
def gerar_etiquetas(id: int = None):
    empresa = get_empresa_config()
    if id:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM orcamentos WHERE id = ?", (id,))
            row = cursor.fetchone()
            if row:
                c_nome = row["cliente_nome"]
                c_amb = row["cliente_ambiente"]
                orc_id = row["id"]
                items = json.loads(row["items_json"]) if row["items_json"] else []
            else:
                return Response(content="Orçamento não encontrado", status_code=404)
    else:
        c_nome = CURRENT_DATA['cliente_nome']
        c_amb = CURRENT_DATA['cliente_ambiente']
        orc_id = CURRENT_DATA['orcamento_id'] or 1
        items = CURRENT_DATA["items"]

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=20, leftMargin=20, topMargin=25, bottomMargin=25)
    styles = getSampleStyleSheet()
    elements = []

    title_style = ParagraphStyle(name='TitleStyle', parent=styles['Heading1'], fontSize=16, alignment=1, textColor=colors.HexColor('#0f172a'), spaceAfter=2)
    sub_title = ParagraphStyle(name='SubTitle', parent=styles['Normal'], fontSize=9, alignment=1, textColor=colors.HexColor('#64748b'), spaceAfter=14)
    
    elements.append(Paragraph(f"<b>{empresa['nome_empresa']}</b> - Etiquetas de Produção & Fitas de Borda", title_style))
    elements.append(Paragraph(f"Projeto: <b>{c_amb}</b> | Cliente: <b>{c_nome}</b> | Ref: #{orc_id}", sub_title))

    pecas_mdf = []
    for idx, it in enumerate(items, 1):
        if "MDF" in it.get("tipo", "") or it.get("largura", 0) > 0:
            qtd = int(it.get("qtd", 1))
            for q in range(1, qtd + 1):
                pecas_mdf.append({
                    "id_tag": f"#{orc_id}-P{len(pecas_mdf)+1:02d}",
                    "nome": it.get("nome", "Peça MDF"),
                    "dim": it.get("dimensoes", "-"),
                    "fitas": "Bordas: 2x Comp. / 1x Larg."
                })

    if not pecas_mdf:
        pecas_mdf = [
            {"id_tag": f"#{orc_id}-P01", "nome": "Lateral Direita Torre Quente", "dim": "2200 x 600 x 18 mm", "fitas": "Bordas: 2C / 1L"},
            {"id_tag": f"#{orc_id}-P02", "nome": "Lateral Esquerda Torre Quente", "dim": "2200 x 600 x 18 mm", "fitas": "Bordas: 2C / 1L"},
            {"id_tag": f"#{orc_id}-P03", "nome": "Base Inferior Balcão", "dim": "1200 x 580 x 18 mm", "fitas": "Bordas: 1C / 2L"},
            {"id_tag": f"#{orc_id}-P04", "nome": "Porta Basculante Superior", "dim": "800 x 400 x 18 mm", "fitas": "Bordas: 4 Lados 22mm"}
        ]

    cards_data = []
    linha_atual = []
    
    lbl_tag = ParagraphStyle(name='LblTag', parent=styles['Normal'], fontSize=8.5, leading=10, textColor=colors.HexColor('#0284c7'), fontName="Helvetica-Bold")
    lbl_nome = ParagraphStyle(name='LblNome', parent=styles['Normal'], fontSize=9.5, leading=12, textColor=colors.HexColor('#0f172a'), fontName="Helvetica-Bold")
    lbl_dim = ParagraphStyle(name='LblDim', parent=styles['Normal'], fontSize=8.5, leading=11, textColor=colors.HexColor('#334155'))
    lbl_fitas = ParagraphStyle(name='LblFitas', parent=styles['Normal'], fontSize=8, leading=10, textColor=colors.HexColor('#166534'), fontName="Helvetica-Bold")

    for p in pecas_mdf:
        conteudo_etiqueta = [
            [Paragraph(f"<b>{p['id_tag']}</b> | {c_amb[:20]}", lbl_tag)],
            [Paragraph(f"{p['nome'][:30]}", lbl_nome)],
            [Paragraph(f"Dimensões: <b>{p['dim']}</b>", lbl_dim)],
            [Paragraph(f"🏷️ {p['fitas']}", lbl_fitas)]
        ]
        t_card = Table(conteudo_etiqueta, colWidths=[270])
        t_card.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
            ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#94a3b8')),
            ('PADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
        ]))
        
        linha_atual.append(t_card)
        if len(linha_atual) == 2:
            cards_data.append(linha_atual)
            linha_atual = []

    if linha_atual:
        linha_atual.append("")
        cards_data.append(linha_atual)

    grid_table = Table(cards_data, colWidths=[280, 280])
    grid_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
    ]))
    elements.append(grid_table)

    doc.build(elements)
    buffer.seek(0)
    nome_arquivo = f"etiquetas-producao-{c_amb.replace(' ', '_')}.pdf"
    return Response(content=buffer.getvalue(), media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename={nome_arquivo}"})

@app.get("/gerar-contrato")
def gerar_contrato(id: int = None):
    empresa = get_empresa_config()
    ambientes_list = []
    if id:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM orcamentos WHERE id = ?", (id,))
            row = cursor.fetchone()
            if row:
                c_nome = row["cliente_nome"]
                c_tel = row["cliente_telefone"]
                c_amb = row["cliente_ambiente"]
                ambientes_list = json.loads(row["ambientes_json"]) if row["ambientes_json"] else [c_amb]
                c_prazo = row["prazo_entrega"]
                pv = row["preco_venda"]
                entrada = float(row["entrada_valor"] or 0.0)
                n_parc = int(row["num_parcelas"] or 1)
                forma_pgto = row["forma_pagamento"] or "PIX"
            else:
                return Response(content="Orçamento não encontrado", status_code=404)
    else:
        dre = calcular_dre_completa(CURRENT_DATA)
        c_nome = CURRENT_DATA['cliente_nome']
        c_tel = CURRENT_DATA['cliente_telefone']
        c_amb = CURRENT_DATA['cliente_ambiente']
        ambientes_list = CURRENT_DATA.get("ambientes", [c_amb])
        c_prazo = CURRENT_DATA['prazo_entrega']
        pv = dre["pv"]
        entrada = dre["entrada"]
        n_parc = dre["n_parc"]
        forma_pgto = CURRENT_DATA.get("forma_pagamento", "PIX")

    v_parc = (pv - entrada) / n_parc if n_parc > 0 else 0.0

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    styles = getSampleStyleSheet()
    elements = []

    title_style = ParagraphStyle(name='TitleStyle', parent=styles['Heading1'], fontSize=15, alignment=1, textColor=colors.HexColor('#0f172a'), spaceAfter=10)
    body_style = ParagraphStyle(name='BodyStyle', parent=styles['Normal'], fontSize=9.5, leading=14, textColor=colors.HexColor('#1e293b'), spaceAfter=8)
    clause_title = ParagraphStyle(name='ClauseTitle', parent=styles['Heading2'], fontSize=11, textColor=colors.HexColor('#0369a1'), spaceBefore=8, spaceAfter=4)

    elements.append(Paragraph("<b>INSTRUMENTO PARTICULAR DE PRESTAÇÃO DE SERVIÇOS DE MARCENARIA</b>", title_style))
    elements.append(Spacer(1, 4))

    elements.append(Paragraph("<b>1. IDENTIFICAÇÃO DAS PARTES CONTRATANTES</b>", clause_title))
    p_partes = f"""
    <b>CONTRATADA:</b> {empresa['nome_empresa']}, inscrita no CNPJ sob o nº {empresa['cnpj']}, contato {empresa['telefone_empresa']}.<br/>
    <b>CONTRATANTE:</b> {c_nome}, telefone/WhatsApp {c_tel}.
    """
    elements.append(Paragraph(p_partes, body_style))

    elements.append(Paragraph("<b>2. OBJETO DO CONTRATO (PROJETO COMPLETO)</b>", clause_title))
    p_obj = f"O presente contrato tem por objeto a fabricação, acabamento e instalação de móveis sob medida destinados aos seguintes ambientes: <b>{', '.join(ambientes_list)}</b>, em conformidade com o projeto executivo e relação de insumos aprovados."
    elements.append(Paragraph(p_obj, body_style))

    elements.append(Paragraph("<b>3. VALOR E FORMA DE PAGAMENTO</b>", clause_title))
    cond_extenso = f"Entrada no valor de <b>R$ {entrada:,.2f}</b> mais <b>{n_parc} parcela(s)</b> de <b>R$ {v_parc:,.2f}</b> através de {forma_pgto}." if n_parc > 1 else f"Pagamento à vista no valor de <b>R$ {pv:,.2f}</b> via {forma_pgto}."
    p_preco = f"Pela execução integral dos serviços descritos, o CONTRATANTE pagará à CONTRATADA o valor total de <b>R$ {pv:,.2f}</b>, nas seguintes condições: {cond_extenso}"
    elements.append(Paragraph(p_preco, body_style))

    elements.append(Paragraph("<b>4. PRAZO DE FABRICAÇÃO E INSTALAÇÃO</b>", clause_title))
    p_prazo = f"A CONTRATADA compromete-se a entregar e finalizar a montagem dos móveis no prazo estimado de <b>{c_prazo}</b>, contados a partir da aprovação final das medidas no local e confirmação do pagamento inicial."
    elements.append(Paragraph(p_prazo, body_style))

    elements.append(Paragraph("<b>5. TERMO DE GARANTIA</b>", clause_title))
    p_garantia = "A CONTRATADA concede a garantia de <b>12 (doze) meses</b> a contar da data de entrega, cobrindo eventuais defeitos de fabricação e montagem de ferragens estruturais, não cobrindo danos ocasionados por umidade excessiva, mau uso ou intervenções de terceiros."
    elements.append(Paragraph(p_garantia, body_style))
    elements.append(Spacer(1, 16))

    data_extenso = date.today().strftime("%d/%m/%Y")
    elements.append(Paragraph(f"Data de formalização: {data_extenso}.", body_style))
    elements.append(Spacer(1, 24))

    sign_data = [
        ["_____________________________________________", "_____________________________________________"],
        [f"<b>{empresa['nome_empresa']}</b>\nCONTRATADA (CNPJ: {empresa['cnpj']})", f"<b>{c_nome}</b>\nCONTRATANTE"]
    ]
    sign_table = Table(sign_data, colWidths=[270, 270])
    sign_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#0f172a')),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    elements.append(sign_table)

    doc.build(elements)
    buffer.seek(0)
    nome_arquivo = f"contrato-{c_nome.replace(' ', '_')}.pdf"
    return Response(content=buffer.getvalue(), media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename={nome_arquivo}"})

@app.get("/gerar-pdf-compras")
def gerar_pdf_compras(id: int = None):
    empresa = get_empresa_config()
    if id:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM orcamentos WHERE id = ?", (id,))
            row = cursor.fetchone()
            if row:
                c_nome = row["cliente_nome"]
                c_amb = row["cliente_ambiente"]
                items = json.loads(row["items_json"]) if row["items_json"] else []
            else:
                return Response(content="Orçamento não encontrado", status_code=404)
    else:
        c_nome = CURRENT_DATA['cliente_nome']
        c_amb = CURRENT_DATA['cliente_ambiente']
        items = CURRENT_DATA["items"]

    compras = consolidar_compras_e_nesting(items)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    styles = getSampleStyleSheet()
    elements = []

    title_style = ParagraphStyle(name='TitleStyle', parent=styles['Heading1'], fontSize=18, textColor=colors.HexColor('#1e1b4b'), spaceAfter=4)
    elements.append(Paragraph(f"{empresa['nome_empresa']} - Cotação Fornecedor & Plano de Corte", title_style))
    elements.append(Spacer(1, 8))

    meta_data = [
        ["Projeto / Ambiente:", c_amb, "Data de Emissão:", date.today().strftime("%d/%m/%Y")],
        ["Identificação Interna:", f"Ref: {c_nome}", "Tipo:", "Cotação Direta / Madeireira"]
    ]
    meta_table = Table(meta_data, colWidths=[130, 160, 110, 140])
    meta_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#e0e7ff')),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#1e1b4b')),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#c7d2fe')),
    ]))
    elements.append(meta_table)
    elements.append(Spacer(1, 14))

    sum_title = ParagraphStyle(name='SumTitle', parent=styles['Heading2'], fontSize=13, textColor=colors.HexColor('#312e81'), spaceAfter=6)
    elements.append(Paragraph("1. Resumo de Insumos a Comprar", sum_title))

    sum_data = [
        ["Item / Insumo Requerido", "Quantidade Consolidada", "Observações Técnicas"],
        ["Chapas de MDF (Estimado)", f"{compras['chapas_mdf']} un", f"Área de corte aprox: {compras['area_m2']:.1f} m²"],
        ["Fita de Borda PVC", f"{compras['fita_metros']} metros", "Espessura padrão 22mm"],
        ["Dobradiças 35mm Slowmotion", f"{compras['dobradicas']} unidades", "Com amortecedor integrado"],
        ["Corrediças Telescópicas", f"{compras['corredicas']} pares", "Extração total / reforçada"],
        ["Puxadores / Perfis", f"{compras['puxadores']} unidades", "Conforme projeto aprovado"],
        ["Insumos Gerais / Ferragens", f"{compras['outros']} itens", "Parafusos, cantoneiras e acabamentos"]
    ]
    sum_table = Table(sum_data, colWidths=[200, 140, 200])
    sum_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4338ca')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f8fafc')),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
    ]))
    elements.append(sum_table)
    elements.append(Spacer(1, 14))

    elements.append(Paragraph("2. Detalhamento de Peças do Plano de Corte", sum_title))
    items_table_data = [["Descrição da Peça", "Ambiente", "Dimensões (mm)", "Qtd"]]
    for it in (items or [{"nome": "Sem itens", "ambiente": "-", "dimensoes": "-", "qtd": 1}]):
        items_table_data.append([
            it.get("nome", "Peça"),
            it.get("ambiente", "Geral"),
            it.get("dimensoes", "-"),
            str(it.get("qtd", 1))
        ])

    items_doc_table = Table(items_table_data, colWidths=[220, 130, 140, 50])
    items_doc_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#64748b')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (3, 0), (3, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
    ]))
    elements.append(items_doc_table)

    doc.build(elements)
    buffer.seek(0)
    nome_arquivo = f"lista-compras-{c_amb.replace(' ', '_')}.pdf"
    return Response(content=buffer.getvalue(), media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename={nome_arquivo}"})

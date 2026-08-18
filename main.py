from fastapi import FastAPI, Form, UploadFile, File, Response, Request, HTTPException
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

app = FastAPI(title="SaaS Marcenaria Multi-Empresa")
DB_PATH = "marcenaria_saas.db"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Tabela de Empresas Clientes (Tenants)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS empresas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT UNIQUE,
            nome_empresa TEXT,
            cnpj TEXT,
            telefone TEXT,
            pix TEXT,
            precos_json TEXT,
            ativa INTEGER DEFAULT 1
        )
    """)

    # Tabela de Usuários (Funcionários e Administradores)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            email TEXT PRIMARY KEY,
            senha TEXT,
            nome TEXT,
            perfil TEXT,
            empresa_id INTEGER,
            FOREIGN KEY (empresa_id) REFERENCES empresas (id)
        )
    """)

    # Tabela de Estoque por Empresa
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS estoque (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa_id INTEGER,
            codigo TEXT,
            descricao TEXT,
            quantidade REAL DEFAULT 0,
            qtd_minima REAL DEFAULT 0,
            unidade TEXT,
            FOREIGN KEY (empresa_id) REFERENCES empresas (id)
        )
    """)

    # Tabela de Orçamentos com Vínculo de Empresa
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orcamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa_id INTEGER,
            criado_em TEXT,
            cliente_nome TEXT,
            cliente_telefone TEXT,
            cliente_ambiente TEXT,
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
            FOREIGN KEY (empresa_id) REFERENCES empresas (id)
        )
    """)
    conn.commit()

    # Criação da Empresa Master MVI inicial
    cursor.execute("SELECT id FROM empresas WHERE id = 1")
    if not cursor.fetchone():
        default_precos = {
            "mdf_m2": 65.0, "dobradica": 18.50, "corredica": 38.00,
            "fita_borda_m": 3.20, "puxador": 25.00, "outros_insumos": 15.00
        }
        cursor.execute("""
            INSERT INTO empresas (id, slug, nome_empresa, cnpj, telefone, pix, precos_json)
            VALUES (1, 'mvi', 'MVI Móveis Planejados', '00.000.000/0001-00', '(11) 98888-7777', 'contato@mvi.com', ?)
        """, (json.dumps(default_precos),))

        # Usuários padrão
        cursor.execute("INSERT INTO usuarios VALUES ('admin@mvi.com', '123456', 'Administrador MVI', 'admin_empresa', 1)")
        cursor.execute("INSERT INTO usuarios VALUES ('vendedor@mvi.com', '123456', 'Vendedor MVI', 'vendedor', 1)")
        conn.commit()

    conn.close()

init_db()

# SESSÃO GLOBAL TEMPORÁRIA
SESSION = {
    "user_email": "admin@mvi.com",
    "user_nome": "Administrador MVI",
    "user_perfil": "admin_empresa",
    "empresa_id": 1
}

def get_empresa_by_id(empresa_id: int):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM empresas WHERE id = ?", (empresa_id,))
    row = cursor.fetchone()
    conn.close()
    return row

def get_empresa_by_slug(slug: str):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM empresas WHERE slug = ?", (slug,))
    row = cursor.fetchone()
    conn.close()
    return row

def calcular_engenharia_avancada(
    ambientes_selecionados: list,
    area_m2_total: float,
    espessura_caixa: str,
    espessura_tamponamento: str,
    fabricante_mdf: str,
    cor_mdf: str,
    modelo_portas: str,
    marca_ferragens: str,
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

    fator_mdf = 1.0
    if "Duratex" in fabricante_mdf:
        fator_mdf = 1.35 if any(c in cor_mdf for c in ["Freijó", "Carvalho", "Gianduia", "Carbono"]) else 1.05
    elif "Arauco" in fabricante_mdf:
        fator_mdf = 1.32 if any(c in cor_mdf for c in ["Louro", "Nogueira", "Grafite", "Sal Rosa"]) else 1.05
    elif "Guararapes" in fabricante_mdf:
        fator_mdf = 1.28 if any(c in cor_mdf for c in ["Freijó", "Savana", "Areia", "Cacau"]) else 1.02
    elif "Eucatex" in fabricante_mdf:
        fator_mdf = 1.22 if any(c in cor_mdf for c in ["Canela", "Ripado", "Bellagio"]) else 1.0

    if "Lisa Tradicional" in modelo_portas:
        fator_portas = 1.0
    elif "Cava Usinada" in modelo_portas:
        fator_portas = 1.22
    elif "Perfil Gola" in modelo_portas:
        fator_portas = 1.26
    else:
        fator_portas = 1.60

    if "Blum" in marca_ferragens:
        preco_dob = precos.get("dobradica", 18.5) * 2.8
        preco_corr = precos.get("corredica", 38.0) * 3.2
    elif "Hettich" in marca_ferragens:
        preco_dob = precos.get("dobradica", 18.5) * 2.5
        preco_corr = precos.get("corredica", 38.0) * 2.9
    elif "Häfele" in marca_ferragens:
        preco_dob = precos.get("dobradica", 18.5) * 2.1
        preco_corr = precos.get("corredica", 38.0) * 2.4
    elif "FGVTN" in marca_ferragens:
        preco_dob = precos.get("dobradica", 18.5) * 1.6
        preco_corr = precos.get("corredica", 38.0) * 1.8
    else:
        preco_dob = precos.get("dobradica", 18.5)
        preco_corr = precos.get("corredica", 38.0)

    custo_m2_mdf_base = precos.get("mdf_m2", 65.0) * fator_caixa * fator_tamp * fator_mdf * fator_portas
    area_val = max(area_m2_total, 5.0)
    qtd_ambientes = max(len(ambientes_selecionados), 1)
    area_por_comodo = area_val / qtd_ambientes

    for amb in ambientes_selecionados:
        if "Cozinha" in amb or "Gourmet" in amb:
            m_lin = max(area_por_comodo * 0.32, 3.2 if area_val >= 160 else 2.5)
            num_modulos = max(int(math.ceil(m_lin / 0.8)), 3 if area_val >= 160 else 2)
            
            for i in range(1, num_modulos + 1):
                items.append({
                    "nome": f"Balcão Inferior #{i} ({espessura_caixa}) - {amb}", "tipo": "Chapa MDF / Painel", "ambiente": amb,
                    "largura": 800, "altura": 720, "dimensoes": "800 x 720 x 580 mm", "qtd": 1,
                    "valor": 1.25 * custo_m2_mdf_base
                })
                items.append({
                    "nome": f"Portas Balcão #{i} ({fabricante_mdf} - {cor_mdf})", "tipo": "Chapa MDF / Painel", "ambiente": amb,
                    "largura": 395, "altura": 700, "dimensoes": "395 x 700 x 18 mm", "qtd": 2,
                    "valor": 0.58 * custo_m2_mdf_base
                })
                items.append({
                    "nome": f"Armário Aéreo #{i} ({amb})", "tipo": "Chapa MDF / Painel", "ambiente": amb,
                    "largura": 800, "altura": 700, "dimensoes": "800 x 700 x 350 mm", "qtd": 1,
                    "valor": 0.98 * custo_m2_mdf_base
                })

            if area_val >= 160:
                items.append({
                    "nome": f"Ilha Central / Bancada Gourmet ({espessura_tamponamento})", "tipo": "Chapa MDF / Painel", "ambiente": amb,
                    "largura": 2200, "altura": 900, "dimensoes": "2200 x 900 x 900 mm", "qtd": 1,
                    "valor": 2.8 * custo_m2_mdf_base
                })
            
            qtd_gavetas = 6 if area_val >= 160 else 3
            items.append({
                "nome": f"Gaveteiros com Amortecedor ({marca_ferragens})", "tipo": "Ferragem (Corrediça)", "ambiente": amb,
                "largura": 600, "altura": 720, "dimensoes": "600 mm", "qtd": qtd_gavetas,
                "valor": (qtd_gavetas * preco_corr) + (1.2 * (qtd_gavetas/3) * custo_m2_mdf_base)
            })
            qtd_dob = (num_modulos * 4) + (8 if area_val >= 160 else 4)
            items.append({"nome": f"Dobradiças Amortecedor ({marca_ferragens})", "tipo": "Ferragem (Dobradiça)", "ambiente": amb, "largura": 0, "altura": 0, "dimensoes": "Ø35mm", "qtd": qtd_dob, "valor": qtd_dob * preco_dob})
            items.append({"nome": f"Puxadores ({modelo_portas})", "tipo": "Acessório (Puxador)", "ambiente": amb, "largura": 0, "altura": 0, "dimensoes": "Kit", "qtd": qtd_dob // 2, "valor": (qtd_dob // 2) * precos.get("puxador", 25.0)})
            items.append({"nome": f"Fita de Borda PVC ({fabricante_mdf})", "tipo": "Fita de Borda", "ambiente": amb, "largura": 0, "altura": 0, "dimensoes": "-", "qtd": int(m_lin * 20), "valor": (m_lin * 20) * precos.get("fita_borda_m", 3.2)})

        elif "Dormitório" in amb or "Suíte" in amb or "Closet" in amb:
            m_lin = max(area_por_comodo * 0.30, 3.0 if area_val >= 160 else 2.0)
            num_portas = max(int(round(m_lin / 0.5)), 4 if area_val >= 160 else 2)
            
            items.append({"nome": f"Laterais/Estrutura Roupeiro ({espessura_caixa}) - {amb}", "tipo": "Chapa MDF / Painel", "ambiente": amb, "largura": 2600, "altura": 600, "dimensoes": "2600 x 600 x 18 mm", "qtd": num_portas + 1, "valor": (num_portas + 1) * (2.6 * 0.6 * custo_m2_mdf_base)})
            items.append({"nome": f"Portas Armário ({fabricante_mdf} - {cor_mdf})", "tipo": "Chapa MDF / Painel", "ambiente": amb, "largura": 2500, "altura": 500, "dimensoes": "2500 x 500 x 18 mm", "qtd": num_portas, "valor": num_portas * (2.5 * 0.5 * custo_m2_mdf_base)})
            items.append({"nome": f"Divisórias e Maleiros ({amb})", "tipo": "Chapa MDF / Painel", "ambiente": amb, "largura": 900, "altura": 550, "dimensoes": "900 x 550 x 18 mm", "qtd": num_portas * 2, "valor": (num_portas * 2) * (0.9 * 0.55 * custo_m2_mdf_base)})
            
            qtd_gav_closet = 8 if ("Closet" in amb or area_val >= 160) else 4
            items.append({"nome": f"Gavetas Internas Ocultas ({marca_ferragens})", "tipo": "Ferragem (Corrediça)", "ambiente": amb, "largura": 0, "altura": 0, "dimensoes": "450 mm", "qtd": qtd_gav_closet, "valor": qtd_gav_closet * preco_corr})
            items.append({"nome": f"Dobradiças Amortecedor ({marca_ferragens})", "tipo": "Ferragem (Dobradiça)", "ambiente": amb, "largura": 0, "altura": 0, "dimensoes": "Ø35mm", "qtd": num_portas * 4, "valor": (num_portas * 4) * preco_dob})
            items.append({"nome": f"Fita de Borda PVC ({fabricante_mdf})", "tipo": "Fita de Borda", "ambiente": amb, "largura": 0, "altura": 0, "dimensoes": "-", "qtd": int(m_lin * 22), "valor": (m_lin * 22) * precos.get("fita_borda_m", 3.2)})

        elif "Banheiro" in amb or "Lavabo" in amb:
            qtd_gab = 2 if ("Master" in amb or area_val >= 160) else 1
            items.append({"nome": f"Gabinete Suspenso Duplo ({amb})", "tipo": "Chapa MDF / Painel", "ambiente": amb, "largura": 1200 * qtd_gab, "altura": 650, "dimensoes": f"{1200 * qtd_gab} x 650 x 500 mm", "qtd": 1, "valor": 1.5 * qtd_gab * custo_m2_mdf_base})
            items.append({"nome": f"Espelheira / Painel c/ LED ({amb})", "tipo": "Chapa MDF / Painel", "ambiente": amb, "largura": 1200 * qtd_gab, "altura": 800, "dimensoes": f"{1200 * qtd_gab} x 800 x 150 mm", "qtd": 1, "valor": 0.9 * qtd_gab * custo_m2_mdf_base})
            items.append({"nome": f"Corrediças e Dobradiças ({marca_ferragens})", "tipo": "Ferragem (Corrediça)", "ambiente": amb, "largura": 0, "altura": 0, "dimensoes": "Kit", "qtd": 2 * qtd_gab, "valor": 2 * qtd_gab * preco_corr})

        elif "Home" in amb or "Sala" in amb or "Cinema" in amb:
            larg_painel = 3200 if area_val >= 160 else 2200
            items.append({"nome": f"Painel Ripado / Home Theater ({larg_painel}mm)", "tipo": "Chapa MDF / Painel", "ambiente": amb, "largura": larg_painel, "altura": 2600, "dimensoes": f"{larg_painel} x 2600 x 18 mm", "qtd": 1, "valor": ((larg_painel/1000) * 2.6 * custo_m2_mdf_base)})
            items.append({"nome": f"Rack Suspenso com Portas Basculantes ({amb})", "tipo": "Chapa MDF / Painel", "ambiente": amb, "largura": larg_painel, "altura": 450, "dimensoes": f"{larg_painel} x 450 x 400 mm", "qtd": 1, "valor": 1.5 * custo_m2_mdf_base})
            items.append({"nome": f"Pistões e Articulações ({marca_ferragens})", "tipo": "Ferragem (Dobradiça)", "ambiente": amb, "largura": 0, "altura": 0, "dimensoes": "Kit", "qtd": 6 if area_val >= 160 else 4, "valor": (6 if area_val >= 160 else 4) * preco_dob})

        else:
            items.append({"nome": f"Módulos e Armários Sob Medida ({amb})", "tipo": "Chapa MDF / Painel", "ambiente": amb, "largura": 1800, "altura": 2200, "dimensoes": "1800 x 2200 x 500 mm", "qtd": 1, "valor": 2.1 * custo_m2_mdf_base})
            items.append({"nome": f"Ferragens e Amortecedores ({marca_ferragens})", "tipo": "Ferragem (Dobradiça)", "ambiente": amb, "largura": 0, "altura": 0, "dimensoes": "Kit", "qtd": 6, "valor": 6 * preco_dob})

    total_mat = sum(i["valor"] for i in items)
    return items, total_mat

def render_login_page(msg_erro=""):
    erro_tag = f"<p class='text-rose-400 text-xs text-center bg-rose-950/60 border border-rose-800 p-2 rounded-xl'>{msg_erro}</p>" if msg_erro else ""
    return f"""<!DOCTYPE html>
<html lang="pt-br">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SaaS Marcenaria - Acesso ao Painel</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-slate-950 text-slate-100 flex items-center justify-center min-h-screen p-4 font-sans">
    <div class="max-w-md w-full bg-slate-900 border border-amber-500/30 rounded-3xl p-8 shadow-2xl space-y-6">
        <div class="text-center space-y-2">
            <div class="w-14 h-14 mx-auto rounded-2xl bg-gradient-to-br from-amber-400 to-amber-600 flex items-center justify-center font-black text-slate-950 text-xl shadow-lg">
                MVI
            </div>
            <h1 class="text-xl font-bold tracking-tight text-white">Plataforma SaaS Marcenaria</h1>
            <p class="text-xs text-slate-400">Acesso Corporativo da Empresa e Funcionários</p>
        </div>
        {erro_tag}
        <form action="/painel" method="post" class="space-y-4">
            <div>
                <label class="block text-xs font-semibold text-slate-300 uppercase mb-1">E-mail do Funcionário / Admin</label>
                <input type="email" name="username" required value="admin@mvi.com" class="w-full px-4 py-3 bg-slate-950 border border-slate-700 rounded-xl text-sm focus:outline-none focus:border-amber-500 text-slate-200">
            </div>
            <div>
                <label class="block text-xs font-semibold text-slate-300 uppercase mb-1">Senha de Acesso</label>
                <input type="password" name="password" required value="123456" class="w-full px-4 py-3 bg-slate-950 border border-slate-700 rounded-xl text-sm focus:outline-none focus:border-amber-500 text-slate-200">
            </div>
            <button type="submit" class="w-full py-3.5 bg-gradient-to-r from-amber-500 to-amber-600 hover:from-amber-400 hover:to-amber-500 text-slate-950 font-bold rounded-xl text-sm transition-all shadow-lg">
                Entrar no Sistema
            </button>
        </form>
        <div class="border-t border-slate-800 pt-4 text-center">
            <p class="text-[11px] text-slate-500">Sistema Multi-Tenant Comercial protegido por licença.</p>
        </div>
    </div>
</body>
</html>"""

def render_dashboard():
    empresa = get_empresa_by_id(SESSION["empresa_id"])
    nome_empresa = empresa["nome_empresa"] if empresa else "Marcenaria"
    is_admin = (SESSION["user_perfil"] == "admin_empresa")
    metricas = get_metricas_financeiras()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM orcamentos WHERE empresa_id = ? ORDER BY id DESC LIMIT 25", (SESSION["empresa_id"],))
    historico_rows = cursor.fetchall()
    
    # Buscar usuários cadastrados da empresa
    cursor.execute("SELECT email, nome, perfil FROM usuarios WHERE empresa_id = ?", (SESSION["empresa_id"],))
    usuarios_rows = cursor.fetchall()
    conn.close()

    historico_html = ""
    for h in historico_rows:
        pv_item = float(h['preco_venda'] or 0.0)
        rec_item = float(h['valor_recebido'] or 0.0)
        current_st = h['status'] or 'Em Negociação'
        
        tag_pgto = "<span class='px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-950 text-emerald-300 border border-emerald-800'>🟢 Quitado</span>" if (pv_item > 0 and rec_item >= pv_item) else "<span class='px-2 py-0.5 rounded text-[10px] font-semibold bg-rose-950 text-rose-300 border border-rose-800'>🔴 Pendente</span>"
        lucro_item = float(h['lucro_liquido'] or 0.0)
        lucro_col = f"<td class='py-3 px-4 text-right text-emerald-400 font-semibold'>R$ {lucro_item:,.2f}</td>" if is_admin else "<td class='py-3 px-4 text-right text-slate-500'>—</td>"

        historico_html += f"""
        <tr class="border-b border-slate-800 hover:bg-slate-800/40 text-xs">
            <td class="py-3 px-4 text-slate-400 font-mono">#{h['id']}</td>
            <td class="py-3 px-4 text-slate-300">{h['criado_em']}</td>
            <td class="py-3 px-4 text-white font-medium">{h['cliente_nome']}</td>
            <td class="py-3 px-4 text-slate-300">{h['cliente_ambiente']}</td>
            <td class="py-3 px-4 text-right text-amber-400 font-bold">R$ {pv_item:,.2f}</td>
            {lucro_col}
            <td class="py-3 px-4 text-center">
                <span class="px-2 py-1 bg-slate-950 border border-slate-700 rounded text-[11px] text-slate-200">{current_st}</span>
            </td>
            <td class="py-3 px-4 text-center">{tag_pgto}</td>
        </tr>
        """

    if not historico_html:
        historico_html = "<tr><td colspan='8' class='py-8 text-center text-xs text-slate-500'>Nenhum lead recebido ainda. Divulgue o formulário de captação exclusivo da empresa.</td></tr>"

    usuarios_html = ""
    for u in usuarios_rows:
        badge = "<span class='text-[10px] bg-amber-950 text-amber-300 border border-amber-500/40 px-2 py-0.5 rounded-xl'>Admin</span>" if u['perfil'] == 'admin_empresa' else "<span class='text-[10px] bg-emerald-950 text-emerald-300 border border-emerald-800 px-2 py-0.5 rounded-xl'>Vendedor</span>"
        usuarios_html += f"""
        <li class="flex items-center justify-between py-2 border-b border-slate-800 text-xs">
            <div>
                <span class="font-semibold text-white">{u['nome']}</span>
                <span class="text-slate-400 block text-[11px]">{u['email']}</span>
            </div>
            {badge}
        </li>
        """

    return f"""<!DOCTYPE html>
<html lang="pt-br">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{nome_empresa} - Painel</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        .tab-btn.active {{
            background: linear-gradient(135deg, #f59e0b, #d97706);
            color: #0f172a;
            border-color: #f59e0b;
            font-weight: 800;
        }}
        .tab-content {{
            display: none;
        }}
        .tab-content.active {{
            display: block;
        }}
    </style>
</head>
<body class="bg-slate-950 text-slate-100 min-h-screen font-sans">
    <header class="bg-slate-900 border-b border-slate-800 px-6 py-4 flex flex-wrap items-center justify-between gap-3">
        <div class="flex items-center space-x-3">
            <div class="w-9 h-9 rounded-xl bg-gradient-to-br from-amber-400 to-amber-600 flex items-center justify-center font-black text-slate-950 text-lg shadow">MVI</div>
            <span class="font-bold text-lg text-white tracking-wide">{nome_empresa}</span>
            <span class="text-xs bg-amber-950 border border-amber-500/40 text-amber-300 px-2.5 py-1 rounded-full">Ambiente Corporativo</span>
        </div>
        <div class="flex items-center space-x-3">
            <a href="/solicitar-orcamento/{empresa['slug'] if empresa else 'mvi'}" target="_blank" class="text-xs bg-amber-950 text-amber-300 border border-amber-500/40 px-3 py-1.5 rounded-xl hover:bg-amber-900/60 transition-colors">🔗 Link Instagram da Empresa</a>
            <span class="text-xs text-slate-400">Usuário: <b class="text-amber-400">{SESSION['user_nome']}</b></span>
            <a href="/" class="text-xs bg-slate-800 hover:bg-slate-700 px-3 py-1.5 rounded-xl text-slate-300 border border-slate-700">Sair</a>
        </div>
    </header>

    <nav class="bg-slate-900/80 border-b border-slate-800 px-6 py-3 sticky top-0 z-50 backdrop-blur-md">
        <div class="max-w-7xl mx-auto flex items-center gap-2 overflow-x-auto">
            <button onclick="mudarAba('aba-leads')" id="btn-aba-leads" class="tab-btn active px-4 py-2 rounded-xl text-xs font-bold border border-slate-700 text-slate-300 hover:bg-slate-800 transition-all shrink-0">
                <span>🏠 Leads & Orçamentos</span>
            </button>
            <button onclick="mudarAba('aba-equipe')" id="btn-aba-equipe" class="tab-btn px-4 py-2 rounded-xl text-xs font-bold border border-slate-700 text-slate-300 hover:bg-slate-800 transition-all shrink-0">
                <span>👥 Gestão de Funcionários</span>
            </button>
            <button onclick="mudarAba('aba-config')" id="btn-aba-config" class="tab-btn px-4 py-2 rounded-xl text-xs font-bold border border-slate-700 text-slate-300 hover:bg-slate-800 transition-all shrink-0">
                <span>⚙️ Dados da Empresa</span>
            </button>
        </div>
    </nav>

    <main class="max-w-7xl mx-auto p-6 space-y-6">

        <div id="aba-leads" class="tab-content active space-y-6">
            <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                <div class="bg-slate-900 border border-slate-800 p-5 rounded-2xl space-y-1 shadow-lg">
                    <p class="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">Faturamento Fechado</p>
                    <p class="text-xl font-bold text-amber-400">R$ {metricas['faturamento_total']:,.2f}</p>
                    <p class="text-[11px] text-slate-500">Recebido: R$ {metricas['total_recebido']:,.2f} | Saldo: R$ {metricas['saldo_a_receber']:,.2f}</p>
                </div>
                <div class="bg-slate-900 border border-slate-800 p-5 rounded-2xl space-y-1 shadow-lg">
                    <p class="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">Lucro Líquido</p>
                    <p class="text-xl font-bold text-emerald-400">R$ {metricas['lucro_acumulado']:,.2f}</p>
                    <p class="text-[11px] text-slate-500">Saldo limpo gerado no caixa</p>
                </div>
                <div class="bg-slate-900 border border-slate-800 p-5 rounded-2xl space-y-1 shadow-lg">
                    <p class="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">Ticket Médio</p>
                    <p class="text-xl font-bold text-white">R$ {metricas['ticket_medio']:,.2f}</p>
                    <p class="text-[11px] text-slate-500">{metricas['aprovados']} projetos fechados</p>
                </div>
                <div class="bg-slate-900 border border-slate-800 p-5 rounded-2xl space-y-1 shadow-lg">
                    <p class="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">Taxa de Conversão</p>
                    <p class="text-xl font-bold text-amber-400">{metricas['taxa_conversao']:.1f}%</p>
                    <p class="text-[11px] text-slate-500">{metricas['total_orcamentos']} orçamentos gerados</p>
                </div>
            </div>

            <div class="bg-slate-900 border border-slate-800 rounded-3xl overflow-hidden shadow-lg">
                <div class="p-4 border-b border-slate-800 flex justify-between items-center bg-slate-850">
                    <h3 class="text-sm font-semibold text-white">📁 Pedidos & Briefings Recebidos</h3>
                    <a href="/exportar-csv" class="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 rounded-xl text-xs font-semibold">
                        <span>📊 Exportar CSV</span>
                    </a>
                </div>
                <div class="overflow-x-auto">
                    <table class="w-full text-left border-collapse">
                        <thead>
                            <tr class="bg-slate-800/40 border-b border-slate-800 text-xs font-semibold text-slate-400 uppercase">
                                <th class="py-3 px-4"># ID</th>
                                <th class="py-3 px-4">Data/Hora</th>
                                <th class="py-3 px-4">Cliente</th>
                                <th class="py-3 px-4">Ambiente</th>
                                <th class="py-3 px-4 text-right">Valor Venda</th>
                                <th class="py-3 px-4 text-right">Lucro Líquido</th>
                                <th class="py-3 px-4 text-center">Status</th>
                                <th class="py-3 px-4 text-center">Pagamento</th>
                            </tr>
                        </thead>
                        <tbody>
                            {historico_html}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>

        <div id="aba-equipe" class="tab-content space-y-6">
            <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <div class="lg:col-span-2 bg-slate-900 border border-slate-800 rounded-3xl p-6 shadow-lg space-y-4">
                    <h2 class="text-base font-semibold text-white">Cadastrar Novo Funcionário</h2>
                    <form action="/criar-usuario" method="post" class="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                        <div>
                            <label class="block text-slate-400 mb-1">Nome do Funcionário</label>
                            <input type="text" name="nome" required placeholder="Ex: Lucas Vendedor" class="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-xl text-white">
                        </div>
                        <div>
                            <label class="block text-slate-400 mb-1">E-mail de Login</label>
                            <input type="email" name="email" required placeholder="lucas@marcenaria.com" class="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-xl text-white">
                        </div>
                        <div>
                            <label class="block text-slate-400 mb-1">Senha</label>
                            <input type="password" name="senha" required placeholder="******" class="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-xl text-white">
                        </div>
                        <div>
                            <label class="block text-slate-400 mb-1">Nível de Acesso</label>
                            <select name="perfil" class="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-xl text-white">
                                <option value="vendedor">Vendedor (Sem acesso a margens/lucro)</option>
                                <option value="admin_empresa">Gerente / Admin da Marcenaria</option>
                            </select>
                        </div>
                        <div class="col-span-full pt-2">
                            <button type="submit" class="px-6 py-2.5 bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold rounded-xl text-xs">
                                + Cadastrar Acesso
                            </button>
                        </div>
                    </form>
                </div>
                <div class="bg-slate-900 border border-slate-800 rounded-3xl p-6 shadow-lg">
                    <h3 class="text-xs font-semibold text-slate-300 uppercase mb-3">Equipe Ativa</h3>
                    <ul class="divide-y divide-slate-800">
                        {usuarios_html}
                    </ul>
                </div>
            </div>
        </div>

        <div id="aba-config" class="tab-content space-y-6">
            <div class="bg-slate-900 border border-slate-800 rounded-3xl p-6 shadow-lg space-y-4">
                <h2 class="text-base font-semibold text-white">Dados da Empresa Licenciada</h2>
                <form action="/salvar-empresa" method="post" class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 text-xs">
                    <div>
                        <label class="block text-slate-400 mb-1">Razão Social / Nome Fantasia</label>
                        <input type="text" name="nome_empresa" value="{empresa['nome_empresa']}" required class="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-xl text-white">
                    </div>
                    <div>
                        <label class="block text-slate-400 mb-1">CNPJ</label>
                        <input type="text" name="cnpj" value="{empresa['cnpj']}" required class="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-xl text-white">
                    </div>
                    <div>
                        <label class="block text-slate-400 mb-1">WhatsApp da Empresa</label>
                        <input type="text" name="telefone_empresa" value="{empresa['telefone']}" required class="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-xl text-white">
                    </div>
                    <div>
                        <label class="block text-slate-400 mb-1">Chave PIX</label>
                        <div class="flex gap-2">
                            <input type="text" name="pix" value="{empresa['pix']}" required class="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-xl text-white">
                            <button type="submit" class="px-4 py-2 bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold rounded-xl shrink-0">
                                Salvar
                            </button>
                        </div>
                    </div>
                </form>
            </div>
        </div>

    </main>

    <script>
        function mudarAba(abaId) {{
            var contents = document.getElementsByClassName('tab-content');
            for (var i = 0; i < contents.length; i++) {{
                contents[i].classList.remove('active');
            }}
            var btns = document.getElementsByClassName('tab-btn');
            for (var i = 0; i < btns.length; i++) {{
                btns[i].classList.remove('active');
            }}
            var target = document.getElementById(abaId);
            if (target) {{
                target.classList.add('active');
            }}
            var btn = document.getElementById('btn-' + abaId);
            if (btn) {{
                btn.classList.add('active');
            }}
            window.scrollTo({{ top: 0, behavior: 'smooth' }});
        }}
    </script>
</body>
</html>"""

@app.get("/", response_class=HTMLResponse)
def home():
    return render_login_page()

@app.get("/solicitar-orcamento", response_class=HTMLResponse)
@app.get("/solicitar-orcamento/{slug}", response_class=HTMLResponse)
def solicitar_orcamento(slug: str = "mvi"):
    return render_pagina_captacao()

@app.get("/painel", response_class=HTMLResponse)
def painel_direto():
    return render_dashboard()

@app.get("/painel-get", response_class=HTMLResponse)
def painel_get():
    return render_dashboard()

@app.post("/painel", response_class=HTMLResponse)
def login(username: str = Form(...), password: str = Form(...)):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM usuarios WHERE email = ? AND senha = ?", (username, password))
    user_row = cursor.fetchone()
    conn.close()
    
    if not user_row:
        return render_login_page("E-mail ou senha incorretos. Tente novamente.")

    SESSION["user_email"] = user_row["email"]
    SESSION["user_nome"] = user_row["nome"]
    SESSION["user_perfil"] = user_row["perfil"]
    SESSION["empresa_id"] = user_row["empresa_id"]

    return render_dashboard()

@app.post("/enviar-solicitacao-lead", response_class=HTMLResponse)
async def enviar_solicitacao_lead(
    nome: str = Form(...),
    whatsapp: str = Form(...),
    area_m2_total: float = Form(180.0),
    espessura_caixa: str = Form("MDF 18mm"),
    espessura_tamponamento: str = Form("Tamponamento 25mm"),
    fabricante_mdf: str = Form("Duratex"),
    cor_mdf: str = Form("Freijó Puro / Natural"),
    modelo_portas: str = Form("Perfil Gola em Alumínio (Rometal)"),
    marca_ferragens: str = Form("Blum (Linha Blumotion Áustria)"),
    ambientes_check: List[str] = Form(["Cozinha c/ Ilha", "Suíte Master c/ Closet"]),
    cidade: str = Form(...),
    descricao: str = Form(""),
    planta: UploadFile = File(...),
    inspiracao: UploadFile = File(None)
):
    empresa = get_empresa_by_id(SESSION.get("empresa_id", 1))
    precos = json.loads(empresa["precos_json"]) if empresa and empresa["precos_json"] else get_precos_config()
    
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

    items_auto, total_mat = calcular_engenharia_avancada(
        ambientes_check, area_m2_total, espessura_caixa, espessura_tamponamento,
        fabricante_mdf, cor_mdf, modelo_portas, marca_ferragens, precos
    )
    
    qtd_comodos = max(len(ambientes_check), 1)
    dias_prod = max(int(math.ceil(qtd_comodos * 3.0)), 4)
    custo_mo = dias_prod * 180.0
    custo_frete_mont = max(qtd_comodos * 450.0, 800.0)
    markup = 2.2
    
    pv_estimado = (total_mat + custo_mo + custo_frete_mont) * markup
    lucro_estimado = pv_estimado - (total_mat + custo_mo + custo_frete_mont + (pv_estimado * 0.10))

    nome_ambientes_str = " + ".join(ambientes_check)
    obs_completa = f"Lead {area_m2_total}m² ({cidade}) | MDF: {fabricante_mdf} ({cor_mdf}) | Ferragens: {marca_ferragens} | Portas: {modelo_portas}"
    if descricao:
        obs_completa += f" | Detalhes: {descricao}"

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO orcamentos (
            empresa_id, criado_em, cliente_nome, cliente_telefone, cliente_ambiente,
            prazo_entrega, data_entrega_prevista, status, custo_materiais,
            custo_mao_obra, custo_frete_montagem, imposto_pct, comissao_pct,
            markup, preco_venda, lucro_liquido, entrada_valor, num_parcelas,
            forma_pagamento, valor_recebido, imagens_json, ambientes_json,
            observacoes_tecnicas, items_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        empresa["id"] if empresa else 1,
        agora,
        nome,
        whatsapp,
        nome_ambientes_str,
        "30 dias úteis",
        (date.today() + timedelta(days=30)).strftime("%Y-%m-%d"),
        "Novo Lead Instagram",
        total_mat, custo_mo, custo_frete_mont, 6.0, 4.0, markup,
        pv_estimado, lucro_estimado, pv_estimado * 0.3, 3,
        "Entrada + 3x no Cartão", 0.0, json.dumps(imagens_lead), json.dumps(ambientes_check),
        obs_completa, json.dumps(items_auto)
    ))
    conn.commit()
    novo_id = cursor.lastrowid
    conn.close()

    msg_zap = f"""Olá! Meu nome é *{nome}*.
Simulei meu projeto de móveis sob medida (#{novo_id:04d}):

📋 *BRIEFING:*
• *Cidade:* {cidade}
• *Metragem:* {area_m2_total} m²
• *Ambientes:* {nome_ambientes_str}
• *MDF:* {fabricante_mdf} ({cor_mdf})
• *Ferragens:* {marca_ferragens}
• *Portas:* {modelo_portas}
• *Estimativa:* R$ {pv_estimado:,.2f}
"""
    tel_limpo = str(empresa['telefone'] or "").replace('(', '').replace(')', '').replace('-', '').replace(' ', '')
    zap_url = f"https://api.whatsapp.com/send?phone=55{tel_limpo}&text={urllib.parse.quote(msg_zap)}"

    return render_pagina_captacao(sucesso=True, orc_id=novo_id, estimativa=pv_estimado, zap_url=zap_url)

@app.post("/criar-usuario", response_class=HTMLResponse)
def criar_usuario(nome: str = Form(...), email: str = Form(...), senha: str = Form(...), perfil: str = Form(...)):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO usuarios (email, senha, nome, perfil, empresa_id) VALUES (?, ?, ?, ?, ?)", (email, senha, nome, perfil, SESSION["empresa_id"]))
    conn.commit()
    conn.close()
    return RedirectResponse(url="/painel-get", status_code=303)

@app.post("/salvar-empresa", response_class=HTMLResponse)
def salvar_empresa(nome_empresa: str = Form(...), cnpj: str = Form(...), telefone_empresa: str = Form(...), pix: str = Form(...)):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE empresas SET nome_empresa = ?, cnpj = ?, telefone = ?, pix = ? WHERE id = ?
    """, (nome_empresa, cnpj, telefone_empresa, pix, SESSION["empresa_id"]))
    conn.commit()
    conn.close()
    return RedirectResponse(url="/painel-get", status_code=303)

@app.get("/exportar-csv")
def exportar_csv():
    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')
    writer.writerow(["ID", "Data/Hora", "Cliente", "Telefone", "Ambiente", "Preco Venda (R$)", "Lucro Liquido (R$)"])
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM orcamentos WHERE empresa_id = ? ORDER BY id DESC", (SESSION["empresa_id"],))
    for r in cursor.fetchall():
        writer.writerow([r["id"], r["criado_em"], r["cliente_nome"], r["cliente_telefone"], r["cliente_ambiente"], f"{r['preco_venda']:.2f}", f"{r['lucro_liquido']:.2f}"])
    conn.close()
    
    return Response(
        content=output.getvalue().encode('utf-8-sig'),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=relatorio-marcenaria.csv"}
    )

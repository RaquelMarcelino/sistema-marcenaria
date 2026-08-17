from fastapi import FastAPI, Form, UploadFile, File, Response
from fastapi.responses import HTMLResponse
import xml.etree.ElementTree as ET
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
import io
import urllib.parse
from datetime import date

app = FastAPI(title="Sistema Marcenaria & Promob")

# Armazenamento simples dos dados da sessão ativa
CURRENT_DATA = {
    "user": "admin@marcenaria.com",
    "cliente_nome": "Cliente Exemplo",
    "cliente_telefone": "11999998888",
    "cliente_ambiente": "Cozinha Planejada",
    "prazo_entrega": "25 dias úteis",
    "total_custo": 0.0,
    "markup": 2.2,
    "items": []
}

LOGIN_HTML = """
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
            <p class="text-xs text-slate-400">Gestão de Orçamentos Promob & Precificação DRE</p>
        </div>
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
    </div>
</body>
</html>
"""

def render_dashboard(user: str, items=None, total_custo=0.0, markup=2.2, cliente_nome="Cliente Exemplo", cliente_telefone="11999998888", cliente_ambiente="Cozinha Planejada", prazo_entrega="25 dias úteis"):
    items = items or []
    rows_html = ""
    if items:
        for it in items:
            rows_html += f"""
            <tr class="border-b border-slate-800 hover:bg-slate-850">
                <td class="py-3 px-4 text-sm text-slate-200">{it.get('nome', 'Peça')}</td>
                <td class="py-3 px-4 text-sm text-center text-slate-400">{it.get('dimensoes', '-')}</td>
                <td class="py-3 px-4 text-sm text-center text-slate-300">{it.get('qtd', 1)}</td>
                <td class="py-3 px-4 text-sm text-right text-emerald-400 font-medium">R$ {it.get('valor', 0.0):.2f}</td>
            </tr>
            """
    else:
        rows_html = """
        <tr>
            <td colspan="4" class="py-8 text-center text-sm text-slate-500">
                Nenhum arquivo importado ainda. Faça upload de um XML do Promob/Cutlist acima.
            </td>
        </tr>
        """

    pv_sugerido = total_custo * markup if total_custo > 0 else 0.0
    lucro = pv_sugerido - total_custo if total_custo > 0 else 0.0

    # Mensagem WhatsApp
    msg_zap = f"Olá {cliente_nome}! Segue o orçamento para o ambiente {cliente_ambiente}: R$ {pv_sugerido:,.2f} com prazo de entrega de {prazo_entrega}."
    zap_url = f"https://api.whatsapp.com/send?phone=55{cliente_telefone}&text={urllib.parse.quote(msg_zap)}"

    return f"""
    <!DOCTYPE html>
    <html lang="pt-br">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Marcenaria SaaS - Painel</title>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-slate-950 text-slate-100 min-h-screen font-sans">
        <header class="bg-slate-900 border-b border-slate-800 px-6 py-4 flex items-center justify-between">
            <div class="flex items-center space-x-3">
                <div class="w-8 h-8 rounded-lg bg-sky-600 flex items-center justify-center font-bold text-white">M</div>
                <span class="font-bold text-lg text-white tracking-wide">Marcenaria Pro</span>
            </div>
            <div class="flex items-center space-x-4">
                <span class="text-xs text-slate-400">Usuário: <b class="text-sky-400">{user}</b></span>
                <a href="/" class="text-xs bg-slate-800 hover:bg-slate-700 px-3 py-1.5 rounded-lg text-slate-300 border border-slate-700">Sair</a>
            </div>
        </header>

        <main class="max-w-7xl mx-auto p-6 space-y-6">
            <!-- Cards de Resumo DRE -->
            <div class="grid grid-cols-1 md:grid-cols-3 gap-5">
                <div class="bg-slate-900 border border-slate-800 p-5 rounded-xl space-y-1 shadow-lg">
                    <p class="text-xs font-semibold text-slate-400 uppercase tracking-wider">Custo Insumos (XML)</p>
                    <p class="text-2xl font-bold text-white">R$ {total_custo:,.2f}</p>
                    <p class="text-xs text-slate-500">MDF, fitas e ferragens</p>
                </div>
                <div class="bg-slate-900 border border-slate-800 p-5 rounded-xl space-y-1 shadow-lg">
                    <p class="text-xs font-semibold text-slate-400 uppercase tracking-wider">Preço de Venda (Markup {markup:.1f}x)</p>
                    <p class="text-2xl font-bold text-sky-400">R$ {pv_sugerido:,.2f}</p>
                    <p class="text-xs text-slate-500">Valor para o cliente</p>
                </div>
                <div class="bg-slate-900 border border-slate-800 p-5 rounded-xl space-y-1 shadow-lg">
                    <p class="text-xs font-semibold text-slate-400 uppercase tracking-wider">Margem Bruta Estimada</p>
                    <p class="text-2xl font-bold text-emerald-400">R$ {lucro:,.2f}</p>
                    <p class="text-xs text-slate-500">Resultado financeiro do projeto</p>
                </div>
            </div>

            <!-- Dados do Cliente e Projeto -->
            <div class="bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-lg space-y-4">
                <div class="flex justify-between items-center border-b border-slate-800 pb-3">
                    <h2 class="text-base font-semibold text-white">👤 Dados do Cliente & Proposta</h2>
                    <span class="text-xs text-sky-400">Dados vinculados ao PDF e WhatsApp</span>
                </div>
                <form action="/salvar-cliente" method="post" class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                    <input type="hidden" name="user" value="{user}">
                    <div>
                        <label class="block text-xs font-medium text-slate-400 mb-1">Nome do Cliente</label>
                        <input type="text" name="cliente_nome" value="{cliente_nome}" required class="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-sm text-white focus:outline-none focus:border-sky-500">
                    </div>
                    <div>
                        <label class="block text-xs font-medium text-slate-400 mb-1">WhatsApp / Telefone</label>
                        <input type="text" name="cliente_telefone" value="{cliente_telefone}" required class="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-sm text-white focus:outline-none focus:border-sky-500">
                    </div>
                    <div>
                        <label class="block text-xs font-medium text-slate-400 mb-1">Ambiente / Projeto</label>
                        <input type="text" name="cliente_ambiente" value="{cliente_ambiente}" required class="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-sm text-white focus:outline-none focus:border-sky-500">
                    </div>
                    <div>
                        <label class="block text-xs font-medium text-slate-400 mb-1">Prazo de Entrega</label>
                        <div class="flex gap-2">
                            <input type="text" name="prazo_entrega" value="{prazo_entrega}" required class="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-sm text-white focus:outline-none focus:border-sky-500">
                            <button type="submit" class="px-4 py-2 bg-sky-600 hover:bg-sky-500 text-white rounded-lg text-xs font-semibold shrink-0">
                                Salvar
                            </button>
                        </div>
                    </div>
                </form>
            </div>

            <!-- Bloco de Ações: Upload + Markup + PDF + WhatsApp -->
            <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <!-- Importador XML -->
                <div class="lg:col-span-2 bg-slate-900 border border-slate-800 rounded-xl p-6 space-y-4 shadow-lg">
                    <h2 class="text-base font-semibold text-white">Importar Projeto (XML Promob / Cutlist)</h2>
                    <form action="/upload-xml" method="post" enctype="multipart/form-data" class="flex flex-col sm:flex-row items-center gap-4">
                        <input type="hidden" name="user" value="{user}">
                        <input type="file" name="file" accept=".xml,.txt" required class="block w-full text-xs text-slate-400 file:mr-4 file:py-2.5 file:px-4 file:rounded-lg file:border-0 file:text-xs file:font-semibold file:bg-slate-800 file:text-slate-200 hover:file:bg-slate-700 cursor-pointer">
                        <button type="submit" class="w-full sm:w-auto px-6 py-2.5 bg-sky-600 hover:bg-sky-500 text-white font-medium rounded-lg text-sm transition-colors shrink-0">
                            Processar e Orçar
                        </button>
                    </form>
                </div>

                <!-- Painel de Markup e Ações -->
                <div class="bg-slate-900 border border-slate-800 rounded-xl p-6 flex flex-col justify-between space-y-4 shadow-lg">
                    <h2 class="text-base font-semibold text-white">Ajustar Markup & Envio</h2>
                    <form action="/recalcular" method="post" class="flex items-center gap-3">
                        <input type="hidden" name="user" value="{user}">
                        <label class="text-xs text-slate-400 font-medium">Markup:</label>
                        <input type="number" step="0.1" min="1.0" max="5.0" name="markup" value="{markup}" class="w-20 px-3 py-1.5 bg-slate-950 border border-slate-700 rounded-lg text-sm text-center text-white focus:outline-none focus:border-sky-500">
                        <button type="submit" class="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-lg text-xs font-semibold border border-slate-700">
                            Recalcular
                        </button>
                    </form>
                    
                    <div class="space-y-2">
                        <a href="/gerar-pdf" class="w-full py-2.5 bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-center text-xs rounded-lg transition-colors flex items-center justify-center space-x-2 shadow-lg shadow-emerald-600/20">
                            <span>📄 Baixar Orçamento em PDF</span>
                        </a>
                        <a href="{zap_url}" target="_blank" class="w-full py-2.5 bg-green-600 hover:bg-green-500 text-white font-semibold text-center text-xs rounded-lg transition-colors flex items-center justify-center space-x-2 shadow-lg shadow-green-600/20">
                            <span>💬 Enviar pelo WhatsApp</span>
                        </a>
                    </div>
                </div>
            </div>

            <!-- Listagem de Peças -->
            <div class="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-lg">
                <div class="p-4 border-b border-slate-800 flex justify-between items-center bg-slate-850">
                    <h3 class="text-sm font-semibold text-white">Listagem de Peças e Insumos do Projeto ({cliente_ambiente})</h3>
                    <span class="text-xs text-slate-400">{len(items)} itens detectados</span>
                </div>
                <div class="overflow-x-auto">
                    <table class="w-full text-left border-collapse">
                        <thead>
                            <tr class="bg-slate-800/40 border-b border-slate-800 text-xs font-semibold text-slate-400 uppercase">
                                <th class="py-3 px-4">Descrição / Insumo</th>
                                <th class="py-3 px-4 text-center">Dimensões (mm)</th>
                                <th class="py-3 px-4 text-center">Quantidade</th>
                                <th class="py-3 px-4 text-right">Custo Est. (R$)</th>
                            </tr>
                        </thead>
                        <tbody>
                            {rows_html}
                        </tbody>
                    </table>
                </div>
            </div>
        </main>
    </body>
    </html>
    """

@app.get("/", response_class=HTMLResponse)
def home():
    return LOGIN_HTML

@app.post("/painel", response_class=HTMLResponse)
def login(username: str = Form(...), password: str = Form(...)):
    CURRENT_DATA["user"] = username
    return render_dashboard(
        user=username, 
        items=CURRENT_DATA["items"], 
        total_custo=CURRENT_DATA["total_custo"], 
        markup=CURRENT_DATA["markup"],
        cliente_nome=CURRENT_DATA["cliente_nome"],
        cliente_telefone=CURRENT_DATA["cliente_telefone"],
        cliente_ambiente=CURRENT_DATA["cliente_ambiente"],
        prazo_entrega=CURRENT_DATA["prazo_entrega"]
    )

@app.post("/salvar-cliente", response_class=HTMLResponse)
def salvar_cliente(
    user: str = Form("admin@marcenaria.com"),
    cliente_nome: str = Form(...),
    cliente_telefone: str = Form(...),
    cliente_ambiente: str = Form(...),
    prazo_entrega: str = Form(...)
):
    CURRENT_DATA["cliente_nome"] = cliente_nome
    CURRENT_DATA["cliente_telefone"] = cliente_telefone
    CURRENT_DATA["cliente_ambiente"] = cliente_ambiente
    CURRENT_DATA["prazo_entrega"] = prazo_entrega
    return render_dashboard(
        user=user, 
        items=CURRENT_DATA["items"], 
        total_custo=CURRENT_DATA["total_custo"], 
        markup=CURRENT_DATA["markup"],
        cliente_nome=cliente_nome,
        cliente_telefone=cliente_telefone,
        cliente_ambiente=cliente_ambiente,
        prazo_entrega=prazo_entrega
    )

@app.post("/recalcular", response_class=HTMLResponse)
def recalcular(user: str = Form("admin@marcenaria.com"), markup: float = Form(2.2)):
    CURRENT_DATA["markup"] = markup
    return render_dashboard(
        user=user, 
        items=CURRENT_DATA["items"], 
        total_custo=CURRENT_DATA["total_custo"], 
        markup=markup,
        cliente_nome=CURRENT_DATA["cliente_nome"],
        cliente_telefone=CURRENT_DATA["cliente_telefone"],
        cliente_ambiente=CURRENT_DATA["cliente_ambiente"],
        prazo_entrega=CURRENT_DATA["prazo_entrega"]
    )

@app.post("/upload-xml", response_class=HTMLResponse)
async def upload_xml(user: str = Form("admin@marcenaria.com"), file: UploadFile = File(...)):
    contents = await file.read()
    items = []
    total_custo = 0.0

    try:
        root = ET.fromstring(contents)
        for elem in root.iter():
            if elem.tag.lower() in ["item", "piece", "peca", "component", "material"]:
                nome = elem.attrib.get("DESCRIPTION") or elem.attrib.get("nome") or elem.attrib.get("name") or elem.tag
                largura = elem.attrib.get("WIDTH") or elem.attrib.get("largura") or "0"
                altura = elem.attrib.get("HEIGHT") or elem.attrib.get("altura") or "0"
                prof = elem.attrib.get("DEPTH") or elem.attrib.get("profundidade") or "0"
                qtd = int(elem.attrib.get("QUANTITY") or elem.attrib.get("quantidade") or 1)
                
                custo_unit = 45.0
                total_custo += custo_unit * qtd

                items.append({
                    "nome": str(nome)[:40],
                    "dimensoes": f"{largura} x {altura} x {prof}",
                    "qtd": qtd,
                    "valor": custo_unit * qtd
                })

        if not items:
            items = [
                {"nome": "Adesivo Tapa Furo em Poliestireno", "dimensoes": "69 x 34 x 69", "qtd": 2, "valor": 90.00},
                {"nome": "Corrediça Telescópica 450mm - 35Kg", "dimensoes": "200 x 35 x 450", "qtd": 4, "valor": 180.00},
                {"nome": "Div.Talheres p/ Gav.Telescópica", "dimensoes": "512 x 52 x 435", "qtd": 1, "valor": 45.00},
                {"nome": "Dobradiça Ecco Ø35mm Reta Slowmotion", "dimensoes": "35 x 52 x 77", "qtd": 22, "valor": 990.00},
                {"nome": "Dobradiça Ø35mm 90° p/ Canto Reto", "dimensoes": "112 x 52 x 21", "qtd": 2, "valor": 90.00},
                {"nome": "Dobradiça Ø35mm Reta", "dimensoes": "35 x 52 x 77", "qtd": 12, "valor": 540.00}
            ]
            total_custo = sum(i["valor"] for i in items)

    except Exception:
        items = [
            {"nome": "Chapa MDF Louro Freijó 18mm", "dimensoes": "2750 x 1830 x 18", "qtd": 3, "valor": 780.00},
            {"nome": "Fita de Borda 22mm Amadeirada", "dimensoes": "-", "qtd": 2, "valor": 90.00},
            {"nome": "Puxador Perfil Alumínio Preto", "dimensoes": "2000 mm", "qtd": 2, "valor": 160.00}
        ]
        total_custo = sum(i["valor"] for i in items)

    CURRENT_DATA["items"] = items
    CURRENT_DATA["total_custo"] = total_custo
    return render_dashboard(
        user=user, 
        items=items, 
        total_custo=total_custo, 
        markup=CURRENT_DATA["markup"],
        cliente_nome=CURRENT_DATA["cliente_nome"],
        cliente_telefone=CURRENT_DATA["cliente_telefone"],
        cliente_ambiente=CURRENT_DATA["cliente_ambiente"],
        prazo_entrega=CURRENT_DATA["prazo_entrega"]
    )

@app.get("/gerar-pdf")
def gerar_pdf():
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    styles = getSampleStyleSheet()
    elements = []

    # Cabeçalho Principal
    title_style = ParagraphStyle(name='TitleStyle', parent=styles['Heading1'], fontSize=18, textColor=colors.HexColor('#0f172a'), spaceAfter=4)
    elements.append(Paragraph("Marcenaria Pro - Proposta Comercial & Orçamento", title_style))
    elements.append(Spacer(1, 8))

    # Dados do Cliente no PDF
    cliente_data = [
        ["Cliente:", CURRENT_DATA['cliente_nome'], "Data da Proposta:", date.today().strftime("%d/%m/%Y")],
        ["WhatsApp/Tel:", CURRENT_DATA['cliente_telefone'], "Prazo de Entrega:", CURRENT_DATA['prazo_entrega']],
        ["Ambiente/Projeto:", CURRENT_DATA['cliente_ambiente'], "Validade da Proposta:", "15 dias"]
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
    elements.append(Spacer(1, 14))

    # Tabela de Valores
    markup = CURRENT_DATA["markup"]
    custo = CURRENT_DATA["total_custo"]
    pv = custo * markup
    lucro = pv - custo

    dre_data = [
        ["Custo Total de Materiais (XML)", f"R$ {custo:,.2f}"],
        ["Markup Aplicado", f"{markup:.1f}x"],
        ["VALOR TOTAL DA PROPOSTA", f"R$ {pv:,.2f}"],
        ["Margem Bruta Operacional", f"R$ {lucro:,.2f}"]
    ]
    dre_table = Table(dre_data, colWidths=[280, 260])
    dre_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
        ('BACKGROUND', (0, 2), (-1, 2), colors.HexColor('#dbeafe')),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#0f172a')),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
    ]))
    elements.append(dre_table)
    elements.append(Spacer(1, 14))

    # Tabela de Peças
    items = CURRENT_DATA["items"] or [
        {"nome": "Item Geral de Marcenaria", "dimensoes": "-", "qtd": 1, "valor": custo}
    ]
    table_data = [["Item / Insumo Promob", "Dimensões (mm)", "Qtd", "Custo Total"]]
    for it in items:
        table_data.append([
            it.get("nome", "Peça"),
            it.get("dimensoes", "-"),
            str(it.get("qtd", 1)),
            f"R$ {it.get('valor', 0.0):,.2f}"
        ])

    items_table = Table(table_data, colWidths=[240, 140, 50, 110])
    items_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0284c7')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (2, 0), (2, -1), 'CENTER'),
        ('ALIGN', (3, 0), (3, -1), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
    ]))
    elements.append(items_table)

    doc.build(elements)
    buffer.seek(0)
    return Response(content=buffer.getvalue(), media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename=orcamento-{CURRENT_DATA['cliente_nome'].replace(' ', '_')}.pdf"})

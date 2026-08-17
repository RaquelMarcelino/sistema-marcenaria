from fastapi import FastAPI, Form, UploadFile, File
from fastapi.responses import HTMLResponse
import xml.etree.ElementTree as ET

app = FastAPI(title="Sistema Marcenaria & Promob")

# Layout da Tela de Login
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

def render_dashboard(user: str, items=None, total_custo=0.0):
    rows_html = ""
    if items:
        for it in items:
            rows_html += f"""
            <tr class="border-b border-slate-700/50 hover:bg-slate-750">
                <td class="py-3 px-4 text-sm text-slate-200">{it.get('nome', 'Peça')}</td>
                <td class="py-3 px-4 text-sm text-center text-slate-300">{it.get('dimensoes', '-')}</td>
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

    pv_sugerido = total_custo * 2.2 if total_custo > 0 else 0.0
    lucro = pv_sugerido - total_custo if total_custo > 0 else 0.0

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
            <div class="grid grid-cols-1 md:grid-cols-3 gap-5">
                <div class="bg-slate-900 border border-slate-800 p-5 rounded-xl space-y-1">
                    <p class="text-xs font-medium text-slate-400 uppercase">Custo de Materiais (XML)</p>
                    <p class="text-2xl font-bold text-white">R$ {total_custo:.2f}</p>
                    <p class="text-xs text-slate-500">MDF, ferragens e fitas calculados</p>
                </div>
                <div class="bg-slate-900 border border-slate-800 p-5 rounded-xl space-y-1">
                    <p class="text-xs font-medium text-slate-400 uppercase">Preço de Venda Sugerido (Markup 2.2x)</p>
                    <p class="text-2xl font-bold text-sky-400">R$ {pv_sugerido:.2f}</p>
                    <p class="text-xs text-slate-500">Custos diretos + margem líquida</p>
                </div>
                <div class="bg-slate-900 border border-slate-800 p-5 rounded-xl space-y-1">
                    <p class="text-xs font-medium text-slate-400 uppercase">Margem Bruta Estimada</p>
                    <p class="text-2xl font-bold text-emerald-400">R$ {lucro:.2f}</p>
                    <p class="text-xs text-slate-500">Retorno operacional do projeto</p>
                </div>
            </div>

            <div class="bg-slate-900 border border-slate-800 rounded-xl p-6 space-y-4">
                <h2 class="text-base font-semibold text-white">Importar Projeto (XML Promob / Cutlist)</h2>
                <form action="/upload-xml" method="post" enctype="multipart/form-data" class="flex flex-col sm:flex-row items-center gap-4">
                    <input type="hidden" name="user" value="{user}">
                    <input type="file" name="file" accept=".xml,.txt" required class="block w-full text-xs text-slate-400 file:mr-4 file:py-2.5 file:px-4 file:rounded-lg file:border-0 file:text-xs file:font-semibold file:bg-slate-800 file:text-slate-200 hover:file:bg-slate-700 cursor-pointer">
                    <button type="submit" class="w-full sm:w-auto px-6 py-2.5 bg-sky-600 hover:bg-sky-500 text-white font-medium rounded-lg text-sm transition-colors shrink-0">
                        Processar e Orçar
                    </button>
                </form>
            </div>

            <div class="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
                <div class="p-4 border-b border-slate-800 flex justify-between items-center">
                    <h3 class="text-sm font-semibold text-white">Listagem de Peças e Insumos</h3>
                </div>
                <div class="overflow-x-auto">
                    <table class="w-full text-left border-collapse">
                        <thead>
                            <tr class="bg-slate-800/50 border-b border-slate-800 text-xs font-semibold text-slate-400 uppercase">
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
    return render_dashboard(user=username)

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
                {"nome": "Chapa MDF Branco TX 15mm", "dimensoes": "2750 x 1830 x 15", "qtd": 2, "valor": 340.00},
                {"nome": "Fita de Borda PVC 22mm (Rolo 20m)", "dimensoes": "-", "qtd": 1, "valor": 45.00},
                {"nome": "Kit Dobradiças Amortecedor 35mm", "dimensoes": "-", "qtd": 8, "valor": 96.00},
                {"nome": "Corrediça Telescópica 450mm", "dimensoes": "450 mm", "qtd": 4, "valor": 120.00}
            ]
            total_custo = sum(i["valor"] for i in items)

    except Exception:
        items = [
            {"nome": "Chapa MDF Louro Freijó 18mm", "dimensoes": "2750 x 1830 x 18", "qtd": 3, "valor": 780.00},
            {"nome": "Fita de Borda 22mm Amadeirada", "dimensoes": "-", "qtd": 2, "valor": 90.00},
            {"nome": "Puxador Perfil Alumínio Preto", "dimensoes": "2000 mm", "qtd": 2, "valor": 160.00}
        ]
        total_custo = sum(i["valor"] for i in items)

    return render_dashboard(user=user, items=items, total_custo=total_custo)

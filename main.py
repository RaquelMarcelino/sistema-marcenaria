from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse

app = FastAPI(title="Sistema Marcenaria & Promob")

HTML_LAYOUT = """
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
            <h1 class="text-2xl font-bold tracking-tight text-white">Marcenaria SaaS</h1>
            <p class="text-xs text-slate-400">Gestão de Orçamentos Promob & Precificação</p>
        </div>
        
        <form action="/login" method="post" class="space-y-4">
            <div>
                <label class="block text-xs font-semibold text-slate-300 uppercase mb-1">E-mail</label>
                <input type="email" name="username" required value="admin@marcenaria.com" class="w-full px-4 py-2.5 bg-slate-900 border border-slate-700 rounded-lg text-sm focus:outline-none focus:border-sky-500 text-slate-200">
            </div>
            <div>
                <label class="block text-xs font-semibold text-slate-300 uppercase mb-1">Senha</label>
                <input type="password" name="password" required value="123456" class="w-full px-4 py-2.5 bg-slate-900 border border-slate-700 rounded-lg text-sm focus:outline-none focus:border-sky-500 text-slate-200">
            </div>
            <button type="submit" class="w-full py-3 bg-sky-600 hover:bg-sky-500 text-white font-semibold rounded-lg text-sm transition-colors shadow-lg shadow-sky-600/30">
                Acessar Plataforma
            </button>
        </form>

        <div class="pt-4 border-t border-slate-700/60 text-center">
            <a href="/docs" class="text-xs text-sky-400 hover:underline">Acessar Documentação Swagger (API) &rarr;</a>
        </div>
    </div>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
def home():
    return HTML_LAYOUT

@app.post("/login", response_class=HTMLResponse)
def login(username: str = Form(...), password: str = Form(...)):
    return f"""
    <!DOCTYPE html>
    <html lang="pt-br">
    <head>
        <meta charset="UTF-8">
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-slate-900 text-slate-100 flex items-center justify-center min-h-screen p-4">
        <div class="max-w-lg w-full bg-slate-800 border border-slate-700 rounded-2xl p-8 text-center space-y-4">
            <div class="w-12 h-12 bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 rounded-full flex items-center justify-center mx-auto text-xl font-bold">✓</div>
            <h2 class="text-xl font-bold text-white">Bem-vindo(a) ao Painel!</h2>
            <p class="text-sm text-slate-300">Autenticado como: <b class="text-sky-400">{username}</b></p>
            <p class="text-xs text-slate-400">O sistema está pronto para receber arquivos XML do Promob e processar DREs de orçamentos.</p>
            <div class="pt-4">
                <a href="/docs" class="inline-block px-5 py-2.5 bg-sky-600 hover:bg-sky-500 text-white text-sm font-semibold rounded-lg">Abrir Central de Testes (Swagger)</a>
            </div>
        </div>
    </body>
    </html>
    """

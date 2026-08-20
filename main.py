@app.post("/excluir-lead", response_class=HTMLResponse)
def excluir_lead_route(orcamento_id: int = Form(...)):
    # Trava de segurança: apenas usuário ADM pode excluir
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

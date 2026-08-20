taxa_juros_empresa = float(empresa.get("taxa_juros_mensal", 1.99))
    saldo_para_financiar = max(c_p_venda - c_entrada, 0.0)

    # Cálculo da parcela com acréscimo de juros via Tabela Price caso use financiamento
    if "Financiamento" in c_mod or "MVI Crédito" in c_mod:
        valor_por_parcela = calcular_parcela_price(saldo_para_financiar, taxa_juros_empresa, c_parc)
    else:
        valor_por_parcela = (saldo_para_financiar / c_parc) if c_parc > 0 else 0.0

    total_com_juros_cronograma = c_entrada + (valor_por_parcela * c_parc)

    linhas_parcelas = ""
    hoje = date.today()

    # Linha da Entrada (se houver entrada)
    if c_entrada > 0:
        linhas_parcelas += f"""
        <tr class="border-b border-slate-800 text-xs bg-emerald-950/20 hover:bg-slate-800/40">
            <td class="py-2.5 px-3 text-center text-emerald-400 font-bold font-mono">Entrada</td>
            <td class="py-2.5 px-3 text-slate-300">{hoje.strftime("%d/%m/%Y")}</td>
            <td class="py-2.5 px-3 font-bold text-emerald-400 text-right">R$ {fmt_br(c_entrada)}</td>
            <td class="py-2.5 px-3 text-slate-300">PIX / À Vista (Ato)</td>
            <td class="py-2.5 px-3 text-emerald-400 font-semibold">✓ Confirmado / Entrada</td>
        </tr>
        """

    # Linhas das Parcelas com Juros
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
        <td colspan="2" class="py-3 px-3 text-amber-400 uppercase">Total Geral (Entrada + Parcelas c/ Juros):</td>
        <td class="py-3 px-3 font-black text-amber-400 text-right text-sm">R$ {fmt_br(total_com_juros_cronograma)}</td>
        <td colspan="2" class="py-3 px-3 text-slate-400 text-[11px]">Plano {c_parc}x com juros de {taxa_juros_empresa}% a.m.</td>
    </tr>
    """

def render_pre_orcamento_agendamento(
    empresa, orcamento_id, nome, whatsapp, cidade, area_m2, preco_venda,
    esp_caixa, cor_caixa, esp_porta, cor_porta, acab_porta, marca_ferr, esp_tamp, ambientes_str
):
    pv_redondo = int(round(preco_venda))
    desconto_vista_5 = int(round(pv_redondo * 0.95))
    
    # Formatação com ponto para milhar no padrão brasileiro
    pv_fmt = f"{pv_redondo:,}".replace(",", ".")
    desconto_fmt = f"{desconto_vista_5:,}".replace(",", ".")
    
    tel_limpo = (empresa.get("telefone") or "").replace("-","").replace(" ","").replace("(","").replace(")","")

    return f"""<!DOCTYPE html>
<html lang="pt-br">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{empresa['nome_empresa']} - Pré-Orçamento</title>
    <script src="https://cdn.tailwindcss.com"></script>
    
    <script>
    !function(f,b,e,v,n,t,s)
    {{if(f.fbq)return;n=f.fbq=function(){{n.callMethod?
    n.callMethod.apply(n,arguments):n.queue.push(arguments)}};
    if(!f._fbq)f._fbq=n;n.push=n;n.loaded=!0;n.version='2.0';
    n.queue=[];t=b.createElement(e);t.async=!0;
    t.src=v;s=b.getElementsByTagName(e)[0];
    s.parentNode.insertBefore(t,s)}}(window, document,'script',
    'https://connect.facebook.net/en_US/fbevents.js');
    fbq('init', '{META_PIXEL_ID}');
    fbq('track', 'PageView');
    fbq('track', 'Lead', {{
        content_name: '{ambientes_str}',
        value: {pv_redondo},
        currency: 'BRL'
    }});
    </script>
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

        <div class="bg-slate-950/80 p-5 rounded-2xl border border-slate-800 space-y-4">
            <div class="text-center">
                <h3 class="text-sm font-bold text-white uppercase tracking-wide">Deseja dar continuidade ao seu projeto?</h3>
                <p class="text-xs text-slate-400 mt-1">Selecione uma opção abaixo:</p>
            </div>

            <div class="space-y-3">
                <a href="https://wa.me/55{tel_limpo}?text=Ol%C3%A1!%20Simulei%20meu%20projeto%20no%20site%20da%20{empresa['nome_empresa']}%20(Projeto%20%23{orcamento_id:04d})%20e%20quero%20dar%20continuidade%20ao%20atendimento!" target="_blank" class="w-full py-4 bg-emerald-500 hover:bg-emerald-600 text-slate-950 font-black rounded-2xl flex items-center justify-center space-x-2 shadow-lg shadow-emerald-500/20 transition-all text-sm uppercase tracking-wider text-center block">
                    ✅ Sim, quero dar continuidade no WhatsApp
                </a>

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

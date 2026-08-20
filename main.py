<!-- ABA 4: PROMOB COM CAMPO DE VALOR DE VENDA -->
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
            <span class="text-[10px] text-slate-500 block mt-0.5">Deixe preenchido com o valor negociado ou o sistema usará o total do arquivo.</span>
        </div>
        <div class="p-4 bg-slate-950 border border-slate-800 rounded-2xl">
            <label class="block font-bold text-slate-300 mb-1">Arquivo Promob (.xml, .csv, .txt, .cut):</label>
            <input type="file" name="arquivo_promob" accept=".xml,.csv,.txt,.cut" required class="w-full text-slate-400 file:bg-amber-500 file:border-0 file:rounded-xl file:px-3 file:py-1 file:font-bold">
        </div>
        <button type="submit" class="w-full py-3.5 bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold rounded-xl shadow-lg">⚡ Processar Peças do Promob</button>
    </form>
</div>

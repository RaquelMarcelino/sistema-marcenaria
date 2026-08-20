# Trava de segurança: apenas o perfil 'adm' visualiza o botão de exclusão direta
pode_excluir_pasta = (perfil == "adm")

botao_excluir_ativo_html = f"""
<form action="/excluir-lead" method="post" onsubmit="return confirm('ATENÇÃO ADM: Deseja excluir permanentemente a Pasta P{c_id:05d} - {c_nome}? Esta ação não pode ser desfeita.')" class="pt-2">
    <input type="hidden" name="orcamento_id" value="{c_id}">
    <button type="submit" class="w-full py-2 bg-rose-950/70 hover:bg-rose-900 text-rose-300 border border-rose-800 rounded-xl text-xs font-bold transition flex items-center justify-center gap-1.5 shadow">
        🔒 🗑️ Excluir Pasta (Exclusivo ADM)
    </button>
</form>
""" if (pode_excluir_pasta and c_id > 0) else """
<div class="pt-2 text-center text-[10px] text-slate-500 flex items-center justify-center gap-1">
    🔒 Exclusão restrita ao Administrador
</div>
"""

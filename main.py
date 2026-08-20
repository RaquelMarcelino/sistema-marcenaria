def calcular_engenharia(
    ambientes: list,
    area_m2: float,
    esp_caixa: str,
    cor_caixa: str,
    esp_porta: str,
    cor_porta: str,
    acabamento_porta: str,
    esp_tamp: str,
    marca_ferr: str
):
    empresa = get_empresa_dados(CURRENT_SESSION.get("empresa_id", 1))
    
    # Valores de referência base por tipo de ambiente sob medida
    tabela_base_ambiente = {
        "Cozinha": 16500.0,
        "Lavanderia": 6800.0,
        "Sala": 9800.0,
        "Sacada": 7500.0,
        "Área Gourmet": 14500.0,
        "Dorm. Solteiro": 11500.0,
        "Dorm. Casal/Suíte": 19500.0,
        "Banheiro": 4800.0,
        "Projeto Completo Sob Medida": 18000.0
    }

    # Multiplicadores de acabamento e materiais
    fator_caixa = 1.15 if "18mm" in esp_caixa else 1.0
    if "Amadeirado" in cor_caixa: fator_caixa *= 1.10

    fator_porta = 1.12 if "18mm" in esp_porta else 1.0
    if "Amadeirado" in cor_porta: fator_porta *= 1.12

    if "Lacca" in acabamento_porta:
        fator_porta *= 1.55
    elif "Vidro" in acabamento_porta or "Reflecta" in acabamento_porta:
        fator_porta *= 1.48
    elif "Provençal" in acabamento_porta:
        fator_porta *= 1.35
    elif "Americana" in acabamento_porta:
        fator_porta *= 1.28
    elif "Passantes" in acabamento_porta:
        fator_porta *= 1.22

    fator_ferragem = 1.25 if "Blum" in marca_ferr else (1.18 if "Hettich" in marca_ferr else (1.12 if "Häfele" in marca_ferr else 1.0))
    fator_tamponamento = 1.20 if "36mm" in esp_tamp else (1.12 if "25mm" in esp_tamp else 1.0)

    fator_geral_materiais = fator_caixa * fator_porta * fator_ferragem * fator_tamponamento
    fator_area = max(area_m2 / 70.0, 0.85)

    items, desc_promob_auto = [], []
    soma_venda_ambientes = 0.0

    for amb in ambientes:
        # Extrai quantidade caso venha como "2x Banheiro" ou "1x Dorm. Solteiro"
        qtd = 1
        nome_limpo = amb
        if "x " in amb:
            partes = amb.split("x ")
            try:
                qtd = int(partes[0].strip())
                nome_limpo = partes[1].strip()
            except Exception:
                qtd = 1
                nome_limpo = amb

        valor_unit_base = 12000.0
        for chave, val in tabela_base_ambiente.items():
            if chave.lower() in nome_limpo.lower():
                valor_unit_base = val
                break

        valor_ambiente = valor_unit_base * fator_geral_materiais * (fator_area ** 0.6) * qtd
        soma_venda_ambientes += valor_ambiente
        
        items.append({
            "nome": f"{amb} (Estrutura {esp_caixa}, Portas {acabamento_porta}, Ferragens {marca_ferr})",
            "valor": round(valor_ambiente * 0.40)
        })
        desc_promob_auto.append(f"{amb}: Caixaria {esp_caixa} ({cor_caixa}), portas {acabamento_porta} ({cor_porta}), ferragens {marca_ferr}.")

    preco_venda = round(soma_venda_ambientes)
    total_materiais = round(preco_venda * 0.38)
    custo_mo = round(preco_venda * 0.18)
    custo_frete = round(preco_venda * 0.06)
    preco_bruto = preco_venda
    
    comissao_venda = round(preco_venda * (float(empresa.get("comissao_padrao_pct", 4.0)) / 100.0))
    lucro = round(preco_venda - (total_materiais + custo_mo + custo_frete + (preco_venda * 0.10)))

    return {
        "items": items,
        "total_mat": total_materiais,
        "custo_mo": custo_mo,
        "custo_frete": custo_frete,
        "preco_bruto": preco_bruto,
        "preco_venda": preco_venda,
        "lucro": lucro,
        "comissao": comissao_venda,
        "desc_promob": "\n".join(desc_promob_auto)
    }

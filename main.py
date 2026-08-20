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
    
    # 1. Base líquida de custo (calibrada para padrão apartamento de 45m² a 60m²)
    # Cozinha + Lavanderia juntas fecham a base líquida de ~R$ 3.800 (R$ 12.000 final)
    tabela_base_liquida = {
        "Cozinha": 2900.0,
        "Lavanderia": 950.0,
        "Sala": 1800.0,
        "Sacada": 1200.0,
        "Área Gourmet": 2400.0,
        "Dorm. Solteiro": 1900.0,
        "Dorm. Casal/Suíte": 2900.0,
        "Banheiro": 750.0,
        "Projeto Completo Sob Medida": 3200.0
    }

    # Custo médio de ferragens por ambiente
    tabela_ferragens = {
        "Blum": 1400.0,
        "Hettich": 1150.0,
        "Häfele": 950.0,
        "FGVTN": 650.0
    }
    
    ferragem_unit = 750.0
    for k, v in tabela_ferragens.items():
        if k.lower() in marca_ferr.lower():
            ferragem_unit = v
            break

    # Fatores adicionais de acabamento nas portas e caixas
    fator_acab = 1.0
    if "18mm" in esp_caixa: fator_acab *= 1.05
    if "Amadeirado" in cor_caixa: fator_acab *= 1.05
    if "18mm" in esp_porta: fator_acab *= 1.05
    if "Amadeirado" in cor_porta: fator_acab *= 1.05

    if "Lacca" in acabamento_porta:
        fator_acab *= 1.35
    elif "Vidro" in acabamento_porta or "Reflecta" in acabamento_porta:
        fator_acab *= 1.30
    elif "Provençal" in acabamento_porta:
        fator_acab *= 1.20
    elif "Americana" in acabamento_porta:
        fator_acab *= 1.15

    if "36mm" in esp_tamp:
        fator_acab *= 1.15
    elif "25mm" in esp_tamp:
        fator_acab *= 1.08

    # Proporção de escala por metragem informada pelo cliente (base neutra 45m²)
    fator_area = max((area_m2 / 45.0) ** 0.45, 0.80)

    soma_base_liquida = 0.0
    total_ferragens = 0.0
    items, desc_promob_auto = [], []

    for amb in ambientes:
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

        base_amb = 2000.0
        for chave, val in tabela_base_liquida.items():
            if chave.lower() in nome_limpo.lower():
                base_amb = val
                break

        custo_liquido_ambiente = base_amb * fator_acab * fator_area * qtd
        soma_base_liquida += custo_liquido_ambiente
        total_ferragens += (ferragem_unit * qtd)

        items.append({
            "nome": f"{amb} (Estrutura {esp_caixa}, Portas {acabamento_porta})",
            "valor": round(custo_liquido_ambiente)
        })
        desc_promob_auto.append(f"{amb}: Caixaria {esp_caixa} ({cor_caixa}), portas {acabamento_porta} ({cor_porta}), ferragens {marca_ferr}.")

    # 2. Montagem (+ 15% do valor líquido sem os adicionais)
    custo_montagem = soma_base_liquida * 0.15

    # 3. Frete fixo
    custo_frete = 180.0

    # 4. Markup de +150% (multiplicador 2.50) sobre a base e montagem + ferragens médias + frete
    preco_venda = round(((soma_base_liquida + custo_montagem) * 2.50) + total_ferragens + custo_frete)
    preco_bruto = preco_venda

    total_materiais = round(soma_base_liquida + total_ferragens)
    custo_mo = round(custo_montagem)
    
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

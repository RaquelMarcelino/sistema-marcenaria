// Exemplo de payload enviado para a API de IA no backend
const projectAuditPrompt = {
  model: "gpt-4o-mini", // ou claude-3-5-sonnet / gemini-1.5-pro
  messages: [
    {
      role: "system",
      content: "Você é um auditor sênior de marcenaria sob medida e engenharia Promob. Analise a lista de peças, identifique inconsistências de ferragens, topos sem fita de borda e calcule se o markup cobre os custos operacionais."
    },
    {
      role: "user",
      content: JSON.stringify(promobPartsList)
    }
  ]
};

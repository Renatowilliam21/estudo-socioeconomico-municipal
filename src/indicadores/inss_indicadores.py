"""Indicadores de beneficios do INSS por municipio (Emitidos por Municipios, 2025).

Uso (na raiz do projeto, com o .venv ativo):
    python -m src.indicadores.inss_indicadores

Entrada: data/processed/inss_emitidos_longo.csv  (gerado por src.tratamento.inss_emitidos)
Saida:   data/processed/inss_indicadores.csv

Atencao: os valores da fonte sao LIQUIDOS (apos descontos) e os dados seguem o municipio do orgao
pagador, nao o da residencia. A categoria 'assistenciais' inclui o BPC: nao some com o BPC do Portal.
"""
from pathlib import Path

import pandas as pd

ENTRADA = Path("data/processed/inss_emitidos_longo.csv")
SAIDA = Path("data/processed/inss_indicadores.csv")
RG = "Benefícios do Regime Geral de Previdência Social"
CAMPOS = {
    "populacao_2025": ("Qtd_dez2025", "População no Município"),
    "benef_total_dez2025": ("Qtd_dez2025", "Total"),
    "benef_previdenciarios_dez2025": ("Qtd_dez2025", f"{RG} | Total de benefícios previdenciários"),
    "benef_assistenciais_dez2025": ("Qtd_dez2025", "Benefícios assistenciais e de legislação específica"),
    "aposentadorias_dez2025": ("Qtd_dez2025", f"{RG} | Aposentadorias | Total de Aposentadorias"),
    "aposentadorias_idade_dez2025": ("Qtd_dez2025", f"{RG} | Aposentadorias | Aposentadorias por idade"),
    "pensoes_dez2025": ("Qtd_dez2025", f"{RG} | Pensões por morte"),
    "valor_total_2025": ("Valor_Total_2025", "Total"),
    "valor_previdenciario_2025": ("Valor_Total_2025", f"{RG} | Total de benefícios previdenciários"),
    "valor_assistencial_2025": ("Valor_Total_2025", "Benefícios assistenciais e de legislação específica"),
}


def main():
    df = pd.read_csv(ENTRADA, dtype={"codigo_ibge": str})
    wide = pd.DataFrame(index=sorted(df["municipio"].unique()))

    for campo, (aba, coluna) in CAMPOS.items():
        sub = df[(df["aba"] == aba) & (df["coluna"] == coluna)].set_index("municipio")["valor"]
        if sub.empty:
            achadas = sorted(df[df["aba"] == aba]["coluna"].unique())
            raise SystemExit(f"Coluna nao encontrada: [{aba}] {coluna}\nColunas dessa aba: {achadas}")
        wide[campo] = sub

    clientela = df[df["arquivo"].str.contains("clientela")]
    qtd = clientela[clientela["coluna"].str.startswith("Quantidade de Benefícios do RGPS")]
    wide["rgps_rural_dez2025"] = qtd[qtd["coluna"].str.endswith("| Rural")].set_index("municipio")["valor"]

    w = wide
    w["benef_por_1000_hab"] = (w["benef_total_dez2025"] / w["populacao_2025"] * 1000).round(1)
    w["previdenciarios_por_1000_hab"] = (w["benef_previdenciarios_dez2025"] / w["populacao_2025"] * 1000).round(1)
    w["pct_aposentadorias_por_idade"] = (w["aposentadorias_idade_dez2025"] / w["aposentadorias_dez2025"] * 100).round(1)
    w["pct_rural_previdenciarios"] = (w["rgps_rural_dez2025"] / w["benef_previdenciarios_dez2025"] * 100).round(1)
    w["valor_inss_per_capita_2025"] = (w["valor_total_2025"] / w["populacao_2025"]).round(0)
    w = w.reset_index(names="municipio")
    w.to_csv(SAIDA, index=False, encoding="utf-8")
    print(f"Salvo: {SAIDA} ({len(w)} municipios)\n")

    tab = w.set_index("municipio")[["populacao_2025", "benef_por_1000_hab", "previdenciarios_por_1000_hab",
                                    "pct_aposentadorias_por_idade", "pct_rural_previdenciarios",
                                    "valor_total_2025", "valor_inss_per_capita_2025"]]
    tab.columns = ["Populacao 2025", "Benef./1.000 hab", "Previd./1.000 hab", "% aposent. por idade",
                   "% rural (previd.)", "Valor 2025 (R$)", "R$ por habitante/ano"]
    print(tab.sort_values("R$ por habitante/ano", ascending=False).to_string(
        float_format=lambda v: f"{v:,.1f}"))


if __name__ == "__main__":
    main()

"""Painel consolidado: um indicador por municipio, lado a lado (Boa Viagem + comparacao).

Uso (na raiz do projeto, com o .venv ativo):
    python -m src.indicadores.painel_consolidado

Entradas (todas em data/processed/): pib_per_capita.csv, estrutura_economica.csv,
bolsa_familia_mensal.csv, bpc_mensal.csv, inss_indicadores.csv
Saida: data/processed/painel_consolidado.csv

Regras de leitura:
- Taxas 'por 1.000 hab.' usam a populacao estimada de 2025 (a mesma em todos os indicadores).
- Transferencias per capita = INSS 2025 (liquido, ja inclui assistenciais/BPC) + Bolsa Familia 2025 (bruto).
  O BPC do Portal NAO entra na soma, para nao contar duas vezes.
- Misturam-se valores liquidos e brutos e anos diferentes (PIB 2023, setores 2021): use como ordem de grandeza.
"""
import re
from pathlib import Path

import pandas as pd

P = Path("data/processed")
SAIDA = P / "painel_consolidado.csv"


def nome(x):
    return re.sub(r"\s*(\([A-Z]{2}\)|-\s*[A-Z]{2})\s*$", "", str(x)).strip()


def main():
    inss = pd.read_csv(P / "inss_indicadores.csv").set_index("municipio")
    pop25 = inss["populacao_2025"]

    pib = pd.read_csv(P / "pib_per_capita.csv", dtype={"localidade_id": str})
    pib["municipio"] = pib["localidade"].map(nome)
    ultimo_pib = pib["periodo"].max()
    pib = pib[pib["periodo"] == ultimo_pib].set_index("municipio")

    est = pd.read_csv(P / "estrutura_economica.csv", dtype={"localidade_id": str})
    est["municipio"] = est["localidade"].map(nome)
    com_setor = est[est["pct_administracao_publica"].notna()]
    ano_set = com_setor["periodo"].max()
    est = com_setor[com_setor["periodo"] == ano_set].set_index("municipio")

    bf = pd.read_csv(P / "bolsa_familia_mensal.csv", dtype={"competencia": str})
    bpc = pd.read_csv(P / "bpc_mensal.csv", dtype={"competencia": str})
    mes_bf, mes_bpc = bf["competencia"].max(), bpc["competencia"].max()
    bf_ult = bf[bf["competencia"] == mes_bf].set_index("municipio")
    bpc_ult = bpc[bpc["competencia"] == mes_bpc].set_index("municipio")
    bf_2025 = bf[bf["competencia"].str.startswith("2025")].groupby("municipio")["valor_total"].sum()
    bpc_2025 = bpc[bpc["competencia"].str.startswith("2025")].groupby("municipio")["valor_total"].sum()

    d = pd.DataFrame(index=inss.index)
    d["populacao_2025"] = pop25
    d[f"pib_per_capita_{ultimo_pib}_reais"] = pib["pib_per_capita_reais"]
    d[f"pct_adm_publica_{ano_set}"] = est["pct_administracao_publica"]
    d[f"pct_agropecuaria_{ano_set}"] = est["pct_agropecuaria"]
    d[f"pct_industria_{ano_set}"] = est["pct_industria"]
    d[f"pct_servicos_{ano_set}"] = est["pct_servicos_privados"]
    d[f"bolsa_familia_familias_{mes_bf}"] = bf_ult["familias"]
    d["bolsa_familia_familias_por_1000_hab"] = (bf_ult["familias"] / pop25 * 1000).round(1)
    d[f"bpc_beneficiarios_{mes_bpc}"] = bpc_ult["beneficiarios"]
    d["bpc_por_1000_hab"] = (bpc_ult["beneficiarios"] / pop25 * 1000).round(1)
    d["inss_benef_por_1000_hab"] = inss["benef_por_1000_hab"]
    d["inss_pct_rural"] = inss["pct_rural_previdenciarios"]
    d["inss_valor_2025_reais"] = inss["valor_total_2025"]
    d["bolsa_familia_valor_2025_reais"] = bf_2025.round(2)
    d["bpc_portal_valor_2025_reais"] = bpc_2025.round(2)
    d["transferencias_per_capita_2025_reais"] = ((d["inss_valor_2025_reais"] + d["bolsa_familia_valor_2025_reais"]) / pop25).round(0)
    d["transferencias_sobre_pib_per_capita"] = (d["transferencias_per_capita_2025_reais"]
                                                / d[f"pib_per_capita_{ultimo_pib}_reais"]).round(2)
    d = d.reset_index(names="municipio")
    d.to_csv(SAIDA, index=False, encoding="utf-8")
    print(f"Salvo: {SAIDA} ({len(d)} municipios)")
    print(f"Referencias: PIB {ultimo_pib}, setores {ano_set}, Bolsa Familia {mes_bf}, BPC {mes_bpc}, INSS 2025\n")

    tab = d.set_index("municipio")[[f"pib_per_capita_{ultimo_pib}_reais", f"pct_adm_publica_{ano_set}",
                                    "bolsa_familia_familias_por_1000_hab", "bpc_por_1000_hab",
                                    "inss_benef_por_1000_hab", "transferencias_per_capita_2025_reais",
                                    "transferencias_sobre_pib_per_capita"]]
    tab.columns = [f"PIB p.c. {ultimo_pib}", f"% adm.publ. {ano_set}", "PBF fam./1.000", "BPC/1.000",
                   "INSS/1.000", "Transf. p.c. 2025 (R$)", "Transf./PIB p.c."]
    print(tab.sort_values("Transf. p.c. 2025 (R$)", ascending=False).to_string(float_format=lambda v: f"{v:,.2f}"))

    print("\nCorrelacao de Spearman entre os municipios (indicativa; amostra pequena)")
    c = d[[f"pib_per_capita_{ultimo_pib}_reais", "bolsa_familia_familias_por_1000_hab", "bpc_por_1000_hab",
           "inss_benef_por_1000_hab", f"pct_adm_publica_{ano_set}"]].corr(method="spearman").round(2)
    c.columns = c.index = ["PIB p.c.", "PBF/1.000", "BPC/1.000", "INSS/1.000", "% adm.publ."]
    print(c.to_string())


if __name__ == "__main__":
    main()

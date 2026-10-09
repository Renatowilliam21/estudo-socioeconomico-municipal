"""PIB per capita dos municipios (PIB do SIDRA 5938 / populacao do Censo 2022, SIDRA 4714).

Uso (na raiz do projeto, com o .venv ativo):
    python -m src.indicadores.pib_per_capita

Entradas: data/processed/sidra_tabela_5938.csv e data/processed/sidra_tabela_4714.csv
Saida:    data/processed/pib_per_capita.csv

Observacao: usa a populacao do Censo 2022 como divisor de todos os anos. O PIB per capita
oficial do IBGE usa a estimativa de populacao de cada ano, entao os valores diferem um pouco.
"""
from pathlib import Path

import pandas as pd
import yaml

CONFIG = Path("config/municipio.yml")
PIB_CSV = Path("data/processed/sidra_tabela_5938.csv")
POP_CSV = Path("data/processed/sidra_tabela_4714.csv")
SAIDA = Path("data/processed/pib_per_capita.csv")
VAR_PIB, VAR_POP, VAR_AREA = 37, 93, 6318


def calcular(pib_df, pop_df):
    pib = pib_df[pib_df["variavel_id"].astype(int) == VAR_PIB][["localidade_id", "localidade", "periodo", "valor"]]
    pib = pib.rename(columns={"valor": "pib_mil_reais"})
    pop = pop_df[pop_df["variavel_id"].astype(int) == VAR_POP][["localidade_id", "valor"]]
    pop = pop.rename(columns={"valor": "populacao_2022"})
    area = pop_df[pop_df["variavel_id"].astype(int) == VAR_AREA][["localidade_id", "valor"]]
    area = area.rename(columns={"valor": "area_km2"})

    df = pib.merge(pop, on="localidade_id", how="left").merge(area, on="localidade_id", how="left")
    df["periodo"] = df["periodo"].astype(int)
    df["pib_per_capita_reais"] = (df["pib_mil_reais"] * 1000 / df["populacao_2022"]).round(0)
    return df.sort_values(["localidade_id", "periodo"])


def main():
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    codigo = str(cfg["municipio"]["codigo_ibge"])
    dtype = {"localidade_id": str}
    df = calcular(pd.read_csv(PIB_CSV, dtype=dtype), pd.read_csv(POP_CSV, dtype=dtype))
    df.to_csv(SAIDA, index=False, encoding="utf-8")
    print(f"Salvo: {SAIDA} ({len(df)} linhas)")

    sem_pop = df[df["populacao_2022"].isna()]["localidade"].unique()
    if len(sem_pop):
        print("ATENCAO: sem populacao para:", ", ".join(sem_pop))

    ultimo = df["periodo"].max()
    print(f"\nPIB per capita (R$), populacao do Censo 2022 como divisor")
    tab = (df[df["periodo"].isin([2021, ultimo])]
           .pivot_table(index="localidade", columns="periodo", values="pib_per_capita_reais"))
    tab["Populacao"] = df.drop_duplicates("localidade").set_index("localidade")["populacao_2022"]
    tab = tab.sort_values(ultimo, ascending=False)
    tab.insert(0, "Posicao", range(1, len(tab) + 1))
    print(tab.to_string(float_format=lambda v: f"{v:,.0f}".replace(",", ".")))

    mediana = df[df["periodo"] == ultimo]["pib_per_capita_reais"].median()
    bv = df[(df["localidade_id"] == codigo) & (df["periodo"] == ultimo)]["pib_per_capita_reais"].iloc[0]
    print(f"\nMediana do grupo em {ultimo}: R$ {mediana:,.0f}".replace(",", ".")
          + f" | Boa Viagem: R$ {bv:,.0f}".replace(",", ".") + f" ({bv / mediana:.2f}x a mediana)")

    print("\nSerie de Boa Viagem (R$ por habitante)")
    serie = df[df["localidade_id"] == codigo].set_index("periodo")["pib_per_capita_reais"]
    print(serie.to_string(float_format=lambda v: f"{v:,.0f}".replace(",", ".")))


if __name__ == "__main__":
    main()

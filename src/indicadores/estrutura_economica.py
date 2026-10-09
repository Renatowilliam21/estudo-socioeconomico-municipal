"""Estrutura economica: peso de cada setor no valor adicionado bruto (VAB).

Uso (na raiz do projeto, com o .venv ativo):
    python -m src.indicadores.estrutura_economica

Entrada: data/processed/sidra_tabela_5938.csv  (gerado por src.coleta.ibge_sidra)
Saida:   data/processed/estrutura_economica.csv
"""
from pathlib import Path

import pandas as pd
import yaml

CONFIG = Path("config/municipio.yml")
ENTRADA = Path("data/processed/sidra_tabela_5938.csv")
SAIDA = Path("data/processed/estrutura_economica.csv")

# IDs das variaveis da tabela 5938 (conferidos com --listar)
PIB, IMPOSTOS, VAB_TOTAL = 37, 543, 498
SETORES = {
    513: "agropecuaria",
    517: "industria",
    6575: "servicos_privados",     # exclui administracao, defesa, educacao e saude publicas
    525: "administracao_publica",  # inclui educacao e saude publicas e seguridade social
}


def montar(df):
    df = df.copy()
    df["variavel_id"] = df["variavel_id"].astype(int)
    ids = [PIB, IMPOSTOS, VAB_TOTAL, *SETORES]
    largo = (df[df["variavel_id"].isin(ids)]
             .pivot_table(index=["localidade_id", "localidade", "periodo"],
                          columns="variavel_id", values="valor", aggfunc="first")
             .rename(columns={PIB: "pib_mil_reais", IMPOSTOS: "impostos_mil_reais",
                              VAB_TOTAL: "vab_total_mil_reais",
                              **{k: f"vab_{v}_mil_reais" for k, v in SETORES.items()}})
             .reset_index())
    for nome in SETORES.values():
        largo[f"pct_{nome}"] = (largo[f"vab_{nome}_mil_reais"] / largo["vab_total_mil_reais"] * 100).round(1)
    soma = sum(largo[f"vab_{n}_mil_reais"] for n in SETORES.values())
    largo["dif_soma_setores_pct"] = ((largo["vab_total_mil_reais"] - soma) / largo["vab_total_mil_reais"] * 100).round(2)
    pcts = [f"pct_{n}" for n in SETORES.values()]
    tem = largo[pcts].notna().any(axis=1)
    largo["setor_principal"] = pd.NA
    largo.loc[tem, "setor_principal"] = (largo.loc[tem, pcts].idxmax(axis=1)
                                         .str.replace("pct_", "", regex=False))
    largo["periodo"] = largo["periodo"].astype(int)
    return largo.sort_values(["localidade_id", "periodo"])


def main():
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    codigo = str(cfg["municipio"]["codigo_ibge"])
    df = pd.read_csv(ENTRADA, dtype={"localidade_id": str})
    out = montar(df)
    out.to_csv(SAIDA, index=False, encoding="utf-8")
    print(f"Salvo: {SAIDA} ({len(out)} linhas)\n")

    pcts = [f"pct_{n}" for n in SETORES.values()]
    com_setor = out[out[pcts].notna().any(axis=1)]
    periodos_sem = sorted(set(out["periodo"]) - set(com_setor["periodo"]))
    if periodos_sem:
        print("ATENCAO: a fonte nao trouxe detalhe por setor para os periodos "
              f"{periodos_sem} (so PIB total). Eles ficam de fora das tabelas abaixo.\n")

    ultimo = com_setor["periodo"].max()
    print(f"Peso dos setores no valor adicionado, {ultimo} (% do VAB total)")
    tab = out[out["periodo"] == ultimo].set_index("localidade")[["pib_mil_reais", *pcts]]
    tab.columns = ["PIB (mil R$)", "Agro", "Industria", "Servicos", "Adm. publica"]
    print(tab.sort_values("Adm. publica", ascending=False).to_string())

    print("\nSerie de Boa Viagem (% do VAB total)")
    serie = com_setor[com_setor["localidade_id"] == codigo].set_index("periodo")[pcts + ["setor_principal"]]
    serie.columns = ["Agro", "Industria", "Servicos", "Adm. publica", "Maior setor"]
    print(serie.to_string())

    maior = com_setor["dif_soma_setores_pct"].abs().max()
    print(f"\nConferencia ({len(com_setor)} linhas com setores): maior diferenca entre VAB total "
          f"e soma dos 4 setores = {maior}% (esperado perto de 0)")


if __name__ == "__main__":
    main()

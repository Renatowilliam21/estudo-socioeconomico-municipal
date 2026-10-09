"""Indicadores de condicoes de vida do Censo 2022 (renda, saneamento, lixo, agua, alfabetizacao).

Uso (na raiz do projeto, com o .venv ativo):
    python -m src.indicadores.condicoes_de_vida

Entradas (data/processed/, geradas por src.coleta.ibge_sidra): sidra_tabela_N.csv com N em
10295 (renda media e mediana), 10296 (classes de renda), 6805 (esgotamento), 6892 (lixo),
6803 (agua), 9543 (alfabetizacao) e, se existir com dados, 10301 (Gini).
Saida: data/processed/condicoes_de_vida.csv

As categorias do IBGE sao hierarquicas (ex.: 'Coletado' = servico de limpeza + cacamba). Por isso
o script usa categorias EXATAS e nunca soma pai com filho. Percentuais sao calculados com o
'Total' da mesma tabela e municipio. Retrato de 2022 (nao e serie).
"""
import re
from pathlib import Path

import pandas as pd

P = Path("data/processed")
SAIDA = P / "condicoes_de_vida.csv"
BASE = {"tabela", "variavel_id", "variavel", "unidade", "localidade_id", "localidade",
        "periodo", "valor_original", "valor"}


def nome(x):
    return re.sub(r"\s*(\([A-Z]{2}\)|-\s*[A-Z]{2})\s*$", "", str(x)).strip()


def ler(tabela, obrigatoria=True):
    caminho = P / f"sidra_tabela_{tabela}.csv"
    if not caminho.exists():
        if obrigatoria:
            raise SystemExit(f"Falta {caminho}. Baixe com: python -m src.coleta.ibge_sidra --tabela {tabela} ...")
        return None
    d = pd.read_csv(caminho, dtype={"localidade_id": str})
    d["variavel_id"] = d["variavel_id"].astype(int)
    return d


def contagens(d, var_id, filtro=None):
    """Retorna DataFrame municipio x categoria com os valores da variavel (categoria = unica classificacao)."""
    x = d[d["variavel_id"] == var_id]
    if filtro:
        for col, val in filtro.items():
            x = x[x[col] == val]
    cls = [c for c in d.columns if c not in BASE and c not in (filtro or {})]
    if len(cls) != 1:
        raise SystemExit(f"Esperava 1 classificacao, achei {cls}")
    return x.pivot_table(index="localidade_id", columns=cls[0], values="valor", aggfunc="sum", dropna=False)


def pct(tab, categorias, total="Total"):
    faltam = [c for c in [*categorias, total] if c not in tab.columns]
    if faltam:
        raise SystemExit(f"Categoria(s) nao encontrada(s): {faltam}\nExistentes: {list(tab.columns)}")
    return (tab[categorias].fillna(0).sum(axis=1) / tab[total] * 100).round(1)


def main():
    renda = ler(10295)
    media = renda[renda["variavel_id"] == 13431].set_index("localidade_id")["valor"]
    mediana = renda[renda["variavel_id"] == 13534].set_index("localidade_id")["valor"]
    nomes = renda.drop_duplicates("localidade_id").set_index("localidade_id")["localidade"].map(nome)

    cl = contagens(ler(10296), 13604, {"Sexo": "Total", "Cor ou raça": "Total"})
    esg = contagens(ler(6805), 381)
    lixo = contagens(ler(6892), 381)
    agua = contagens(ler(6803), 381)
    alf = ler(9543).set_index("localidade_id")["valor"]
    gini_df = ler(10301, obrigatoria=False)
    gini = (gini_df[gini_df["valor"].notna()].set_index("localidade_id")["valor"]
            if gini_df is not None and gini_df["valor"].notna().any() else None)

    caes = ["Mais de 2 a 3 salários mínimos", "Mais de 3 a 5 salários mínimos", "Mais de 5 a 10 salários mínimos",
            "Mais de 10 a 15 salários mínimos", "Mais de 15 a 20 salários mínimos", "Mais de 20 salários mínimos"]
    inadequado = ["Fossa rudimentar ou buraco", "Vala", "Rio, lago, córrego ou mar", "Outra forma",
                  "Não tinham banheiro nem sanitário"]

    d = pd.DataFrame({"municipio": nomes})
    d["moradores_2022"] = cl["Total"]
    d["renda_media_pc_2022"] = media.round(0)
    d["renda_mediana_pc_2022"] = mediana.round(0)
    d["razao_mediana_media"] = (mediana / media).round(2)
    d["pct_ate_1_4_sm"] = pct(cl, ["Até 1/4 de salário mínimo"])
    d["pct_ate_1_2_sm"] = pct(cl, ["Até 1/4 de salário mínimo", "Mais de 1/4 a 1/2 salário mínimo"])
    d["pct_sem_rendimento"] = pct(cl, ["Sem rendimento"])
    d["pct_mais_de_2_sm"] = pct(cl, caes)
    d["gini_2022"] = gini.round(3) if gini is not None else pd.NA
    d["esgoto_rede_pct"] = pct(esg, ["Rede geral, rede pluvial ou fossa ligada à rede"])
    d["esgoto_fossa_septica_nao_ligada_pct"] = pct(esg, ["Fossa séptica ou fossa filtro não ligada à rede"])
    d["esgoto_inadequado_pct"] = pct(esg, inadequado)
    d["agua_rede_principal_pct"] = pct(agua, ["Possui ligação à rede geral e a utiliza como forma principal"])
    d["agua_sem_ligacao_pct"] = pct(agua, ["Não possui ligação com a rede geral"])
    d["lixo_coletado_pct"] = pct(lixo, ["Coletado"])
    d["lixo_queimado_pct"] = pct(lixo, ["Queimado na propriedade"])
    d["alfabetizacao_15mais_pct"] = alf.round(1)
    d = d.reset_index(names="codigo_ibge")
    d.to_csv(SAIDA, index=False, encoding="utf-8")

    print(f"Salvo: {SAIDA} ({len(d)} municipios). Censo 2022.")
    if gini is None:
        print("Aviso: sem Gini municipal (tabela 10301 ausente ou vazia); desigualdade lida por mediana/media e classes de renda.")
    cols = ["municipio", "renda_media_pc_2022", "renda_mediana_pc_2022", "pct_ate_1_2_sm", "esgoto_rede_pct",
            "esgoto_inadequado_pct", "agua_rede_principal_pct", "lixo_coletado_pct", "alfabetizacao_15mais_pct"]
    t = d.sort_values("pct_ate_1_2_sm", ascending=False)[cols].set_index("municipio")
    t.columns = ["Renda media", "Renda mediana", "% ate 1/2 SM", "Esgoto rede %", "Esgoto inadeq. %",
                 "Agua rede %", "Lixo coletado %", "Alfabet. %"]
    print("\n(ordenado do maior para o menor % de moradores com renda per capita ate 1/2 salario minimo)\n")
    print(t.to_string(float_format=lambda v: f"{v:,.1f}"))
    ordem = list(t.index).index("Boa Viagem") + 1 if "Boa Viagem" in t.index else None
    if ordem:
        print(f"\nBoa Viagem: {ordem}o em % de moradores ate 1/2 SM entre {len(t)} municipios (1o = maior proporcao).")


if __name__ == "__main__":
    main()

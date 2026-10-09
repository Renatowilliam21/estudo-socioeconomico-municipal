"""Emprego formal: Censo 2022 (tabela 10261) e Cadastro Central de Empresas (tabela 9509).

Le data/processed/sidra_tabela_10261.csv e sidra_tabela_9509.csv e grava
data/processed/emprego_formal.csv, com uma linha por municipio.

Uso: python -m src.indicadores.emprego_formal

- Censo 2022 conta MORADORES ocupados na semana de referencia (por residencia).
- Cadastro Central de Empresas conta pessoas em empresas e organizacoes com CNPJ no
  municipio (inclui setor publico; nao e o mesmo que carteira assinada).
"""
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
PROC = RAIZ / "data" / "processed"

CARTEIRA = [
    "Empregado no setor privado, exclusive trabalhador doméstico - com carteira de trabalho assinada",
    "Trabalhador doméstico (inclusive diarista) - com carteira de trabalho assinada",
    "Empregado no setor público - empregado não estatutário com carteira de trabalho assinada",
    "Empregado de empresas estatais com carteira de trabalho assinada",
]
SEM_CARTEIRA = [
    "Empregado no setor privado, exclusive trabalhador doméstico - sem carteira de trabalho assinada",
    "Trabalhador doméstico (inclusive diarista) - sem carteira de trabalho assinada",
    "Empregado do setor público - empregado não estatutário sem carteira de trabalho assinada",
    "Empregado de empresas estatais sem carteira de trabalho assinada",
]
ESTATUTARIO = ["Empregado no setor público - funcionário estatutário"]
MILITAR = ["Militar do exército, da marinha, da aeronáutica, da polícia militar ou do corpo de bombeiros militar"]
CONTA_PROPRIA = ["Conta própria (sem empregados)"]
FAMILIAR = ["Trabalhador familiar auxiliar"]
EMPREGADOR = ["Empregador (com pelo menos um empregado)"]
TOTAL = "Total"

COL_POS = "Posição na ocupação e categoria do emprego no trabalho principal"


def nome(s):
    return s.str.replace(r"\s*(\([A-Z]{2}\)|-\s*[A-Z]{2})\s*$", "", regex=True).str.strip()


def censo():
    df = pd.read_csv(PROC / "sidra_tabela_10261.csv", dtype={"localidade_id": str})
    df = df[(df["variavel_id"] == 4090) & (df["Sexo"] == "Total") & (df["Cor ou raça"] == "Total")]
    df = df[df["periodo"] == df["periodo"].max()].copy()
    df["municipio"] = nome(df["localidade"])
    df[COL_POS] = df[COL_POS].map(lambda x: " ".join(str(x).split()))
    p = df.pivot_table(index="municipio", columns=COL_POS, values="valor", aggfunc="first", dropna=False)
    usadas = CARTEIRA + SEM_CARTEIRA + ESTATUTARIO + MILITAR + CONTA_PROPRIA + FAMILIAR + EMPREGADOR + [TOTAL]
    faltando = [c for c in usadas if c not in p.columns]
    if faltando:
        print("AVISO: categorias ausentes (tratadas como zero):")
        for c in faltando:
            print("  ", repr(c))
        print("  colunas com 'estatais':", [repr(c) for c in p.columns if "estatais" in c])
        for c in faltando:
            p[c] = 0.0
    vazios = int(p[usadas].isna().sum().sum())
    if vazios:
        print(f"AVISO: {vazios} celulas sem valor (suprimidas pelo IBGE) tratadas como zero.")
    p = p.fillna(0)
    soma = lambda cols: p[cols].sum(axis=1)
    out = pd.DataFrame(index=p.index)
    out["ocupados_2022"] = p[TOTAL]
    out["com_carteira"] = soma(CARTEIRA)
    out["estatutarios_militares"] = soma(ESTATUTARIO + MILITAR)
    out["sem_carteira"] = soma(SEM_CARTEIRA)
    out["conta_propria"] = soma(CONTA_PROPRIA)
    out["familiar_auxiliar"] = soma(FAMILIAR)
    out["empregadores"] = soma(EMPREGADOR)
    fecha = (out[["com_carteira", "estatutarios_militares", "sem_carteira", "conta_propria",
                  "familiar_auxiliar", "empregadores"]].sum(axis=1) - out["ocupados_2022"]).abs()
    if (fecha > 0).any():
        print("AVISO: categorias nao fecham com o total em:", list(fecha[fecha > 0].index))
    out["pct_com_carteira"] = out["com_carteira"] / out["ocupados_2022"] * 100
    out["pct_formal_carteira_estatutario"] = (out["com_carteira"] + out["estatutarios_militares"]) / out["ocupados_2022"] * 100
    out["pct_sem_carteira"] = out["sem_carteira"] / out["ocupados_2022"] * 100
    out["pct_conta_propria_familiar"] = (out["conta_propria"] + out["familiar_auxiliar"]) / out["ocupados_2022"] * 100
    return out


def cempre():
    df = pd.read_csv(PROC / "sidra_tabela_9509.csv", dtype={"localidade_id": str})
    df["municipio"] = nome(df["localidade"])
    ass = df[df["variavel_id"] == 708].pivot_table(index="municipio", columns="periodo", values="valor")
    sal = df[df["variavel_id"] == 10143].pivot_table(index="municipio", columns="periodo", values="valor")
    ult, pri = ass.columns.max(), ass.columns.min()
    out = pd.DataFrame(index=ass.index)
    out[f"assalariados_cempre_{pri}"] = ass[pri]
    out[f"assalariados_cempre_{ult}"] = ass[ult]
    out["var_assalariados_pct"] = (ass[ult] / ass[pri] - 1) * 100
    out[f"salario_medio_{ult}_reais"] = sal[ult]
    return out


def main():
    t = censo().join(cempre())
    t["assalariados_cempre_por_100_ocupados"] = t["assalariados_cempre_2022"] / t["ocupados_2022"] * 100
    t = t.sort_values("pct_com_carteira", ascending=False)
    t.round(2).to_csv(PROC / "emprego_formal.csv", index_label="municipio")
    print(f"Salvo: data/processed/emprego_formal.csv ({len(t)} municipios)\n")
    cols = ["ocupados_2022", "com_carteira", "pct_com_carteira", "pct_formal_carteira_estatutario",
            "pct_sem_carteira", "pct_conta_propria_familiar"]
    print("CENSO 2022 (ordenado por % com carteira)")
    r = t[cols].round(1)
    r.insert(0, "posicao", range(1, len(r) + 1))
    print(r.to_string())
    print("\nCADASTRO CENTRAL DE EMPRESAS")
    cc = [c for c in t.columns if c.startswith(("assalariados_cempre", "var_assal", "salario_medio"))]
    print(t[cc].round(1).to_string())
    if "Boa Viagem" in t.index:
        b = t.loc["Boa Viagem"]
        pos = list(t.index).index("Boa Viagem") + 1
        print(f"\nBoa Viagem: {int(b['com_carteira'])} ocupados com carteira ({b['pct_com_carteira']:.1f}%), "
              f"{pos}o de {len(t)} em % com carteira.")


if __name__ == "__main__":
    main()

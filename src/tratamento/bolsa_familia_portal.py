"""Agrega o Novo Bolsa Familia (Portal da Transparencia) por municipio e mes.

Uso (na raiz do projeto, com o .venv ativo):
    python -m src.tratamento.bolsa_familia_portal

Entrada: todos os .zip em data/raw/portal_transparencia/bolsa_familia/
Saida:   data/processed/bolsa_familia_mensal.csv  (apenas numeros agregados, sem dados pessoais)

Privacidade: o script le somente as colunas necessarias e NAO carrega CPF nem nome de pessoas.
O NIS e usado apenas para contar familias distintas e nao e gravado em nenhuma saida.

Leitura dos numeros: cada linha do arquivo e um pagamento a uma familia (o 'favorecido' e o
responsavel familiar). Portanto 'familias' e familias beneficiarias, nao pessoas.
"""
import re
import unicodedata
import zipfile
from pathlib import Path

import pandas as pd

ENTRADA = Path("data/raw/portal_transparencia/bolsa_familia")
POP_CSV = Path("data/processed/sidra_tabela_4714.csv")
SAIDA = Path("data/processed/bolsa_familia_mensal.csv")
UF = "CE"
COLUNAS = ["MÊS COMPETÊNCIA", "UF", "NOME MUNICÍPIO", "NIS FAVORECIDO", "VALOR PARCELA"]
VAR_POP = 93


def sem_acento(texto):
    base = unicodedata.normalize("NFD", str(texto))
    return "".join(c for c in base if unicodedata.category(c) != "Mn").upper().strip()


def parse_valor(serie):
    s = serie.astype(str).str.strip()
    if s.str.contains(",").any():  # formato brasileiro: 1.234,56
        s = s.str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
    return pd.to_numeric(s, errors="coerce")


def municipios_alvo():
    """Nomes dos municipios (Boa Viagem + comparacao) a partir da tabela de populacao ja coletada."""
    pop = pd.read_csv(POP_CSV, dtype={"localidade_id": str})
    pop = pop[pop["variavel_id"].astype(int) == VAR_POP]
    nomes = {}
    for _, r in pop.iterrows():
        nome = re.sub(r"\s*\(" + UF + r"\)\s*$", "", r["localidade"])
        nomes[sem_acento(nome)] = (r["localidade_id"], nome, r["valor"])
    return nomes


def agregar_zip(caminho, alvo):
    partes = []
    with zipfile.ZipFile(caminho) as zf:
        for membro in [n for n in zf.namelist() if n.lower().endswith(".csv")]:
            with zf.open(membro) as f:
                for chunk in pd.read_csv(f, sep=";", quotechar='"', encoding="latin1", dtype=str,
                                         usecols=COLUNAS, chunksize=500_000):
                    chunk = chunk[chunk["UF"].str.strip().str.upper() == UF]
                    chunk = chunk.assign(chave=chunk["NOME MUNICÍPIO"].map(sem_acento))
                    chunk = chunk[chunk["chave"].isin(alvo)]
                    if chunk.empty:
                        continue
                    partes.append(pd.DataFrame({
                        "competencia": chunk["MÊS COMPETÊNCIA"].str.strip(),
                        "chave": chunk["chave"],
                        "nis": chunk["NIS FAVORECIDO"],
                        "valor": parse_valor(chunk["VALOR PARCELA"]),
                    }))
    if not partes:
        return pd.DataFrame()
    df = pd.concat(partes, ignore_index=True)
    return (df.groupby(["competencia", "chave"])
              .agg(familias=("nis", "nunique"), parcelas=("nis", "size"), valor_total=("valor", "sum"))
              .reset_index())


def main():
    alvo = municipios_alvo()
    zips = sorted(ENTRADA.glob("*.zip"))
    if not zips:
        raise SystemExit(f"Nenhum .zip em {ENTRADA}. Coloque os arquivos do Portal da Transparencia ali.")
    print(f"{len(zips)} arquivo(s) encontrados. Processando...")

    resultados = []
    for z in zips:
        r = agregar_zip(z, alvo)
        print(f"  {z.name}: {len(r)} linhas agregadas")
        resultados.append(r)
    df = pd.concat([r for r in resultados if not r.empty], ignore_index=True)
    n_antes = len(df)
    df = df.drop_duplicates(["competencia", "chave"], keep="last")  # mesmo mes em 2 zips: nao somar duas vezes
    if len(df) < n_antes:
        print(f"ATENCAO: {n_antes - len(df)} linha(s) repetida(s) (mesmo mes em mais de um zip) foram descartadas.")

    df["codigo_ibge"] = df["chave"].map(lambda k: alvo[k][0])
    df["municipio"] = df["chave"].map(lambda k: alvo[k][1])
    df["populacao_2022"] = df["chave"].map(lambda k: alvo[k][2])
    df["valor_total"] = df["valor_total"].round(2)
    df["valor_medio_por_familia"] = (df["valor_total"] / df["familias"]).round(2)
    df["familias_por_1000_hab"] = (df["familias"] / df["populacao_2022"] * 1000).round(1)
    df = df[["competencia", "codigo_ibge", "municipio", "familias", "parcelas", "valor_total",
             "valor_medio_por_familia", "populacao_2022", "familias_por_1000_hab"]]
    df = df.sort_values(["competencia", "municipio"])
    df.to_csv(SAIDA, index=False, encoding="utf-8")
    print(f"\nSalvo: {SAIDA} ({len(df)} linhas)")

    sem_dados = sorted(set(v[1] for v in alvo.values()) - set(df["municipio"]))
    if sem_dados:
        print("ATENCAO: nenhuma linha encontrada para:", ", ".join(sem_dados),
              "(provavel diferenca de grafia do nome no Portal)")

    ultimo = df["competencia"].max()
    print(f"\nCompetencia {ultimo}")
    tab = (df[df["competencia"] == ultimo]
           .set_index("municipio")[["familias", "valor_total", "valor_medio_por_familia", "familias_por_1000_hab"]]
           .sort_values("familias_por_1000_hab", ascending=False))
    tab.columns = ["Familias", "Valor total (R$)", "Valor medio/familia (R$)", "Familias por 1.000 hab"]
    print(tab.to_string(float_format=lambda v: f"{v:,.1f}"))

    print("\nSerie de Boa Viagem")
    bv = df[df["municipio"] == "Boa Viagem"].set_index("competencia")
    print(bv[["familias", "valor_total", "valor_medio_por_familia", "familias_por_1000_hab"]]
          .to_string(float_format=lambda v: f"{v:,.1f}"))

    print("\nConferencia: parcelas por familia (perto de 1,0 e esperado; muito acima indica pagamentos retroativos)")
    print((df["parcelas"] / df["familias"]).describe().round(2).to_string())


if __name__ == "__main__":
    main()

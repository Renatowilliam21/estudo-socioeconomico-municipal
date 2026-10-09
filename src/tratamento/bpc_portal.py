"""Agrega o BPC (Portal da Transparencia) por municipio e mes.

Uso (na raiz do projeto, com o .venv ativo):
    python -m src.tratamento.bpc_portal

Entrada: todos os .zip em data/raw/portal_transparencia/bpc/
Saida:   data/processed/bpc_mensal.csv  (apenas numeros agregados, sem dados pessoais)

Privacidade: o BPC e pago a idosos e a pessoas com deficiencia, entao so a agregacao e publicavel.
O script le somente as colunas necessarias e NAO carrega CPF nem nomes (do beneficiario ou do
representante legal). O NIS e o numero do beneficio servem apenas para contar pessoas distintas
e nao sao gravados em nenhuma saida.

Leitura dos numeros: cada linha do arquivo e um pagamento a um beneficiario. 'beneficiarios' conta
pessoas distintas (NIS; se faltar, usa o numero do beneficio).
"""
import zipfile
from pathlib import Path

import pandas as pd

from src.tratamento.bolsa_familia_portal import UF, municipios_alvo, parse_valor, sem_acento

ENTRADA = Path("data/raw/portal_transparencia/bpc")
SAIDA = Path("data/processed/bpc_mensal.csv")
COLUNAS = ["MÊS COMPETÊNCIA", "UF", "NOME MUNICÍPIO", "NIS BENEFICIÁRIO", "NÚMERO BENEFÍCIO", "VALOR PARCELA"]


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
                    nis = chunk["NIS BENEFICIÁRIO"].str.strip().replace("", pd.NA)
                    num = chunk["NÚMERO BENEFÍCIO"].str.strip().replace("", pd.NA)
                    partes.append(pd.DataFrame({
                        "competencia": chunk["MÊS COMPETÊNCIA"].str.strip(),
                        "chave": chunk["chave"],
                        "pessoa": nis.fillna(num),
                        "beneficio": num,
                        "valor": parse_valor(chunk["VALOR PARCELA"]),
                    }))
    if not partes:
        return pd.DataFrame()
    df = pd.concat(partes, ignore_index=True)
    return (df.groupby(["competencia", "chave"])
              .agg(beneficiarios=("pessoa", "nunique"), beneficios=("beneficio", "nunique"),
                   parcelas=("pessoa", "size"), valor_total=("valor", "sum"))
              .reset_index())


def main():
    alvo = municipios_alvo()
    zips = sorted(ENTRADA.glob("*.zip"))
    if not zips:
        raise SystemExit(f"Nenhum .zip em {ENTRADA}. Coloque os arquivos do BPC ali.")
    print(f"{len(zips)} arquivo(s) encontrados. Processando...")

    resultados = []
    for z in zips:
        print(f"  lendo {z.name} ...", flush=True)
        r = agregar_zip(z, alvo)
        print(f"    {len(r)} linhas agregadas")
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
    df["valor_medio_por_beneficiario"] = (df["valor_total"] / df["beneficiarios"]).round(2)
    df["beneficiarios_por_1000_hab"] = (df["beneficiarios"] / df["populacao_2022"] * 1000).round(1)
    df = df[["competencia", "codigo_ibge", "municipio", "beneficiarios", "beneficios", "parcelas", "valor_total",
             "valor_medio_por_beneficiario", "populacao_2022", "beneficiarios_por_1000_hab"]]
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
           .set_index("municipio")[["beneficiarios", "valor_total", "valor_medio_por_beneficiario",
                                    "beneficiarios_por_1000_hab"]]
           .sort_values("beneficiarios_por_1000_hab", ascending=False))
    tab.columns = ["Beneficiarios", "Valor total (R$)", "Valor medio/pessoa (R$)", "Beneficiarios por 1.000 hab"]
    print(tab.to_string(float_format=lambda v: f"{v:,.1f}"))

    print("\nSerie de Boa Viagem")
    bv = df[df["municipio"] == "Boa Viagem"].set_index("competencia")
    print(bv[["beneficiarios", "valor_total", "valor_medio_por_beneficiario", "beneficiarios_por_1000_hab"]]
          .to_string(float_format=lambda v: f"{v:,.1f}"))

    print("\nConferencia: parcelas por beneficiario (perto de 1,0 e esperado)")
    print((df["parcelas"] / df["beneficiarios"]).describe().round(2).to_string())
    dif = ((df["beneficiarios"] - df["beneficios"]).abs() / df["beneficios"]).max()
    print(f"Maior diferenca relativa entre pessoas (NIS) e numeros de beneficio: {dif:.1%} (esperado perto de 0)")


if __name__ == "__main__":
    main()

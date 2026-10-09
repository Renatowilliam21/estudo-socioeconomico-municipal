"""Agrega Garantia-Safra e Seguro-Defeso (Portal da Transparencia) por municipio e mes.

Uso (na raiz do projeto, com o .venv ativo):
    python -m src.tratamento.beneficio_portal garantia_safra
    python -m src.tratamento.beneficio_portal seguro_defeso

Entrada: os .zip em data/raw/portal_transparencia/<programa>/ (nome AAAAMM_Programa.zip)
Saidas:  data/processed/<programa>_mensal.csv   (por competencia e municipio)
         data/processed/<programa>_anual.csv    (pessoas distintas e valor por ano)
Apenas numeros agregados, sem dados pessoais.

Privacidade: le somente UF, municipio, valor e o identificador usado para contar pessoas distintas
(NIS; no Seguro-Defeso, o RGP quando falta o NIS). NAO carrega CPF nem nome. O identificador fica so
na memoria durante a contagem e nao e gravado em nenhuma saida.

Leitura dos numeros: cada linha e um pagamento a um favorecido (pessoa). A competencia e o AAAAMM do
nome do arquivo. Arquivos repetidos do mesmo mes (nome com '(1)', copia de download) sao ignorados.
"""
import argparse
import hashlib
import re
import zipfile
from pathlib import Path

import pandas as pd

from src.tratamento.bolsa_familia_portal import UF, municipios_alvo, parse_valor, sem_acento

BASE = Path("data/raw/portal_transparencia")
PROCESSED = Path("data/processed")
PROGRAMAS = {
    "garantia_safra": {"rotulo": "Garantia-Safra", "pessoa": ["NIS FAVORECIDO"]},
    "seguro_defeso": {"rotulo": "Seguro-Defeso", "pessoa": ["NIS FAVORECIDO", "RGP FAVORECIDO"]},
}


def md5(caminho):
    h = hashlib.md5()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def arquivos_por_mes(pasta):
    """Um zip por mes (AAAAMM). Se houver copias, prefere o nome sem '(1)' e avisa se forem diferentes."""
    grupos = {}
    for z in sorted(pasta.glob("*.zip")):
        m = re.match(r"(\d{6})_", z.name)
        if m:
            grupos.setdefault(m.group(1), []).append(z)
        else:
            print(f"  ignorado (nome fora do padrao AAAAMM_): {z.name}")
    escolhidos = {}
    for mes, lista in sorted(grupos.items()):
        lista = sorted(lista, key=lambda p: (" (" in p.name, p.name))
        escolhidos[mes] = lista[0]
        if len(lista) > 1:
            base = md5(lista[0])
            iguais = all(md5(o) == base for o in lista[1:])
            msg = "copia identica ignorada" if iguais else "ATENCAO: copias DIFERENTES; usando " + lista[0].name
            print(f"  {mes}: {len(lista)} arquivos, {msg}")
    return escolhidos


def meses_faltando(meses):
    if not meses:
        return []
    todos = pd.period_range(min(meses), max(meses), freq="M").strftime("%Y%m")
    return [m for m in todos if m not in set(meses)]


def agregar_zip(caminho, alvo, cols_pessoa):
    usar = {sem_acento(c) for c in ["UF", "NOME MUNICÍPIO", "VALOR PARCELA", *cols_pessoa]}
    partes = []
    with zipfile.ZipFile(caminho) as zf:
        for membro in [n for n in zf.namelist() if n.lower().endswith(".csv")]:
            with zf.open(membro) as f:
                for chunk in pd.read_csv(f, sep=";", quotechar='"', encoding="latin1", dtype=str,
                                         usecols=lambda c: sem_acento(c) in usar, chunksize=500_000):
                    chunk.columns = [sem_acento(c) for c in chunk.columns]
                    chunk = chunk[chunk["UF"].str.strip().str.upper() == UF]
                    chunk = chunk.assign(chave=chunk["NOME MUNICIPIO"].map(sem_acento))
                    chunk = chunk[chunk["chave"].isin(alvo)]
                    if chunk.empty:
                        continue
                    pessoa = None
                    for c in cols_pessoa:
                        col = sem_acento(c)
                        if col in chunk.columns:
                            s = chunk[col].str.strip().replace("", pd.NA)
                            pessoa = s if pessoa is None else pessoa.fillna(s)
                    partes.append(pd.DataFrame({"chave": chunk["chave"], "pessoa": pessoa,
                                                "valor": parse_valor(chunk["VALOR PARCELA"])}))
    return pd.concat(partes, ignore_index=True) if partes else pd.DataFrame(columns=["chave", "pessoa", "valor"])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("programa", choices=sorted(PROGRAMAS))
    prog = ap.parse_args().programa
    cfg = PROGRAMAS[prog]
    alvo = municipios_alvo()
    pasta = BASE / prog
    meses = arquivos_por_mes(pasta)
    if not meses:
        raise SystemExit(f"Nenhum .zip AAAAMM_*.zip em {pasta}.")
    print(f"{cfg['rotulo']}: {len(meses)} mes(es), {min(meses)} a {max(meses)}. Processando...")
    falt = meses_faltando(list(meses))
    if falt:
        print(f"ATENCAO: sem arquivo para {len(falt)} mes(es) entre o primeiro e o ultimo: {', '.join(falt)}")

    todos = []
    for mes, z in meses.items():
        print(f"  lendo {z.name} ...", flush=True)
        r = agregar_zip(z, alvo, cfg["pessoa"])
        print(f"    {len(r)} pagamentos nos municipios do estudo")
        if not r.empty:
            todos.append(r.assign(competencia=mes))
    if not todos:
        raise SystemExit("Nenhum pagamento encontrado nos municipios do estudo.")
    df = pd.concat(todos, ignore_index=True)

    mensal = (df.groupby(["competencia", "chave"])
                .agg(beneficiarios=("pessoa", "nunique"), parcelas=("chave", "size"), valor_total=("valor", "sum"))
                .reset_index())
    df["ano"] = df["competencia"].str[:4]
    anual = (df.groupby(["ano", "chave"])
               .agg(pessoas_distintas=("pessoa", "nunique"), meses_com_pagamento=("competencia", "nunique"),
                    valor_total=("valor", "sum"))
               .reset_index())
    for t in (mensal, anual):
        t["codigo_ibge"] = t["chave"].map(lambda k: alvo[k][0])
        t["municipio"] = t["chave"].map(lambda k: alvo[k][1])
        t["populacao_2022"] = t["chave"].map(lambda k: alvo[k][2])
        t["valor_total"] = t["valor_total"].round(2)
    mensal["valor_medio_por_pagamento"] = (mensal["valor_total"] / mensal["parcelas"]).round(2)
    mensal["beneficiarios_por_1000_hab"] = (mensal["beneficiarios"] / mensal["populacao_2022"] * 1000).round(1)
    anual["pessoas_por_1000_hab"] = (anual["pessoas_distintas"] / anual["populacao_2022"] * 1000).round(1)
    mensal = mensal[["competencia", "codigo_ibge", "municipio", "beneficiarios", "parcelas", "valor_total",
                     "valor_medio_por_pagamento", "populacao_2022", "beneficiarios_por_1000_hab"]]
    anual = anual[["ano", "codigo_ibge", "municipio", "pessoas_distintas", "meses_com_pagamento", "valor_total",
                   "populacao_2022", "pessoas_por_1000_hab"]]
    mensal = mensal.sort_values(["competencia", "municipio"])
    anual = anual.sort_values(["ano", "municipio"])
    PROCESSED.mkdir(parents=True, exist_ok=True)
    mensal.to_csv(PROCESSED / f"{prog}_mensal.csv", index=False, encoding="utf-8")
    anual.to_csv(PROCESSED / f"{prog}_anual.csv", index=False, encoding="utf-8")
    print(f"\nSalvo: {PROCESSED / (prog + '_mensal.csv')} ({len(mensal)} linhas) e {PROCESSED / (prog + '_anual.csv')} ({len(anual)} linhas)")

    sem_dados = sorted(set(v[1] for v in alvo.values()) - set(mensal["municipio"]))
    if sem_dados:
        print("ATENCAO: nenhum pagamento para:", ", ".join(sem_dados),
              "(pode ser que o programa nao pague ali ou que o nome tenha outra grafia no Portal)")

    print(f"\n{cfg['rotulo']}: pessoas distintas por ano (todas as competencias disponiveis)")
    tab = anual.pivot_table(index="municipio", columns="ano", values="pessoas_distintas", aggfunc="sum").fillna(0).astype(int)
    print(tab.sort_values(tab.columns[-1], ascending=False).to_string())

    print("\nSerie mensal de Boa Viagem")
    bv = mensal[mensal["municipio"] == "Boa Viagem"].set_index("competencia")
    print(bv[["beneficiarios", "parcelas", "valor_total", "valor_medio_por_pagamento"]].to_string(
        float_format=lambda v: f"{v:,.1f}"))

    print("\nConferencia: pagamentos por pessoa no mes (perto de 1,0 e esperado)")
    print((mensal["parcelas"] / mensal["beneficiarios"]).describe().round(2).to_string())


if __name__ == "__main__":
    main()

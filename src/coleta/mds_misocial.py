"""Consulta a API MI Social do MDS (Bolsa Familia e Cadastro Unico por municipio, em numeros agregados).

Uso (na raiz do projeto, com o .venv ativo):
    # 1) descobrir os nomes dos campos (valores de Boa Viagem no mes mais recente com dados)
    python -m src.coleta.mds_misocial --campos
    python -m src.coleta.mds_misocial --campos --filtro pess      # so campos que contem 'pess'

    # 2) baixar os campos escolhidos, de uma competencia em diante, para os 11 municipios
    python -m src.coleta.mds_misocial --baixar campo_a,campo_b --desde 202301

Saidas:
    data/raw/mds_misocial/consulta_<desde>.json   (resposta original, fora do Git)
    data/processed/mds_misocial.csv               (municipio, codigo_ibge, anomes, <campos>)

A API devolve o codigo do municipio com 6 ou 7 digitos conforme o campo; o script consulta os dois.
So existem totais por municipio e mes, sem dados de pessoas.
"""
import argparse
import json
import sys
from pathlib import Path

import pandas as pd
import requests
import yaml

API = "https://aplicacoes.mds.gov.br/sagi/servicos/misocial/"
CONFIG = Path("config/municipio.yml")
RAW = Path("data/raw/mds_misocial")
SAIDA = Path("data/processed/mds_misocial.csv")


def codigos(cfg):
    """Codigos de 7 digitos e suas versoes de 6 digitos para o municipio e a comparacao."""
    sete = [str(cfg["municipio"]["codigo_ibge"])] + [str(c) for c in cfg.get("comparacao", {}).get("municipios") or []]
    return sete, [c[:6] for c in sete]


def filtro_codigos(sete, seis):
    return "codigo_ibge:(" + " OR ".join(sete + seis) + ")"


def consultar(params):
    r = requests.get(API, params=params, timeout=180)
    r.raise_for_status()
    return r.json()


def tem_dados(doc):
    """Meses futuros vem com tudo zerado; campos terminados em _d sao datas e nao contam."""
    return any(isinstance(v, (int, float)) and v != 0 for k, v in doc.items()
               if not k.endswith("_d") and k not in ("anomes_s", "codigo_ibge"))


def listar_campos(sete, seis, filtro=None, anomes=None, nao_zero=False):
    fq = [f"codigo_ibge:({sete[0]} OR {seis[0]})"]
    if anomes:
        fq.append(f"anomes_s:{anomes}")
    d = consultar({"q": "*:*", "fq": fq, "rows": 60, "sort": "anomes_s desc", "wt": "json"})
    docs = d["response"]["docs"]
    if not docs:
        sys.exit("Nenhum registro de Boa Viagem. O codigo no config/municipio.yml esta correto?")
    doc = next((x for x in docs if tem_dados(x)), None)
    if doc is None:
        sys.exit("Nenhum mes com dados para Boa Viagem nos 60 registros mais recentes.")
    print(f"Boa Viagem: codigo_ibge={doc.get('codigo_ibge')} anomes_s={doc.get('anomes_s')} | {len(doc)} campos")
    print("(mes mais recente com dados; use --anomes AAAAMM para escolher outro)\n")
    for k in sorted(doc):
        if filtro and filtro.lower() not in k.lower():
            continue
        if nao_zero and doc[k] == 0:
            continue
        print(f"  {k} = {doc[k]}")


def baixar(sete, seis, campos, desde):
    fl = ",".join(["codigo_ibge", "anomes_s", *campos])
    params = {"q": "*:*", "fq": [filtro_codigos(sete, seis), f"anomes_s:[{desde} TO *]"],
              "fl": fl, "rows": 100000, "sort": "anomes_s asc, codigo_ibge asc", "wt": "json"}
    d = consultar(params)
    docs = d["response"]["docs"]
    if not docs:
        sys.exit("A API nao retornou registros. Confira os nomes dos campos com --campos.")
    RAW.mkdir(parents=True, exist_ok=True)
    (RAW / f"consulta_{desde}.json").write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    df = pd.DataFrame(docs)
    df["codigo_ibge"] = df["codigo_ibge"].astype(str)
    por6 = {c[:6]: c for c in sete}
    df["codigo_ibge"] = df["codigo_ibge"].map(lambda c: c if c in sete else por6.get(c[:6], c))
    df = df.rename(columns={"anomes_s": "anomes"})
    faltam = [c for c in campos if c not in df.columns]
    if faltam:
        print("Aviso: campos sem dados:", faltam)
    ok = [c for c in campos if c in df.columns]
    # descarta meses em que todos os municipios estao zerados (meses futuros ou ainda nao publicados)
    num = df[ok].apply(pd.to_numeric, errors="coerce").fillna(0)
    soma = num.abs().sum(axis=1).groupby(df["anomes"]).transform("sum")
    vazios = sorted(df.loc[soma == 0, "anomes"].unique())
    if vazios:
        print(f"Descartados {len(vazios)} mes(es) sem dados: {vazios[0]} a {vazios[-1]}")
    return df[soma > 0].reset_index(drop=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--campos", action="store_true", help="listar campos de um registro de Boa Viagem")
    ap.add_argument("--filtro", help="com --campos: so campos que contem este texto")
    ap.add_argument("--nao-zero", action="store_true", help="com --campos: esconde campos com valor zero")
    ap.add_argument("--anomes", help="com --campos: competencia AAAAMM (padrao: a mais recente com dados)")
    ap.add_argument("--baixar", help="campos separados por virgula")
    ap.add_argument("--desde", default="202301", help="primeira competencia AAAAMM (padrao 202301)")
    args = ap.parse_args()

    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    sete, seis = codigos(cfg)
    if args.campos:
        listar_campos(sete, seis, args.filtro, args.anomes, args.nao_zero)
        return
    if not args.baixar:
        ap.error("use --campos ou --baixar")
    df = baixar(sete, seis, [c.strip() for c in args.baixar.split(",") if c.strip()], args.desde)

    nomes = {}
    sidra = Path("data/processed/sidra_tabela_4714.csv")
    if sidra.exists():
        s = pd.read_csv(sidra, dtype={"localidade_id": str}).drop_duplicates("localidade_id")
        nomes = dict(zip(s["localidade_id"], s["localidade"].str.replace(r"\s*(\([A-Z]{2}\)|-\s*[A-Z]{2})\s*$", "", regex=True)))
    df.insert(0, "municipio", df["codigo_ibge"].map(nomes))
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(SAIDA, index=False, encoding="utf-8")
    print(f"Salvo: {SAIDA} ({len(df)} linhas, competencias {df['anomes'].min()} a {df['anomes'].max()})")
    ult = df[df["anomes"] == df["anomes"].max()]
    print(f"\nCompetencia mais recente ({df['anomes'].max()}):")
    print(ult.drop(columns=["anomes"]).to_string(index=False))


if __name__ == "__main__":
    main()

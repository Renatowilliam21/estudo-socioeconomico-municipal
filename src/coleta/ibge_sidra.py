"""Baixa tabelas do SIDRA (API de agregados do IBGE) para o municipio e os de comparacao.

Uso (na raiz do projeto, com o .venv ativo):
    # 1) conferir nome e variaveis da tabela antes de baixar
    python -m src.coleta.ibge_sidra --tabela 5938 --listar

    # 2) baixar (todas as variaveis, ultimos 6 periodos, municipio + comparacao)
    python -m src.coleta.ibge_sidra --tabela 5938 --periodos -6

Saidas:
    data/raw/ibge_sidra/tabela_<N>_<periodos>.json   (resposta original, fora do Git)
    data/processed/sidra_tabela_<N>.csv              (formato longo, agregado, vai para o Git)
"""
import argparse
import json
import re
import sys
from pathlib import Path

import pandas as pd
import requests
import yaml

API = "https://servicodados.ibge.gov.br/api/v3/agregados"
CONFIG = Path("config/municipio.yml")
RAW = Path("data/raw/ibge_sidra")
PROCESSED = Path("data/processed")


def get(url):
    resposta = requests.get(url, timeout=120)
    resposta.raise_for_status()
    return resposta.json()


def localidades(cfg, so_municipio):
    codigos = [cfg["municipio"]["codigo_ibge"]]
    if not so_municipio:
        codigos += list(cfg.get("comparacao", {}).get("municipios") or [])
    return "N6[" + ",".join(str(c) for c in codigos) + "]"


def listar(tabela):
    meta = get(f"{API}/{tabela}/metadados")
    print(f"Tabela {tabela}: {meta['nome']}")
    print(f"Periodicidade: {meta.get('periodicidade', {}).get('frequencia', '?')}")
    print("Variaveis:")
    for v in meta.get("variaveis", []):
        print(f"  {v['id']}  {v['nome']} [{v.get('unidade', '')}]")
    classes = meta.get("classificacoes", [])
    if classes:
        print("Classificacoes (algumas tabelas exigem --classificacao, ex.: '782[all]'):")
        for c in classes:
            print(f"  {c['id']}  {c['nome']}")


def normalizar(dados, tabela):
    """Converte a resposta da API em tabela longa: uma linha por variavel/local/periodo."""
    linhas = []
    for v in dados:
        for res in v.get("resultados", []):
            classes = {}
            for c in res.get("classificacoes", []):
                classes[c["nome"]] = next(iter(c["categoria"].values()), "")
            for s in res.get("series", []):
                loc = s["localidade"]
                for periodo, valor in s["serie"].items():
                    linhas.append({
                        "tabela": tabela,
                        "variavel_id": v["id"],
                        "variavel": v["variavel"],
                        "unidade": v.get("unidade", ""),
                        "localidade_id": loc["id"],
                        "localidade": loc["nome"],
                        **classes,
                        "periodo": periodo,
                        "valor_original": valor,
                    })
    df = pd.DataFrame(linhas)
    if not df.empty:
        # '-', '...', 'X' viram vazio (dado inexistente ou sigiloso); o texto original fica em valor_original
        df["valor"] = pd.to_numeric(df["valor_original"], errors="coerce")
    return df


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tabela", required=True, help="numero da tabela no SIDRA, ex.: 5938")
    ap.add_argument("--periodos", default="-6", help="ex.: -6 (ultimos 6), 2022, 2019|2020|2021, all")
    ap.add_argument("--variaveis", default="all", help="ex.: all ou 37|513")
    ap.add_argument("--classificacao", help="ex.: 782[all] (obrigatoria em algumas tabelas)")
    ap.add_argument("--so-municipio", action="store_true", help="nao incluir municipios de comparacao")
    ap.add_argument("--listar", action="store_true", help="apenas mostrar nome e variaveis da tabela")
    args = ap.parse_args()

    if args.listar:
        listar(args.tabela)
        return

    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    url = (f"{API}/{args.tabela}/periodos/{args.periodos}/variaveis/{args.variaveis}"
           f"?localidades={localidades(cfg, args.so_municipio)}")
    if args.classificacao:
        url += f"&classificacao={args.classificacao}"
    print("Consultando:", url)

    dados = get(url)
    if not dados:
        sys.exit("A API nao retornou dados. Confira tabela, periodos e classificacao com --listar.")

    RAW.mkdir(parents=True, exist_ok=True)
    PROCESSED.mkdir(parents=True, exist_ok=True)
    sufixo = re.sub(r"[^0-9a-zA-Z-]+", "_", args.periodos)
    bruto = RAW / f"tabela_{args.tabela}_{sufixo}.json"
    bruto.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")

    df = normalizar(dados, args.tabela)
    saida = PROCESSED / f"sidra_tabela_{args.tabela}.csv"
    df.to_csv(saida, index=False, encoding="utf-8")

    print(f"Bruto:     {bruto}")
    print(f"Processado: {saida} ({len(df)} linhas, {df['variavel'].nunique()} variaveis, "
          f"{df['localidade'].nunique()} localidades)")
    print(df[df["localidade_id"].astype(str) == str(cfg['municipio']['codigo_ibge'])]
          .head(12)[["variavel", "periodo", "valor", "unidade"]].to_string(index=False))


if __name__ == "__main__":
    main()

"""Busca tabelas no catalogo de agregados do IBGE (SIDRA) por palavra-chave.

Uso (na raiz do projeto, com o .venv ativo):
    python -m src.coleta.ibge_buscar rendimento domiciliar
    python -m src.coleta.ibge_buscar esgotamento --pesquisa Censo
    python -m src.coleta.ibge_buscar --pesquisa Censo --max 80

Todas as palavras devem aparecer no nome da tabela (sem distinguir acento ou maiuscula).
Depois de achar o numero, confira com:  python -m src.coleta.ibge_sidra --tabela N --listar
"""
import argparse
import unicodedata

import requests

API = "https://servicodados.ibge.gov.br/api/v3/agregados"


def norm(t):
    base = unicodedata.normalize("NFD", str(t))
    return "".join(c for c in base if unicodedata.category(c) != "Mn").lower()


def achatar(catalogo):
    for pesq in catalogo:
        for ag in pesq.get("agregados", []):
            yield pesq.get("nome", ""), str(ag["id"]), ag.get("nome", "")


def filtrar(catalogo, palavras, pesquisa=None):
    ps = [norm(p) for p in palavras]
    pq = norm(pesquisa) if pesquisa else None
    return [(p, i, n) for p, i, n in achatar(catalogo)
            if all(w in norm(n) for w in ps) and (pq is None or pq in norm(p))]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("palavras", nargs="*", help="palavras que devem aparecer no nome da tabela")
    ap.add_argument("--pesquisa", help="trecho do nome da pesquisa, ex.: Censo")
    ap.add_argument("--max", type=int, default=60, help="maximo de linhas (padrao 60)")
    args = ap.parse_args()

    r = requests.get(API, timeout=120)
    r.raise_for_status()
    achados = filtrar(r.json(), args.palavras, args.pesquisa)
    print(f"{len(achados)} tabela(s) encontradas" + (f" (mostrando {args.max})" if len(achados) > args.max else ""))
    for p, i, n in achados[:args.max]:
        print(f"{i:>6}  [{p}]  {n}")


if __name__ == "__main__":
    main()

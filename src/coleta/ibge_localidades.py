"""Confirma o municipio no IBGE e resolve os codigos dos municipios de comparacao.

Uso (na raiz do projeto, com o .venv ativo):
    python -m src.coleta.ibge_localidades
    python -m src.coleta.ibge_localidades --nomes "Madalena,Quixeramobim,Canindé" --gravar
"""
import argparse
import re
import sys
import unicodedata
from pathlib import Path

import requests
import yaml

API = "https://servicodados.ibge.gov.br/api/v1/localidades"
CONFIG = Path("config/municipio.yml")


def sem_acento(texto):
    base = unicodedata.normalize("NFD", texto)
    return "".join(c for c in base if unicodedata.category(c) != "Mn").lower().strip()


def get(url):
    resposta = requests.get(url, timeout=60)
    resposta.raise_for_status()
    return resposta.json()


def gravar_vizinhos(codigos):
    """Troca a linha 'municipios: [...]' do YAML, preservando os comentarios."""
    texto = CONFIG.read_text(encoding="utf-8")
    novo, n = re.subn(
        r"^(\s*municipios:\s*)\[.*?\]",
        lambda m: f"{m.group(1)}[{', '.join(str(c) for c in codigos)}]",
        texto,
        count=1,
        flags=re.MULTILINE,
    )
    if n != 1:
        sys.exit("Nao encontrei a linha 'municipios: [...]' em config/municipio.yml.")
    CONFIG.write_text(novo, encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--nomes", help="nomes separados por virgula (mesmo estado) para buscar o codigo")
    ap.add_argument("--gravar", action="store_true", help="grava os codigos em config/municipio.yml")
    args = ap.parse_args()

    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    codigo = cfg["municipio"]["codigo_ibge"]
    m = get(f"{API}/municipios/{codigo}")

    micro = m["microrregiao"]
    uf = micro["mesorregiao"]["UF"]
    print(f"Codigo {m['id']}: {m['nome']} ({uf['sigla']})")
    print(f"Microrregiao: {micro['nome']} | Mesorregiao: {micro['mesorregiao']['nome']}")

    if sem_acento(m["nome"]) != sem_acento(cfg["municipio"]["nome"]):
        sys.exit(f"ERRO: o codigo {codigo} e de '{m['nome']}', mas o config diz '{cfg['municipio']['nome']}'. "
                 "Corrija config/municipio.yml.")
    print("Municipio confirmado.\n")

    print(f"Municipios da microrregiao {micro['nome']}:")
    for v in get(f"{API}/microrregioes/{micro['id']}/municipios"):
        print(f"  {v['id']}  {v['nome']}")

    if args.nomes:
        pedidos = [sem_acento(n) for n in args.nomes.split(",") if n.strip()]
        todos = {sem_acento(x["nome"]): x for x in get(f"{API}/estados/{uf['id']}/municipios")}
        achados, faltando = [], []
        for nome in pedidos:
            (achados if nome in todos else faltando).append(todos.get(nome, nome))
        print("\nMunicipios de comparacao:")
        for x in achados:
            print(f"  {x['id']}  {x['nome']}")
        for nome in faltando:
            print(f"  NAO ENCONTRADO: {nome}")
        codigos = [x["id"] for x in achados]
        print(f"\nmunicipios: {codigos}")
        if args.gravar and codigos:
            gravar_vizinhos(codigos)
            print("Gravado em config/municipio.yml")


if __name__ == "__main__":
    main()

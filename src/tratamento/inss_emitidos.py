"""Extrai das planilhas 'Emitidos por Municipios' (Ministerio da Previdencia) os municipios do estudo.

Uso (na raiz do projeto, com o .venv ativo):
    python -m src.tratamento.inss_emitidos

Entrada: todos os .xlsx em data/raw/inss/
Saida:   data/processed/inss_emitidos_longo.csv  (arquivo, aba, codigo_ibge, municipio, coluna, valor)

As planilhas tem cabecalho em varias linhas (grupos que ocupam varias colunas). O script remonta o
nome completo de cada coluna e traz TODAS as colunas dos municipios do estudo, sem depender de nomes
fixos. Sao tabelas agregadas por municipio (sem dados de pessoas).

Atencao (conforme a propria fonte): os dados sao classificados pelo municipio do orgao pagador
(agencia/banco), nao necessariamente pelo da residencia do beneficiario.
"""
from pathlib import Path

import pandas as pd

from src.tratamento.bolsa_familia_portal import municipios_alvo, sem_acento

ENTRADA = Path("data/raw/inss")
SAIDA = Path("data/processed/inss_emitidos_longo.csv")
INICIOS_CABECALHO = {"NOME", "MUNICIPIO", "MUNICIPIO "}


def eh_codigo(x):
    try:
        return len(str(int(float(x)))) == 7
    except (TypeError, ValueError):
        return False


def localizar_cabecalho(df):
    ini = next((i for i in range(len(df)) if sem_acento(df.iat[i, 0]) in INICIOS_CABECALHO), None)
    if ini is None:
        return None, None
    fim = next((i for i in range(ini + 1, len(df)) if eh_codigo(df.iat[i, 1])), None)
    return ini, fim


def nomes_das_colunas(df, ini, fim):
    """Junta os rotulos das linhas de cabecalho. Um rotulo de grupo (celula mesclada) so e
    repetido para a direita nas colunas que tem um rotulo mais embaixo."""
    cab = [[None if pd.isna(v) else str(v).strip() or None for v in df.iloc[r].tolist()]
           for r in range(ini, fim)]
    nomes = []
    for c in range(len(cab[0])):
        partes = []
        for r in range(len(cab)):
            v = cab[r][c]
            if v is None and any(cab[r2][c] is not None for r2 in range(r + 1, len(cab))):
                k = c - 1
                while k >= 0 and cab[r][k] is None:
                    k -= 1
                v = cab[r][k] if k >= 0 else None
            if v and (not partes or partes[-1] != v):
                partes.append(v)
        nomes.append(" | ".join(partes))
    return nomes


def extrair(caminho, alvo_por_codigo):
    linhas = []
    with pd.ExcelFile(caminho) as xls:
        abas = {aba: xls.parse(aba, header=None) for aba in xls.sheet_names}
    for aba, df in abas.items():
        ini, fim = localizar_cabecalho(df)
        if ini is None or fim is None:
            print(f"    aba '{aba}': cabecalho nao reconhecido, ignorada")
            continue
        nomes = nomes_das_colunas(df, ini, fim)
        dados = df.iloc[fim:]
        dados = dados[dados[1].map(eh_codigo)]
        dados = dados.assign(cod=dados[1].map(lambda x: str(int(float(x)))))
        dados = dados[dados["cod"].isin(alvo_por_codigo)]
        for c in range(df.shape[1]):
            if c < 3 or not nomes[c]:
                continue
            for _, r in dados.iterrows():
                v = pd.to_numeric(r[c], errors="coerce")
                if pd.notna(v):
                    linhas.append({"arquivo": caminho.name, "aba": aba, "codigo_ibge": r["cod"],
                                   "municipio": alvo_por_codigo[r["cod"]], "coluna": nomes[c], "valor": float(v)})
        print(f"    aba '{aba}': {len(dados)} municipio(s) do estudo, {sum(1 for n in nomes[3:] if n)} colunas")
    return linhas


def main():
    alvo = {cod: nome for cod, nome, _ in municipios_alvo().values()}
    arquivos = sorted(ENTRADA.glob("*.xlsx"))
    if not arquivos:
        raise SystemExit(f"Nenhum .xlsx em {ENTRADA}.")
    linhas = []
    for a in arquivos:
        print(f"  lendo {a.name} ...", flush=True)
        linhas += extrair(a, alvo)
    df = pd.DataFrame(linhas)
    df.to_csv(SAIDA, index=False, encoding="utf-8")
    print(f"\nSalvo: {SAIDA} ({len(df)} linhas)")

    faltando = sorted(set(alvo.values()) - set(df["municipio"]))
    if faltando:
        print("ATENCAO: sem dados para:", ", ".join(faltando))

    bv = df[df["municipio"] == "Boa Viagem"]
    for (arq, aba), g in bv.groupby(["arquivo", "aba"], sort=False):
        print(f"\n== Boa Viagem | {arq} | aba {aba}")
        for _, r in g.iterrows():
            print(f"  {r['coluna']}: {r['valor']:,.2f}")


if __name__ == "__main__":
    main()

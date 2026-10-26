"""Baixa o boletim de urna (bweb) de um turno e resume presidente por seção.

Fonte: dados abertos do TSE, conjunto resultados-2026-boletim-de-urna (um zip
por UF e turno). O que interessa aqui, e que o resultado por município não
tem, é o horário de abertura e de encerramento de cada urna.

Uso: python src/download_bweb.py 1   (ou 2, quando o TSE publicar o 2º turno)

Saída: data/processed/secao_presidente_{turno}t.csv, uma linha por seção, com
os horários já convertidos para o horário de Brasília.
"""
import io
import json
import sys
import urllib.request
import zipfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "bweb"
OUT = ROOT / "data" / "processed"
API = "https://dadosabertos.tse.jus.br/api/3/action/package_show?id=resultados-2026-boletim-de-urna"
COLS = ["SG_UF", "CD_MUNICIPIO", "NM_MUNICIPIO", "NR_ZONA", "NR_SECAO", "NR_LOCAL_VOTACAO",
        "CD_CARGO_PERGUNTA", "QT_APTOS", "QT_COMPARECIMENTO", "QT_ABSTENCOES", "DS_TIPO_URNA",
        "NR_VOTAVEL", "QT_VOTOS", "DS_SECOES_AGREGADAS", "DT_ABERTURA", "DT_ENCERRAMENTO",
        "QT_ELEI_BIOM_SEM_HABILITACAO"]
CHAVE = ["SG_UF", "CD_MUNICIPIO", "NR_ZONA", "NR_SECAO"]


def urls(turno):
    res = json.loads(urllib.request.urlopen(API, timeout=60).read())["result"]["resources"]
    out = sorted({r["url"] for r in res if f"/bweb_{turno}t_" in r["url"] and r["url"].endswith(".zip")})
    if not out:
        sys.exit(f"o TSE ainda não publicou o bweb do {turno}º turno")
    return out


def baixar(url):
    path = RAW / url.rsplit("/", 1)[1]
    if not path.exists():
        RAW.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".part")
        with urllib.request.urlopen(url, timeout=600) as r, open(tmp, "wb") as f:
            while chunk := r.read(1 << 20):
                f.write(chunk)
        tmp.rename(path)
    return path


def resumir(path):
    """Lê só as linhas de presidente do CSV dentro do zip e devolve uma linha por seção."""
    parts = []
    with zipfile.ZipFile(path) as z:
        nome = next(n for n in z.namelist() if n.endswith(".csv"))
        with z.open(nome) as f:
            for ch in pd.read_csv(io.TextIOWrapper(f, encoding="latin1"), sep=";", usecols=COLS,
                                  chunksize=1_000_000, low_memory=False):
                parts.append(ch[ch.CD_CARGO_PERGUNTA == 1])
    d = pd.concat(parts)
    d["grupo"] = d.NR_VOTAVEL.map({13: "lula", 22: "flavio", 95: "brancos", 96: "nulos"}).fillna("outros")
    votos = d.pivot_table(index=CHAVE, columns="grupo", values="QT_VOTOS", aggfunc="sum", fill_value=0)
    meta = d.groupby(CHAVE)[["NM_MUNICIPIO", "NR_LOCAL_VOTACAO", "QT_APTOS", "QT_COMPARECIMENTO",
                             "QT_ABSTENCOES", "DS_TIPO_URNA", "DS_SECOES_AGREGADAS", "DT_ABERTURA",
                             "DT_ENCERRAMENTO", "QT_ELEI_BIOM_SEM_HABILITACAO"]].first()
    return meta.join(votos).reset_index()


def horario_brasilia(df):
    """O bweb traz hora local. A votação abre às 8h de Brasília em todo o país, então o
    deslocamento de cada município é 8h menos a hora mediana de abertura das suas urnas."""
    for c in ("DT_ABERTURA", "DT_ENCERRAMENTO"):
        df[c] = pd.to_datetime(df[c], errors="coerce")
    hora = df.DT_ABERTURA.dt.hour + df.DT_ABERTURA.dt.minute / 60
    desloc = (8 - hora.groupby([df.SG_UF, df.CD_MUNICIPIO]).transform("median")).round()
    df["fuso_h"] = desloc
    df["abertura_bsb"] = df.DT_ABERTURA + pd.to_timedelta(desloc, unit="h")
    df["encerramento_bsb"] = df.DT_ENCERRAMENTO + pd.to_timedelta(desloc, unit="h")
    return df


def main():
    turno = int(sys.argv[1])
    secoes = []
    for url in urls(turno):
        path = baixar(url)
        secoes.append(resumir(path))
        print(path.name, len(secoes[-1]), "seções", flush=True)
    df = horario_brasilia(pd.concat(secoes, ignore_index=True))
    OUT.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT / f"secao_presidente_{turno}t.csv", index=False)
    print(df[["QT_APTOS", "QT_COMPARECIMENTO", "lula", "flavio"]].sum())


if __name__ == "__main__":
    main()

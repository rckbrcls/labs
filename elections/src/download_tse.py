"""Baixa o resultado de presidente por município nos dois turnos de 2026.

Fonte: o portal de divulgação do TSE (resultados.tse.jus.br), um JSON por
município e por turno. Os arquivos brutos ficam em data/raw/{eleicao}/ como
cache; rodar de novo só baixa o que falta.

Saída: data/processed/presidente_municipio_2026.csv, uma linha por
município x turno, com eleitorado, comparecimento, brancos, nulos e os votos
de cada candidato (colunas c{número}).
"""
import json
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed"
BASE = "https://resultados.tse.jus.br/oficial/ele2026"
ELEICOES = {1: "6257", 2: "6258"}  # presidente, 1º e 2º turno


def get(url, tries=4):
    for i in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                return r.read()
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(2 ** i)


def municipios(ele):
    """Lista (uf, código TSE, código IBGE, nome) a partir do config da eleição."""
    cfg = json.loads(get(f"{BASE}/{ele}/config/mun-e00{ele}-cm.json"))
    return [(a["cd"], m["cd"], m["cdi"], m["nm"]) for a in cfg["abr"] for m in a["mu"]]


def baixar(ele, uf, cd):
    path = RAW / ele / f"{uf}{cd}.json"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(get(f"{BASE}/{ele}/dados/{uf}/{uf}{cd}-c0001-e00{ele}-u.json"))
    return path


def n(x):
    return int(x) if x not in (None, "") else 0


def linha(turno, uf, cd, cdi, nome, path):
    d = json.loads(path.read_text())
    e, v = d["e"], d["v"]
    row = dict(turno=turno, uf=uf.upper(), cd_tse=cd, cd_ibge=cdi, municipio=nome,
               apurado=d["and"] == "f", aptos=n(e["te"]), comparecimento=n(e["c"]),
               abstencao=n(e["a"]), brancos=n(v["vb"]), nulos=n(v["tvn"]), validos=n(v["vv"]))
    for agr in d["carg"][0]["agr"]:
        for par in agr["par"]:
            for c in par["cand"]:
                row[f"c{c['n']}"] = n(c["vap"])
    return row


def main():
    rows = []
    for turno, ele in ELEICOES.items():
        mus = municipios(ele)
        with ThreadPoolExecutor(12) as pool:
            paths = list(pool.map(lambda m: baixar(ele, m[0], m[1]), mus))
        rows += [linha(turno, *m, p) for m, p in zip(mus, paths)]
        print(f"turno {turno}: {len(mus)} municípios")
    df = pd.DataFrame(rows)
    cand = sorted(c for c in df.columns if c.startswith("c") and c[1:].isdigit())
    df[cand] = df[cand].fillna(0).astype(int)
    OUT.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT / "presidente_municipio_2026.csv", index=False)
    print(df.groupby("turno")[["aptos", "comparecimento", "validos", "c13", "c22"]].sum())


if __name__ == "__main__":
    main()

"""Prepara as bases dos notebooks de segundo-turno/.

1. Presidente 2022 por município e turno, a partir de dois arquivos pequenos do
   CDN do TSE (baixados para data/raw/ se faltarem):
   - detalhe_votacao_munzona_2022.zip: aptos, comparecimento, abstenção,
     brancos e nulos;
   - votacao_partido_munzona_2022.zip: votos nominais por partido (no cargo de
     presidente, partido = candidato: PT 13 = Lula, PL 22 = Bolsonaro).
   Saída: data/processed/presidente_municipio_2022.csv, com as mesmas colunas de
   presidente_municipio_2026.csv (cd_tse, aptos, comparecimento, abstencao,
   brancos, nulos, validos, c13, c22, outros).

2. Perfil municipal do Censo 2022 (IBGE SIDRA, API v3): renda média, população,
   % urbano, % evangélicos, % pretos e pardos, % sem instrução/fundamental
   incompleto e % com superior. Os JSON ficam em data/raw/ibge_*.json.
   Saída: data/processed/ibge_municipio_2022.csv, por código IBGE de 7 dígitos.

Uso (na raiz de elections/):
    .venv/bin/python src/prepare_segundo_turno.py
"""
import io
import json
import time
import urllib.request
import zipfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed"
CDN = "https://cdn.tse.jus.br/estatistica/sead/odsele"
SIDRA = "https://servicodados.ibge.gov.br/api/v3/agregados"


def get(url, tries=4):
    for i in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=300) as r:
                return r.read()
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(2 ** i)


def baixar(nome, url):
    path = RAW / nome
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        print("baixando", nome, flush=True)
        path.write_bytes(get(url))
    return path


# ---------------------------------------------------------------- 1. TSE 2022
def ler_brasil(zip_path, cols):
    """Lê o CSV nacional do zip (ou concatena os por UF, se não houver)."""
    with zipfile.ZipFile(zip_path) as z:
        nomes = [n for n in z.namelist() if n.endswith(".csv")]
        br = [n for n in nomes if n.endswith("_BRASIL.csv")]
        partes = []
        for n in br or nomes:
            with z.open(n) as f:
                d = pd.read_csv(io.TextIOWrapper(f, "latin1"), sep=";", usecols=cols, low_memory=False)
            partes.append(d[d.CD_CARGO == 1])
    return pd.concat(partes)


def presidente_2022():
    det = ler_brasil(
        baixar("detalhe_votacao_munzona_2022.zip", f"{CDN}/detalhe_votacao_munzona/detalhe_votacao_munzona_2022.zip"),
        ["NR_TURNO", "SG_UF", "CD_MUNICIPIO", "NM_MUNICIPIO", "CD_CARGO", "QT_APTOS", "QT_COMPARECIMENTO",
         "QT_ABSTENCOES", "QT_VOTOS_BRANCOS", "QT_TOTAL_VOTOS_NULOS", "QT_TOTAL_VOTOS_VALIDOS"])
    chave = ["NR_TURNO", "SG_UF", "CD_MUNICIPIO"]
    det = det.groupby(chave + ["NM_MUNICIPIO"], as_index=False).sum(numeric_only=True)
    det = det.rename(columns={"QT_APTOS": "aptos", "QT_COMPARECIMENTO": "comparecimento",
                              "QT_ABSTENCOES": "abstencao", "QT_VOTOS_BRANCOS": "brancos",
                              "QT_TOTAL_VOTOS_NULOS": "nulos", "QT_TOTAL_VOTOS_VALIDOS": "validos"})

    par = ler_brasil(
        baixar("votacao_partido_munzona_2022.zip", f"{CDN}/votacao_partido_munzona/votacao_partido_munzona_2022.zip"),
        chave + ["CD_CARGO", "NR_PARTIDO", "QT_VOTOS_NOMINAIS_VALIDOS"])
    par["col"] = par.NR_PARTIDO.map({13: "c13", 22: "c22"}).fillna("outros")
    par = par.pivot_table(index=chave, columns="col", values="QT_VOTOS_NOMINAIS_VALIDOS",
                          aggfunc="sum", fill_value=0).reset_index()

    d = det.merge(par, on=chave, how="left").fillna({"c13": 0, "c22": 0, "outros": 0})
    d = d.rename(columns={"NR_TURNO": "turno", "SG_UF": "uf", "CD_MUNICIPIO": "cd_tse", "NM_MUNICIPIO": "municipio"})
    d = d.drop(columns="CD_CARGO")
    for c in ("aptos", "comparecimento", "abstencao", "brancos", "nulos", "validos", "c13", "c22", "outros"):
        d[c] = d[c].astype(int)
    return d.sort_values(["turno", "uf", "cd_tse"])


# ---------------------------------------------------------------- 2. IBGE
# tabela, variável, classificações fixas (as demais em "Total") e a classificação aberta
TABELAS = {
    "renda": (10299, 13502, "2[6794]|629[32385]|58[95253]", None),
    "urbano": (10211, 93, "1[6795,1]|2661[32776]", "1"),
    "religiao": (9537, 140, "133[95278,95277,95263,2836]|2[6794]|58[95253]", "133"),
    "cor": (9605, 93, "86[95251,2776,2777,2779]", "86"),
    "instrucao": (10061, 2667, "1568[120704,9493,99713]|58[95253]|2[6794]|86[95251]", "1568"),
}


def sidra(nome):
    t, var, cls, _ = TABELAS[nome]
    url = f"{SIDRA}/{t}/periodos/2022/variaveis/{var}?localidades=N6[all]&classificacao={cls}"
    return json.loads(baixar(f"ibge_{nome}.json", url).read_text())


def serie(nome):
    """{categoria: {cd_ibge: valor}} para a classificação aberta da tabela."""
    aberta = TABELAS[nome][3]
    out = {}
    for res in sidra(nome)[0]["resultados"]:
        cat = "valor"
        for c in res["classificacoes"]:
            if c["id"] == aberta:
                cat = list(c["categoria"].values())[0]
        out[cat] = {s["localidade"]["id"]: pd.to_numeric(s["serie"]["2022"], errors="coerce")
                    for s in res["series"]}
    return pd.DataFrame(out)


def ibge_2022():
    renda, urb, rel, cor, ins = (serie(n) for n in TABELAS)
    d = pd.DataFrame(index=renda.index)
    d["renda"] = renda["valor"]
    d["pop"] = urb["Total"]
    d["pct_urbano"] = 100 * urb["Urbana"] / urb["Total"]
    d["pct_evang"] = 100 * rel["Evangélicas"] / rel["Total"]
    d["pct_catolico"] = 100 * rel["Católica Apostólica Romana"] / rel["Total"]
    d["pct_sem_religiao"] = 100 * rel["Sem religião"] / rel["Total"]
    d["pct_branca"] = 100 * cor["Branca"] / cor["Total"]
    d["pct_preta_parda"] = 100 * (cor["Preta"] + cor["Parda"]) / cor["Total"]
    d["pct_inst_baixa"] = 100 * ins["Sem instrução e fundamental incompleto"] / ins["Total"]
    d["pct_superior"] = 100 * ins["Superior completo"] / ins["Total"]
    d.index.name = "cd_ibge"
    return d.reset_index()


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    p = presidente_2022()
    p.to_csv(OUT / "presidente_municipio_2022.csv", index=False)
    print("presidente 2022:", p.groupby("turno")[["aptos", "abstencao", "c13", "c22"]].sum().to_string())
    ib = ibge_2022()
    ib.to_csv(OUT / "ibge_municipio_2022.csv", index=False)
    print("ibge:", ib.shape, "| sem renda:", ib.renda.isna().sum())

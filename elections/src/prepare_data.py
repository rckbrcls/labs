"""Agrega os dados públicos (TSE + IBGE) em tabelas pequenas para o notebook.

Entradas (data/raw, baixadas do TSE/IBGE — ver README):
  detalhe_votacao_secao_{2022,2026}_BR.csv      aptos / comparecimento / abstenção por seção
  votacao_secao_{2022,2026}_BR.csv              votos por candidato por seção
  dvm_{2002..2018}.zip                          detalhe por município-zona (série histórica)
  perfil_eleitorado_{2022,2026}_BRASIL.csv      eleitorado por idade x escolaridade
  perfil_comparecimento_abstencao_2022_BRASIL   abstenção 2022 por idade x escolaridade
  ibge_renda.json, ibge_urbano.json             Censo 2022 (SIDRA)

Saídas (data/processed): parquet/csv usados pelo notebook.
"""
import difflib
import json
import re
import unicodedata
import zipfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed"
OUT.mkdir(parents=True, exist_ok=True)
CHUNK = 2_000_000


def read_chunks(path, usecols, **kw):
    return pd.read_csv(path, sep=";", encoding="latin1", usecols=usecols,
                       chunksize=CHUNK, low_memory=False, **kw)


# ---------------------------------------------------------------- 1. comparecimento por zona
def detalhe_zona(year):
    """Presidente, por turno x UF x município x zona."""
    cols = ["NR_TURNO", "SG_UF", "CD_MUNICIPIO", "NM_MUNICIPIO", "NR_ZONA", "DS_CARGO",
            "QT_APTOS", "QT_COMPARECIMENTO", "QT_ABSTENCOES", "QT_VOTOS_BRANCOS", "QT_VOTOS_NULOS"]
    parts = []
    for ch in read_chunks(RAW / f"detalhe_votacao_secao_{year}_BR.csv", cols):
        ch = ch[ch.DS_CARGO.str.upper() == "PRESIDENTE"]
        parts.append(ch.groupby(["NR_TURNO", "SG_UF", "CD_MUNICIPIO", "NM_MUNICIPIO", "NR_ZONA"],
                                as_index=False)[["QT_APTOS", "QT_COMPARECIMENTO", "QT_ABSTENCOES",
                                                 "QT_VOTOS_BRANCOS", "QT_VOTOS_NULOS"]].sum())
    d = pd.concat(parts).groupby(["NR_TURNO", "SG_UF", "CD_MUNICIPIO", "NM_MUNICIPIO", "NR_ZONA"],
                                 as_index=False).sum()
    d.insert(0, "ano", year)
    return d


# ---------------------------------------------------------------- 2. votos por candidato por zona
def votos_zona(year):
    """Lula (13), candidato do PL (22: Bolsonaro 2022 / Flávio 2026), outros, brancos, nulos."""
    cols = ["NR_TURNO", "SG_UF", "CD_MUNICIPIO", "NR_ZONA", "DS_CARGO", "NR_VOTAVEL", "QT_VOTOS"]
    parts = []
    for ch in read_chunks(RAW / f"votacao_secao_{year}_BR.csv", cols):
        ch = ch[ch.DS_CARGO.str.upper() == "PRESIDENTE"].copy()
        ch["grupo"] = ch.NR_VOTAVEL.map({13: "lula", 22: "pl", 95: "branco", 96: "nulo"}).fillna("outros")
        parts.append(ch.groupby(["NR_TURNO", "SG_UF", "CD_MUNICIPIO", "NR_ZONA", "grupo"],
                                as_index=False).QT_VOTOS.sum())
    v = (pd.concat(parts).groupby(["NR_TURNO", "SG_UF", "CD_MUNICIPIO", "NR_ZONA", "grupo"])
         .QT_VOTOS.sum().unstack("grupo", fill_value=0).reset_index())
    v.insert(0, "ano", year)
    return v


# ---------------------------------------------------------------- 3. série histórica nacional
def serie_historica():
    rows = []
    for y in (2002, 2006, 2010, 2014, 2018):
        with zipfile.ZipFile(RAW / f"dvm_{y}.zip") as z:
            name = [n for n in z.namelist() if n.endswith(("_BRASIL.csv", "_BR.csv"))]
            name = sorted(name, key=lambda n: "BRASIL" not in n)[0]
            with z.open(name) as f:
                d = pd.read_csv(f, sep=";", encoding="latin1", low_memory=False,
                                usecols=["NR_TURNO", "SG_UF", "DS_CARGO", "QT_APTOS", "QT_COMPARECIMENTO",
                                         "QT_ABSTENCOES", "ST_VOTO_EM_TRANSITO"])
        d = d[(d.DS_CARGO.str.upper() == "PRESIDENTE") & (d.ST_VOTO_EM_TRANSITO == "N")]
        for t, g in d.groupby("NR_TURNO"):
            rows.append(dict(ano=y, turno=t, aptos=g.QT_APTOS.sum(), comp=g.QT_COMPARECIMENTO.sum(),
                             abst=g.QT_ABSTENCOES.sum(),
                             aptos_ext=g[g.SG_UF == "ZZ"].QT_APTOS.sum(),
                             abst_ext=g[g.SG_UF == "ZZ"].QT_ABSTENCOES.sum()))
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- 4. perfil do eleitorado
def faixa(s):
    """Agrupa a faixa etária do TSE em categorias que importam para o voto facultativo."""
    n = pd.to_numeric(s.str.extract(r"^(\d+)")[0], errors="coerce")
    out = pd.Series("Inválido", index=s.index)
    out[n.between(16, 17)] = "16-17"
    out[n.between(18, 24)] = "18-24"
    out[n.between(25, 44)] = "25-44"
    out[n.between(45, 59)] = "45-59"
    out[n.between(60, 69)] = "60-69"
    out[n >= 70] = "70+"
    return out


def escol(s):
    s = s.str.upper()
    out = pd.Series("Médio", index=s.index)
    out[s.str.contains("ANALFABETO")] = "Analfabeto"
    out[s.str.contains("LÊ E ESCREVE")] = "Lê/escreve"
    out[s.str.contains("FUNDAMENTAL")] = "Fundamental"
    out[s.str.contains("SUPERIOR")] = "Superior"
    out[s.str.contains("NÃO INFORMADO")] = "Não inform."
    return out


def perfil_eleitorado(year):
    cols = ["SG_UF", "CD_MUNICIPIO", "DS_FAIXA_ETARIA", "DS_GRAU_ESCOLARIDADE", "QT_ELEITORES",
            "QT_ELEITORES_BIOMETRIA"]
    parts = []
    for ch in read_chunks(RAW / f"perfil_eleitorado_{year}_BRASIL.csv", cols):
        ch["faixa"] = faixa(ch.DS_FAIXA_ETARIA)
        ch["escol"] = escol(ch.DS_GRAU_ESCOLARIDADE)
        parts.append(ch.groupby(["SG_UF", "CD_MUNICIPIO", "faixa", "escol"], as_index=False)
                     [["QT_ELEITORES", "QT_ELEITORES_BIOMETRIA"]].sum())
    d = pd.concat(parts).groupby(["SG_UF", "CD_MUNICIPIO", "faixa", "escol"], as_index=False).sum()
    d["CD_MUNICIPIO"] = d.CD_MUNICIPIO.astype(int)
    d.insert(0, "ano", year)
    return d


def perfil_abstencao_2022():
    num = ["QT_APTOS", "QT_ABSTENCAO", "QT_COMPAREC_FACULTATIVO", "QT_ABST_FACULTATIVO",
           "QT_COMPAREC_OBRIGATORIO", "QT_ABST_OBRIGATORIO"]
    cols = ["NR_TURNO", "SG_UF", "CD_MUNICIPIO", "DS_FAIXA_ETARIA", "DS_GRAU_ESCOLARIDADE"] + num
    parts = []
    for ch in read_chunks(RAW / "perfil_comparecimento_abstencao_2022_BRASIL.csv", cols):
        ch = ch[ch.NR_TURNO == 1].copy()
        ch["faixa"] = faixa(ch.DS_FAIXA_ETARIA)
        ch["escol"] = escol(ch.DS_GRAU_ESCOLARIDADE)
        parts.append(ch.groupby(["SG_UF", "faixa", "escol"], as_index=False)[num].sum())
    return pd.concat(parts).groupby(["SG_UF", "faixa", "escol"], as_index=False).sum()


# ---------------------------------------------------------------- 5. IBGE (renda, urbanização)
def norm(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().upper()
    return re.sub(r"[^A-Z0-9]", "", s)


def ibge(tse_mun):
    """Casa município TSE <-> IBGE por UF + nome normalizado (com fuzzy para sobras)."""
    def series(fname):
        res = json.load(open(RAW / fname))[0]["resultados"]
        return res
    renda = {r["series"][0]["localidade"]["id"]: r["series"] for r in series("ibge_renda.json")}
    rows = {}
    for s in series("ibge_renda.json")[0]["series"]:
        loc = s["localidade"]
        nome, uf = loc["nome"].rsplit(" - ", 1)
        rows[loc["id"]] = dict(cd_ibge=loc["id"], uf=uf, nome=nome,
                               renda=pd.to_numeric(s["serie"]["2022"], errors="coerce"))
    for res in series("ibge_urbano.json"):
        cat = list(res["classificacoes"][0]["categoria"].values())[0]
        col = {"Total": "pop", "Urbana": "pop_urb", "Rural": "pop_rur"}[cat]
        for s in res["series"]:
            rows[s["localidade"]["id"]][col] = pd.to_numeric(s["serie"]["2022"], errors="coerce")
    ib = pd.DataFrame(rows.values())
    ib["pct_urbano"] = 100 * ib.pop_urb / ib["pop"]
    ib["key"] = ib.uf + "|" + ib.nome.map(norm)

    tse = tse_mun.drop_duplicates("CD_MUNICIPIO").copy()
    tse["key"] = tse.SG_UF + "|" + tse.NM_MUNICIPIO.map(norm)
    m = tse.merge(ib.drop(columns=["uf", "nome"]), on="key", how="left")
    # fuzzy para os que sobraram, dentro da mesma UF
    miss = m[m.cd_ibge.isna()]
    ib_by_uf = {uf: g for uf, g in ib.groupby("uf")}
    for i, r in miss.iterrows():
        g = ib_by_uf.get(r.SG_UF)
        if g is None:
            continue
        cand = difflib.get_close_matches(r.key, g.key.tolist(), n=1, cutoff=0.88)
        if cand:
            hit = g[g.key == cand[0]].iloc[0]
            for c in ("cd_ibge", "renda", "pop", "pop_urb", "pop_rur", "pct_urbano"):
                m.loc[i, c] = hit[c]
    print(f"IBGE: casados {m.cd_ibge.notna().sum()} de {len(m)} municípios TSE")
    return m[["CD_MUNICIPIO", "cd_ibge", "renda", "pop", "pct_urbano"]]


# ---------------------------------------------------------------- main
if __name__ == "__main__":
    print("série histórica ..."); h = serie_historica(); h.to_csv(OUT / "serie_historica.csv", index=False)

    z_det = pd.concat([detalhe_zona(2022), detalhe_zona(2026)])
    z_vot = pd.concat([votos_zona(2022), votos_zona(2026)])
    z = z_det.merge(z_vot, on=["ano", "NR_TURNO", "SG_UF", "CD_MUNICIPIO", "NR_ZONA"], how="outer")
    z.to_parquet(OUT / "zona.parquet", index=False)
    print("zona:", z.shape)

    print("perfil eleitorado ...")
    pd.concat([perfil_eleitorado(2022), perfil_eleitorado(2026)]).to_parquet(OUT / "perfil_eleitorado.parquet", index=False)
    print("perfil abstenção 2022 ...")
    perfil_abstencao_2022().to_parquet(OUT / "perfil_abstencao_2022.parquet", index=False)

    print("ibge ...")
    mun = z[["CD_MUNICIPIO", "SG_UF", "NM_MUNICIPIO"]].dropna().query("SG_UF != 'ZZ'")
    ibge(mun).to_parquet(OUT / "ibge_municipio.parquet", index=False)
    print("ok")

"""Exporta os números que alimentam os gráficos do relatório "Electoral Psychosis".

Executa as células de código dos três notebooks (com backend sem tela) e extrai
as tabelas que eles já calculam. Nada é recalculado por fora: se o notebook
mudar, o JSON muda. Saída: JSON em stdout ou no caminho passado como argumento.

Uso (na raiz de elections/):
    .venv/bin/python src/export_labs_data.py /caminho/saida.json
"""
import json
import re
import sys
import warnings
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
warnings.filterwarnings("ignore")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def run_notebook(name: str) -> dict:
    """Executa todas as células de código num namespace e o devolve.

    `name` é relativo à raiz (ex.: "primeiro-turno/analise_abstencao_2026"); o
    notebook roda de dentro da própria pasta, como no Jupyter.
    """
    import os

    path = ROOT / f"{name}.ipynb"
    nb = json.loads(path.read_text())
    os.chdir(path.parent)
    ns: dict = {"__name__": "__main__"}
    for cell in nb["cells"]:
        if cell["cell_type"] != "code":
            continue
        src = "".join(cell["source"])
        src = "\n".join(l for l in src.split("\n") if not l.lstrip().startswith(("%", "!")))
        exec(compile(src, f"{name}", "exec"), ns)
    return ns


def r(x, n=2):
    return None if pd.isna(x) else round(float(x), n)


def main() -> dict:
    out: dict = {}

    # ---------------------------------------------------------------- abstenção
    a = run_notebook("primeiro-turno/analise_abstencao_2026")
    serie = a["serie"].set_index("ano").abst_pct
    out["abstentionSeries"] = [{"year": str(int(y)), "abstention": r(v)} for y, v in serie.items()]

    dec = a["dec"]
    out["decileDeltas"] = [
        {
            "decile": str(int(k)),
            "abstention": r(row["Δ abstenção (p.p.)"]),
            "lula": r(row["Δ Lula (p.p. válidos)"]),
            "right": r(row["Δ Flávio vs Bolsonaro (p.p. válidos)"]),
        }
        for k, row in dec.iterrows()
    ]

    acc = a["acc"]
    d = acc["Δ"].drop("Eleitores aptos") / 1e6
    keys = {
        "Lula": "lula",
        "PL (Bolsonaro → Flávio)": "right",
        "Outros candidatos": "others",
        "Brancos + nulos": "blank",
        "Abstenções": "abstention",
    }
    out["nationalAccounts"] = {keys[k]: r(v) for k, v in d.items()}
    out["electorateGrowth"] = r(acc.loc["Eleitores aptos", "Δ"] / 1e6)

    pa = a["pa"]
    ages = ["16-17", "18-24", "25-44", "45-59", "60-69", "70+"]
    g = pa[pa.faixa.isin(ages)].groupby("faixa")[["QT_APTOS", "QT_ABSTENCAO"]].sum().loc[ages]
    out["abstentionByAge"] = [
        {"group": k, "abstention": r(100 * v.QT_ABSTENCAO / v.QT_APTOS, 1)} for k, v in g.iterrows()
    ]

    out["counterfactual"] = {"margin": int(a["margem"]), "extraAbstentions": int(a["extra"])}
    xs = a["xs"]
    out["ageShiftVsAbstention"] = [
        {"shift70": r(row.dp70), "abstention": r(row.dabst)} for _, row in xs.iterrows()
    ]

    # ------------------------------------------------------------ pobre de direita
    p = run_notebook("primeiro-turno/analise_pobre_de_direita")
    pres, d_all, wfn = p["pres"], p["d"], p["w"]

    left_q = pres.groupby(["ano", "q"]).apply(lambda x: wfn(x, "esq")).unstack("q")
    out["leftByQuintile"] = [
        {"year": str(int(y)), **{f"q{q}": r(row[q], 1) for q in range(1, 6)}}
        for y, row in left_q.iterrows()
    ]

    y26 = pres[pres.ano == 2026]
    reg_names = {"Norte": "north", "Nordeste": "northeast", "Centro-Oeste": "midwest", "Sudeste": "southeast", "Sul": "south"}
    cell = y26.groupby(["q", "reg"]).apply(
        lambda x: pd.Series({"dir": wfn(x, "dir"), "mi": x.tot.sum() / 1e6})
    )
    rows = []
    for q in range(1, 6):
        row = {"quintile": f"Q{q}"}
        for reg, key in reg_names.items():
            if (q, reg) in cell.index and cell.loc[(q, reg), "mi"] > 0.3:
                row[key] = r(cell.loc[(q, reg), "dir"], 1)
            else:
                row[key] = None
        rows.append(row)
    out["rightByRegion2026"] = rows

    offices = ["presidente", "governador", "senador", "dep_federal", "dep_estadual"]
    out["rightByOffice"] = {}
    for year in (2022, 2026):
        t = d_all[d_all.ano == year].groupby(["cargo", "q"]).apply(lambda x: wfn(x, "dir")).unstack("q")
        out["rightByOffice"][str(year)] = [
            {"office": c, "q1": r(t.loc[c, 1], 1), "q5": r(t.loc[c, 5], 1)} for c in offices
        ]

    coef = p["coef"]
    labels = {
        "renda (log)": "income",
        "% pretos e pardos": "black_mixed",
        "% evangélicos": "evangelical",
        "% instrução baixa": "low_education",
        "% urbano": "urban",
    }
    out["leftPredictors"] = [
        {"year": str(int(y)), **{labels[k]: r(coef.loc[k, y], 1) for k in coef.index}}
        for y in coef.columns
    ]

    comp = p["comp"]
    out["voteOriginByQuintile"] = [
        {
            "quintile": f"Q{int(q)}",
            "left": r(row["esquerda"], 1),
            "right": r(row["direita"], 1),
            "electorate": r(row["eleitorado"], 1),
        }
        for q, row in comp.iterrows()
    ]

    # ------------------------------------------------------------------- virada
    v = run_notebook("primeiro-turno/analise_virada_direita")
    nat = v["nat"]
    pres_nat = nat.loc["presidente"]
    out["nationalBlocsPresident"] = [
        {"year": str(int(y)), "left": r(row.esquerda, 1), "center": r(row.centro, 1), "right": r(row.direita, 1)}
        for y, row in pres_nat.iterrows()
    ]

    ev = v["ev"]
    out["historicLeftEvolution"] = [
        {
            "year": str(int(y)),
            "left": r(row["% votos na esquerda"], 1),
            "center": r(row["% votos no centro"], 1),
            "right": r(row["% votos na direita"], 1),
            "munisRightAhead": r(row["% municípios com direita à frente"], 1),
        }
        for y, row in ev.iterrows()
    ]

    base, h = v["base"], v["h"]
    out["flipSummary"] = {
        "historicMunicipalities": int(base.historica.sum()),
        "flipped2026": int(h.virou26.sum()),
        "byFirstFlip": {k: int(n) for k, n in h[h.virou26].primeira_virada.value_counts().items()},
    }

    t = v["tabela"](h, "uf").sort_values("% municípios", ascending=False)
    out["flipByState"] = [
        {"state": u, "share": r(row["% municípios"], 1), "flipped": int(row.virou_2026), "total": int(row["municípios"])}
        for u, row in t.iterrows()
    ]

    # sensibilidade: centro conta como direita
    Ee, T, E = v["Ee"], v["T"], v["E"]
    hist_a = v["hist_a"]
    out["sensitivity"] = {
        "main": int(h.virou26.sum()),
        "broad": int((Ee[2026] <= 0.5)[v["hist"]].sum()),
    }

    # títulos no nome de urna (deputado federal)
    part = v["partilha"]
    out["ballotTitles"] = {
        ideo: [
            {"year": str(int(y)), "security": r(row["segurança / militar"], 1), "religious": r(row["religioso"], 1)}
            for y, row in part(ideo).iterrows()
        ]
        for ideo in ("direita", "esquerda")
    }

    return out


if __name__ == "__main__":
    dest = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else None
    data = main()
    text = json.dumps(data, ensure_ascii=False, indent=1)
    if dest:
        dest.write_text(text)
        print("wrote", sys.argv[1], len(text), "bytes")
    else:
        print(text)

"""Agrega votos por cargo (2002–2026) e perfil extra do IBGE para o notebook de viradas.

Entradas (data/raw, ver README):
  vcm_{ano}/votacao_candidato_munzona_{ano}_BRASIL.csv   votos nominais por candidato x município x zona
  cc_{ano}/consulta_cand_{ano}_BRASIL.csv                perfil dos candidatos
  ibge_religiao.json, ibge_cor.json, ibge_instrucao.json Censo 2022 (SIDRA 9537, 9605, 10061)

Saídas (data/processed):
  votos_partido_municipio.parquet  ano x turno x cargo x UF x município x partido -> votos nominais
  votos_candidato_uf.parquet       ano x turno x cargo x UF x candidato -> votos (para perfil de candidatos)
  candidatos.parquet               SQ_CANDIDATO -> ocupação, instrução, gênero, cor/raça
  ibge_perfil_extra.parquet        % evangélicos, católicos, sem religião, cor, instrução (por cd_ibge)
  municipios_tse.parquet           CD_MUNICIPIO TSE -> UF, nome (para casar com o IBGE)
"""
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from prepare_data import CHUNK, OUT, RAW, ibge, read_chunks  # noqa: E402

YEARS = (2002, 2006, 2010, 2014, 2018, 2022, 2026)
CARGOS = {"PRESIDENTE": "presidente", "GOVERNADOR": "governador", "SENADOR": "senador",
          "DEPUTADO FEDERAL": "dep_federal", "DEPUTADO ESTADUAL": "dep_estadual",
          "DEPUTADO DISTRITAL": "dep_estadual"}


def votos(year):
    cols = ["NR_TURNO", "SG_UF", "CD_MUNICIPIO", "NM_MUNICIPIO", "DS_CARGO", "SQ_CANDIDATO",
            "NM_URNA_CANDIDATO", "SG_PARTIDO", "QT_VOTOS_NOMINAIS"]
    mun, cand = [], []
    for ch in read_chunks(RAW / f"vcm_{year}" / f"votacao_candidato_munzona_{year}_BRASIL.csv", cols):
        ch = ch[ch.SG_UF != "ZZ"].copy()
        ch["cargo"] = ch.DS_CARGO.str.upper().map(CARGOS)
        ch = ch[ch.cargo.notna()]
        mun.append(ch.groupby(["NR_TURNO", "cargo", "SG_UF", "CD_MUNICIPIO", "SG_PARTIDO"],
                              as_index=False).QT_VOTOS_NOMINAIS.sum())
        cand.append(ch.groupby(["NR_TURNO", "cargo", "SG_UF", "SQ_CANDIDATO", "NM_URNA_CANDIDATO",
                                "SG_PARTIDO"], as_index=False).QT_VOTOS_NOMINAIS.sum())
    keys_m = ["NR_TURNO", "cargo", "SG_UF", "CD_MUNICIPIO", "SG_PARTIDO"]
    keys_c = ["NR_TURNO", "cargo", "SG_UF", "SQ_CANDIDATO", "NM_URNA_CANDIDATO", "SG_PARTIDO"]
    m = pd.concat(mun).groupby(keys_m, as_index=False).QT_VOTOS_NOMINAIS.sum()
    c = pd.concat(cand).groupby(keys_c, as_index=False).QT_VOTOS_NOMINAIS.sum()
    m.insert(0, "ano", year)
    c.insert(0, "ano", year)
    return m, c


def presidente_2026():
    """O arquivo munzona de 2026 não traz Presidente; usa votacao_secao_2026 + partido via consulta_cand."""
    cand = pd.read_csv(RAW / "cc_2026" / "consulta_cand_2026_BRASIL.csv", sep=";", encoding="latin1",
                       usecols=["DS_CARGO", "NR_CANDIDATO", "SG_PARTIDO"])
    cand = cand[cand.DS_CARGO.str.upper() == "PRESIDENTE"].drop_duplicates("NR_CANDIDATO")
    party = dict(zip(cand.NR_CANDIDATO, cand.SG_PARTIDO))
    cols = ["NR_TURNO", "SG_UF", "CD_MUNICIPIO", "DS_CARGO", "NR_VOTAVEL", "QT_VOTOS"]
    parts = []
    for ch in read_chunks(RAW / "votacao_secao_2026_BR.csv", cols):
        ch = ch[(ch.DS_CARGO.str.upper() == "PRESIDENTE") & (ch.SG_UF != "ZZ")].copy()
        ch["SG_PARTIDO"] = ch.NR_VOTAVEL.map(party)
        ch = ch[ch.SG_PARTIDO.notna()]
        parts.append(ch.groupby(["NR_TURNO", "SG_UF", "CD_MUNICIPIO", "SG_PARTIDO"],
                                as_index=False).QT_VOTOS.sum())
    d = (pd.concat(parts).groupby(["NR_TURNO", "SG_UF", "CD_MUNICIPIO", "SG_PARTIDO"], as_index=False)
         .QT_VOTOS.sum().rename(columns={"QT_VOTOS": "QT_VOTOS_NOMINAIS"}))
    d.insert(0, "cargo", "presidente")
    d.insert(0, "ano", 2026)
    return d[["ano", "NR_TURNO", "cargo", "SG_UF", "CD_MUNICIPIO", "SG_PARTIDO", "QT_VOTOS_NOMINAIS"]]


def candidatos(year):
    cols = ["SQ_CANDIDATO", "DS_CARGO", "SG_PARTIDO", "DS_GENERO", "DS_GRAU_INSTRUCAO",
            "DS_COR_RACA", "DS_OCUPACAO", "DS_SIT_TOT_TURNO"]
    d = pd.read_csv(RAW / f"cc_{year}" / f"consulta_cand_{year}_BRASIL.csv", sep=";",
                    encoding="latin1", usecols=cols, low_memory=False)
    d.insert(0, "ano", year)
    return d


def ibge_extra():
    def load(fname, cats):
        out = {}
        for res in json.load(open(RAW / fname))[0]["resultados"]:
            cat = list(res["classificacoes"][0]["categoria"].values())[0]
            for s in res["series"]:
                out.setdefault(s["localidade"]["id"], {})[cats[cat]] = pd.to_numeric(
                    s["serie"]["2022"], errors="coerce")
        return pd.DataFrame.from_dict(out, orient="index")
    rel = load("ibge_religiao.json", {"Total": "rel_tot", "Evangélicas": "rel_evang",
                                      "Católica Apostólica Romana": "rel_cat", "Sem religião": "rel_sem"})
    cor = load("ibge_cor.json", {"Total": "cor_tot", "Branca": "cor_branca", "Preta": "cor_preta",
                                 "Parda": "cor_parda"})
    ins = load("ibge_instrucao.json", {"Total": "ins_tot", "Sem instrução e fundamental incompleto": "ins_baixa",
                                       "Superior completo": "ins_superior"})
    d = rel.join(cor).join(ins)
    out = pd.DataFrame(index=d.index)
    out["pct_evang"] = 100 * d.rel_evang / d.rel_tot
    out["pct_catolico"] = 100 * d.rel_cat / d.rel_tot
    out["pct_sem_religiao"] = 100 * d.rel_sem / d.rel_tot
    out["pct_branca"] = 100 * d.cor_branca / d.cor_tot
    out["pct_preta_parda"] = 100 * (d.cor_preta + d.cor_parda) / d.cor_tot
    out["pct_inst_baixa"] = 100 * d.ins_baixa / d.ins_tot
    out["pct_superior"] = 100 * d.ins_superior / d.ins_tot
    out.index.name = "cd_ibge"
    return out.reset_index()


if __name__ == "__main__":
    ms, cs = [], []
    for y in YEARS:
        print("votos", y, "...", flush=True)
        m, c = votos(y)
        ms.append(m); cs.append(c)
        print("  linhas:", len(m), len(c), flush=True)
    print("presidente 2026 ...", flush=True)
    ms.append(presidente_2026())
    vm = pd.concat(ms); vm.to_parquet(OUT / "votos_partido_municipio.parquet", index=False)
    pd.concat(cs).to_parquet(OUT / "votos_candidato_uf.parquet", index=False)
    print("candidatos ...")
    pd.concat([candidatos(y) for y in YEARS]).to_parquet(OUT / "candidatos.parquet", index=False)

    # município TSE -> UF/nome e casamento com IBGE
    names = pd.read_csv(RAW / "vcm_2026" / "votacao_candidato_munzona_2026_BRASIL.csv", sep=";", encoding="latin1",
                        usecols=["SG_UF", "CD_MUNICIPIO", "NM_MUNICIPIO"]).drop_duplicates()
    names = names[names.SG_UF != "ZZ"]
    names.to_parquet(OUT / "municipios_tse.parquet", index=False)
    cod = ibge(names)  # CD_MUNICIPIO, cd_ibge, renda, pop, pct_urbano
    ex = ibge_extra()
    ex["cd_ibge"] = ex.cd_ibge.astype(str)
    cod["cd_ibge"] = cod.cd_ibge.astype("string")
    cod.merge(ex, on="cd_ibge", how="left").to_parquet(OUT / "ibge_perfil_extra.parquet", index=False)
    print("ok")

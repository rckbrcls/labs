"""Amostra de logs de urna para medir o voto depois das 17h (Brasília).

Em 25/10/2026, às 17h03, o STF (Rcl 101.673, rel. Zanin) estendeu o segundo
turno até as 19h de Brasília nas seções ainda abertas. O boletim de urna do
segundo turno ainda não foi publicado e os logs completos passam de 80 GB, mas o
portal de resultados do TSE expõe o log de cada urna (log.jez). Cada voto vira a
linha "O voto do eleitor foi computado", com o horário local da urna.

O script sorteia uma amostra estratificada por UF das seções do segundo turno
(pleito 3221), baixa o log da mesma seção também no primeiro turno (pleito 3220,
a linha de base: lá a votação terminou às 17h e só votou depois quem já estava
na fila) e guarda, por seção e turno, a contagem de votos por faixa de horário.
O log bruto não é guardado.

Saída: data/processed/amostra_logs_urna.csv (uma linha por seção e turno) e
data/processed/amostra_logs_urna_estratos.csv (seções por UF, para expandir).

Uso (na raiz de elections/):
    .venv/bin/python src/amostra_logs_urna.py [n_secoes]   # padrão 6000
"""
import io
import json
import random
import sys
import time
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "processed"
CACHE = ROOT / "data" / "raw" / "logs_urna.jsonl"
BASE = "https://resultados.tse.jus.br/oficial/ele2026/arquivo-urna"
PLEITOS = {1: ("3220", "04/10/2026"), 2: ("3221", "25/10/2026")}
UFS = ("ac al am ap ba ce df es go ma mg ms mt pa pb pe pi pr rj rn ro rr rs sc se sp to").split()
# faixas de 5 minutos entre 16h e 19h30 de Brasília
INICIO, PASSO, N_FAIXAS = 16 * 60, 5, 42
SEED = 2026


def get(url, tries=5):
    for i in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(2 ** i)
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(2 ** i)
    return None


def secoes_uf(uf):
    d = json.loads(get(f"{BASE}/3221/config/{uf}/{uf}-p003221-cs.json"))
    return [(uf, m["cd"], z["cd"], s["ns"]) for m in d["abr"][0]["mu"] for z in m["zon"] for s in z["sec"]]


def fusos():
    """Diferença Brasília − hora local por município (do boletim do 1º turno)."""
    s = pd.read_csv(OUT / "secao_presidente_1t.csv", usecols=["SG_UF", "CD_MUNICIPIO", "fuso_h"])
    s = s[s.SG_UF != "ZZ"].groupby(["SG_UF", "CD_MUNICIPIO"]).fuso_h.median()
    return {(uf.lower(), int(mun)): f for (uf, mun), f in s.items()}


def ler_log(blob, data):
    """Horários dos votos e do encerramento na data da eleição (hora local)."""
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        txt = z.read("logd.dat").decode("latin1")
    votos, encerra = [], None
    for linha in txt.splitlines():
        if not linha.startswith(data):
            continue
        c = linha.split("\t")
        if len(c) < 5:
            continue
        if c[4] == "O voto do eleitor foi computado":
            votos.append(c[0][11:19])
        elif c[4] == "Procedimento de encerramento confirmado":
            encerra = c[0][11:19]
    return votos, encerra


def processar(sec, turno, fuso):
    uf, mun, zona, ns = sec
    pleito, data = PLEITOS[turno]
    base = f"{BASE}/{pleito}/dados/{uf}/{mun}/{zona}/{ns}"
    row = {"uf": uf.upper(), "cd_tse": int(mun), "zona": int(zona), "secao": int(ns), "turno": turno, "ok": False}
    aux = get(f"{base}/p00{pleito}-{uf}-m{mun}-z{zona}-s{ns}-aux.json")
    if not aux:
        return row
    aux = json.loads(aux)
    arq = [(h["hash"], a["nm"]) for h in aux.get("hashes", []) for a in h["arq"] if a["tp"] == "log"]
    if not arq:
        return row
    blob = get(f"{base}/{arq[-1][0]}/{arq[-1][1]}")
    if not blob:
        return row
    votos, encerra = ler_log(blob, data)
    bsb = lambda h: datetime.strptime(h, "%H:%M:%S") + timedelta(hours=fuso)
    faixas = [0] * N_FAIXAS
    for v in votos:
        t = bsb(v)
        m = t.hour * 60 + t.minute - INICIO
        if 0 <= m < N_FAIXAS * PASSO:
            faixas[m // PASSO] += 1
    ts = sorted(bsb(v) for v in votos)
    row.update(ok=True, fuso_h=fuso, votos=len(votos),
               ultimo_voto_bsb=ts[-1].strftime("%H:%M:%S") if ts else None,
               encerramento_bsb=bsb(encerra).strftime("%H:%M:%S") if encerra else None,
               faixas=" ".join(map(str, faixas)))
    return row


def amostra(n):
    with ThreadPoolExecutor(8) as ex:
        todas = [s for lst in ex.map(secoes_uf, UFS) for s in lst]
    estratos = pd.Series([s[0].upper() for s in todas]).value_counts().rename_axis("uf").rename("secoes")
    rng = random.Random(SEED)
    por_uf = {}
    for s in todas:
        por_uf.setdefault(s[0], []).append(s)
    sorteio = []
    for uf, lst in sorted(por_uf.items()):
        k = min(len(lst), max(80, round(n * len(lst) / len(todas))))
        sorteio += rng.sample(lst, k)
    return sorteio, estratos.reset_index()


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 6000
    sorteio, estratos = amostra(n)
    estratos.to_csv(OUT / "amostra_logs_urna_estratos.csv", index=False)
    fz = fusos()
    feitos = set()
    if CACHE.exists():
        for l in CACHE.read_text().splitlines():
            r = json.loads(l)
            feitos.add((r["uf"].lower(), r["cd_tse"], r["zona"], r["secao"], r["turno"]))
    tarefas = [(s, t) for s in sorteio for t in (1, 2)
               if (s[0], int(s[1]), int(s[2]), int(s[3]), t) not in feitos]
    print(f"{len(sorteio)} seções sorteadas, {len(tarefas)} logs a baixar", flush=True)
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE, "a") as f, ThreadPoolExecutor(16) as ex:
        futs = [ex.submit(processar, s, t, fz.get((s[0], int(s[1])), 0.0)) for s, t in tarefas]
        for i, fu in enumerate(as_completed(futs), 1):
            try:
                f.write(json.dumps(fu.result()) + "\n")
            except Exception as e:
                print("erro:", e, flush=True)
            if i % 500 == 0:
                f.flush()
                print(i, flush=True)
    sel = {(s[0].upper(), int(s[1]), int(s[2]), int(s[3])) for s in sorteio}
    d = pd.read_json(CACHE, lines=True)
    d = d[[k in sel for k in zip(d.uf, d.cd_tse, d.zona, d.secao)]]
    d = d.drop_duplicates(["uf", "cd_tse", "zona", "secao", "turno"], keep="last")
    d.sort_values(["uf", "cd_tse", "zona", "secao", "turno"]).to_csv(OUT / "amostra_logs_urna.csv", index=False)
    print(d.groupby("turno").agg(secoes=("ok", "size"), ok=("ok", "sum"), votos=("votos", "sum")).to_string())


if __name__ == "__main__":
    main()

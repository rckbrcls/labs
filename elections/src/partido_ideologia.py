"""Classificação ideológica dos partidos (esquerda / centro / direita) usada no notebook de viradas.

É um julgamento, baseado na posição convencional na literatura de ciência política brasileira
(ex.: pesquisas de survey com cientistas políticos / Bolognesi et al.) e no comportamento em votações.
Partidos que mudaram de sigla (PMDB→MDB, PFL→DEM→UNIÃO, PPB→PP, PRB→REPUBLICANOS, PR→PL, PSL→UNIÃO,
SD→SOLIDARIEDADE, PT do B→AVANTE, PTN→PODE, PMN→MOBILIZA, PC do B→PCDOB) são tratados como o mesmo partido.

O notebook testa uma classificação alternativa ("direita ampliada" = direita + centro) como sensibilidade.
Gera data/processed/partido_ideologia.csv.
"""
from pathlib import Path

import pandas as pd

ESQUERDA = ["PT", "PSB", "PDT", "PSOL", "PC do B", "PCDOB", "PCB", "PSTU", "PCO", "UP", "REDE", "PPL", "PV"]
CENTRO = ["PSDB", "PMDB", "MDB", "PSD", "PODE", "PTN", "SOLIDARIEDADE", "SD", "AVANTE", "PT do B", "PROS",
          "PMN", "MOBILIZA", "PPS", "CIDADANIA", "PHS", "PAN", "PGT", "DEMOCRATA"]
DIREITA = ["PL", "PR", "PSL", "PP", "PPB", "PFL", "DEM", "UNIÃO", "REPUBLICANOS", "PRB", "PSC", "PTB", "NOVO",
           "PRTB", "PRP", "PTC", "PSDC", "DC", "PATRIOTA", "PATRI", "PEN", "PRONA", "PST", "AGIR", "PMB",
           "PRD", "MISSÃO"]

if __name__ == "__main__":
    rows = ([(p, "esquerda") for p in ESQUERDA] + [(p, "centro") for p in CENTRO] +
            [(p, "direita") for p in DIREITA])
    df = pd.DataFrame(rows, columns=["SG_PARTIDO", "ideologia"])
    assert df.SG_PARTIDO.is_unique
    out = Path(__file__).resolve().parents[1] / "data" / "processed" / "partido_ideologia.csv"
    df.to_csv(out, index=False)
    print(df.ideologia.value_counts())

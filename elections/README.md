# elections

Municipal- and section-level analysis of Brazil's 2026 election, using TSE results from 2002 to 2026 and the 2022 IBGE census.

Report: [Where Did the Vote Go?](https://labs.rckbrcls.com/reports/where-did-the-vote-go)

> The notebooks and code comments are written in Portuguese.

## Layout

The notebooks are grouped by round. Every notebook reads from the shared `data/` folder at the root of `elections/` (as `../data/processed/`), so run them from inside their own folder, which is what Jupyter does by default.

```
elections/
  primeiro-turno/    1st round (4 Oct 2026)
  segundo-turno/     2nd round (25 Oct 2026)
  eleicao-inteira/   both rounds compared
  src/               download, preparation and export scripts
  data/              raw/ (not in git) and processed/
```

### `primeiro-turno/`

| Notebook | Question |
|---|---|
| [`analise_abstencao_2026.ipynb`](primeiro-turno/analise_abstencao_2026.ipynb) | Did abstention decide the 2026 first round? |
| [`analise_virada_direita.ipynb`](primeiro-turno/analise_virada_direita.ipynb) | Which historically left municipalities and states moved right (2002–2026, all offices), and what do they look like? |
| [`analise_pobre_de_direita.ipynb`](primeiro-turno/analise_pobre_de_direita.ipynb) | Where is the right strong among poorer municipalities, by income quintile, region, race and religion? |

### `segundo-turno/`

| Notebook | Question |
|---|---|
| [`analise_abstencao_segundo_turno.ipynb`](segundo-turno/analise_abstencao_segundo_turno.ipynb) | Abstention fell 1.9 points between the rounds, a first in the series. Did that decide the runoff? |
| [`analise_pobre_de_direita_segundo_turno.ipynb`](segundo-turno/analise_pobre_de_direita_segundo_turno.ipynb) | How did the income gradient change from the 2022 runoff to the 2026 runoff, and where is the right strong among poorer municipalities? |
| [`analise_horario_votacao.ipynb`](segundo-turno/analise_horario_votacao.ipynb) | How many sections stayed open after 17h, where, and could the late vote have changed the result? |
| [`analise_extensao_stf.ipynb`](segundo-turno/analise_extensao_stf.ipynb) | How many people voted because the STF extended voting to 19h, and how much did it matter for Lula's margin? |

The STF-extension notebook counts votes by the minute from the urn logs of a stratified sample of 6,230 sections, in both rounds, and expands the counts to the country. The voting-hours notebook compares closing times in both rounds section by section. It needs the TSE ballot-box bulletin (`bweb`) for each round. While the 2nd-round file is not published, the notebook runs on the 1st-round baseline only and skips the comparison.

### `eleicao-inteira/`

| Notebook | Question |
|---|---|
| [`analise_virada_segundo_turno.ipynb`](eleicao-inteira/analise_virada_segundo_turno.ipynb) | How did Lula turn a 2.2M-vote first-round deficit against Flávio Bolsonaro into a 4.4M-vote runoff win? |

It covers the national vote accounting, the swing by state, region, municipality size and flipped municipalities, a state fixed-effects regression of the municipal swing, a model-free accounting bound, and two ecological inference specifications (net flows with bootstrap intervals, and a full constrained transfer matrix) compared against each other.

## Scripts

- [`src/prepare_data.py`](src/prepare_data.py): aggregates the raw files for the abstention notebook into `data/processed/`.
- [`src/prepare_data_cargos.py`](src/prepare_data_cargos.py): aggregates votes by office, party and municipality (2002–2026) plus the extra IBGE profile.
- [`src/partido_ideologia.py`](src/partido_ideologia.py): the party classification (see below).
- [`src/download_tse.py`](src/download_tse.py): downloads the presidential result per municipality for both 2026 rounds from the TSE results portal and writes `data/processed/presidente_municipio_2026.csv`.
- [`src/download_bweb.py`](src/download_bweb.py): downloads the ballot-box bulletin for one round (`1` or `2`) and writes one row per section, with the presidential vote and opening and closing times converted to Brasília time, to `data/processed/secao_presidente_{1,2}t.csv`.
- [`src/prepare_segundo_turno.py`](src/prepare_segundo_turno.py): builds the 2022 presidential result by municipality and round (`presidente_municipio_2022.csv`, from two small TSE files) and the 2022 Census profile by municipality (`ibge_municipio_2022.csv`, from the IBGE SIDRA API) for the `segundo-turno/` notebooks.
- [`src/amostra_logs_urna.py`](src/amostra_logs_urna.py): draws a sample of sections stratified by state, downloads each section's urn log for both rounds from the results portal, and writes vote counts in 5-minute bins (16h to 19h30, Brasília time) plus the closing time to `data/processed/amostra_logs_urna.csv`. Raw logs are not kept.
- [`src/export_labs_data.py`](src/export_labs_data.py): runs the notebooks and exports the numbers the report charts use.

## Party classification

Sorting parties into left, center and right is a judgment call, and it changes the results, mostly before 2018 when the center was large. The full list is in [`data/processed/partido_ideologia.csv`](data/processed/partido_ideologia.csv), generated by [`src/partido_ideologia.py`](src/partido_ideologia.py).

- It follows the conventional placement in Brazilian political science (expert surveys such as Bolognesi et al.) and roll-call behavior.
- PSDB, MDB and PSD are in the center.
- Parties that changed names are treated as the same party (PMDB→MDB, PFL→DEM→UNIÃO, PPB→PP, PRB→REPUBLICANOS, PR→PL, and so on).
- The flips notebook reruns the main count with a broader right (right + center) as a sensitivity check.

If you disagree with a placement, change the script, rerun it and the notebooks.

## Caveats

- Everything is an analysis of **municipalities or sections**, not people. "Poor municipalities vote for X" is not "poor people vote for X" (ecological fallacy).
- The census predictors are associations measured in 2022, controlled within each state. They do not establish cause.
- The 2026 `votacao_candidato_munzona` file does not include the presidential race. The 2026 presidential vote comes from `votacao_secao_2026_BR.csv`, with the party matched by candidate number in `consulta_cand_2026` (see `presidente_2026()`).
- In the runoff notebook, the two ecological specifications agree on direction and on finalist loyalty, but not on how to split credit between eliminated candidates' voters and voters leaving blank/null ballots or abstention. The notebook reports the range instead of picking one.
- A section that closed late is not the same as votes cast late. The bulletin has the closing time, not when each vote was cast. The urn logs have that. The full set is more than 80 GB, so the STF-extension notebook uses a sample: its numbers carry 95% intervals, and the voter's choice is not in the log, so the effect on the margin uses the municipal result and an all-for-Lula ceiling.
- Abroad (`ZZ`) is included in the descriptive counts and left out of the models.

## Sources

All public.

**TSE**, under `https://cdn.tse.jus.br/estatistica/sead/odsele/`:

- `detalhe_votacao_secao/detalhe_votacao_secao_{2022,2026}.zip`
- `votacao_secao/votacao_secao_{2022,2026}_BR.zip`
- `detalhe_votacao_munzona/detalhe_votacao_munzona_{2002..2018}.zip`
- `perfil_eleitorado/perfil_eleitorado_{2022,2026}.zip`
- `perfil_comparecimento_abstencao/perfil_comparecimento_abstencao_2022.zip`
- `votacao_candidato_munzona/votacao_candidato_munzona_{2002,...,2026}.zip` (extracted to `data/raw/vcm_{year}/`)
- `consulta_cand/consulta_cand_{2002,...,2026}.zip` (extracted to `data/raw/cc_{year}/`)

**TSE results portal** (`resultados.tse.jus.br`), one JSON per municipality and round for the presidential race: election `6257` (1st round) and `6258` (2nd round). About 11,500 files, cached in `data/raw/{6257,6258}/`.

**TSE results portal, urn files** (`resultados.tse.jus.br/oficial/ele2026/arquivo-urna/{3220,3221}/`): the section list per state (`{uf}-p00{pleito}-cs.json`) and, per section, the index (`-aux.json`) and the urn log (`-log.jez`, a zip with `logd.dat`). Pleito 3220 is the 1st round, 3221 the 2nd.

**TSE open data** (`dadosabertos.tse.jus.br`), dataset `resultados-2026-boletim-de-urna`: `bweb_{1,2}t_{UF}_*.zip`, cached in `data/raw/bweb/`.

**TSE**, for the 2022 runoff comparison: `detalhe_votacao_munzona_2022.zip` and `votacao_partido_munzona_2022.zip` (about 30 MB together).

**IBGE SIDRA**, 2022 Census at municipality level: tables 10299 (income), 10211 (urban/rural population), 9537 (religion), 9605 (race), 10061 (education). Saved as `data/raw/ibge_*.json`.

## Reproduce

The raw files add up to about 30 GB and are not in the repository. Download and extract them into `data/raw/` (see sources), then, from `elections/`:

```bash
python3 -m venv .venv && .venv/bin/pip install pandas matplotlib seaborn jupyter statsmodels pyarrow scipy
.venv/bin/python src/prepare_data.py            # abstention notebook
.venv/bin/python src/prepare_data_cargos.py     # flips and income notebooks (~1 h, reads ~17 GB of CSV)
.venv/bin/python src/partido_ideologia.py
.venv/bin/python src/download_tse.py            # runoff and segundo-turno notebooks
.venv/bin/python src/prepare_segundo_turno.py   # segundo-turno notebooks
.venv/bin/python src/download_bweb.py 1         # voting-hours notebook (and 2, once published)
.venv/bin/python src/amostra_logs_urna.py        # STF-extension notebook (~12,000 logs, ~2 GB downloaded, ~20 min)
for nb in */analise_*.ipynb; do
  .venv/bin/jupyter nbconvert --to notebook --execute --inplace "$nb"
done
```

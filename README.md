# labs

The notebooks, scripts and small data tables behind the reports on [rckbrcls_labs](https://labs.rckbrcls.com).

Each folder is a self-contained experiment with its own data, environment and notebooks. Raw data never goes into git; only the code and the small hand-made tables that a report cites do.

| Experiment | Question | Report |
|---|---|---|
| [`elections/`](elections) | What abstention, income and region do, and don't, explain about Brazil's 2026 election | [Where Did the Vote Go?](https://labs.rckbrcls.com/reports/where-did-the-vote-go) |
| [`ufc/`](ufc) | Not started yet | — |

## How an experiment becomes a report

1. Run the analysis inside the experiment folder.
2. Export the final numbers to JSON (for example, `elections/src/export_labs_data.py`). The exporter runs the notebooks and reads the tables they already compute, so nothing is recalculated on the side.
3. The JSON becomes a typed data file in the labs app, and the report is written in MDX next to it.

## Data

Everything here is built on public data (TSE and IBGE for `elections/`). Each experiment's README lists the exact sources and how to rebuild the processed files.

If you find a mistake, open an issue. I want to know.

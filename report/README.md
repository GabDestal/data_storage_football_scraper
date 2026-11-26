# Report

`report.tex` is the final report (max 5 pages); `report.pdf` is the compiled version.

## Compile locally
```bash
cd report
tectonic -X compile report.tex   # -> report.pdf
```
The figures are read from `../results/figures/`, so run `analysis.py` first if they are missing.

## Edit on Overleaf
1. Create a blank project and upload `report/report.tex` to its root.
2. Create a folder `figures/` and upload the two figures the report uses:
   - `results/figures/a0_example_match.png`
   - `results/figures/a1_trajectory_by_league.png`
3. Compile. The file looks for figures in `../results/figures/` and in `figures/`, so no path needs changing. pdfLaTeX (Overleaf's default) and XeLaTeX both work. It was compiled locally with tectonic (XeTeX); the pdfLaTeX setup is standard but was not run locally.

## Where the numbers come from
Every number comes from `data/clean/quality_summary.json`, the files in `results/` (`summary.txt` and `tables/`), the row counts printed by `store.py`, or `data/raw/scrape_log.csv`. If the data or the analysis changes, update the report from those files, not by hand.

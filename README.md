# Group G – Football ticket resale prices

Charles, Erdem, Chris, Liam, Gabriel

**Question:** how do football ticket resale (asking) prices evolve in the weeks before a match, and what explains the differences between matches? Seat categories are a secondary, descriptive analysis.

**Data:** one snapshot per day of each match page on Ticombo (ticombo.fr), 27.09 → 23.11.2026, for the 100 Premier League and LaLiga matches kicking off 17.10–23.11.2026 (97 found on Ticombo), plus fixtures and results from the football-data.org API. Why we made each choice is explained in `docs/justification.docx`.

| Key numbers | |
|---|---|
| Raw Ticombo pages | 5,463 |
| Match snapshots after parsing | 5,435 (97 matches) |
| Pre-kickoff snapshots | 3,367 (97 matches) |
| Snapshots with a usable price | 3,227 (95 matches) |
| Seat category snapshots | 26,060 (230 labels) |

Details of every cleaning rule and count: `data/clean/quality_summary.json`.

## How to reproduce
The collection can't be repeated (each day's prices are gone the next day), so we keep every raw page and the pipeline reruns from them. Every output below is rebuilt by a script; nothing is edited by hand.

```bash
pip install -r requirements.txt

# 1. get the raw pages (1.06 GB unzipped)
git lfs pull                      # only needed if data/raw/raw_zip_file.zip is a few bytes
cd data/raw && unzip raw_zip_file.zip && cd ../..
#   Windows PowerShell: Expand-Archive data/raw/raw_zip_file.zip -DestinationPath data/raw
#   -> data/raw/ticombo/<date>/*.html

# 2. rebuild everything from the raw data
python parse.py
python clean_data.py
python map_categories.py
python features.py
python store.py
python compare_storage.py         # CSV vs SQLite vs Parquet + DuckDB (Storage section)
python analysis.py
```

The football-data.org files are already in `data/raw/football_data/`, so `get_matches.py` and `get_season_results.py` don't need to be rerun. They need a free API key: `FOOTBALL_DATA_TOKEN=... python get_matches.py`.

## Pipeline
| Step | Script | Reads | Writes |
|---|---|---|---|
| 1 | `get_matches.py` | football-data.org API | `data/reference/matches.csv`, `data/raw/football_data/<date>_{matches,standings}_*.json` |
| 1b | `get_season_results.py` | football-data.org API | `data/raw/football_data/<date>_season_*.json` (all season results, for ranks at kickoff) |
| 2 | `scrape.py` (**done, do not rerun**) | `data/reference/match_urls.csv` | `data/raw/ticombo/<date>/*.html`, `data/raw/scrape_log.csv` |
| 3 | `parse.py` | raw pages, scrape log | `data/events_v0.csv`, `data/categories_v0.csv` |
| 4 | `clean_data.py` | `*_v0.csv`, `matches.csv` | `data/clean/`: every row with flags, pre-match rows, `quality_summary.json` |
| 5 | `map_categories.py` | `categories_v0.csv` | `data/reference/seat_category_map.csv` |
| 6 | `features.py` | `matches.csv`, season results, `derbies.csv` | `data/clean/match_features.csv` |
| 7 | `store.py` | clean data, `matches.csv`, standings, seat map | `football.db` (SQLite, 5 tables) |
| 7b | `compare_storage.py` | `football.db`, clean CSVs | `data/parquet/`, `results/tables/storage_comparison.csv` |
| 8 | `analysis.py` | `football.db`, `match_features.csv` | `results/figures/`, `results/tables/` |

During collection, `scrape.py` ran once a day (cron: `0 11 * * * cd /path/to/project && python3 scrape.py`).

## Main choices
- **Price measure:** the lowest asking price **without fees** (`listing_startPrice`). From 04.11 the platform fee rises from 1.30× to 1.35× for some listings, which would distort trends in the fee-included price. The fee-included price is a robustness check.
- **Rows are flagged, never deleted:** post-kickoff snapshots, days with no listings, inconsistent fees and the top 1% of prices are flags in `data/clean/`. The 21-day window before kickoff is a flag, too.
- **Team rank at kickoff** is rebuilt from official results of matches finished *before* each kickoff. It matches all 6 standings files we saved during collection.
- **Seat groups** (side, behind goal, corner, premium, away) come from keyword rules on the platform's labels, with no stadium-by-stadium manual mapping.
- **Storage:** SQLite with 5 normalised tables and primary/foreign keys, compared with CSV and Parquet + DuckDB.

## Data notes and limitations
- Asking prices only: no transactions or listing IDs. A drop in listed tickets is **supply**, not sales.
- One platform (Ticombo). StubHub and viagogo were rejected because their terms forbid scrapers.
- No snapshot on 03.10; the 06.10 run was interrupted. Snapshot times vary between about 05:00 and 21:00 UTC.
- Seat category rows cover about 37% of listed tickets, so seat results are secondary.
- Two LaLiga matches (564717, 564733) never had listings before kickoff.

## Files
| File | What it is |
|---|---|
| `config.py` | competitions, match window, platform, user-agent, delays |
| `inspect_page.py` | helper used to explore the structure of a Ticombo page |
| `requirements.txt` | Python packages |
| `data/raw/` | everything we downloaded, never modified |
| `data/raw/raw_zip_file.zip` | the 5,463 raw Ticombo pages, zipped (Git LFS). Also on the [`raw-data-v1` release](https://github.com/GabDestal/data_storage_football_scraper/releases/tag/raw-data-v1) |
| `data/raw/football_data/` | fixtures, standings and season results from football-data.org, one dated file per run |
| `data/raw/scrape_log.csv` | every request we made, with its status (success, blocked, error...) |
| `data/raw_sample/` | 4 example pages (one PL and one LaLiga match, at the first scrape and the day before kickoff) |
| `data/events_v0.csv`, `data/categories_v0.csv` | parsed tables: one row per match snapshot / per seat category snapshot |
| `data/clean/` | cleaned tables with flags, pre-match subsets, match features, `quality_summary.json` |
| `data/reference/matches.csv` | the 100 matches: id, league, matchday, kickoff, teams |
| `data/reference/match_urls.csv` | link between each match and its Ticombo page |
| `data/reference/seat_category_map.csv` | seat label → seat group and stand level |
| `data/reference/derbies.csv` | hand-made derby list: same city, plus El Clásico, Liverpool–Man United and the Basque derby |
| `data/reference/face_values.csv` | official prices from club websites (dropped from the analysis after peer review) |
| `results/` | tables and figures for the report |
| `docs/justification.docx` | round 1 justification of our choices |
| `docs/tos_checks/` | screenshots of the terms of service and robots.txt we checked |
| `football.db`, `data/parquet/` | **not in the repository**: rebuilt by `store.py` / `compare_storage.py` |

CSVs written by our scripts are UTF-8 with BOM (`utf-8-sig`), so Excel shows accents correctly.

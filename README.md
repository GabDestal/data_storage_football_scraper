# Group G – Football ticket resale prices

Charles, Erdem, Chris, Liam, Gabriel

Our question: **how do football ticket resale (asking) prices evolve in the weeks before a match, and what explains the differences between matches?** Seat categories are a secondary, descriptive analysis.

Data: one snapshot per day of each match page on Ticombo (ticombo.fr), 27.09 → 23.11.2026, for the 100 Premier League and LaLiga matches kicking off 17.10–23.11.2026, plus fixtures and standings from football-data.org. Why we made each choice is explained in `docs/justification.docx`.

## Pipeline
Run the scripts in this order. Scripts marked *(to do)* are not in the repository yet.

| Step | Script | Reads | Writes |
|---|---|---|---|
| 1 | `get_matches.py` | football-data.org API | `data/reference/matches.csv`, `data/raw/football_data/*.json` |
| 1b | `get_season_results.py` | football-data.org API | `data/raw/football_data/<date>_season_*.json` (all season results, for ranks at kickoff) |
| 2 | `scrape.py` (**done, do not rerun**) | `data/reference/match_urls.csv` | `data/raw/ticombo/<date>/*.html`, `data/raw/scrape_log.csv` |
| 3 | `parse.py` | raw pages + scrape log | `data/events_v0.csv`, `data/categories_v0.csv` |
| 4 | `clean_data.py` *(to do)* | `*_v0.csv` | `data/clean/` (rows flagged, never deleted) |
| 5 | `map_categories.py` | categories | `data/reference/seat_category_map.csv` |
| 6 | `features.py` *(to do)* | matches, results, `derbies.csv` | match features (ranks, derby, weekend, kickoff hour) |
| 7 | `store.py` *(to do)* | clean data + reference tables | `football.db` (SQLite) |
| 8 | `analysis.py` *(to do)* | `football.db` | `results/figures/`, `results/tables/` |

## How to reproduce
```bash
pip install -r requirements.txt
git lfs pull                      # gets the raw zip if it is only a few bytes
cd data/raw && unzip raw_zip_file.zip && cd ../..   # -> data/raw/ticombo/<date>/*.html
export FOOTBALL_DATA_TOKEN=...    # free key on football-data.org (only for get_matches.py)
python get_matches.py
python get_season_results.py
python parse.py
python clean_data.py
python map_categories.py
python features.py
python store.py
python analysis.py
```

**Important:** the scraping can't be reproduced, since the prices on a given day are gone the next day. This is why we keep every raw page: anyone can rerun the pipeline from `parse.py` on and get the same tables. During collection, `scrape.py` ran once a day (cron: `0 11 * * * cd /path/to/project && python3 scrape.py`).

## Files
| File | What it is |
|---|---|
| `config.py` | competitions, match window, platform, user-agent, delays |
| `inspect_page.py` | helper used to explore the structure of a Ticombo page |
| `data/raw/` | everything we downloaded, never modified |
| `data/raw/raw_zip_file.zip` | all 5,463 raw Ticombo pages, zipped, stored with Git LFS. Also attached to the [`raw-data-v1` release](https://github.com/GabDestal/data_storage_football_scraper/releases/tag/raw-data-v1) |
| `data/raw/football_data/` | fixtures and standings from football-data.org, one dated file per run |
| `data/raw/scrape_log.csv` | every request we made, with its status (success, blocked, error...) |
| `data/raw_sample/` | 4 example pages (one PL and one LaLiga match, at the first scrape and the day before kickoff) |
| `data/reference/matches.csv` | the 100 matches: id, league, matchday, kickoff, teams |
| `data/reference/match_urls.csv` | link between each match and its Ticombo page |
| `data/reference/seat_category_map.csv` | seat label → seat group (side, behind goal, corner, premium, away) and stand level |
| `data/reference/derbies.csv` | hand-made derby list: same city, plus El Clásico, Liverpool–Man United and the Basque derby (Athletic–Real Sociedad) |
| `data/reference/face_values.csv` | official prices from the club websites (dropped from the analysis after peer review) |
| `docs/justification.docx` | round 1 justification of our choices |
| `docs/tos_checks/` | screenshots of the terms of service / robots.txt we checked |

CSVs written by our scripts are UTF-8 with BOM (`utf-8-sig`), so Excel shows accents correctly.

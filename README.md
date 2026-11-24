# Group G – Football ticket resale prices (raw data acquisition, 29.09)

Charles, Erdem, Chris, Liam, Gabriel

Our question: **how do football ticket resale prices evolve in the weeks before a match, and what explains the differences between matches and seat categories?**

This folder contains our first raw dataset and the code to collect it again. Why we made each choice is explained in our 1 page justification document

## Files
| File | What it does |
|---|---|
| `config.py` | competitions, match window, platform, delays |
| `get_matches.py` | gets fixtures + standings from football-data.org |
| `scrape.py` | downloads the event page of each match (run daily) |
| `parse.py` | first version of the table: one row per listing per snapshot |
| `data/reference/match_urls.csv` | link between each match and its page on the platform |
| `data/reference/face_values.csv` | official prices from the club websites |
| `data/reference/seat_category_map.csv` | which platform category corresponds to which club category |
| `data/raw/` | everything we downloaded, never modified |
| `data/raw/scrape_log.csv` | every request we made, with its status (success, blocked, error...) |
| `docs/tos_checks/` | screenshots of the terms of service / robots.txt we checked |

## How to reproduce
```bash
pip install -r requirements.txt
export FOOTBALL_DATA_TOKEN=...   # free key on football-data.org
python get_matches.py            # 1. list of matches
# 2. fill data/reference/match_urls.csv by hand (one line per match)
python scrape.py                 # 3. one snapshot -> we run this every day at 11:00 Paris time
python parse.py                  # 4. builds data/listings_v0.csv
```
To run it automatically every day (Mac/Linux): `crontab -e` then add
`0 11 * * * cd /path/to/project && python3 scrape.py`

**Important:** the scraping can't be reproduced exactly, since the prices on a given day are gone the next day. This is why we keep all raw pages in `data/raw/`: anyone can rerun `parse.py` on them and get the same table.

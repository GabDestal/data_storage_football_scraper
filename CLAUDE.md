# CLAUDE.md — Group G: Football Ticket Resale Dynamics

Course: Data, Data Storage, Data Collection 
Group G

## Goal

Research question: **how do football ticket resale (asking) prices evolve in the weeks before a match, and what explains the variation across matches?**
Seat categories are secondary: one descriptive analysis only (see "Known data issues").

The project is graded on: collection, cleaning, storage, analysis, communication and reproducibility. The grade depends on how **appropriate and justified** each choice is, not on technical complexity. The final deliverables are:
- a runnable, documented workflow (collection → cleaning → storage → analysis),
- a report of **at most 5 pages**,
- a 15-minute presentation.

## Deadlines

- **27.11.2026:** final report (PDF) + code. Collection ended 23.11 (last snapshot 23.11 09:00 UTC).
- **02.12.2026:** presentation, 15 min + questions. Slides submitted by the end of the session.

## Hard rules

- **Never modify raw data.** `data/raw/` is immutable: HTML pages, the API JSON, `scrape_log.csv`. Every derived table is rebuilt by a script.
- **Never edit CSVs by hand.** Every transformation lives in a script, so the pipeline can rerun from the raw data.
- **Collection is finished.** Don't run `scrape.py` again and don't add new data sources.
- **No machine learning or advanced statistics** without the professor's approval. Allowed: descriptive statistics, group comparisons, simple OLS, and the fixed-effects OLS promised in the proposal.
- **Only claim asking prices.** Never call a drop in listed tickets "sales" or "demand": the data has no listing IDs or transactions.
- **Keep observations separate from interpretations** in every result, as the brief requires.
- **Keep the code simple and readable, in a student style:** short scripts, plain pandas, comments that explain *why*. No frameworks, no over-engineering.
- **Never commit the football-data.org API key** (environment variable `FOOTBALL_DATA_TOKEN`), and never commit personal files.

## Pipeline (run order)

```
get_matches.py    → data/reference/matches.csv + data/raw/football_data/<date>_{matches,standings}_{PL,PD}.json
get_season_results.py → data/raw/football_data/<date>_season_{PL,PD}.json (all season results, for ranks at kickoff)
scrape.py         → data/raw/ticombo/<date>/*.html + data/raw/scrape_log.csv     (DONE, do not rerun)
parse.py          → data/events_v0.csv, data/categories_v0.csv
clean_data.py     → data/clean/{events,categories}_all_clean.csv (flags), *_pre_match.csv, quality_summary.json
map_categories.py → data/reference/seat_category_map.csv  (label → tier, automatic keyword rules)
features.py       → match features: ranks at kickoff date, rank gap, derby, weekend, kickoff hour
store.py          → football.db (SQLite)
analysis.py       → results/figures/*.png, results/tables/*.csv, results/summary.txt
```
`config.py` holds the settings: competitions PL and PD, kickoff window 17.10–23.11.2026, platform ticombo.fr, user-agent, delays.

## Data

- **Source:** Ticombo (ticombo.fr). Each match page embeds a JSON block `<script id="ng-state">` holding match-level and per-category **summaries**, with no individual listings.
  - StubHub/viagogo were rejected: their terms of service forbid scrapers.
  - Ticombo passed all checks: robots.txt, terms, no login, no captcha.
  - robots.txt blocks `/buy` URLs; `scrape.py` skips them by hand.
- **Fixtures and standings:** football-data.org API v4. Each run of `get_matches.py` writes dated files. Three runs were saved (27.09, 20.10, 24.11). The 24.11 run is final: all 100 matches FINISHED with results. Team ranks at kickoff are recomputed from match results, not taken from a saved standings file.
- **Scope:** Premier League + LaLiga, 100 matches kicking off 17.10–23.11.2026. 97 have a Ticombo link: Levante–Athletic was never found, and Real Sociedad–Rayo and Getafe–Atlético were added late. One snapshot per match per day, 27.09 → 23.11, request quantity fixed to 1 ticket.
- **Keys:**
  - `match_id` is the football-data.org fixture ID.
  - An event snapshot = (`match_id`, `snapshot_utc`).
  - A category snapshot = (`match_id`, `snapshot_utc`, `category`).

### Main fields (`events_*.csv`)

| Field | Meaning |
|---|---|
| `listing_startPrice` | lowest asking price, without fees |
| `listing_finalStartPrice` | lowest asking price, fees included. Usually 1.30 × `listing_startPrice`, but 219 of 3,245 rows with both prices deviate by more than 1% (ratio 0.09–1.35): `clean_data.py` flags them. Has more non-missing values. **Main price measure.** |
| `listing_avgPrice`, `listing_maxPrice` | average and maximum. Distorted by extreme listings, so don't use as main measures. |
| `listing_availableTickets` | tickets listed. Treat as **listed supply**, not demand. |
| `event_kickoff_platform` / `kickoff_utc_reference` | kickoff according to Ticombo / football-data |
| `days_to_kickoff_exact` | days before kickoff, as a decimal. Use this, not the rounded value. |
| `flag_*`, `eligible_pre_match` | cleaning flags. Rows are flagged, never silently deleted. |

Categories (`categories_*.csv`): `category` (raw label), `averagePrice`, `availableTickets`.

## Locked decisions

1. **Price measure:** `listing_finalStartPrice`, the lowest price with fees. The base price is used only as a robustness check.
2. **One snapshot per match per calendar day.** If there are two, keep the latest; the interrupted 06.10 run left duplicates.
3. **Pre-kickoff snapshots only.** After the peer-review fix, the scraper kept collecting until 24.11, including matches already played.
4. **Kickoff rule:** exclude a match only if the Ticombo and football-data kickoffs differ by **more than 1 day** after the final refresh. Gaps of a few hours are placeholder times, so keep them. The old rule (any mismatch) dropped 9 whole LaLiga matches, which was too aggressive.
5. **Common window:** the last 21 days before kickoff, for trajectories. Every match has it (peer review 1).
6. **Extreme prices** are flagged but kept, and handled through robustness checks (without the top 1%).
7. **Face values and markup are dropped.** The reference file was never filled, face values are ranges, and the question doesn't need them.
8. **Standings:** each team's rank at kickoff is recomputed in `features.py` from the official results of matches played *before* that kickoff (`data/raw/football_data/<date>_season_{PL,PD}.json`, from `get_season_results.py`), never later information. Replaces the planned weekly standings refreshes, which were only saved 3 times.
9. **Storage:** SQLite with 4 normalised tables (`matches`, `standings`, `event_snapshots`, `category_snapshots`), with primary and foreign keys and no repeated match columns. The report compares it with CSV and with Parquet + DuckDB.

## Known data issues (document them, don't hide them)

- 03.10 has no snapshot (laptop off). Snapshot times vary between about 05:00 and 21:00 UTC.
- The 06.10 run was interrupted. Its log lines point to deleted files, and `parse.py` skips them with a warning.
- Category totals **don't match** match totals: categories cover about 37% of listed tickets.
  - 191 raw labels across about 40 stadiums, so categories stay a **secondary** analysis.
- Some matches have days with no listings: price missing, 0 tickets. Exclude them from price analyses and keep them for supply.
- LaLiga kickoff times were placeholders (00:00) in the 20.10 run, with 9 matches more than 1 h off Ticombo (2 by more than a day). Fixed by the final 24.11 `get_matches.py` run: 10 kickoffs updated, 0 at 00:00, 0 mismatches with Ticombo.
- All CSVs are written in `utf-8-sig` so Excel shows accents correctly. The data itself is fine UTF-8; a "�" seen in a terminal is a display issue only.
- Extreme prices exist: maximums up to about €31,000, category averages above €10,000.
- One platform only: no official exchanges, other resale sites or private sales.

## Seat mapping (`map_categories.py`)

Automatic, no stadium-by-stadium manual mapping:
1. Normalise labels: lowercase, strip accents and spaces.
2. Assign a `seat_group` with keyword rules, first match wins, in this order (most labels describe position, not home/away, so grouping is by position):
   - **away:** away, visiting, visitors, visitante
   - **premium:** vip, hospitality, club, lounge, bar, package, suite, platinum, palco, corporate, premium, box, dugout, offsite…
   - **corner:** corner, esquina
   - **behind_goal:** shortside, fondo, gol, goal
   - **side:** longside, tribuna, lateral, preferencia, main stand
   - **unmapped:** no keyword (e.g. "Categoria 1", stadium-specific names like "Rio Alto")
   A separate `level` column (upper / middle / lower) comes from alta/baja/superior/inferior etc.
3. Output `seat_category_map.csv`: category, label_norm, seat_group, level, matched_keyword, double_match, n_matches, n_rows, n_tickets.
   On categories_v0: 230 labels; side 49.7% of category tickets, behind_goal 38.0%, premium 7.6%, unmapped 2.5%, away 1.3%, corner 0.9%.
4. Check by hand only the 20–30 most frequent labels and any double matches. Report the share of tickets mapped.
5. Alternative grouping: within each match and snapshot, split categories into price thirds (cheap, mid, premium).

## Analysis plan (`analysis.py`)

| ID | Analysis | Answers |
|---|---|---|
| A0 | Data description: snapshots per day, matches per league, coverage; one example match chart (peer review 2's EDA) | quality |
| A1 | Average trajectory: price indexed to 100 at day −21, median + middle-50% band by league; FE regression `log(price) ~ C(days bin) + C(match_id)` with SE clustered by match; bins 14–21 (reference), 7–13, 3–6, 0–2 | how prices move |
| A2 | Different paths: share of matches falling / flat / rising (0–2 days vs 14–21 days); trajectories by price third and by league | do all matches behave alike |
| A3 | Listed supply by day (indexed) + within-match correlation of daily changes in supply and price. Wording: supply, never sales. | supply |
| A4 | Price level between matches: median lowest price 7–14 days before vs league, best rank, rank gap, weekend, derby; one simple OLS with HC1 SE. Main factors: league + team rank; derby and weekend secondary. | what explains differences |
| A5 | Seat tiers: median category price by tier by day (secondary, with the coverage caveat) | seat types |
| A6 | Robustness: base price vs fees included, without top 1%, each league alone, full window vs 21 days | credibility |

Preliminary result on October data (70 matches): the lowest price is about **19% lower in the last 2 days** than 14–21 days before (PL −27%, LaLiga −9%). Weekend matches are about 40% more expensive. This must be **re-checked on the final data**.

`data/reference/derbies.csv` holds the hand-made derby list. Definition: same city, plus El Clásico, Liverpool–Man United and the Basque derby (Athletic–Real Sociedad). 26 pairs (`team_a`, `team_b`, `competition`, `derby_type`, `derby_name`), names exactly as in `matches.csv`. 6 of our 100 matches are derbies. Not included (borderline, group to decide): Getafe vs Madrid clubs, Celta–Deportivo, Newcastle–Sunderland.

## Report outline (5 pages max)

1. Question and data, 0.75 page: sources, scope, legal checks.
2. Cleaning, 0.75 page: rules, how many rows were excluded and why.
3. Storage, 0.5 page: SQLite choice and comparison.
4. Results, about 2 pages: 3–4 charts, the FE regression table, and an observation line plus an interpretation line for each result.
5. Limitations, 0.5 page.
6. Changes after the peer reviews, 0.5 page:
   - automatic daily run, backup and gap check,
   - lowest price instead of averages,
   - common 21-day window,
   - face values dropped and categories made secondary,
   - SQLite with no redundancy,
   - EDA added,
   - "supply, not demand".

## Team split

| Person | Responsibility |
|---|---|
| Gabriel | final collection and archive, GitHub repo, README, report "Data & collection", full rerun test, submission |
| [cleaning] | `clean_data.py` on the final data, report "Cleaning" |
| [person 2] | `map_categories.py`, `features.py` (ranks, derbies) |
| [person 3] | `store.py` (SQLite), report "Storage" |
| [person 4] | `analysis.py` A0–A3 |
| [person 3/4] | `analysis.py` A4–A6 |
| All | limitations, changes after reviews, slides |

## Repository notes

- `data/raw/ticombo/` is in `.gitignore` (too large). The full raw archive is `data/raw/raw_zip_file.zip`, committed with Git LFS and also attached to the GitHub Release `raw-data-v1`. Four example pages are in `data/raw_sample/`.
- `docs/justification.docx` is the round 1 justification document. `docs/tos_checks/` is still empty: the ToS / robots.txt screenshots must be found or retaken (with the new date stated).
- Charts: matplotlib, one axis per chart, labelled axes, legend for 2 or more series. Use the same colours everywhere: PL `#2a78d6`, LaLiga `#eb6834`.
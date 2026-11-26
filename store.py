#Step 7: store the clean data in one SQLite database (football.db).

#Input : data/reference/matches.csv, data/clean/match_features.csv (from features.py)
#        data/raw/football_data/<date>_standings_{PL,PD}.json
#        data/clean/events_all_clean.csv, data/clean/categories_all_clean.csv
#        data/reference/seat_category_map.csv (from map_categories.py)
#Output: football.db with 5 normalised tables:
#   matches            one row per match                      PK match_id
#   standings          one row per team per standings file    PK (standings_date, competition, team)
#   event_snapshots    one row per match per snapshot         PK (match_id, snapshot_utc)
#   seat_categories    one row per raw category label         PK category
#   category_snapshots one row per category per snapshot      PK (match_id, snapshot_utc, category)

#Why SQLite: one file, no server, keys and types are enforced, and every group member can
#query it with plain SQL or pandas. Our data is small (~5,000 + ~26,000 rows).
#Why normalised: match information (teams, kickoff, league) is stored once in `matches`
#instead of being repeated on every snapshot row, so it cannot become inconsistent.
#Same idea for seat groups: each label is classified once in `seat_categories` (230 rows)
#instead of repeating its group on the ~26,000 category snapshots.
#We load the *_all_clean files (every row + flags), not only the pre-match rows: rows are
#flagged, never deleted, and the analysis filters with eligible_pre_match = 1.

import os
import glob
import json
import sqlite3
import pandas as pd

os.chdir(os.path.dirname(os.path.abspath(__file__)))
DB = "football.db"

# start from an empty database so the script can be rerun safely
if os.path.exists(DB):
    os.remove(DB)
con = sqlite3.connect(DB)
con.execute("PRAGMA foreign_keys = ON")  # SQLite only checks foreign keys if asked to

# --- 1. create the tables ---
con.executescript("""
CREATE TABLE matches (
    match_id     INTEGER PRIMARY KEY,   -- football-data.org fixture ID
    competition  TEXT NOT NULL,         -- PL or PD (LaLiga)
    matchday     INTEGER,
    kickoff_utc  TEXT NOT NULL,         -- final kickoff from football-data (24.11 refresh)
    home_team    TEXT NOT NULL,
    away_team    TEXT NOT NULL,
    event_uuid   TEXT,                  -- Ticombo event ID, NULL if the match was never found
    -- match features from features.py (one value per match, so they belong here)
    home_rank           INTEGER,        -- rank at kickoff, from results played before kickoff
    away_rank           INTEGER,
    best_rank           INTEGER,        -- rank of the better of the two teams
    rank_gap            INTEGER,
    home_points         INTEGER,
    away_points         INTEGER,
    games_played_before INTEGER,
    derby               INTEGER NOT NULL,  -- 0/1, from data/reference/derbies.csv
    derby_name          TEXT,
    weekend             INTEGER NOT NULL,  -- 0/1
    kickoff_weekday     TEXT,
    kickoff_hour_local  INTEGER
);

CREATE TABLE standings (
    standings_date TEXT NOT NULL,       -- date of the football-data refresh (from the file name)
    competition    TEXT NOT NULL,
    team           TEXT NOT NULL,
    position       INTEGER NOT NULL,
    played_games   INTEGER,
    won            INTEGER,
    draw           INTEGER,
    lost           INTEGER,
    points         INTEGER,
    goals_for      INTEGER,
    goals_against  INTEGER,
    goal_difference INTEGER,
    PRIMARY KEY (standings_date, competition, team)
);

CREATE TABLE event_snapshots (
    match_id                  INTEGER NOT NULL REFERENCES matches(match_id),
    snapshot_utc              TEXT NOT NULL,
    snapshot_date             TEXT NOT NULL,
    days_to_kickoff_exact     REAL,
    raw_file                  TEXT,     -- raw HTML page this row comes from (traceability)
    event_kickoff_platform    TEXT,     -- kickoff according to Ticombo
    event_updated_platform    TEXT,
    listing_availableTickets  REAL,     -- listed supply, not demand
    listing_availableListings REAL,
    listing_startPrice        REAL,     -- lowest asking price, without fees (main measure)
    listing_finalStartPrice   REAL,     -- lowest asking price, fees included (robustness only)
    listing_avgPrice          REAL,
    listing_maxPrice          REAL,
    listing_finalMaxPrice     REAL,
    fee_ratio                 REAL,
    flag_duplicate_day        INTEGER NOT NULL,  -- flags are 0/1
    flag_post_kickoff         INTEGER NOT NULL,
    flag_kickoff_mismatch     INTEGER NOT NULL,
    flag_no_listings          INTEGER NOT NULL,
    flag_fee_above_30         INTEGER NOT NULL,
    flag_fee_inconsistent     INTEGER NOT NULL,
    flag_extreme_price        INTEGER NOT NULL,
    eligible_pre_match        INTEGER NOT NULL,
    eligible_price            INTEGER NOT NULL,
    in_window_21d             INTEGER NOT NULL,
    PRIMARY KEY (match_id, snapshot_utc)
);

CREATE TABLE seat_categories (
    category       TEXT PRIMARY KEY,    -- raw label from Ticombo
    label_norm     TEXT,                -- lowercase, no accents
    seat_group     TEXT NOT NULL,       -- side / behind_goal / corner / premium / away / unmapped
    level          TEXT,                -- upper / middle / lower, NULL if unknown
    matched_keyword TEXT,
    double_match   INTEGER NOT NULL     -- 1 if the label matched two groups (checked by hand)
);

CREATE TABLE category_snapshots (
    match_id           INTEGER NOT NULL,
    snapshot_utc       TEXT NOT NULL,
    category           TEXT NOT NULL REFERENCES seat_categories(category),
    averagePrice       REAL,
    availableTickets   REAL,
    flag_extreme_price INTEGER NOT NULL,
    PRIMARY KEY (match_id, snapshot_utc, category),
    FOREIGN KEY (match_id, snapshot_utc) REFERENCES event_snapshots(match_id, snapshot_utc)
);
""")

# --- 2. matches ---
matches = pd.read_csv("data/reference/matches.csv", encoding="utf-8-sig")
events = pd.read_csv("data/clean/events_all_clean.csv", encoding="utf-8-sig")
# the Ticombo event ID is the same on every snapshot of a match -> store it once, here
uuid = events.groupby("match_id")["event_uuid"].first().reset_index()
matches = matches.merge(uuid, on="match_id", how="left")
# match features (ranks at kickoff, derby, weekend) are one value per match: store them in
# `matches` instead of a separate CSV, so the analysis reads everything from one database
features = pd.read_csv("data/clean/match_features.csv", encoding="utf-8-sig")
assert set(features["match_id"]) == set(matches["match_id"]), "features.py must cover every match"
for col in ["derby", "weekend"]:
    features[col] = features[col].astype(int)   # True/False -> 1/0, like the flags
matches = matches.merge(features, on="match_id", how="left")
matches.to_sql("matches", con, if_exists="append", index=False)

# --- 3. standings: one row per team, for every dated standings file ---
rows = []
for path in sorted(glob.glob("data/raw/football_data/*_standings_*.json")):
    name = os.path.basename(path)            # e.g. 2026-11-24_standings_PL.json
    date = name.split("_")[0]
    competition = name.split("_")[-1].replace(".json", "")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    # the API also returns HOME and AWAY tables; we only need the overall one
    table = [s for s in data["standings"] if s["type"] == "TOTAL"][0]["table"]
    for t in table:
        rows.append({
            "standings_date": date, "competition": competition, "team": t["team"]["name"],
            "position": t["position"], "played_games": t["playedGames"], "won": t["won"],
            "draw": t["draw"], "lost": t["lost"], "points": t["points"],
            "goals_for": t["goalsFor"], "goals_against": t["goalsAgainst"],
            "goal_difference": t["goalDifference"],
        })
pd.DataFrame(rows).to_sql("standings", con, if_exists="append", index=False)

# --- 4. event snapshots ---
# drop columns that are constant (platform, currency) or already stored in `matches`
# (event_uuid, kickoff_utc_reference): keeping them would repeat the same value on every row
event_cols = [c for c in events.columns
              if c not in ["platform", "currency", "event_uuid", "kickoff_utc_reference"]]
events[event_cols].to_sql("event_snapshots", con, if_exists="append", index=False)

# --- 5. seat categories ---
# n_matches, n_rows and n_tickets are counts computed from the snapshots: they can be
# recomputed with a query, so storing them would be redundant
seats = pd.read_csv("data/reference/seat_category_map.csv", encoding="utf-8-sig")
seat_cols = ["category", "label_norm", "seat_group", "level", "matched_keyword", "double_match"]
seats[seat_cols].to_sql("seat_categories", con, if_exists="append", index=False)

# --- 6. category snapshots ---
# clean_data.py copied the snapshot-level columns (dates, flags, window) onto every category
# row. They are already in event_snapshots, so we keep only what belongs to the category.
cats = pd.read_csv("data/clean/categories_all_clean.csv", encoding="utf-8-sig")
cat_cols = ["match_id", "snapshot_utc", "category", "averagePrice", "availableTickets",
            "flag_extreme_price"]
cats[cat_cols].to_sql("category_snapshots", con, if_exists="append", index=False)

# indexes for the joins and filters the analysis uses most
con.execute("CREATE INDEX idx_events_eligible ON event_snapshots(eligible_pre_match, match_id)")
con.commit()

# --- 7. checks: the database must hold exactly what the CSVs hold ---
def count(sql):
    return con.execute(sql).fetchone()[0]

assert count("SELECT COUNT(*) FROM matches") == len(matches)
assert count("SELECT COUNT(*) FROM seat_categories") == len(seats)
assert count("SELECT COUNT(*) FROM event_snapshots") == len(events)
assert count("SELECT COUNT(*) FROM category_snapshots") == len(cats)
assert count("SELECT COUNT(*) FROM standings") == len(rows)
# no orphan rows (foreign keys are already enforced on insert; this double-checks)
assert con.execute("PRAGMA foreign_key_check").fetchall() == []
# the pre-match subset must match clean_data.py's quality summary
with open("data/clean/quality_summary.json") as f:
    quality = json.load(f)
assert count("SELECT COUNT(*) FROM event_snapshots WHERE eligible_pre_match = 1") \
    == quality["eligible_pre_match_rows"]
assert count("SELECT COUNT(*) FROM event_snapshots WHERE eligible_price = 1") \
    == quality["eligible_price_rows"]
# every team of every match appears in the standings (needed for ranks at kickoff)
missing = con.execute("""
    SELECT DISTINCT team FROM (SELECT home_team AS team FROM matches
                               UNION SELECT away_team FROM matches)
    WHERE team NOT IN (SELECT team FROM standings)
""").fetchall()
assert missing == [], f"teams missing from standings: {missing}"

for table in ["matches", "standings", "event_snapshots", "seat_categories", "category_snapshots"]:
    print(f"{table:20s} {count(f'SELECT COUNT(*) FROM {table}'):6d} rows")
print(f"saved {DB} ({os.path.getsize(DB) / 1e6:.1f} MB)")
con.close()

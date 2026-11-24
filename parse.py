#Step 3: turn the raw Ticombo pages into tables.

#Each Ticombo event page contains its data as JSON inside <script id="ng-state">. The event
#object in it has a summary of all the listings of the match:
#  - "listing": totals for the match (available tickets, start/avg/max price...)
#  - "stats" -> "ticketTypes": the same per seat category (average price, available tickets)

#We build 2 tables:
#  data/events_v0.csv      1 row per match per snapshot
#  data/categories_v0.csv  1 row per seat category per match per snapshot  <- our main table
#                          (= our unit of analysis: match x seat category x days to kickoff)

#We keep every simple field the site gives (we don't choose now), so nothing is lost before
#the cleaning checkpoint. Individual listings are NOT in the page (the site loads them later
#with another request), so we only have aggregates. See justification.md.

import json
import pandas as pd
from bs4 import BeautifulSoup

import os
os.chdir(os.path.dirname(os.path.abspath(__file__)))

matches = pd.read_csv("data/reference/matches.csv")
log = pd.read_csv("data/raw/scrape_log.csv")
log = log[log["file"].notna() & (log["file"] != "")]


def simple_fields(d, prefix=""):
    """Keeps only numbers / text / booleans (drops nested lists and dicts)."""
    return {prefix + k: v for k, v in d.items() if isinstance(v, (int, float, str, bool)) or v is None}


events, categories = [], []

for _, entry in log.iterrows():
    if not os.path.exists(entry["file"]):
        print("WARNING: missing raw file (in the log but not on disk):", entry["file"])
        continue
    with open(entry["file"], "rb") as f:
        soup = BeautifulSoup(f.read(), "html.parser")
        
    tag = soup.find("script", id="ng-state")
    if tag is None or not tag.string:
        print("WARNING: no ng-state in", entry["file"], "(page changed or we got blocked?)")
        continue
    data = json.loads(tag.string)

    event_keys = [k for k in data if k.startswith("/discovery/events/")]
    if not event_keys or not data[event_keys[0]]:
        print("WARNING: no event data in", entry["file"])
        continue
    event = data[event_keys[0]][0]

    # currency of the prices shown (EUR for us, we scrape ticombo.fr from France)
    cur_tag = soup.find("meta", attrs={"property": "og:price:currency"})
    currency = cur_tag["content"] if cur_tag else None

    base = {"snapshot_utc": entry["timestamp_utc"], "platform": entry["platform"],
            "match_id": entry["match_id"], "event_uuid": event.get("eventId"),
            "currency": currency, "raw_file": entry["file"]}

    # --- 1. match level ---
    events.append({**base,
                   "event_kickoff_platform": event.get("date", {}).get("from"),
                   "event_updated_platform": event.get("updatedDate"),
                   **simple_fields(event.get("listing", {}), prefix="listing_")})

    # --- 2. seat category level ---
    for cat in event.get("stats", {}).get("ticketTypes", []):
        categories.append({**base, **simple_fields(cat)})

    if not event.get("stats", {}).get("ticketTypes"):
        print("NOTE: no category stats in", entry["file"], "(no listings for this match?)")

# add days to kickoff (from football-data.org kickoff, not the platform's)
kickoffs = matches[["match_id", "kickoff_utc"]]
for name, rows in [("events", events), ("categories", categories)]:
    df = pd.DataFrame(rows)
    if df.empty:
        print(f"{name}: nothing parsed")
        continue
    df = df.merge(kickoffs, on="match_id", how="left")
    df["days_to_kickoff"] = ((pd.to_datetime(df["kickoff_utc"]) - pd.to_datetime(df["snapshot_utc"]))
                             .dt.total_seconds() / 86400).round(1)
    if name == "events":
        # check that each link points to the right fixture: the platform's date must match
        # football-data.org's (a wrong link often points to the reverse fixture, months away)
        gap = (pd.to_datetime(df["event_kickoff_platform"]) - pd.to_datetime(df["kickoff_utc"])).abs()
        wrong = df[gap > pd.Timedelta(days=1)][["match_id", "event_kickoff_platform", "kickoff_utc"]].drop_duplicates("match_id")
        if len(wrong):
            print("WARNING: these links may point to the wrong match (dates differ by > 1 day):")
            print(wrong.to_string(index=False))
    df.to_csv(f"data/{name}_v0.csv", index=False, encoding="utf-8-sig")
    print(f"{name}: {len(df)} rows, {df['match_id'].nunique()} matches")

ev = pd.read_csv("data/events_v0.csv")
per_day = ev.groupby(ev["snapshot_utc"].str[:10])["match_id"].nunique()
all_days = pd.date_range(per_day.index.min(), pd.Timestamp.now().strftime("%Y-%m-%d")).strftime("%Y-%m-%d")
per_day = per_day.reindex(all_days, fill_value=0)
print("\nmatches captured per day (expected ~97):")
print(per_day.to_string())
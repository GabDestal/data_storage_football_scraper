#Step 4: clean the parsed tables. Rows are FLAGGED, never silently deleted.

#Input : data/events_v0.csv, data/categories_v0.csv, data/reference/matches.csv
#Output: data/clean/events_all_clean.csv      every row + flags
#        data/clean/events_pre_match.csv      only rows usable for the analysis (eligible_pre_match)
#        data/clean/categories_all_clean.csv  same for seat categories
#        data/clean/categories_pre_match.csv
#        data/clean/quality_summary.json      how many rows each rule flags (for the report)

#Rules (see "Locked decisions" in CLAUDE.md):
#  1. one snapshot per match per calendar day (keep the latest)
#  2. pre-kickoff snapshots only (the scraper kept running after some matches were played)
#  3. drop a match only if Ticombo and football-data kickoffs differ by more than 1 day
#  4. "no listings": 0 tickets listed -> no price (the page can still show an old price)
#  5. fee check: the fees-included price should be 1.30 x the base price; from 04.11 some
#     listings show 1.35 (looks like a fee increase), so we keep 1.30-1.35 and only flag
#     ratios outside that range as inconsistent
#  6. extreme prices (top 1% of the base price) are flagged but kept -> robustness check
#  7. the 21-day window is a flag for the analysis, not a deletion

import os
import json
import pandas as pd

os.chdir(os.path.dirname(os.path.abspath(__file__)))
os.makedirs("data/clean", exist_ok=True)

events = pd.read_csv("data/events_v0.csv")
cats = pd.read_csv("data/categories_v0.csv")
matches = pd.read_csv("data/reference/matches.csv", encoding="utf-8-sig")

# parse.py computed days_to_kickoff with the kickoff times known at that time (some LaLiga
# kickoffs were 00:00 placeholders). We recompute everything from the final matches.csv.
events = events.drop(columns=["kickoff_utc", "days_to_kickoff"])
cats = cats.drop(columns=["kickoff_utc", "days_to_kickoff"])
kick = matches[["match_id", "kickoff_utc"]].rename(columns={"kickoff_utc": "kickoff_utc_reference"})
events = events.merge(kick, on="match_id", how="left")

snap = pd.to_datetime(events["snapshot_utc"], utc=True)
kickoff = pd.to_datetime(events["kickoff_utc_reference"], utc=True)
events["snapshot_date"] = snap.dt.strftime("%Y-%m-%d")
events["days_to_kickoff_exact"] = (kickoff - snap).dt.total_seconds() / 86400

# --- 1. one snapshot per match per day: keep the latest ---
events = events.sort_values(["match_id", "snapshot_utc"])
latest = events.groupby(["match_id", "snapshot_date"])["snapshot_utc"].transform("max")
events["flag_duplicate_day"] = events["snapshot_utc"] != latest

# --- 2. snapshots taken at or after kickoff ---
events["flag_post_kickoff"] = events["days_to_kickoff_exact"] <= 0

# --- 3. kickoff mismatch between Ticombo and football-data (whole match) ---
platform_kickoff = pd.to_datetime(events["event_kickoff_platform"], utc=True, errors="coerce")
# use the latest platform kickoff of each match (the page can be updated over time)
last_platform = platform_kickoff.groupby(events["match_id"]).transform("last")
events["flag_kickoff_mismatch"] = (last_platform - kickoff).abs() > pd.Timedelta(days=1)

# --- 4. no listings ---
# 0 or missing tickets = nothing for sale. The page may still show a "from" price, which is
# a leftover and must not be used as a price.
events["flag_no_listings"] = events["listing_availableTickets"].fillna(0) == 0

# --- 5. fee check ---
events["fee_ratio"] = events["listing_finalStartPrice"] / events["listing_startPrice"]
ratio = events["fee_ratio"]
# +/- 1% tolerance around 1.30 and 1.35
events["flag_fee_above_30"] = ratio > 1.30 * 1.01
events["flag_fee_inconsistent"] = ratio.notna() & ((ratio < 1.30 * 0.99) | (ratio > 1.35 * 1.01))

# --- which rows we use ---
events["eligible_pre_match"] = ~(events["flag_duplicate_day"] | events["flag_post_kickoff"]
                                 | events["flag_kickoff_mismatch"])
# price analyses also need listings and a consistent price (supply analyses don't)
events["eligible_price"] = (events["eligible_pre_match"] & ~events["flag_no_listings"]
                            & ~events["flag_fee_inconsistent"])

# --- 6. extreme prices: top 1% of the usable lowest prices ---
# computed on the base price (listing_startPrice), our main measure: the fee-included price
# moved from 1.30x to 1.35x on 04.11, so a threshold on it would shift over time
p99 = events.loc[events["eligible_price"], "listing_startPrice"].quantile(0.99)
events["flag_extreme_price"] = events["eligible_price"] & (events["listing_startPrice"] > p99)

# --- 7. common window: the last 21 days before kickoff ---
events["in_window_21d"] = (events["days_to_kickoff_exact"] > 0) & (events["days_to_kickoff_exact"] <= 21)

# --- categories: take the snapshot-level flags from the events table ---
snapshot_cols = ["match_id", "snapshot_utc", "kickoff_utc_reference", "snapshot_date",
                 "days_to_kickoff_exact", "flag_duplicate_day", "flag_post_kickoff",
                 "flag_kickoff_mismatch", "eligible_pre_match", "in_window_21d"]
n_cats = len(cats)
cats = cats.merge(events[snapshot_cols], on=["match_id", "snapshot_utc"], how="inner")
assert len(cats) == n_cats, "some category rows have no matching event snapshot"
cp99 = cats.loc[cats["eligible_pre_match"], "averagePrice"].quantile(0.99)
cats["flag_extreme_price"] = cats["eligible_pre_match"] & (cats["averagePrice"] > cp99)

# --- save ---
events.to_csv("data/clean/events_all_clean.csv", index=False, encoding="utf-8-sig")
events[events["eligible_pre_match"]].to_csv("data/clean/events_pre_match.csv", index=False, encoding="utf-8-sig")
cats.to_csv("data/clean/categories_all_clean.csv", index=False, encoding="utf-8-sig")
cats[cats["eligible_pre_match"]].to_csv("data/clean/categories_pre_match.csv", index=False, encoding="utf-8-sig")

# --- quality summary (numbers for the "Cleaning" section of the report) ---
pre = events[events["eligible_pre_match"]]
usable = events[events["eligible_price"]]
summary = {
    "event_rows_total": len(events),
    "matches_total": int(events["match_id"].nunique()),
    "flag_duplicate_day": int(events["flag_duplicate_day"].sum()),
    "flag_post_kickoff": int(events["flag_post_kickoff"].sum()),
    "flag_kickoff_mismatch_rows": int(events["flag_kickoff_mismatch"].sum()),
    "flag_kickoff_mismatch_matches": int(events.loc[events["flag_kickoff_mismatch"], "match_id"].nunique()),
    "eligible_pre_match_rows": len(pre),
    "eligible_pre_match_matches": int(pre["match_id"].nunique()),
    "pre_match_no_listings": int(pre["flag_no_listings"].sum()),
    "pre_match_fee_inconsistent": int(pre["flag_fee_inconsistent"].sum()),
    "pre_match_fee_above_30": int(pre["flag_fee_above_30"].sum()),
    "pre_match_fee_above_30_first_date": pre.loc[pre["flag_fee_above_30"], "snapshot_date"].min(),
    "eligible_price_rows": len(usable),
    "eligible_price_matches": int(usable["match_id"].nunique()),
    "eligible_price_in_window_21d": int(usable["in_window_21d"].sum()),
    "extreme_price_threshold_eur": round(float(p99), 2),
    "flag_extreme_price": int(events["flag_extreme_price"].sum()),
    "category_rows_total": len(cats),
    "category_rows_pre_match": int(cats["eligible_pre_match"].sum()),
    "category_extreme_price_threshold_eur": round(float(cp99), 2),
    "category_flag_extreme_price": int(cats["flag_extreme_price"].sum()),
}
with open("data/clean/quality_summary.json", "w") as f:
    json.dump(summary, f, indent=2)

for k, v in summary.items():
    print(f"{k:40s} {v}")

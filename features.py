#Step 6: match features used to explain price differences between matches (analysis A4).

#Input : data/reference/matches.csv
#        data/raw/football_data/<date>_season_{PL,PD}.json   (from get_season_results.py)
#        data/reference/derbies.csv
#Output: data/clean/match_features.csv   (one row per match)

#Team rank at kickoff: we planned weekly standings refreshes but only saved 3 standings files,
#so we rebuild the league table from the official results of matches finished BEFORE each
#kickoff (never later information). Ranking: points, then goal difference, then goals scored.
#Simplification: the real tie-breakers differ (LaLiga uses head-to-head), which only matters
#for teams level on points AND goal difference. We check our table against the saved
#standings files at the end.

import os
import glob
import json
import pandas as pd

os.chdir(os.path.dirname(os.path.abspath(__file__)))

matches = pd.read_csv("data/reference/matches.csv", encoding="utf-8-sig")
derbies = pd.read_csv("data/reference/derbies.csv", encoding="utf-8-sig")


def load_season(comp):
    """All matches of the season for one league, from the most recent season file."""
    path = sorted(glob.glob(f"data/raw/football_data/*_season_{comp}.json"))[-1]
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    rows = []
    for m in data["matches"]:
        rows.append({"kickoff": m["utcDate"], "status": m["status"],
                     "home": m["homeTeam"]["name"], "away": m["awayTeam"]["name"],
                     "home_goals": m["score"]["fullTime"]["home"],
                     "away_goals": m["score"]["fullTime"]["away"]})
    df = pd.DataFrame(rows)
    df["kickoff"] = pd.to_datetime(df["kickoff"], utc=True)
    return df


def table_before(season, moment):
    """League table using only matches finished before `moment`. Returns team -> rank row."""
    played = season[(season["status"] == "FINISHED") & (season["kickoff"] < moment)]
    teams = sorted(set(season["home"]) | set(season["away"]))  # every team, even with 0 games
    stats = {t: {"played": 0, "points": 0, "gf": 0, "ga": 0} for t in teams}
    for _, m in played.iterrows():
        h, a, hg, ag = m["home"], m["away"], m["home_goals"], m["away_goals"]
        stats[h]["played"] += 1; stats[a]["played"] += 1
        stats[h]["gf"] += hg; stats[h]["ga"] += ag
        stats[a]["gf"] += ag; stats[a]["ga"] += hg
        if hg > ag:
            stats[h]["points"] += 3
        elif hg < ag:
            stats[a]["points"] += 3
        else:
            stats[h]["points"] += 1; stats[a]["points"] += 1
    t = pd.DataFrame.from_dict(stats, orient="index")
    t["gd"] = t["gf"] - t["ga"]
    t = t.sort_values(["points", "gd", "gf"], ascending=False)
    t["rank"] = range(1, len(t) + 1)
    return t


seasons = {comp: load_season(comp) for comp in matches["competition"].unique()}
derby_pairs = {frozenset([a, b]): name for a, b, name
               in zip(derbies["team_a"], derbies["team_b"], derbies["derby_name"])}
# local time of the league, for weekend and kickoff hour (what fans see)
local_tz = {"PL": "Europe/London", "PD": "Europe/Madrid"}

rows = []
for _, m in matches.iterrows():
    kickoff = pd.Timestamp(m["kickoff_utc"])
    table = table_before(seasons[m["competition"]], kickoff)
    home, away = table.loc[m["home_team"]], table.loc[m["away_team"]]
    local = kickoff.tz_convert(local_tz[m["competition"]])
    derby = derby_pairs.get(frozenset([m["home_team"], m["away_team"]]))
    rows.append({
        "match_id": m["match_id"],
        "home_rank": int(home["rank"]),
        "away_rank": int(away["rank"]),
        "best_rank": int(min(home["rank"], away["rank"])),   # the bigger team of the two
        "rank_gap": int(abs(home["rank"] - away["rank"])),
        "home_points": int(home["points"]),
        "away_points": int(away["points"]),
        "games_played_before": int(home["played"]),
        "derby": derby is not None,
        "derby_name": derby or "",
        "weekend": local.dayofweek >= 5,                   # Saturday or Sunday
        "kickoff_weekday": local.day_name(),
        "kickoff_hour_local": local.hour,
    })

features = pd.DataFrame(rows)
features.to_csv("data/clean/match_features.csv", index=False, encoding="utf-8-sig")
print(f"Wrote data/clean/match_features.csv: {len(features)} matches")
print(features[["derby", "weekend"]].sum().to_string())
print("best_rank:", features["best_rank"].describe()[["min", "50%", "max"]].to_dict())

# --- check: our rebuilt table vs the standings files saved by get_matches.py ---
# (a standings file shows the table at the time it was downloaded)
print("\nCheck against saved standings files (position differences):")
for path in sorted(glob.glob("data/raw/football_data/*_standings_*.json")):
    name = os.path.basename(path)
    date, comp = name.split("_")[0], name.split("_")[-1].replace(".json", "")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    official = [s for s in data["standings"] if s["type"] == "TOTAL"][0]["table"]
    # download time unknown -> rebuild with every match finished before the end of that day
    ours = table_before(seasons[comp], pd.Timestamp(date, tz="UTC") + pd.Timedelta(days=1))
    diff = [(t["team"]["name"], t["position"], int(ours.loc[t["team"]["name"], "rank"]))
            for t in official if t["position"] != ours.loc[t["team"]["name"], "rank"]]
    same_points = all(t["points"] == ours.loc[t["team"]["name"], "points"] for t in official)
    print(f"  {name}: {len(diff)} of {len(official)} teams differ, points identical: {same_points}"
          + (f"  e.g. {diff[:3]}" if diff else ""))

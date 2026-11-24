#Step 1b: get ALL the results of the season, to rebuild the league table at each kickoff.

#Why: get_matches.py only asks for the matches in our window (17.10-23.11), so its files
#can't rebuild a league table (the season started in August). We planned weekly standings
#refreshes but only saved 3 standings files, so instead we recompute each team's rank from
#the official results played BEFORE each kickoff (in features.py). This is more precise and
#fully reproducible. Same source as get_matches.py (football-data.org), one call per league.

#Run once, after the last match of our window:
#   FOOTBALL_DATA_TOKEN=your_key python get_season_results.py

import os
import time
import json
from datetime import datetime
import requests
import config

os.chdir(os.path.dirname(os.path.abspath(__file__)))

API = "https://api.football-data.org/v4"
SEASON = 2026  # football-data names a season by its starting year: 2026 = 2026/27
headers = {"X-Auth-Token": os.environ["FOOTBALL_DATA_TOKEN"]}
today = datetime.now().strftime("%Y-%m-%d")
os.makedirs("data/raw/football_data", exist_ok=True)

for comp in config.COMPETITIONS:
    r = requests.get(f"{API}/competitions/{comp}/matches", headers=headers,
                     params={"season": SEASON})
    r.raise_for_status()
    data = r.json()

    # saved raw, never modified (features.py reads it)
    out = f"data/raw/football_data/{today}_season_{comp}.json"
    with open(out, "w") as f:
        json.dump(data, f)

    finished = [m for m in data["matches"] if m["status"] == "FINISHED"]
    print(f"{comp}: {len(data['matches'])} matches in the season, "
          f"{len(finished)} finished -> {out}")
    time.sleep(7)  # free plan: max 10 requests per minute

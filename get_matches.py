#Step 1: get the list of matches we want to follow, from the football-data.org API.
#We also save the standings because we need them later for the analysis (team rank etc).

#Run:  FOOTBALL_DATA_TOKEN=your_key python get_matches.py

import os
import time
import json
from datetime import datetime
import requests
import pandas as pd
import config

import os
os.chdir(os.path.dirname(os.path.abspath(__file__)))

API = "https://api.football-data.org/v4"
headers = {"X-Auth-Token": os.environ["FOOTBALL_DATA_TOKEN"]}
today = datetime.now().strftime("%Y-%m-%d")
os.makedirs("data/raw/football_data", exist_ok=True)

matches = []
for comp in config.COMPETITIONS:
    # fixtures in our window
    r = requests.get(f"{API}/competitions/{comp}/matches", headers=headers,
                     params={"dateFrom": config.FIRST_KICKOFF, "dateTo": config.LAST_KICKOFF})
    r.raise_for_status()
    with open(f"data/raw/football_data/{today}_matches_{comp}.json", "w") as f:
        json.dump(r.json(), f)

    for m in r.json()["matches"]:
        matches.append({
            "match_id": m["id"],
            "competition": comp,
            "matchday": m["matchday"],
            "kickoff_utc": m["utcDate"],
            "home_team": m["homeTeam"]["name"],
            "away_team": m["awayTeam"]["name"],
        })
    time.sleep(7)

    # standings (saved raw, we will use them later)
    r = requests.get(f"{API}/competitions/{comp}/standings", headers=headers)
    r.raise_for_status()
    with open(f"data/raw/football_data/{today}_standings_{comp}.json", "w") as f:
        json.dump(r.json(), f)
    time.sleep(7)

df = pd.DataFrame(matches)
df.to_csv("data/reference/matches.csv", index=False, encoding="utf-8-sig")
print(f"{len(df)} matches saved")
print(df.groupby("competition").size())

#Step 2: daily scraping. For every match in data/reference/match_urls.csv we download the
#event page and save it as it is (raw HTML). We don't parse anything here, so if our parser
#is wrong we can fix it later without losing data.

#Run once a day at the same time (we use 10:00 Paris time)

import os
import csv
import time
import random
from datetime import datetime, timezone
from urllib import robotparser
import requests
import pandas as pd
import config

import os
os.chdir(os.path.dirname(os.path.abspath(__file__)))

now = datetime.now(timezone.utc)
stamp = now.strftime("%Y-%m-%d_%H%M")
day_folder = f"data/raw/{config.PLATFORM}/{now.strftime('%Y-%m-%d')}"
os.makedirs(day_folder, exist_ok=True)

matches = pd.read_csv("data/reference/matches.csv")
urls = pd.read_csv("data/reference/match_urls.csv")
urls = urls.merge(matches[["match_id", "kickoff_utc"]], on="match_id")
# we keep scraping every match until the end of collection: if a match is moved later we
# don't lose its last days. Snapshots taken after kickoff are dropped during cleaning.
if now >= pd.Timestamp("2026-11-24", tz="UTC"):
    print("collection period is over (24.11), nothing to scrape")
    urls = urls.iloc[0:0]
print(f"{len(urls)} pages to download")

# check robots.txt once
robots = robotparser.RobotFileParser(config.PLATFORM_URL + "/robots.txt")
robots.read()

session = requests.Session()
session.headers["User-Agent"] = config.USER_AGENT

log_file = "data/raw/scrape_log.csv"
new_log = not os.path.exists(log_file)
log = open(log_file, "a", newline="")
writer = csv.writer(log)
if new_log:
    writer.writerow(["timestamp_utc", "platform", "match_id", "url", "status", "file"])

for _, row in urls.iterrows():
    if not robots.can_fetch(config.USER_AGENT, row["event_url"]):
        print("robots.txt says no:", row["event_url"])
        writer.writerow([now.isoformat(), config.PLATFORM, row["match_id"], row["event_url"], "robots_disallowed", ""])
        continue

    # we always ask for 1 ticket, so every snapshot uses the same filter (see justification)
    url = row["event_url"].split("?")[0] + "?quantity=1"
    # robots.txt forbids checkout pages (/buy). Python's robots reader doesn't understand the
    # * and $ wildcards used by Ticombo, so we check this one by hand.
    if url.split("?")[0].rstrip("/").endswith("/buy"):
        print("skipping checkout page (robots.txt):", url)
        continue

    try:
        r = session.get(url, timeout=30)
    except requests.RequestException as e:
        print("error:", row["match_id"], e)
        writer.writerow([now.isoformat(), config.PLATFORM, row["match_id"], row["event_url"], "error", ""])
        continue

    # if the site blocks us (403 / 429 / captcha page) we stop. We decided not to try to get around it.
    # a normal page always contains our data block (ng-state); if it's missing and there is a
    # captcha, we are blocked
    if r.status_code in (403, 429) or ("ng-state" not in r.text and "captcha" in r.text.lower()):
        print("blocked by the platform, stopping this run")
        writer.writerow([now.isoformat(), config.PLATFORM, row["match_id"], row["event_url"], f"blocked_{r.status_code}", ""])
        break

    filename = f"{day_folder}/{stamp}_match_{row['match_id']}.html"
    if os.path.exists(filename):          # never overwrite raw data
        print("already exists, skipping:", filename)
        continue
    with open(filename, "wb") as f:
        f.write(r.content)
    writer.writerow([now.isoformat(), config.PLATFORM, row["match_id"], url, r.status_code, filename])
    print("saved", filename)

    time.sleep(random.uniform(config.MIN_DELAY, config.MAX_DELAY))

log.close()
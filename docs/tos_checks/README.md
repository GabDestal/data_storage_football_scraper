# Terms of service and robots.txt checks

We checked each platform's terms of service and robots.txt **on 27.09.2026, before collecting**. The screenshots in this folder were retaken on **26.11.2026**, because the originals weren't saved.

| File | Source | What it shows |
|---|---|---|
| `ticombo_robots_txt.png` | https://www.ticombo.fr/robots.txt | Only `/*/styleguide/`, `/*/buy$` and `/*/userInfo/*` are disallowed. The event pages we scrape are allowed. `scrape.py` skips `/buy` URLs. |
| `ticombo_tos.png` | https://www.ticombo.fr/en/index/terms-and-conditions/default | Searching the full terms for "scraper" gives 0 results. Read in full on 26.11.2026: the terms ("last updated: August 2026", so in force during our collection) have no clause on robots, spiders, scrapers, crawlers or data mining; "automated" only appears for sellers, who must not buy their tickets with bots. |
| `stubhub/tos_scraper.png` | StubHub terms of use | "use any robot, spider, scraper or other automated means to access our Site or Services for any purpose without our express written permission" is forbidden. This is why StubHub (and viagogo, same group) were rejected. |

Ticombo also needs no login and showed no captcha. We requested one page per match per day, with a delay between requests.

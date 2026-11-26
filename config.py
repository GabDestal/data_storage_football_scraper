# Settings for the data collection. We fixed these before starting so every match
# is collected the same way (see justification.md, section 2).

COMPETITIONS = ["PL", "PD"]          # Premier League, LaLiga (football-data.org codes)
FIRST_KICKOFF = "2026-10-17"         # we track all matches kicking off in this window
LAST_KICKOFF = "2026-11-23"

PLATFORM = "ticombo"                 # kept after the ToS / robots.txt check (see justification.md)
PLATFORM_URL = "https://www.ticombo.fr"   # always the same domain (.fr)

USER_AGENT = "AIDAMS student project - Group G"
MIN_DELAY, MAX_DELAY = 4, 8          # seconds between two requests, to not overload the site
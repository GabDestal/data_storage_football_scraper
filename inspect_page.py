import json, sys, requests
from bs4 import BeautifulSoup
import config

url = sys.argv[1].split("?")[0] + "?quantity=1"
r = requests.get(url, headers={"User-Agent": config.USER_AGENT}, timeout=30)
print("status:", r.status_code, "| size:", len(r.text))

tag = BeautifulSoup(r.text, "html.parser").find("script", id="ng-state")
if tag is None:
    print("no ng-state in the page -> blocked or different page")
    sys.exit()

data = json.loads(tag.string)
for key, value in data.items():
    size = len(value) if hasattr(value, "__len__") else ""
    print(f"- {key[:120]}  ({type(value).__name__} {size})")

# show the first element of anything that looks like listings
for key, value in data.items():
    if "listing" in key.lower():
        first = value[0] if isinstance(value, list) and value else value
        print("\n=== sample from", key[:80], "===")
        print(json.dumps(first, indent=1, ensure_ascii=False)[:2500])
        break

event_key = [k for k in data if k.startswith("/discovery/events/")][0]
event = data[event_key][0]
print("\n=== event fields ===")
for k, v in event.items():
    print(f"{k}: {str(v)[:150]}")
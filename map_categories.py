"""
map_categories.py
Maps each raw Ticombo seat category label to a seat group, with automatic
keyword rules (no stadium-by-stadium manual mapping).

Input : data/categories_v0.csv
Output: data/reference/seat_category_map.csv

Seat groups:
  away         -> away fan sections
  premium      -> VIP, hospitality, boxes, clubs, premium seats
  corner       -> corners
  behind_goal  -> ends of the pitch (shortside, fondo, gol...)
  side         -> along the pitch (longside, tribuna, lateral, preferencia...)
  unmapped     -> no keyword found (e.g. "Categoria 1", "Rio Alto")

Most labels describe WHERE the seat is, not WHO sits there, so we group by
position. English and Spanish words map to the same groups, so PL and LaLiga
can be compared.
"""
import unicodedata
import re
import pandas as pd

INPUT = "data/categories_v0.csv"
OUTPUT = "data/reference/seat_category_map.csv"

# Rules are checked IN THIS ORDER and the first match wins.
# Why this order:
#  - away first: an away section is away whatever the position.
#  - premium before position: "Anfield Road Middle Tier Hospitality" is hospitality.
#  - corner before goal/side: "Esquina Fondo Norte" is a corner.
#  - behind_goal before side: in Spain "Tribuna" is a generic word for stand,
#    so "Tribuna Alta Gol Norte" is behind the goal.
RULES = [
    ("away", ["away", "visiting", "visitors", "visitante", "visitantes"]),
    ("premium", ["vip", "hospitality", "club", "lounge", "bar", "package", "packages",
                 "suite", "platinum", "palco", "palcos", "corporate", "premium",
                 "executive", "box", "dining", "dugout", "offsite", "players zone",
                 "museum", "experience"]),
    ("corner", ["corner", "corners", "esquina"]),
    ("behind_goal", ["shortside", "short side", "fondo", "gol", "goal",
                     "behind the goal"]),
    ("side", ["longside", "long side", "tribuna", "lateral", "preferencia",
              "preferente", "prefrente", "mainstand", "main stand"]),
]

# Second, independent column: which level of the stand.
LEVELS = [
    ("upper", ["upper", "alta", "alto", "superior"]),
    ("middle", ["middle", "media"]),
    ("lower", ["lower", "baja", "bajo", "baixo", "inferior"]),
]


def normalise(label):
    """lowercase, remove accents, keep only letters/digits, single spaces."""
    text = unicodedata.normalize("NFKD", str(label))
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-z0-9]+", " ", text.lower())
    return text.strip()


def find_keyword(norm, keywords):
    """Return the first keyword found as a whole word (or phrase), else None."""
    padded = " " + norm + " "
    for kw in keywords:
        if " " + kw + " " in padded:
            return kw
    return None


def classify(norm):
    """Return (seat_group, matched_keyword, double_match)."""
    hits = []
    for group, keywords in RULES:
        kw = find_keyword(norm, keywords)
        if kw is not None:
            hits.append((group, kw))
    if not hits:
        return "unmapped", "", False
    group, kw = hits[0]
    # A label matching both a side and a goal keyword (e.g. "Lateral Fondo Norte")
    # is flagged so we can check it by hand.
    positions = {g for g, _ in hits if g in ("corner", "behind_goal", "side")}
    double = len(positions) > 1
    return group, kw, double


def find_level(norm):
    for level, keywords in LEVELS:
        if find_keyword(norm, keywords) is not None:
            return level
    return ""


cats = pd.read_csv(INPUT)

# One row per raw label, with how often it appears (to know which labels matter).
labels = (cats.groupby("category")
              .agg(n_rows=("category", "size"),
                   n_tickets=("availableTickets", "sum"),
                   n_matches=("match_id", "nunique"))
              .reset_index()
              # tie-break on the label so labels with the same ticket count always come
              # out in the same order (the default sort is not stable across pandas versions)
              .sort_values(["n_tickets", "category"], ascending=[False, True]))

labels["label_norm"] = labels["category"].apply(normalise)
result = labels["label_norm"].apply(classify)
labels["seat_group"] = [r[0] for r in result]
labels["matched_keyword"] = [r[1] for r in result]
labels["double_match"] = [r[2] for r in result]
labels["level"] = labels["label_norm"].apply(find_level)

cols = ["category", "label_norm", "seat_group", "level", "matched_keyword",
        "double_match", "n_matches", "n_rows", "n_tickets"]
# utf-8-sig like our other CSVs, so Excel shows accents (Categoría) correctly
labels[cols].to_csv(OUTPUT, index=False, encoding="utf-8-sig")
print(f"Wrote {OUTPUT}: {len(labels)} labels")

# --- Checks to report ---
total = labels["n_tickets"].sum()
summary = labels.groupby("seat_group").agg(labels_=("category", "size"),
                                           tickets=("n_tickets", "sum"))
summary["share_tickets_%"] = (100 * summary["tickets"] / total).round(1)
print("\nTickets by seat group (all category snapshots):")
print(summary.sort_values("tickets", ascending=False).to_string())

print("\nDouble matches (check by hand):")
print(labels.loc[labels["double_match"], ["category", "seat_group"]].to_string(index=False))

print("\n30 most frequent labels (check by hand):")
print(labels.head(30)[["category", "seat_group", "level", "matched_keyword"]]
      .to_string(index=False))

print("\nLargest unmapped labels:")
print(labels.loc[labels["seat_group"] == "unmapped", ["category", "n_tickets"]]
      .head(15).to_string(index=False))

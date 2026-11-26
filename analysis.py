#Step 8: analysis. How do the lowest asking prices move in the weeks before a match (A1-A3),
#what explains the differences between matches (A4), seat categories (A5, secondary),
#robustness checks (A6). A0 describes the data first.

#Input : football.db (store.py), data/clean/match_features.csv (features.py),
#        data/clean/quality_summary.json (clean_data.py, used as a check)
#Output: results/figures/a*.png, results/tables/a*.csv,
#        results/summary.txt   one "Observation" and one "Interpretation" line per result

#Choices (see "Locked decisions" and "Analysis plan" in CLAUDE.md):
#  - price = listing_startPrice, the lowest asking price without fees. Fees went from 1.30x to
#    1.35x on 04.11 for some matches, so the fee-included price is only used in A6.
#  - we only see ASKING prices, never transactions: fewer listed tickets is "listed supply".
#  - trajectories use the last 21 days before kickoff. Collection started on 27.09, so the 17
#    matches of 17-18.10 start at day 19-20: each match is indexed to the median price of its
#    14-21 day bin (every match has data there) instead of day 21.
#  - day bins on the exact days before kickoff, rounded down: 0-2, 3-6, 7-13, 14-21 (reference).
#  - descriptive statistics and simple OLS only: results are associations, not causal effects.

import os
import re
import json
import sqlite3
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")  # only write PNG files, never open a window
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import statsmodels.formula.api as smf

os.chdir(os.path.dirname(os.path.abspath(__file__)))
os.makedirs("results/figures", exist_ok=True)
os.makedirs("results/tables", exist_ok=True)

LEAGUES = {"PL": "Premier League", "PD": "LaLiga"}
COLORS = {"PL": "#2a78d6", "PD": "#eb6834"}   # same league colours in every chart
BINS = ["0-2", "3-6", "7-13", "14-21", "22+"]  # days before kickoff; 22+ only in A6
EXAMPLE_MATCH = 560645                         # Liverpool - Man United, the longest derby series
plt.rcParams.update({"axes.spines.top": False, "axes.spines.right": False,
                     "axes.grid": True, "grid.color": "#e5e5e5", "savefig.dpi": 150,
                     "savefig.bbox": "tight"})


# ---------------------------------------------------------------- helpers

def add_day_bins(df):
    """Whole days before kickoff (rounded down) and the bin of the FE model."""
    df = df.copy()
    df["day"] = np.floor(df["days_to_kickoff_exact"]).astype(int)
    df["bin"] = pd.cut(df["day"], [-1, 2, 6, 13, 21, 999], labels=BINS).astype(str)
    return df


def index_to_base(df, col):
    """Value / median of the same match in the 14-21 day bin x 100 (100 = level 2-3 weeks before)."""
    base = df[df["bin"] == "14-21"].groupby("match_id")[col].median().rename("base")
    df = df.merge(base, left_on="match_id", right_index=True)
    df = df[df["base"] > 0].copy()  # a match with nothing listed at 14-21 days has no base
    df["index"] = 100 * df[col] / df["base"]
    return df


def daily_band(df, group):
    """Median and middle 50% of the index per day before kickoff, for each group."""
    return (df.groupby([group, "day"], observed=True)["index"]
              .agg(median="median", q25=lambda s: s.quantile(0.25),
                   q75=lambda s: s.quantile(0.75), n_matches="count")
              .reset_index())


def plot_band(band, group, styles, ylabel, title, name):
    """One line (median) + shaded band (middle 50%) per group, days running towards kickoff."""
    fig, ax = plt.subplots(figsize=(7, 4))
    for key, (label, color, linestyle) in styles.items():
        b = band[band[group] == key]
        ax.plot(b["day"], b["median"], color=color, linestyle=linestyle, lw=2, label=label)
        ax.fill_between(b["day"], b["q25"], b["q75"], color=color, alpha=0.12, lw=0)
    ax.axhline(100, color="grey", lw=0.8)
    ax.set_xlim(20.5, -0.5)  # inverted: kickoff on the right
    ax.set_xticks(range(20, -1, -2))
    ax.set_xlabel("Days before kickoff")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.legend(frameon=False)
    fig.savefig(f"results/figures/{name}.png")
    plt.close(fig)


def fe_model(df, price_col="listing_startPrice"):
    """log(price) ~ day bin + match fixed effects, standard errors clustered by match.
    The match dummies absorb each match's own price level, so a bin coefficient measures how
    the price moves WITHIN a match compared with 14-21 days before kickoff."""
    df = df.copy()
    df["log_price"] = np.log(df[price_col])
    fit = smf.ols("log_price ~ C(bin, Treatment('14-21')) + C(match_id)", data=df).fit(
        cov_type="cluster", cov_kwds={"groups": df["match_id"]})
    rows = []
    for b in [b for b in BINS if b != "14-21" and b in set(df["bin"])]:
        term = f"C(bin, Treatment('14-21'))[T.{b}]"
        coef, se = fit.params[term], fit.bse[term]
        rows.append({"bin": b, "coef_log": coef, "se_log": se, "p_value": fit.pvalues[term],
                     "pct_change": 100 * (np.exp(coef) - 1),   # log points -> % change
                     "ci95_low_pct": 100 * (np.exp(coef - 1.96 * se) - 1),
                     "ci95_high_pct": 100 * (np.exp(coef + 1.96 * se) - 1),
                     "matches_in_bin": df.loc[df["bin"] == b, "match_id"].nunique()})
    out = pd.DataFrame(rows)
    out["n_rows"] = int(fit.nobs)
    out["n_matches"] = df["match_id"].nunique()
    out["n_clusters"] = df["match_id"].nunique()  # one cluster per match
    return out


def pct(x):
    return f"{x:+.1f}%"


# ---------------------------------------------------------------- A0: data description

def a0_description(window, price, pre, all_events, categories, matches):
    # captured match pages per day: shows the collection was daily and where it has gaps
    per_day = all_events.groupby("snapshot_date")["match_id"].nunique()
    days = pd.date_range(per_day.index.min(), per_day.index.max()).strftime("%Y-%m-%d")
    per_day = per_day.reindex(days, fill_value=0)
    fig, ax = plt.subplots(figsize=(8, 3.5))
    ax.bar(pd.to_datetime(per_day.index), per_day.values, color="#52514e", width=0.8)
    for day in per_day[per_day == 0].index:
        ax.annotate("no snapshot", (pd.Timestamp(day), 3), rotation=90, fontsize=8, ha="center")
    ax.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=mdates.MO))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d.%m"))
    ax.set_xlabel("Snapshot date (2026, ticks on Mondays)")
    ax.set_ylabel("Match pages captured")
    ax.set_title("Match pages captured per day")
    fig.savefig("results/figures/a0_snapshots_per_day.png")
    plt.close(fig)

    # share of the listed tickets that the seat categories describe, per snapshot with a price:
    # sum of the category tickets / tickets listed for the whole match
    cat_tickets = categories.groupby(["match_id", "snapshot_utc"])["availableTickets"].sum()
    price = price.join(cat_tickets.rename("category_tickets"), on=["match_id", "snapshot_utc"])
    price["category_tickets"] = price["category_tickets"].fillna(0)

    # coverage table by league
    rows = []
    for comp in ["PL", "PD", "all"]:
        keep = (lambda d: d) if comp == "all" else (lambda d: d[d["competition"] == comp])
        m, p, pr, w = keep(matches), keep(pre), keep(price), keep(window)
        rows.append({"league": LEAGUES.get(comp, "both"), "matches_in_scope": len(m),
                     "matches_with_ticombo_page": int(m["event_uuid"].notna().sum()),
                     "pre_match_snapshots": len(p), "matches_pre_match": p["match_id"].nunique(),
                     "price_snapshots": len(pr), "matches_with_price": pr["match_id"].nunique(),
                     "price_snapshots_21d": len(w), "matches_21d": w["match_id"].nunique(),
                     "median_days_per_match": p.groupby("match_id").size().median(),
                     "category_ticket_share_pct": round(100 * pr["category_tickets"].sum()
                                                        / pr["listing_availableTickets"].sum(), 1)})
    coverage = pd.DataFrame(rows)
    coverage.to_csv("results/tables/a0_coverage.csv", index=False)

    # one example match (peer review 2): the lowest price day by day, every pre-match day
    ex = price[price["match_id"] == EXAMPLE_MATCH].sort_values("days_to_kickoff_exact")
    name = f"{ex['home_team'].iloc[0]} - {ex['away_team'].iloc[0]}"
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(ex["days_to_kickoff_exact"], ex["listing_startPrice"], color=COLORS["PL"],
            lw=2, marker="o", markersize=4)
    ax.invert_xaxis()
    ax.set_xlabel("Days before kickoff")
    ax.set_ylabel("Lowest asking price, without fees (EUR)")
    ax.set_title(f"Example: {name} (North West derby)")
    fig.savefig("results/figures/a0_example_match.png")
    plt.close(fig)
    exw = add_day_bins(ex)
    early, late = (exw.loc[exw["bin"] == b, "listing_startPrice"].median() for b in ["14-21", "0-2"])

    t = coverage.iloc[-1]
    missing = ", ".join(per_day[per_day == 0].index)
    return [
        "A0 - Data description",
        f"Observation: {t.matches_with_ticombo_page} of {t.matches_in_scope} matches have a Ticombo page; "
        f"{t.pre_match_snapshots:,} pre-kickoff daily snapshots, {t.price_snapshots:,} with a price "
        f"({t.matches_with_price} matches), {t.price_snapshots_21d:,} in the last 21 days. "
        f"Days without any snapshot: {missing}. Seat categories describe {t.category_ticket_share_pct}% "
        f"of the listed tickets.",
        f"Observation: example match {name}: median lowest price EUR {early:.0f} at 14-21 days and "
        f"EUR {late:.0f} at 0-2 days, with day-to-day values between EUR {ex['listing_startPrice'].min():.0f} "
        f"and EUR {ex['listing_startPrice'].max():.0f}.",
        "Interpretation: coverage is almost complete in both leagues, so the trajectories are not driven "
        "by a few matches. A single match is noisy"
        + (" (this one even ends higher than 2-3 weeks before, against the average)" if late > early else "")
        + ", which is why we compare medians over many matches and use a regression with match "
        "fixed effects. Categories describe only part of the listed tickets, so seat types stay a "
        "secondary analysis.",
        ""]


# ---------------------------------------------------------------- A1: average trajectory

def a1_trajectory(window):
    idx = index_to_base(window, "listing_startPrice")
    band = daily_band(idx, "competition")
    band.to_csv("results/tables/a1_trajectory_by_day.csv", index=False)
    plot_band(band, "competition",
              {c: (LEAGUES[c], COLORS[c], "-") for c in ["PL", "PD"]},
              "Lowest price, index (14-21 days = 100)",
              "Lowest asking price before kickoff (median, middle 50% shaded)",
              "a1_trajectory_by_league")

    results = []
    for label, df in [("all", window), ("Premier League", window[window["competition"] == "PL"]),
                      ("LaLiga", window[window["competition"] == "PD"])]:
        res = fe_model(df)
        res.insert(0, "sample", label)
        results.append(res)
    fe = pd.concat(results)
    fe.round(4).to_csv("results/tables/a1_fe_regression.csv", index=False)

    main = fe[fe["sample"] == "all"].set_index("bin")
    league = fe[fe["bin"] == "0-2"].set_index("sample")["pct_change"]
    end = band[band["day"] <= 2].groupby("competition")["median"].median()
    return main, [
        "A1 - Average trajectory (lowest price, last 21 days)",
        f"Observation: in the median match the lowest price index is {end['PL']:.0f} (Premier League) and "
        f"{end['PD']:.0f} (LaLiga) in the last 3 days (14-21 days = 100).",
        f"Observation: fixed-effects regression (log price, match fixed effects, SE clustered by match; "
        f"{main['n_rows'].iloc[0]:,} snapshots, {main['n_matches'].iloc[0]} matches): compared with 14-21 days "
        f"before kickoff, the lowest price is {pct(main.loc['7-13', 'pct_change'])} at 7-13 days, "
        f"{pct(main.loc['3-6', 'pct_change'])} at 3-6 days and {pct(main.loc['0-2', 'pct_change'])} at 0-2 days "
        f"(95% CI {main.loc['0-2', 'ci95_low_pct']:.0f}% to {main.loc['0-2', 'ci95_high_pct']:.0f}%); "
        f"Premier League {pct(league['Premier League'])}, LaLiga {pct(league['LaLiga'])} at 0-2 days. "
        f"October preliminary result: -19% (PL -27%, LaLiga -9%).",
        "Interpretation: within the same match, the cheapest ticket on offer gets cheaper as kickoff "
        "approaches, mostly in the last week, and more in the Premier League. This fits sellers cutting "
        "their asking price before the ticket loses its value, but also new cheaper listings or expensive "
        "ones being withdrawn: without listing IDs we cannot tell these apart. The direction of the "
        "October result holds on the final data, with a larger drop.",
        ""]


# ---------------------------------------------------------------- A2: different paths

def a2_paths(window):
    idx = index_to_base(window, "listing_startPrice")
    end = idx[idx["bin"] == "0-2"].groupby("match_id")["index"].median()  # 2 matches have no 0-2 data
    league = idx.groupby("match_id")["competition"].first()
    change = (end / 100 - 1).rename("change").to_frame().join(league)

    rows = []
    for band in [0.05, 0.10]:  # +/-5% is the main rule, +/-10% shows how much it depends on it
        path = np.select([change["change"] < -band, change["change"] > band],
                         ["falling", "rising"], "flat")
        for comp in ["PL", "PD", "all"]:
            keep = (change["competition"] == comp) if comp != "all" else np.full(len(change), True)
            counts = pd.Series(path[keep]).value_counts()
            n = int(keep.sum())
            rows.append({"flat_band_pct": int(band * 100), "league": LEAGUES.get(comp, "both"),
                         "n_matches": n, **{p: int(counts.get(p, 0)) for p in ["falling", "flat", "rising"]},
                         **{f"{p}_pct": round(100 * counts.get(p, 0) / n, 1)
                            for p in ["falling", "flat", "rising"]}})
    paths = pd.DataFrame(rows)
    paths.to_csv("results/tables/a2_paths.csv", index=False)

    # thirds of matches by their price level 14-21 days before (cheap / middle / expensive)
    base = idx.groupby("match_id")["base"].first()
    third = pd.qcut(base, 3, labels=["cheapest third", "middle third", "most expensive third"])
    idx["third"] = idx["match_id"].map(third)
    band = daily_band(idx, "third")
    band.to_csv("results/tables/a2_trajectory_by_price_third.csv", index=False)
    plot_band(band, "third",
              {"cheapest third": (f"Cheapest third (below EUR {base.quantile(1/3):.0f})", "#b7aef0", ":"),
               "middle third": ("Middle third", "#7f72e0", "--"),
               "most expensive third": (f"Most expensive third (above EUR {base.quantile(2/3):.0f})", "#3b2fa0", "-")},
              "Lowest price, index (14-21 days = 100)",
              "Lowest asking price before kickoff, by price level of the match",
              "a2_trajectory_by_price_third")
    by_third = band[band["day"] <= 2].groupby("third", observed=True)["median"].median()

    main = paths[(paths["flat_band_pct"] == 5)].set_index("league")
    wide = paths[(paths["flat_band_pct"] == 10)].set_index("league")
    return [
        "A2 - Do all matches behave alike?",
        f"Observation: comparing the median lowest price at 0-2 days with 14-21 days ({main.loc['both', 'n_matches']} "
        f"matches with both), {main.loc['both', 'falling_pct']:.0f}% of matches fall by more than 5%, "
        f"{main.loc['both', 'flat_pct']:.0f}% stay within +/-5% and {main.loc['both', 'rising_pct']:.0f}% rise "
        f"(Premier League falling {main.loc['Premier League', 'falling_pct']:.0f}%, LaLiga "
        f"{main.loc['LaLiga', 'falling_pct']:.0f}%; with a +/-10% band: {wide.loc['both', 'falling_pct']:.0f}% "
        f"falling, {wide.loc['both', 'rising_pct']:.0f}% rising).",
        f"Observation: index in the last 3 days by price level of the match: cheapest third "
        f"{by_third['cheapest third']:.0f}, middle {by_third['middle third']:.0f}, most expensive "
        f"{by_third['most expensive third']:.0f}.",
        "Interpretation: a falling lowest price is the most common path but not a rule, so the A1 result "
        "describes the typical match, not every match. The drop is concentrated in the more expensive "
        "matches, while the cheapest ones hardly move (possibly less room to cut an already low price). "
        "Part of this gap can be regression to the mean (a match can look expensive at 14-21 days by chance).",
        ""]


# ---------------------------------------------------------------- A3: listed supply

def a3_supply(window_pre, window):
    # supply uses every pre-kickoff day, including days with 0 tickets listed
    supply = window_pre.copy()
    supply["tickets"] = supply["listing_availableTickets"].fillna(0)
    idx = index_to_base(supply, "tickets")
    band = daily_band(idx, "competition")
    band.to_csv("results/tables/a3_supply_by_day.csv", index=False)
    plot_band(band, "competition",
              {c: (LEAGUES[c], COLORS[c], "-") for c in ["PL", "PD"]},
              "Tickets listed, index (14-21 days = 100)",
              "Listed supply before kickoff (median, middle 50% shaded)",
              "a3_supply_by_league")

    # do supply and price move together from one day to the next, within a match?
    # only pairs of consecutive calendar days (no jump over 03.10 or no-listing days)
    d = window.sort_values(["match_id", "snapshot_date"]).copy()
    d["date"] = pd.to_datetime(d["snapshot_date"])
    g = d.groupby("match_id")
    d["d_log_price"] = np.log(d["listing_startPrice"]) - np.log(g["listing_startPrice"].shift())
    d["d_log_tickets"] = np.log(d["listing_availableTickets"]) - np.log(g["listing_availableTickets"].shift())
    d["gap_days"] = (d["date"] - g["date"].shift()).dt.days
    pairs = d[d["gap_days"] == 1]
    per_match = {}
    for match_id, m in pairs.groupby("match_id"):
        # at least 5 day pairs, and both series must move (a constant series has no correlation)
        if len(m) >= 5 and m["d_log_price"].std() > 0 and m["d_log_tickets"].std() > 0:
            per_match[match_id] = m["d_log_price"].corr(m["d_log_tickets"])
    per_match = pd.Series(per_match)
    corr = pd.DataFrame([{"n_day_pairs": len(pairs), "n_matches": pairs["match_id"].nunique(),
                          "pooled_correlation": pairs["d_log_price"].corr(pairs["d_log_tickets"]),
                          "matches_in_per_match_corr": len(per_match),
                          "median_match_correlation": per_match.median(),
                          "share_matches_negative_pct": 100 * (per_match < 0).mean()}])
    corr.round(3).to_csv("results/tables/a3_supply_price_corr.csv", index=False)

    end = band[band["day"] <= 2].groupby("competition")["median"].median()
    last_day = band[band["day"] == 0].set_index("competition")["median"]
    c = corr.iloc[0]
    return [
        "A3 - Listed supply",
        f"Observation: in the median match the number of tickets listed is at index {end['PL']:.0f} "
        f"(Premier League) and {end['PD']:.0f} (LaLiga) in the last 3 days and {last_day['PL']:.0f} / "
        f"{last_day['PD']:.0f} on the last day (14-21 days = 100; {idx['match_id'].nunique()} matches "
        f"with tickets listed at 14-21 days).",
        f"Observation: from one day to the next within a match, changes in tickets listed and in the "
        f"lowest price have a correlation of {c.pooled_correlation:.2f} ({int(c.n_day_pairs):,} day pairs, "
        f"{int(c.n_matches)} matches); median correlation per match {c.median_match_correlation:.2f}, "
        f"negative in {c.share_matches_negative_pct:.0f}% of matches.",
        "Interpretation: listed supply stays flat until the last week and then shrinks quickly, most on "
        "the last day. Day-to-day changes in supply and in the lowest price are almost unrelated "
        "(correlation close to 0), so the price drop is not simply more tickets on offer. A change in "
        "listed tickets can be a ticket sold, withdrawn or newly listed: we read it as listed supply only.",
        ""]


# ---------------------------------------------------------------- A4: differences between matches

A4_TERMS = {"C(competition)[T.PL]": "Premier League (vs LaLiga)", "best_rank": "best rank (+1 place)",
            "rank_gap": "rank gap (+1 place)", "weekend": "weekend", "derby": "derby"}


def a4_model(price, features):
    """One row per match + the small OLS of A4 (also rerun in A6 without the top 1% prices)."""
    # price level of each match: median lowest price 7-14 days before kickoff, a period that
    # (almost) every match has and that is before the drop of the last days
    level = (price[(price["days_to_kickoff_exact"] >= 7) & (price["days_to_kickoff_exact"] <= 14)]
             .groupby(["match_id", "competition", "home_team", "away_team"])["listing_startPrice"]
             .median().rename("price").reset_index())
    df = level.merge(features, on="match_id", how="left")
    assert df["best_rank"].notna().all(), "a match has no features"
    df["weekend"] = df["weekend"].astype(int)
    df["derby"] = df["derby"].astype(int)
    # small model (94 matches): league and team rank are the main factors, weekend and derby
    # secondary; HC1 standard errors because the spread of prices differs between matches
    fit = smf.ols("np.log(price) ~ C(competition) + best_rank + rank_gap + weekend + derby",
                  data=df).fit(cov_type="HC1")
    return df, fit


def a4_between(price, features):
    df, fit = a4_model(price, features)
    df["rank_group"] = pd.cut(df["best_rank"], [0, 4, 10, 20], labels=["top 4", "5-10", "11-20"])

    rows = []
    for col, labels in [("competition", LEAGUES), ("weekend", {1: "weekend", 0: "weekday"}),
                        ("derby", {1: "derby", 0: "no derby"}),
                        ("rank_group", {"top 4": "best team top 4", "5-10": "best team 5-10",
                                        "11-20": "best team 11-20"})]:
        for value, label in labels.items():
            p = df.loc[df[col] == value, "price"]
            rows.append({"variable": col, "group": label, "n_matches": len(p),
                         "median_price_eur": round(p.median(), 1)})
    pd.DataFrame(rows).to_csv("results/tables/a4_price_by_group.csv", index=False)

    ols = pd.DataFrame({"term": list(A4_TERMS.values()),
                        "coef_log": [fit.params[t] for t in A4_TERMS],
                        "se_hc1": [fit.bse[t] for t in A4_TERMS],
                        "p_value": [fit.pvalues[t] for t in A4_TERMS],
                        "pct_effect": [100 * (np.exp(fit.params[t]) - 1) for t in A4_TERMS]})
    ols["n_matches"] = int(fit.nobs)
    ols["r_squared"] = fit.rsquared
    ols.round(4).to_csv("results/tables/a4_ols.csv", index=False)

    fig, ax = plt.subplots(figsize=(7, 4))
    for comp in ["PL", "PD"]:
        s = df[df["competition"] == comp]
        ax.scatter(s["best_rank"], s["price"], color=COLORS[comp], s=30, label=LEAGUES[comp],
                   edgecolor="white", linewidth=0.8)
    for _, top in df.nlargest(2, "price").iterrows():  # name only the two most expensive matches
        ax.annotate(f"{top['home_team']} - {top['away_team']}", (top["best_rank"], top["price"]),
                    xytext=(6, -3), textcoords="offset points", fontsize=8)
    ax.set_yscale("log")  # prices are skewed: a log scale keeps the cheap matches readable
    ax.set_xticks(range(1, 21))
    ax.set_xlabel("Best league position of the two teams at kickoff (1 = leader)")
    ax.set_ylabel("Median lowest price 7-14 days before (EUR, log scale)")
    ax.set_title("Price level of each match vs the better team's position")
    ax.legend(frameon=False)
    fig.savefig("results/figures/a4_price_vs_best_rank.png")
    plt.close(fig)

    o = ols.set_index("term")
    med = df.groupby("weekend")["price"].median()
    return [
        "A4 - What explains differences between matches",
        f"Observation: OLS on {int(fit.nobs)} matches (log of the median lowest price 7-14 days before, "
        f"HC1 SE, R2 = {fit.rsquared:.2f}): each place further down the table for the better of the two "
        f"teams goes with "
        f"{pct(o.loc['best rank (+1 place)', 'pct_effect'])} (p = {o.loc['best rank (+1 place)', 'p_value']:.3f}); "
        f"weekend {pct(o.loc['weekend', 'pct_effect'])} (p = {o.loc['weekend', 'p_value']:.3f}); "
        f"derby {pct(o.loc['derby', 'pct_effect'])} (p = {o.loc['derby', 'p_value']:.3f}, only "
        f"{df['derby'].sum()} derbies); Premier League vs LaLiga {pct(o.loc['Premier League (vs LaLiga)', 'pct_effect'])} "
        f"(p = {o.loc['Premier League (vs LaLiga)', 'p_value']:.2f}); rank gap "
        f"{pct(o.loc['rank gap (+1 place)', 'pct_effect'])} (p = {o.loc['rank gap (+1 place)', 'p_value']:.2f}).",
        f"Observation: median price EUR {med[1]:.0f} for weekend matches ({(df['weekend'] == 1).sum()}) vs "
        f"EUR {med[0]:.0f} on weekdays ({(df['weekend'] == 0).sum()}). October preliminary result: weekend +40%.",
        "Interpretation: matches involving a team high in the table, weekend matches and derbies are "
        "associated with higher asking prices, while the league itself adds little once these are taken "
        "into account. These are descriptive associations, not causal effects: there are few weekday "
        "matches and derbies, and most of the variation stays unexplained. The weekend association is "
        "the only one that survives dropping the top 1% prices (A6); the best-rank and derby "
        "associations depend on a few extreme matches.",
        ""]


# ---------------------------------------------------------------- A5: seat categories (secondary)

def a5_seats(categories):
    cats = add_day_bins(categories[categories["in_window_21d"] == 1])
    # one value per match, snapshot and seat group: the median of its categories' average prices
    grp = (cats.groupby(["match_id", "snapshot_utc", "day", "bin", "seat_group"])
               .agg(price=("averagePrice", "median"), tickets=("availableTickets", "sum"))
               .reset_index())
    rows, bands = [], []
    for group, g in grp.groupby("seat_group"):
        g = g.copy()
        g["match_id"] = g["match_id"].astype(str) + "_" + group  # index each match x group separately
        idx = index_to_base(g, "price")
        end = idx[idx["bin"] == "0-2"]["index"].median()
        rows.append({"seat_group": group, "n_matches": idx["match_id"].nunique(),
                     "ticket_share_pct": round(100 * g["tickets"].sum() / grp["tickets"].sum(), 1),
                     "median_price_14_21_eur": round(idx.groupby("match_id")["base"].first().median(), 1),
                     "median_index_0_2": round(end, 1)})
        b = daily_band(idx.assign(seat_group=group), "seat_group")
        bands.append(b)
    table = pd.DataFrame(rows).sort_values("ticket_share_pct", ascending=False)
    table.to_csv("results/tables/a5_seat_groups.csv", index=False)
    band = pd.concat(bands)
    # only the 3 biggest groups in the chart; the others are in the table
    plot_band(band, "seat_group",
              {"side": ("Side", "#1baf7a", "-"), "behind_goal": ("Behind the goal", "#6250d6", "--"),
               "premium": ("Premium / hospitality", "#eda100", ":")},
              "Category average price, index (14-21 days = 100)",
              "Seat categories before kickoff (median, middle 50% shaded)",
              "a5_seat_groups")

    t = table.set_index("seat_group")
    return [
        "A5 - Seat categories (secondary: categories describe only part of the listed tickets)",
        "Observation: median category price 14-21 days before / index at 0-2 days: " + "; ".join(
            f"{g.replace('_', ' ')} EUR {t.loc[g, 'median_price_14_21_eur']:.0f} / {t.loc[g, 'median_index_0_2']:.0f}"
            for g in ["side", "behind_goal", "premium", "corner", "away"] if g in t.index) + ".",
        "Interpretation: premium seats are the most expensive, but the three big groups (side, behind the "
        "goal, premium: most category tickets) all end below their level 2-3 weeks before, so the drop "
        "is not limited to one type of seat; corner seats (very few matches) are too few to read. The "
        "drop is smaller than in A1 because a category price is an average over all its listings, "
        "not the cheapest one.",
        ""]


# ---------------------------------------------------------------- A6: robustness

def a6_robustness(window, price, features):
    variants = [
        ("main: base price, last 21 days", window, "listing_startPrice"),
        ("fees included", window, "listing_finalStartPrice"),
        ("without top 1% prices", window[window["flag_extreme_price"] == 0], "listing_startPrice"),
        ("Premier League only", window[window["competition"] == "PL"], "listing_startPrice"),
        ("LaLiga only", window[window["competition"] == "PD"], "listing_startPrice"),
        ("all pre-match days (22+ bin added)", price, "listing_startPrice"),
    ]
    results = []
    for label, df, col in variants:
        res = fe_model(df, col)
        res.insert(0, "variant", label)
        results.append(res)
    rob = pd.concat(results)
    rob.round(4).to_csv("results/tables/a6_robustness.csv", index=False)

    # A4 again without the top 1% snapshots (a match whose 7-14 day prices are all extreme drops out)
    df_all, _ = a4_model(price, features)
    df, fit = a4_model(price[price["flag_extreme_price"] == 0], features)
    dropped = df_all[~df_all["match_id"].isin(df["match_id"])]
    dropped_names = ", ".join(dropped["home_team"] + " - " + dropped["away_team"])
    a4 = pd.DataFrame({"term": list(A4_TERMS.values()),
                       "pct_effect": [100 * (np.exp(fit.params[t]) - 1) for t in A4_TERMS],
                       "p_value": [fit.pvalues[t] for t in A4_TERMS]})
    a4["n_matches"] = int(fit.nobs)
    a4.round(4).to_csv("results/tables/a6_a4_without_top1pct.csv", index=False)

    last = rob[rob["bin"] == "0-2"].set_index("variant")
    a4 = a4.set_index("term")
    extreme = window[window["flag_extreme_price"] == 1]
    top_match = extreme["match_id"].value_counts()
    top_name = window.loc[window["match_id"] == top_match.index[0], ["home_team", "away_team"]].iloc[0]
    return [
        "A6 - Robustness",
        "Observation: 0-2 days vs 14-21 days (same FE model): "
        + "; ".join(f"{v} {pct(r['pct_change'])}" for v, r in last.iterrows()) + ".",
        f"Observation: {top_match.iloc[0]} of the {len(extreme)} top 1% snapshots in the 21-day window are "
        f"{top_name['home_team']} - {top_name['away_team']}, a genuinely expensive match, not a data error.",
        f"Observation: A4 without the top 1% snapshots ({int(fit.nobs)} matches, {dropped_names} drop out): best rank "
        f"{pct(a4.loc['best rank (+1 place)', 'pct_effect'])} (p = {a4.loc['best rank (+1 place)', 'p_value']:.3f}), "
        f"weekend {pct(a4.loc['weekend', 'pct_effect'])} (p = {a4.loc['weekend', 'p_value']:.3f}), "
        f"derby {pct(a4.loc['derby', 'pct_effect'])} (p = {a4.loc['derby', 'p_value']:.3f}).",
        f"Interpretation: the drop in the last days keeps the same sign whatever the price measure, the "
        f"extreme prices or the window (between {last['pct_change'].max():.0f}% and "
        f"{last['pct_change'].min():.0f}%, the leagues being the two ends), so the main result does not "
        f"depend on these choices. Between matches (A4), the weekend association is the only one that "
        f"survives dropping the top 1%; best rank and derby depend on a few extreme matches "
        f"({dropped_names}).",
        ""]


# ---------------------------------------------------------------- A7: does the drop depend on the teams?

def a7_top_team_drop(window, features):
    """A1's FE model with an interaction: is the late drop different for matches with a top-4 team?
    The match dummies already absorb each match's price level (so 'top 4' alone is not in the
    model); the interaction measures whether the WITHIN-match drop differs."""
    df = window.merge(features[["match_id", "best_rank"]], on="match_id", how="left")
    df["top4"] = (df["best_rank"] <= 4).astype(int)  # same cut as the A4 rank groups
    df["log_price"] = np.log(df["listing_startPrice"])
    # interaction dummies written out by hand, with 14-21 days as reference (a 14-21 x top4 term
    # would be the same as the match dummies of the top-4 matches, so it must be left out)
    names = {"7-13": "top4_7_13", "3-6": "top4_3_6", "0-2": "top4_0_2"}
    for b, name in names.items():
        df[name] = ((df["bin"] == b) & (df["top4"] == 1)).astype(int)
    fit = smf.ols("log_price ~ C(bin, Treatment('14-21')) + " + " + ".join(names.values())
                  + " + C(match_id)", data=df).fit(cov_type="cluster", cov_kwds={"groups": df["match_id"]})
    rows = []
    for b in ["7-13", "3-6", "0-2"]:
        base = fit.params[f"C(bin, Treatment('14-21'))[T.{b}]"]
        inter = names[b]
        rows.append({"bin": b,
                     "pct_change_other": 100 * (np.exp(base) - 1),
                     "pct_change_top4": 100 * (np.exp(base + fit.params[inter]) - 1),
                     "interaction_log": fit.params[inter], "interaction_p": fit.pvalues[inter]})
    out = pd.DataFrame(rows)
    n_top4 = df.loc[df["top4"] == 1, "match_id"].nunique()
    out["matches_top4"] = n_top4
    out["matches_other"] = df["match_id"].nunique() - n_top4
    out.round(4).to_csv("results/tables/a7_drop_by_top4.csv", index=False)

    last = out.set_index("bin").loc["0-2"]
    return [
        "A7 - Does the drop depend on the teams? (match with a top-4 team at kickoff vs others)",
        f"Observation: same FE model as A1 with a 'day bin x top-4 team' interaction ({n_top4} matches with a "
        f"top-4 team, {out['matches_other'].iloc[0]} others): at 0-2 days the lowest price is "
        f"{pct(last['pct_change_top4'])} for matches with a top-4 team and {pct(last['pct_change_other'])} for "
        f"the others, compared with 14-21 days before (difference p = {last['interaction_p']:.2f}).",
        "Interpretation: "
        + ("the late drop is clearly different for matches with a top-4 team. "
           if last["interaction_p"] < 0.05 else
           "we cannot say the late drop differs between matches with and without a top-4 team: the "
           "difference is not statistically clear with this number of matches. ")
        + "A smaller drop for big-club matches would fit sellers being able to wait for buyers, but these "
        "are associations between asking prices, not causal effects.",
        ""]


# ---------------------------------------------------------------- A8: when is the lowest price reached?

def a8_lowest_day(window):
    """For each match, the day (in the last 21 days) with the lowest asking price, and how far
    below its 14-21 day level that minimum is. One snapshot per day, so this is the cheapest
    DAILY snapshot, not the cheapest moment."""
    idx = index_to_base(window, "listing_startPrice")
    # the lowest snapshot of each match (if two days tie, keep the one closest to kickoff)
    low = (idx.sort_values(["match_id", "listing_startPrice", "day"])
              .groupby("match_id").first().reset_index())
    low["bin"] = pd.cut(low["day"], [-1, 2, 6, 13, 21], labels=["0-2", "3-6", "7-13", "14-21"])
    table = (low.groupby("bin", observed=False)
                .agg(n_matches=("match_id", "size"), median_index_at_low=("index", "median"))
                .reset_index())
    table["share_pct"] = (100 * table["n_matches"] / len(low)).round(1)
    table.to_csv("results/tables/a8_lowest_price_day.csv", index=False)

    # chart: number of matches reaching their lowest price on each day, stacked by league
    counts = low.groupby(["day", "competition"]).size().unstack(fill_value=0).reindex(range(22), fill_value=0)
    fig, ax = plt.subplots(figsize=(7, 4))
    bottom = np.zeros(len(counts))
    for comp in ["PL", "PD"]:
        vals = counts[comp].values if comp in counts else np.zeros(len(counts))
        ax.bar(counts.index, vals, bottom=bottom, color=COLORS[comp], label=LEAGUES[comp], width=0.8)
        bottom += vals
    ax.set_xlim(21.5, -0.5)  # inverted: kickoff on the right, like the other charts
    ax.set_xticks(range(20, -1, -2))
    ax.set_xlabel("Days before kickoff")
    ax.set_ylabel("Number of matches")
    ax.set_title("Day on which each match had its lowest asking price (last 21 days)")
    ax.legend(frameon=False)
    fig.savefig("results/figures/a8_lowest_price_day.png")
    plt.close(fig)

    t = table.set_index("bin")
    by_league = low.groupby("competition")["day"].median()
    return [
        "A8 - When is the lowest price reached? (last 21 days, one snapshot per day)",
        f"Observation: of {len(low)} matches, {t.loc['0-2', 'share_pct']:.0f}% have their lowest daily asking "
        f"price 0-2 days before kickoff, {t.loc['3-6', 'share_pct']:.0f}% at 3-6 days, "
        f"{t.loc['7-13', 'share_pct']:.0f}% at 7-13 days and {t.loc['14-21', 'share_pct']:.0f}% at 14-21 days. "
        f"Median number of days before kickoff of the lowest price: {low['day'].median():.0f} "
        f"(Premier League {by_league['PL']:.0f}, LaLiga {by_league['PD']:.0f}). On its lowest day the price is "
        f"at a median index of {low['index'].median():.0f} (14-21 days = 100).",
        "Interpretation: for most matches the cheapest asking price comes in the last days before kickoff, "
        "consistent with A1, but about one match in five is cheapest 1-3 weeks before. Waiting is usually "
        "but not always cheaper, and the lowest price may be a single listing that does not last.",
        ""]


# ---------------------------------------------------------------- A9: most and least expensive matches

def a9_extremes(price, features):
    """The 5 most and 5 least expensive matches, on the A4 price level (median lowest price
    7-14 days before kickoff). Makes the A4 associations concrete."""
    df, _ = a4_model(price, features)
    df["match"] = df["home_team"] + " - " + df["away_team"]
    # listed supply over the same 7-14 days, to see whether cheap matches simply have many tickets
    tickets = (price[(price["days_to_kickoff_exact"] >= 7) & (price["days_to_kickoff_exact"] <= 14)]
               .groupby("match_id")["listing_availableTickets"].median().rename("tickets"))
    df = df.merge(tickets, left_on="match_id", right_index=True, how="left")
    top = df.nlargest(5, "price").assign(group="most expensive")
    bottom = df.nsmallest(5, "price").assign(group="least expensive")
    both = pd.concat([top, bottom])
    cols = ["group", "match", "competition", "price", "tickets", "best_rank", "rank_gap", "weekend", "derby"]
    both[cols].round(1).to_csv("results/tables/a9_most_least_expensive.csv", index=False)

    # chart: horizontal bars, most expensive at the top, league colours
    plot = pd.concat([top, bottom.iloc[::-1]]).iloc[::-1]
    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.barh(plot["match"], plot["price"], color=[COLORS[c] for c in plot["competition"]])
    ax.set_xscale("log")  # El Clasico would flatten every other bar on a linear scale
    ax.set_xticks([25, 50, 100, 250, 500, 1000])
    ax.set_xticklabels(["25", "50", "100", "250", "500", "1,000"])
    ax.axhline(4.5, color="grey", lw=0.8, linestyle="--")  # between the two groups
    handles = [matplotlib.patches.Patch(color=COLORS[c], label=LEAGUES[c]) for c in ["PL", "PD"]]
    ax.set_xlabel("Median lowest price 7-14 days before kickoff (EUR, log scale)")
    ax.set_title("The 5 most and 5 least expensive matches")
    ax.legend(handles=handles, frameon=False, loc="lower right")
    ax.grid(axis="y", visible=False)
    fig.savefig("results/figures/a9_most_least_expensive.png")
    plt.close(fig)

    def describe(d):
        return "; ".join(f"{r['match']} EUR {r['price']:.0f}" for _, r in d.iterrows())
    return [
        "A9 - Most and least expensive matches (median lowest price 7-14 days before kickoff)",
        f"Observation: most expensive: {describe(top)}. Least expensive: {describe(bottom)}.",
        f"Observation: derbies: {int(top['derby'].sum())} of the 5 most expensive, {int(bottom['derby'].sum())} of "
        f"the 5 cheapest; weekend: {int(top['weekend'].sum())} vs {int(bottom['weekend'].sum())}; median best "
        f"rank of the two teams: {top['best_rank'].median():.0f} vs {bottom['best_rank'].median():.0f}. "
        f"{home_team_note(bottom, df)}",
        f"Observation: median tickets listed 7-14 days before: {top['tickets'].median():,.0f} for the 5 most "
        f"expensive, {bottom['tickets'].median():,.0f} for the 5 cheapest, {df['tickets'].median():,.0f} for all matches.",
        "Interpretation: team rank alone does not separate the extremes: a top team can play at both ends. "
        "The cheapest matches have far more tickets listed, which fits a large supply of resale tickets "
        "keeping the lowest asking price down; the most expensive one is a thin market (Hull City - Brighton "
        "had 4 tickets at EUR 1,500 for six days, see limitations). These ten matches illustrate A4 and its "
        "limits; they do not add evidence to it.",
        ""]


def home_team_note(bottom, df):
    """Names a home team that appears several times among the cheapest matches, with its supply."""
    counts = bottom["home_team"].value_counts()
    if counts.iloc[0] < 2:
        return ""
    team = counts.index[0]
    t = df.loc[df["home_team"] == team, "tickets"].median()
    return (f"{team} is the home team in {counts.iloc[0]} of the 5 cheapest matches, with a median of "
            f"{t:,.0f} tickets listed (all matches: {df['tickets'].median():.0f}).")


# ---------------------------------------------------------------- run everything

con = sqlite3.connect("football.db")
matches = pd.read_sql("SELECT * FROM matches", con)
all_events = pd.read_sql("SELECT match_id, snapshot_date FROM event_snapshots WHERE flag_duplicate_day = 0", con)
pre = pd.read_sql("""
    SELECT e.*, m.competition, m.home_team, m.away_team
    FROM event_snapshots e JOIN matches m ON m.match_id = e.match_id
    WHERE e.eligible_pre_match = 1""", con)
# categories only on snapshots with a usable price: this also drops category rows on pages
# whose match total says 0 tickets
categories = pd.read_sql("""
    SELECT c.match_id, c.snapshot_utc, c.averagePrice, c.availableTickets, s.seat_group,
           e.days_to_kickoff_exact, e.in_window_21d
    FROM category_snapshots c
    JOIN seat_categories s ON s.category = c.category
    JOIN event_snapshots e ON e.match_id = c.match_id AND e.snapshot_utc = c.snapshot_utc
    WHERE e.eligible_price = 1""", con)
con.close()
features = pd.read_csv("data/clean/match_features.csv", encoding="utf-8-sig")
with open("data/clean/quality_summary.json") as f:
    quality = json.load(f)

pre = add_day_bins(pre)
price = pre[pre["eligible_price"] == 1]
window = price[price["in_window_21d"] == 1]
window_pre = pre[pre["in_window_21d"] == 1]

# checks: the analysis sample is exactly the one described by clean_data.py
assert len(window) == quality["eligible_price_in_window_21d"]
assert price["match_id"].nunique() == quality["eligible_price_matches"]
assert set(window.loc[window["bin"] == "14-21", "match_id"]) == set(price["match_id"]), \
    "a match has no data 14-21 days before kickoff (no base for its index)"
assert (window["listing_startPrice"] > 0).all() and (window["listing_finalStartPrice"] > 0).all()

summary = a0_description(window, price, pre, all_events, categories, matches)
fe_main, lines = a1_trajectory(window)
summary += lines
assert fe_main["n_rows"].iloc[0] == len(window) and fe_main["n_clusters"].iloc[0] == window["match_id"].nunique()
summary += a2_paths(window)
summary += a3_supply(window_pre, window)
summary += a4_between(price, features)
summary += a5_seats(categories)
summary += a6_robustness(window, price, features)
# extra analyses for the presentation
summary += a7_top_team_drop(window, features)
summary += a8_lowest_day(window)
summary += a9_extremes(price, features)

text = "\n".join(summary)
# wording rule of the project: asking prices and listed supply only
assert not re.search(r"\b(sales|sold out|demand)\b", text, re.IGNORECASE), "forbidden wording in summary"
with open("results/summary.txt", "w", encoding="utf-8") as f:
    f.write(text)
print(text)
print("figures:", sorted(os.listdir("results/figures")))
print("tables :", sorted(os.listdir("results/tables")))

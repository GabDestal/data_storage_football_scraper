#Compare three ways of storing the same data, for the "Storage" section of the report.

#Input : football.db (from store.py), data/clean/*_all_clean.csv, data/reference/matches.csv
#Output: data/parquet/*.parquet (the 5 tables of football.db, one file each)
#        results/tables/storage_comparison.csv

#The three options:
#  CSV      the flat files from clean_data.py, read with pandas (no types, no keys,
#           match columns repeated on every row)
#  SQLite   football.db: 5 normalised tables with primary and foreign keys (our choice)
#  Parquet  the same 5 tables as Parquet files, queried with DuckDB (columnar format,
#           built for large analytical queries)

#For each option we measure the size on disk and the time of the same typical query:
#"average lowest price (base price, our main measure) per league and per day before kickoff, over the
#usable snapshots in the 21-day window". Each query is repeated and we keep the median time.
#Our data is small, so the times are all short: the point is the order of magnitude.

import os
import time
import sqlite3
import duckdb
import pandas as pd

os.chdir(os.path.dirname(os.path.abspath(__file__)))
os.makedirs("data/parquet", exist_ok=True)
os.makedirs("results/tables", exist_ok=True)
N_RUNS = 20
TABLES = ["matches", "standings", "event_snapshots", "seat_categories", "category_snapshots"]

# --- 1. export the SQLite tables to Parquet (same content, other format) ---
con = sqlite3.connect("football.db")
for table in TABLES:
    pd.read_sql(f"SELECT * FROM {table}", con).to_parquet(f"data/parquet/{table}.parquet", index=False)
con.close()


# --- 2. the same query in each format ---
def query_csv():
    # with flat CSVs everything is read into memory, then filtered with pandas
    events = pd.read_csv("data/clean/events_all_clean.csv", encoding="utf-8-sig")
    matches = pd.read_csv("data/reference/matches.csv", encoding="utf-8-sig")
    df = events[events["eligible_price"] & events["in_window_21d"]]
    df = df.merge(matches[["match_id", "competition"]], on="match_id")
    df["day"] = df["days_to_kickoff_exact"].astype(int)  # same as CAST in SQL
    out = df.groupby(["competition", "day"])["listing_startPrice"].agg(["count", "mean"])
    return out.reset_index()


SQL = """
SELECT m.competition,
       CAST(e.days_to_kickoff_exact AS INTEGER) AS day,
       COUNT(*) AS count,
       AVG(e.listing_startPrice) AS mean
FROM event_snapshots e
JOIN matches m ON m.match_id = e.match_id
WHERE e.eligible_price = 1 AND e.in_window_21d = 1
GROUP BY 1, 2
ORDER BY 1, 2
"""


def query_sqlite():
    con = sqlite3.connect("football.db")
    out = pd.read_sql(SQL, con)
    con.close()
    return out


def query_duckdb():
    con = duckdb.connect()  # in memory: DuckDB reads the Parquet files directly
    for table in TABLES:
        con.execute(f"CREATE VIEW {table} AS SELECT * FROM 'data/parquet/{table}.parquet'")
    # DuckDB rounds when casting to INTEGER; SQLite and pandas truncate -> use TRUNC
    out = con.execute(SQL.replace("CAST(e.days_to_kickoff_exact AS INTEGER)",
                                  "CAST(TRUNC(e.days_to_kickoff_exact) AS INTEGER)")).df()
    con.close()
    return out


def median_time(func):
    times = []
    for _ in range(N_RUNS):
        start = time.perf_counter()
        func()
        times.append(time.perf_counter() - start)
    return pd.Series(times).median() * 1000  # milliseconds


# --- 3. check that the three formats give the same answer ---
results = {"CSV": query_csv(), "SQLite": query_sqlite(), "Parquet + DuckDB": query_duckdb()}
reference = results["SQLite"].sort_values(["competition", "day"]).reset_index(drop=True)
for name, out in results.items():
    out = out.sort_values(["competition", "day"]).reset_index(drop=True)
    pd.testing.assert_frame_equal(out, reference, check_dtype=False)
print(f"same result in the 3 formats: {len(reference)} rows (league x day)")


# --- 4. sizes and times ---
def size_mb(paths):
    return sum(os.path.getsize(p) for p in paths) / 1e6


csv_files = ["data/clean/events_all_clean.csv", "data/clean/categories_all_clean.csv",
             "data/reference/matches.csv"]
parquet_files = [f"data/parquet/{t}.parquet" for t in TABLES]

comparison = pd.DataFrame([
    {"format": "CSV", "files": len(csv_files), "size_mb": size_mb(csv_files),
     "query_ms": median_time(query_csv), "types_enforced": "no", "keys_enforced": "no",
     "match_info_repeated": "yes", "opens_without_code": "yes (Excel, text editor)"},
    {"format": "SQLite", "files": 1, "size_mb": size_mb(["football.db"]),
     "query_ms": median_time(query_sqlite), "types_enforced": "yes", "keys_enforced": "yes",
     "match_info_repeated": "no", "opens_without_code": "with a viewer (DB Browser)"},
    {"format": "Parquet + DuckDB", "files": len(parquet_files), "size_mb": size_mb(parquet_files),
     "query_ms": median_time(query_duckdb), "types_enforced": "yes", "keys_enforced": "no",
     "match_info_repeated": "no", "opens_without_code": "no"},
])
comparison["size_mb"] = comparison["size_mb"].round(2)
comparison["query_ms"] = comparison["query_ms"].round(1)
comparison.to_csv("results/tables/storage_comparison.csv", index=False)
print(comparison.to_string(index=False))

"""Fetch 5 years of MNQ historical bars from Databento (CME GLBX.MDP3).

Downloads continuous front-month MNQ (volume-roll, MNQ.v.0) 1-minute OHLCV,
saves the raw 1-min bars plus a 5-min aggregation with ET timestamps.

Usage:
    set DATABENTO_API_KEY, then:
    python fetch_mnq_databento.py cost      # print estimated cost only
    python fetch_mnq_databento.py download  # download and save CSVs
"""

import os
import sys
from pathlib import Path

import databento as db
import pandas as pd

DATASET = "GLBX.MDP3"
SCHEMA = "ohlcv-1m"
SYMBOLS = ["MNQ.v.0"]  # continuous front month, rolled by volume
STYPE_IN = "continuous"
START = "2021-07-17"
END = "2026-08-10"  # exclusive; extended 2026-08-10 from 2026-07-17 to pick up the
                    # three extra weeks now published

OUT_DIR = Path(__file__).parent / "data" / "databento"
OUT_1MIN = OUT_DIR / "mnq_1min_2021-2026.csv.gz"
# ⚠ FIXED 2026-08-10: this wrote "mnq_5min_2021-2026.csv" but every analysis script
# reads funded_search.DATA_5M = "mnq_2021-2026_5min.csv" — the two names were
# transposed, so a fresh download landed somewhere nothing would look for and every
# downstream script died on FileNotFoundError. Keep this equal to
# funded_search.DATA_5M.
OUT_5MIN = OUT_DIR / "mnq_2021-2026_5min.csv"


def get_client() -> db.Historical:
    api_key: XXXX("DATABENTO_API_KEY")
    if not api_key:
        sys.exit("DATABENTO_API_KEY environment variable is not set")
    return db.Historical(api_key)


def estimate_cost(client: db.Historical) -> float:
    return client.metadata.get_cost(
        dataset=DATASET,
        symbols=SYMBOLS,
        stype_in=STYPE_IN,
        schema=SCHEMA,
        start=START,
        end=END,
    )


def download(client: db.Historical) -> None:
    print(f"Requesting {SCHEMA} {SYMBOLS} {START} -> {END} ...", flush=True)
    data = client.timeseries.get_range(
        dataset=DATASET,
        symbols=SYMBOLS,
        stype_in=STYPE_IN,
        schema=SCHEMA,
        start=START,
        end=END,
    )
    df = data.to_df()  # tz-aware UTC index, prices as floats, mapped symbol col
    if df.empty:
        sys.exit("Databento returned no rows")

    df = df.reset_index()
    df["ts_event"] = pd.to_datetime(df["ts_event"], utc=True)
    df["ts_et"] = df["ts_event"].dt.tz_convert("America/New_York")
    cols = ["ts_event", "ts_et", "symbol", "open", "high", "low", "close", "volume"]
    df = df[cols].sort_values("ts_event")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT_1MIN, index=False)

    five = (
        df.set_index("ts_et")
        .groupby("symbol")
        .resample("5min")
        .agg(
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            volume=("volume", "sum"),
        )
        .dropna(subset=["open"])
        .reset_index()
        .sort_values("ts_et")
    )
    five.to_csv(OUT_5MIN, index=False)

    print(f"1-min rows : {len(df):,}")
    print(f"5-min rows : {len(five):,}")
    print(f"date range : {df['ts_et'].min()} -> {df['ts_et'].max()}")
    print(f"contracts  : {df['symbol'].nunique()} ({df['symbol'].iloc[0]} ... {df['symbol'].iloc[-1]})")
    print(f"saved      : {OUT_1MIN}")
    print(f"saved      : {OUT_5MIN}")


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "cost"
    client = get_client()
    cost = estimate_cost(client)
    print(f"Estimated cost: ${cost:.4f}")
    if mode == "download":
        download(client)


if __name__ == "__main__":
    main()

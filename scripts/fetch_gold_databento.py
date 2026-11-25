"""Fetch COMEX gold (GC) history from Databento — priced before it downloads.

Mirrors fetch_mnq_databento.py. Continuous front month by volume roll, 1-minute
OHLCV, saved raw plus a 5-minute aggregation with ET timestamps.

    set DATABENTO_API_KEY, then:
        python fetch_gold_databento.py cost       # print the estimate, download nothing
        python fetch_gold_databento.py download

GC vs MGC: the CONTRACT differs ($100/pt vs $10/pt) but the PRICE SERIES is the same
instrument, so bars from either drive identical signals. GC is pulled because it is
the liquid one and therefore the cleaner tape; point-value is applied at backtest
time, not here.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import databento as db
import pandas as pd

DATASET = "GLBX.MDP3"
SCHEMA = "ohlcv-1m"
SYMBOLS = ["GC.v.0"]          # continuous front month, volume roll
STYPE_IN = "continuous"
START = "2021-08-09"          # matched to the MNQ span already on disk
END = "2026-08-10"

OUT_DIR = Path(__file__).parent / "data" / "databento"
OUT_1MIN = OUT_DIR / "gc_2021-2026_1min.csv.gz"
OUT_5MIN = OUT_DIR / "gc_2021-2026_5min.csv"


def get_client() -> db.Historical:
    key = os.environ.get("DATABENTO_API_KEY")
    if not key:
        sys.exit("DATABENTO_API_KEY is not set. Set it in this shell, then re-run.")
    return db.Historical(key)


def estimate(client) -> float:
    return client.metadata.get_cost(dataset=DATASET, symbols=SYMBOLS,
                                    stype_in=STYPE_IN, schema=SCHEMA,
                                    start=START, end=END)


def download(client) -> None:
    print(f"Requesting {SCHEMA} {SYMBOLS} {START} -> {END} ...", flush=True)
    data = client.timeseries.get_range(dataset=DATASET, symbols=SYMBOLS,
                                       stype_in=STYPE_IN, schema=SCHEMA,
                                       start=START, end=END)
    df = data.to_df()
    if df.empty:
        sys.exit("Databento returned no rows")

    df = df.reset_index()
    df["ts_event"] = pd.to_datetime(df["ts_event"], utc=True)
    df["ts_et"] = df["ts_event"].dt.tz_convert("America/New_York")
    df = df[["ts_event", "ts_et", "symbol", "open", "high", "low", "close",
             "volume"]].sort_values("ts_event")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT_1MIN, index=False)

    five = (df.set_index("ts_et").groupby("symbol").resample("5min")
            .agg(open=("open", "first"), high=("high", "max"), low=("low", "min"),
                 close=("close", "last"), volume=("volume", "sum"))
            .dropna(subset=["open"]).reset_index().sort_values("ts_et"))
    five.to_csv(OUT_5MIN, index=False)

    print(f"1-min rows : {len(df):,}")
    print(f"5-min rows : {len(five):,}")
    print(f"date range : {df['ts_et'].min()} -> {df['ts_et'].max()}")
    print(f"saved      : {OUT_1MIN}")
    print(f"saved      : {OUT_5MIN}")


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "cost"
    client = get_client()
    cost = estimate(client)
    print(f"Estimated cost: ${cost:,.2f}  ({SCHEMA}, {START} -> {END})")
    if mode == "download":
        download(client)
    else:
        print("Cost only. Re-run with 'download' to actually fetch.")


if __name__ == "__main__":
    main()

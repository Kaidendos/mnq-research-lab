"""Fetch N years of CME futures bars from Databento (GLBX.MDP3), any root.

Generalizes fetch_mnq_databento.py to multiple symbols and a rolling end date.
Downloads continuous front-month (volume-roll, e.g. MNQ.v.0) 1-minute OHLCV and
saves raw 1-min bars plus a 5-min aggregation with ET timestamps.

The API key is read from DATABENTO_API_KEY, or from the path in
DATABENTO_KEY_FILE. It is never written into this file or the output.

Usage:
    python fetch_futures_databento.py cost                # estimate only, no billing
    python fetch_futures_databento.py download            # fetch + save
    python fetch_futures_databento.py cost MNQ NQ         # pick roots
    python fetch_futures_databento.py download MNQ --years 5 --end 2026-08-08
"""

import argparse
import os
import sys
from pathlib import Path

import databento as db
import pandas as pd

DATASET = "GLBX.MDP3"
SCHEMA = "ohlcv-1m"
STYPE_IN = "continuous"
ROLL = "v.0"  # volume-based roll, front month — matches the 2021-2026 pull

OUT_DIR = Path(__file__).parent / "data" / "databento"


def get_client() -> db.Historical:
    key = os.environ.get("DATABENTO_API_KEY")
    if not key:
        key_file = os.environ.get("DATABENTO_KEY_FILE")
        if key_file and Path(key_file).exists():
            key = Path(key_file).read_text(encoding="utf-8").strip()
    if not key:
        sys.exit("No API key: set DATABENTO_API_KEY or DATABENTO_KEY_FILE")
    return db.Historical(key)


def window(years: int, end: str | None) -> tuple[str, str]:
    end_ts = pd.Timestamp(end) if end else pd.Timestamp.utcnow().normalize().tz_localize(None)
    start_ts = end_ts - pd.DateOffset(years=years)
    return start_ts.strftime("%Y-%m-%d"), end_ts.strftime("%Y-%m-%d")


def estimate(client: db.Historical, sym: str, start: str, end: str) -> float:
    return client.metadata.get_cost(
        dataset=DATASET, symbols=[sym], stype_in=STYPE_IN,
        schema=SCHEMA, start=start, end=end,
    )


def _chunks(start: str, end: str, months: int = 6):
    """Yield [a, b) sub-windows; a 5yr ohlcv-1m pull 504s as a single request."""
    a = pd.Timestamp(start)
    stop = pd.Timestamp(end)
    while a < stop:
        b = min(a + pd.DateOffset(months=months), stop)
        yield a.strftime("%Y-%m-%d"), b.strftime("%Y-%m-%d")
        a = b


def _get_chunk(client: db.Historical, sym: str, a: str, b: str, tries: int = 3):
    for attempt in range(1, tries + 1):
        try:
            return client.timeseries.get_range(
                dataset=DATASET, symbols=[sym], stype_in=STYPE_IN,
                schema=SCHEMA, start=a, end=b,
            ).to_df()
        except Exception as exc:
            if attempt == tries:
                raise
            print(f"    {a}->{b} attempt {attempt} failed ({type(exc).__name__}), retrying", flush=True)
    return None


def fetch(client: db.Historical, root: str, start: str, end: str) -> None:
    sym = f"{root}.{ROLL}"
    print(f"\n=== {sym}  {start} -> {end} ===", flush=True)
    parts = []
    for a, b in _chunks(start, end):
        part = _get_chunk(client, sym, a, b)
        n = 0 if part is None or part.empty else len(part)
        print(f"    {a} -> {b}   {n:>9,} rows", flush=True)
        if n:
            parts.append(part)
    if not parts:
        print(f"  !! no rows returned for {sym}")
        return
    df = pd.concat(parts)

    df = df.reset_index()
    df = df.drop_duplicates(subset=["ts_event"], keep="first")
    df["ts_event"] = pd.to_datetime(df["ts_event"], utc=True)
    df["ts_et"] = df["ts_event"].dt.tz_convert("America/New_York")
    df = df[["ts_event", "ts_et", "symbol", "open", "high", "low", "close", "volume"]]
    df = df.sort_values("ts_event")

    tag = f"{root.lower()}_{start[:4]}-{end[:4]}"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out1 = OUT_DIR / f"{tag}_1min.csv.gz"
    out5 = OUT_DIR / f"{tag}_5min.csv"
    df.to_csv(out1, index=False)

    five = (
        df.set_index("ts_et").groupby("symbol").resample("5min")
        .agg(open=("open", "first"), high=("high", "max"), low=("low", "min"),
             close=("close", "last"), volume=("volume", "sum"))
        .dropna(subset=["open"]).reset_index().sort_values("ts_et")
    )
    five.to_csv(out5, index=False)

    print(f"  1-min rows : {len(df):,}")
    print(f"  5-min rows : {len(five):,}")
    print(f"  range      : {df['ts_et'].min()}  ->  {df['ts_et'].max()}")
    print(f"  saved      : {out1.name}, {out5.name}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["cost", "download"], nargs="?", default="cost")
    ap.add_argument("roots", nargs="*", default=None)
    ap.add_argument("--years", type=int, default=5)
    ap.add_argument("--end", default=None, help="YYYY-MM-DD, exclusive")
    args = ap.parse_args()

    roots = args.roots or ["MNQ", "NQ"]
    start, end = window(args.years, args.end)
    client = get_client()

    total = 0.0
    print(f"Window: {start} -> {end}   schema={SCHEMA}  roll={ROLL}")
    for root in roots:
        try:
            c = estimate(client, f"{root}.{ROLL}", start, end)
        except Exception as exc:
            print(f"  {root:<5} cost estimate FAILED: {exc}")
            continue
        total += c
        print(f"  {root:<5} ${c:,.4f}")
    print(f"  {'TOTAL':<5} ${total:,.4f}")

    if args.mode == "download":
        for root in roots:
            fetch(client, root, start, end)


if __name__ == "__main__":
    main()

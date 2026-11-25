"""Independently audit every signal for LOOKAHEAD. Run before trusting any result.

Test (prefix stability): a causal signal on bar i depends only on bars <= i.
So recomputing it on data TRUNCATED after bar T must reproduce, on every bar <= T,
exactly what the full-history run produced. Any mismatch means the signal consulted
data from the future.

Cut points are chosen MID-SESSION so intraday whole-day aggregates
(groupby.transform("max"), a day's final VWAP, etc.) are caught, not just cross-day ones.

Also flags signals that fire implausibly often/never.

Usage:  python lookahead_audit.py [--only prefix]
"""
from __future__ import annotations

import argparse
import numpy as np
import pandas as pd

import funded_search as fs
import funded_1yr as f1


def signals_for(df):
    """All signals: built-in + plug-in."""
    out = {}
    for name in fs.FAMILIES:
        try:
            e, side = fs.sig(df, name)
            out[name] = (e.reindex(df.index).fillna(False).to_numpy(bool), side, "builtin")
        except Exception as exc:
            out[name] = (None, 0, f"ERROR {type(exc).__name__}: {exc}")
    for name, (e, side) in f1.load_plugins(df).items():
        try:
            arr = pd.Series(e).reindex(df.index).fillna(False).to_numpy(bool)
            out[name] = (arr, side, "plugin")
        except Exception as exc:
            out[name] = (None, 0, f"ERROR {type(exc).__name__}: {exc}")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=None)
    args = ap.parse_args()

    full = fs.load_enriched()
    print(f"full history: {len(full):,} bars  {full.index[0]} -> {full.index[-1]}\n")
    base = signals_for(full)

    # two mid-session cut points
    # compare through the Series (not .values) — _day is tz-aware, and .values
    # drops the tz, so an == against a tz-aware Timestamp matches nothing.
    day_ser = pd.Series(full["_day"].to_numpy(), index=range(len(full)))
    days = list(pd.unique(full["_day"]))
    cuts = []
    for frac in (0.70, 0.86):
        d = days[int(len(days) * frac)]
        idx = np.flatnonzero((day_ser == d).to_numpy())
        cuts.append(full.index[idx[len(idx) // 2]])   # middle of that session
    print("cut points (mid-session):", ", ".join(str(c) for c in cuts), "\n")

    trunc = []
    for c in cuts:
        sub = full[full.index <= c]
        print(f"  recomputing on prefix ending {c} ({len(sub):,} bars)...", flush=True)
        trunc.append((c, signals_for(sub)))

    names = sorted(base)
    if args.only:
        # accept a comma-separated list of prefixes, not just one
        prefixes = tuple(p for p in args.only.split(",") if p)
        names = [n for n in names if n.startswith(prefixes)]

    print(f"\n{'signal':<32}{'kind':<9}{'fires':>8}{'fire%':>8}{'side':>6}  verdict")
    print("-" * 104)
    bad, warn, good = [], [], []
    for n in names:
        arr, side, kind = base[n]
        if arr is None:
            print(f"{n:<32}{'-':<9}{'-':>8}{'-':>8}{'-':>6}  LOAD FAIL: {kind}")
            bad.append(n); continue
        fires = int(arr.sum())
        pct = 100 * fires / len(arr)

        verdict, detail = "OK", ""
        mism_total = 0
        for c, tr in trunc:
            a2 = tr.get(n, (None, 0, ""))[0]
            if a2 is None:
                verdict, detail = "RECOMPUTE FAIL", ""
                break
            m = len(a2)
            mism = int((arr[:m] != a2).sum())
            mism_total += mism
        if verdict == "OK" and mism_total > 0:
            verdict = "LOOKAHEAD"
            detail = f"{mism_total} bars changed when future data removed"
        elif verdict == "OK":
            if fires == 0:
                verdict, detail = "DEAD", "never fires"
            elif pct > 15:
                verdict, detail = "TOO DENSE", "regime filter, not an entry"
            elif fires < 30:
                verdict, detail = "THIN", f"only {fires} fires in 5y"

        tag = {"OK": good, "THIN": warn, "TOO DENSE": warn,
               "DEAD": bad, "LOOKAHEAD": bad, "RECOMPUTE FAIL": bad}[verdict]
        tag.append(n)
        print(f"{n:<32}{kind:<9}{fires:>8}{pct:>7.2f}%{side:>6}  {verdict} {detail}")

    print("\n" + "=" * 70)
    print(f"CLEAN      : {len(good)}")
    print(f"WARN       : {len(warn)}  {warn}")
    print(f"DISQUALIFY : {len(bad)}  {bad}")
    print("=" * 70)
    pd.Series({"clean": len(good), "warn": len(warn), "bad": len(bad)}).to_csv(
        "lookahead_summary.csv")
    with open("lookahead_clean.txt", "w") as fh:
        fh.write("\n".join(good + warn))
    print("\nusable signal list -> lookahead_clean.txt")


if __name__ == "__main__":
    main()

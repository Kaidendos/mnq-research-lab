"""Harvest every completed sweep and report honestly.

Ranks on dead_pct (busted OR never paid) plus mean/median withdrawn — never on
bust_pct, which floor-aware sizing can drive to zero by shrinking positions until
the account cannot trade.
"""
from __future__ import annotations

import glob
import numpy as np
import pandas as pd

pd.set_option("display.width", 260)


def load(pat):
    fs_ = sorted(glob.glob(pat))
    if not fs_:
        return None
    return pd.concat([pd.read_csv(f) for f in fs_], ignore_index=True)


def sec(t):
    print("\n" + "=" * 132)
    print(t)
    print("=" * 132)


# ─────────────────────────── 1. SCALPING ───────────────────────────
for pat, lbl in (("scA_*.csv", "SCALPING — 1-min bars, LAST 5 MONTHS"),
                 ("scB_*.csv", "SCALPING — 1-min bars, FULL 5 YEARS")):
    d = load(pat)
    sec(lbl)
    if d is None or not len(d):
        print("(no output)")
        continue
    print(f"configs {len(d):,}   signals {d.sig.nunique()}")
    paid = d[d.pay_pct > 0]
    print(f"configs producing ANY payout: {len(paid)} of {len(d):,} "
          f"({100*len(paid)/len(d):.2f}%)")
    if len(paid):
        c = ["sig", "tp_ticks", "sl_ticks", "tmax_min", "win", "maxc", "rf",
             "n", "mean_out", "med_out", "pay_pct", "dead_pct"]
        print(paid.sort_values("mean_out", ascending=False)[c].head(12).to_string(index=False))
        print("\n  best by pay_pct:")
        print(paid.sort_values("pay_pct", ascending=False)[c].head(8).to_string(index=False))
    else:
        print("  ZERO configs produced a single payout.")
    print(f"\n  fees are 2.44 ticks round-turn; target sizes tested: "
          f"{sorted(d.tp_ticks.unique())}")

# ─────────────────────── 2. 5-MONTH PAIRINGS ───────────────────────
d = load("m5_*.csv")
sec("5-MONTH WINDOW — 110 pairings x 144 configs (holdout alongside)")
if d is not None and len(d):
    print(f"configs {len(d):,}   pairings {d.groupby(['long','short']).ngroups}")
    c = ["long", "short", "sl", "tp", "win", "rf", "cap", "maxc",
         "sel_mean", "sel_med", "sel_pay", "sel_dead",
         "hold_mean", "hold_med", "hold_pay", "hold_dead"]
    good = d[(d.sel_mean > 0) & (d.hold_mean > 0)]
    print(f"net-positive in BOTH periods: {len(good):,}")
    if len(good):
        print("\n  TOP 15 by selection-window mean withdrawn:")
        print(good.sort_values("sel_mean", ascending=False)[c].head(15).to_string(index=False))
        print("\n  TOP 15 by HOLDOUT mean (the honest one):")
        print(good.sort_values("hold_mean", ascending=False)[c].head(15).to_string(index=False))
        print("\n  lowest dead_pct in BOTH:")
        z = good[(good.sel_dead < 60) & (good.hold_dead < 60)]
        print(f"  count {len(z)}")
        if len(z):
            print(z.sort_values("sel_dead")[c].head(12).to_string(index=False))
    print("\n  does the SCALP family appear at all?")
    sc = d[d.long.str.startswith("scalp") | d.short.str.startswith("scalp")]
    print(f"  scalp-involved configs: {len(sc):,}, net-positive both: "
          f"{len(sc[(sc.sel_mean>0)&(sc.hold_mean>0)]):,}")

# ───────────────────── 3. DAY-OF-WEEK x WINDOW ─────────────────────
d = load("ev_*.csv")
sec("DAY-OF-WEEK x TIME-WINDOW")
if d is not None and len(d):
    print(f"configs {len(d):,}")
    print("\n  mean of sel_mean by day-of-week (is any day special?):")
    print(d.groupby("dow").agg(n=("sel_mean", "size"), sel_mean=("sel_mean", "mean"),
                               hold_mean=("hold_mean", "mean"),
                               sel_pay=("sel_pay", "mean"),
                               hold_pay=("hold_pay", "mean")).round(1).to_string())
    print("\n  mean of sel_mean by window:")
    print(d.groupby("win").agg(n=("sel_mean", "size"), sel_mean=("sel_mean", "mean"),
                               hold_mean=("hold_mean", "mean"),
                               hold_pay=("hold_pay", "mean")).round(1).to_string())
    c = ["long", "short", "dow", "win", "sl", "tp", "rf", "cap",
         "sel_mean", "sel_med", "sel_pay", "sel_dead",
         "hold_mean", "hold_med", "hold_pay", "hold_dead"]
    g = d[(d.sel_mean > 0) & (d.hold_mean > 0)]
    print(f"\n  net-positive BOTH: {len(g):,}")
    if len(g):
        print(g.sort_values("hold_mean", ascending=False)[c].head(15).to_string(index=False))

# ───────────────────── 4. FULL-REGISTRY PAIRINGS ─────────────────────
d = load("rg_*.csv")
sec("FULL-REGISTRY PAIRINGS — families never previously combined")
if d is not None and len(d):
    print(f"configs {len(d):,}   pairings {d.groupby(['long','short']).ngroups}")
    c = ["long", "short", "sl", "tp", "rf", "cap", "maxc",
         "sel_mean", "sel_med", "sel_pay", "sel_dead",
         "hold_mean", "hold_med", "hold_pay", "hold_dead"]
    g = d[(d.sel_mean > 0) & (d.hold_mean > 0)]
    print(f"net-positive BOTH periods: {len(g):,}")
    if len(g):
        print("\n  TOP 20 by HOLDOUT mean:")
        print(g.sort_values("hold_mean", ascending=False)[c].head(20).to_string(index=False))
        print("\n  best shorts by holdout mean (is anything rivalling vol_lw_stretch?):")
        print(g.groupby("short").agg(n=("hold_mean", "size"),
                                     best_hold=("hold_mean", "max"),
                                     best_sel=("sel_mean", "max"))
              .sort_values("best_hold", ascending=False).head(12).to_string())
        print("\n  best longs by holdout mean:")
        print(g.groupby("long").agg(n=("hold_mean", "size"),
                                    best_hold=("hold_mean", "max"),
                                    best_sel=("sel_mean", "max"))
              .sort_values("best_hold", ascending=False).head(12).to_string())

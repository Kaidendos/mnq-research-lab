"""Optimise for BUST < 30% using floor-aware sizing and a withdrawal cushion."""
from __future__ import annotations

import argparse
import itertools

import numpy as np
import pandas as pd

import funded_search as fs
import funded_1yr as f1
import lucid_integrated as LI

PAIRS = [
    ("rsi_bounce35_long", "vol_lw_stretch_short"),
    ("sr_round100_break", "vol_lw_stretch_short"),
    ("ema20_50_long", "vol_lw_stretch_short"),
    ("so_combo_deep_rvol", "vol_lw_stretch_short"),
    ("sr_round100_break", "mr_rsi2_short"),
    ("sr_pivot_s1_bounce", "vol_lw_stretch_short"),
    ("so_k21_th30", "vol_lw_stretch_short"),
    ("ema20_50_long", "mr_rsi2_short"),
]
SLS = (1.0, 1.5, 2.0)
TPS = (1.5, 2.0, 3.0)
WINS = ((9.75, 15.5), (10.0, 13.0))
# the two NEW levers
RISK_FRACS = (0.15, 0.25, 0.35, 0.50, 1.00)     # share of remaining room riskable/day
CUSHIONS = (0.0, 500.0, 1000.0, 2000.0)          # keep this much above the buffer
SIZES = ((300, 300, 5), (440, 300, 10), (200, 200, 4))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slice", default=None)
    ap.add_argument("--out", default="lb2.csv")
    args = ap.parse_args()

    df = fs.load_enriched()
    pl = f1.load_plugins(df)

    def get(n):
        e, _ = pl[n] if n in pl else fs.sig(df, n)
        return pd.Series(e).reindex(df.index).fillna(False).to_numpy(bool)

    cache = {}
    for a, b in PAIRS:
        cache.setdefault(a, get(a))
        cache.setdefault(b, get(b))

    pairs = PAIRS
    if args.slice:
        i, k = (int(x) for x in args.slice.split("/"))
        pairs = PAIRS[i::k]

    rows = []
    for ln, sn in pairs:
        el, es = cache[ln], cache[sn]
        for sl, tp, win, rf, cu, (capd, bud, mc) in itertools.product(
                SLS, TPS, WINS, RISK_FRACS, CUSHIONS, SIZES):
            m = LI.evaluate(df, el, es, sl, tp, win, capd, bud, mc, rf, cu)
            if m["n"] < 100:
                continue
            rows.append(dict(long=ln, short=sn, sl=sl, tp=tp,
                             win=f"{win[0]:.2f}-{win[1]:.2f}", risk_frac=rf,
                             cushion=cu, cap=capd, maxc=mc, **m))
        print(f"  done {ln} + {sn}", flush=True)

    pd.DataFrame(rows).to_csv(args.out, index=False)
    print(f"{len(rows):,} scored -> {args.out}")


if __name__ == "__main__":
    main()

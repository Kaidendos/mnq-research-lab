"""Optimise for BUST < 30% — fast integrated simulator."""
from __future__ import annotations

import argparse
import itertools
import time

import numpy as np
import pandas as pd

import funded_search as fs
import funded_1yr as f1
import lucid_fast as LF

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
RISK_FRACS = (0.10, 0.15, 0.25, 0.35, 0.50, 1.00)
CUSHIONS = (0.0, 500.0, 1000.0, 2000.0)
SIZES = ((300, 300, 5), (440, 300, 10), (200, 200, 4))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slice", default=None)
    ap.add_argument("--out", default="lb3.csv")
    args = ap.parse_args()

    df = fs.load_enriched()
    pl = f1.load_plugins(df)

    def get(n):
        e, _ = pl[n] if n in pl else fs.sig(df, n)
        return pd.Series(e).reindex(df.index).fillna(False).to_numpy(bool)

    sig = {}
    for a, b in PAIRS:
        sig.setdefault(a, get(a))
        sig.setdefault(b, get(b))

    pairs = PAIRS
    if args.slice:
        i, k = (int(x) for x in args.slice.split("/"))
        pairs = PAIRS[i::k]

    rows = []
    t0 = time.time()
    for ln, sn in pairs:
        for win in WINS:
            P = LF.prep(df, sig[ln], sig[sn], win)
            for sl, tp, rf, cu, (capd, bud, mc) in itertools.product(
                    SLS, TPS, RISK_FRACS, CUSHIONS, SIZES):
                m = LF.evaluate(P, sl, tp, capd, bud, mc, rf, cu)
                if m["n"] < 50:
                    continue
                rows.append(dict(long=ln, short=sn, sl=sl, tp=tp,
                                 win=f"{win[0]:.2f}-{win[1]:.2f}", risk_frac=rf,
                                 cushion=cu, cap=capd, maxc=mc, **m))
            print(f"  {ln}+{sn} {win} -> {len(rows)} rows, {time.time()-t0:.0f}s",
                  flush=True)

    pd.DataFrame(rows).to_csv(args.out, index=False)
    print(f"{len(rows):,} scored -> {args.out} in {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()

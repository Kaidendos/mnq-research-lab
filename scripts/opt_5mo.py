"""Big sweep scored on the LAST 5 MONTHS, with the 4.5yr holdout alongside.

Everything the user will actually trade has to work in the current regime, so the
selection window is the last 5 months. The holdout is reported next to it — never
used to filter — so overfitting to 105 sessions is visible rather than hidden.

Includes the new scalping entries. Ranks on dead_pct (busted OR never paid), which
floor-aware sizing cannot game, instead of bust_pct.
"""
from __future__ import annotations

import argparse
import itertools
import time

import numpy as np
import pandas as pd

import funded_search as fs
import funded_1yr as f1
import lucid_fast as LF

LONGS = ["sr_round100_break", "rsi_bounce35_long", "ema20_50_long",
         "so_combo_deep_rvol", "sr_pivot_s1_bounce", "so_k21_th30",
         "scalp_sweep_lo_long", "scalp_vwap_snap_long", "scalp_sigma_snap_long",
         "scalp_vspike_fade_long", "scalp_micro_pull_long"]
SHORTS = ["vol_lw_stretch_short", "mr_rsi2_short", "pdh_fade_short",
          "orb30_short", "engulf_bb_short",
          "scalp_sweep_hi_short", "scalp_vwap_snap_short", "scalp_sigma_snap_short",
          "scalp_vspike_fade_short", "scalp_micro_pull_short"]

SLS = (1.0, 1.5, 2.0)
TPS = (1.0, 1.5, 2.0, 3.0)
WINS = ((9.75, 15.5), (10.0, 13.0))
RFS = (0.25, 0.50, 1.00)
SIZES = ((300, 300, 5), (440, 300, 10))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slice", default=None)
    ap.add_argument("--out", default="m5.csv")
    args = ap.parse_args()

    df = fs.load_enriched()
    pl = f1.load_plugins(df)
    end = df.index[-1]
    w5 = end - pd.DateOffset(months=5)
    sel = df[df.index >= w5]
    hold = df[df.index < w5]
    print(f"SEL {sel.index[0]:%Y-%m-%d}->{sel.index[-1]:%Y-%m-%d} "
          f"({sel['_day'].nunique()} sessions) | HOLD {hold['_day'].nunique()} sessions",
          flush=True)

    def get(frame, n):
        e, _ = pl[n] if n in pl else fs.sig(df, n)
        return pd.Series(e).reindex(frame.index).fillna(False).to_numpy(bool)

    pairs = [(a, b) for a, b in itertools.product(LONGS, SHORTS)]
    if args.slice:
        i, k = (int(x) for x in args.slice.split("/"))
        pairs = pairs[i::k]

    rows, t0 = [], time.time()
    for ln, sn in pairs:
        for win in WINS:
            Ps = LF.prep(sel, get(sel, ln), get(sel, sn), win)
            Ph = LF.prep(hold, get(hold, ln), get(hold, sn), win)
            for sl, tp, rf, (cap, bud, mc) in itertools.product(SLS, TPS, RFS, SIZES):
                ms = LF.evaluate(Ps, sl, tp, cap, bud, mc, rf, 0.0,
                                 horizon=150, stride=3)
                if ms["n"] < 20:
                    continue
                mh = LF.evaluate(Ph, sl, tp, cap, bud, mc, rf, 0.0,
                                 horizon=150, stride=10)
                rows.append(dict(
                    long=ln, short=sn, sl=sl, tp=tp,
                    win=f"{win[0]:.2f}-{win[1]:.2f}", rf=rf, cap=cap, maxc=mc,
                    sel_n=ms["n"], sel_mean=ms["mean_out"], sel_med=ms["med_out"],
                    sel_pay=ms["pay_pct"], sel_bust=ms["bust_pct"],
                    sel_zomb=ms["zombie_pct"], sel_dead=ms["dead_pct"],
                    hold_mean=mh["mean_out"], hold_med=mh["med_out"],
                    hold_pay=mh["pay_pct"], hold_dead=mh["dead_pct"]))
        print(f"  {ln[:20]}+{sn[:20]} -> {len(rows)} rows, {time.time()-t0:.0f}s",
              flush=True)

    pd.DataFrame(rows).to_csv(args.out, index=False)
    print(f"{len(rows):,} scored -> {args.out} in {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()

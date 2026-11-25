"""Pair the best NAMED-TRADER families against each other and the incumbents.

mf_wkpiv_long (Mark Fisher ACD weekly pivot) is now the best long in the whole
271-family registry: holdout net $8,726 at 37.5% bust, vs the incumbent
sr_round100_break's $6,114 at 58.1%. vol_lw_stretch_short (Larry Williams stretch)
remains the best short at $10,635.

Both top families are published methodologies from traders with real records, which
is a strong argument for mining more of them rather than generic strategy blogs.

Selection = last 5 months, holdout = everything before. Ranked on dead_pct
(busted OR never paid) plus mean/median withdrawn. Writes INCREMENTALLY.
"""
from __future__ import annotations

import argparse
import itertools
import os
import time

import pandas as pd

import funded_search as fs
import funded_1yr as f1
import lucid_fast as LF

LONGS = ["mf_wkpiv_long", "tt_turtle_s2_long", "tt_turtle_s1_long",
         "ab_brooks_bopb", "lr_raschke_holygrail_long", "lr_raschke_anti_long",
         "jc_carter_squeeze_long", "sr_round100_break", "so_k21_th30",
         "ema20_50_long"]
SHORTS = ["vol_lw_stretch_short", "lr_raschke_firstcross_short", "lw_oops_short",
          "tt_turtle_s2_short", "jc_crabel_orb_stretch_short", "mf_bias_short",
          "cn_connors_rsi2_short", "pdh_fade_short", "bb_break_short",
          "mr_rsi2_short"]

SLS, TPS = (1.0, 1.5, 2.0), (1.5, 2.0, 3.0)
WINS = ((9.75, 15.5), (9.75, 12.0), (9.75, 11.0))   # 9:45 start — proven essential
RFS = (0.5, 1.0)
SIZES = ((300, 300, 5), (440, 300, 10))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slice", default=None)
    ap.add_argument("--out", default="tp.csv")
    args = ap.parse_args()

    df = fs.load_enriched()
    pl = f1.load_plugins(df)
    end = df.index[-1]
    w5 = end - pd.DateOffset(months=5)
    sel, hold = df[df.index >= w5], df[df.index < w5]

    def get(frame, n):
        e, _ = pl[n] if n in pl else fs.sig(df, n)
        return pd.Series(e).reindex(frame.index).fillna(False).to_numpy(bool)

    pairs = list(itertools.product(LONGS, SHORTS))
    if args.slice:
        i, k = (int(x) for x in args.slice.split("/"))
        pairs = pairs[i::k]
    print(f"{len(pairs)} pairings", flush=True)

    first = not os.path.exists(args.out)
    t0 = time.time()
    for ln, sn in pairs:
        rows = []
        try:
            els, ess = get(sel, ln), get(sel, sn)
            elh, esh = get(hold, ln), get(hold, sn)
        except Exception as exc:
            print(f"  !! {ln}+{sn}: {exc}", flush=True)
            continue
        for win in WINS:
            Ps = LF.prep(sel, els, ess, win)
            Ph = LF.prep(hold, elh, esh, win)
            for sl, tp, rf, (cap, bud, mc) in itertools.product(SLS, TPS, RFS, SIZES):
                ms = LF.evaluate(Ps, sl, tp, cap, bud, mc, rf, 0.0,
                                 horizon=150, stride=2)
                if ms["n"] < 12:
                    continue
                mh = LF.evaluate(Ph, sl, tp, cap, bud, mc, rf, 0.0,
                                 horizon=150, stride=10)
                rows.append(dict(long=ln, short=sn, win=f"{win[0]:.2f}-{win[1]:.2f}",
                                 sl=sl, tp=tp, rf=rf, cap=cap, maxc=mc,
                                 sel_mean=ms["mean_out"], sel_med=ms["med_out"],
                                 sel_pay=ms["pay_pct"], sel_dead=ms["dead_pct"],
                                 hold_mean=mh["mean_out"], hold_med=mh["med_out"],
                                 hold_pay=mh["pay_pct"], hold_dead=mh["dead_pct"]))
        if rows:
            pd.DataFrame(rows).to_csv(args.out, mode="a", header=first, index=False)
            first = False
        print(f"  {ln[:26]}+{sn[:26]} +{len(rows)} {time.time()-t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()

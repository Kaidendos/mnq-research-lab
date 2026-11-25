"""Broad pairing sweep across the FULL signal registry.

174 families exist (111 long, 63 short) after the web-research plug-ins. Only ~26
have ever been paired, and `vol_lw_stretch_short` carries almost every winner found
so far — which is either a genuinely exceptional signal or a sign that the search
never looked anywhere else. This looks everywhere else.

Writes results INCREMENTALLY (appends every pairing) so a run killed by a reboot
or a limit still leaves usable output — earlier scripts only wrote at the end.
"""
from __future__ import annotations

import argparse
import itertools
import os
import time

import numpy as np
import pandas as pd

import funded_search as fs
import funded_1yr as f1
import lucid_fast as LF

SLS, TPS = (1.0, 1.5, 2.0), (1.5, 2.0, 3.0)
WIN = (9.75, 15.5)
RFS = (0.5, 1.0)
SIZES = ((300, 300, 5), (440, 300, 10))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slice", default=None)
    ap.add_argument("--top", type=int, default=14, help="top N families per side")
    ap.add_argument("--out", default="rg.csv")
    args = ap.parse_args()

    df = fs.load_enriched()
    pl = f1.load_plugins(df)
    end = df.index[-1]
    w5 = end - pd.DateOffset(months=5)
    sel, hold = df[df.index >= w5], df[df.index < w5]

    # pick candidates from the side ranking, excluding what has already been swept
    rk = pd.read_csv("rank_sides.csv")
    rk = rk[rk.hold_net > 0]
    already = {"vol_lw_stretch_short", "mr_rsi2_short", "pdh_fade_short",
               "orb30_short", "engulf_bb_short", "sr_round100_break",
               "rsi_bounce35_long", "ema20_50_long", "so_k21_th30",
               "sr_pivot_s1_bounce", "so_combo_deep_rvol"}
    longs = [n for n in rk[rk.side == 1].sort_values("hold_net", ascending=False)
             .family.tolist() if n not in already][:args.top]
    shorts = [n for n in rk[rk.side == -1].sort_values("hold_net", ascending=False)
              .family.tolist() if n not in already][:args.top]
    print(f"NEW longs  : {longs}", flush=True)
    print(f"NEW shorts : {shorts}", flush=True)

    def get(frame, n):
        e, _ = pl[n] if n in pl else fs.sig(df, n)
        return pd.Series(e).reindex(frame.index).fillna(False).to_numpy(bool)

    pairs = list(itertools.product(longs, shorts))
    if args.slice:
        i, k = (int(x) for x in args.slice.split("/"))
        pairs = pairs[i::k]
    print(f"{len(pairs)} pairings", flush=True)

    first = not os.path.exists(args.out)
    t0 = time.time()
    for ln, sn in pairs:
        rows = []
        try:
            Ps = LF.prep(sel, get(sel, ln), get(sel, sn), WIN)
            Ph = LF.prep(hold, get(hold, ln), get(hold, sn), WIN)
        except Exception as exc:
            print(f"  !! {ln}+{sn}: {exc}", flush=True)
            continue
        for sl, tp, rf, (cap, bud, mc) in itertools.product(SLS, TPS, RFS, SIZES):
            ms = LF.evaluate(Ps, sl, tp, cap, bud, mc, rf, 0.0, horizon=150, stride=2)
            if ms["n"] < 12:
                continue
            mh = LF.evaluate(Ph, sl, tp, cap, bud, mc, rf, 0.0, horizon=150, stride=12)
            rows.append(dict(long=ln, short=sn, sl=sl, tp=tp, rf=rf, cap=cap, maxc=mc,
                             sel_n=ms["n"], sel_mean=ms["mean_out"],
                             sel_med=ms["med_out"], sel_pay=ms["pay_pct"],
                             sel_dead=ms["dead_pct"], hold_mean=mh["mean_out"],
                             hold_med=mh["med_out"], hold_pay=mh["pay_pct"],
                             hold_dead=mh["dead_pct"]))
        if rows:
            pd.DataFrame(rows).to_csv(args.out, mode="a", header=first, index=False)
            first = False
        print(f"  {ln[:22]}+{sn[:22]} +{len(rows)} rows {time.time()-t0:.0f}s",
              flush=True)


if __name__ == "__main__":
    main()

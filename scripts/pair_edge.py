"""Pair the families that top the CLEAN-EDGE ranking, not the net-P&L ranking.

`harvest_clean_rank.py` showed the two orderings barely relate — Spearman +0.265
across 349 families. Concretely, of the old top-10 by holdout net:

    vol_lw_stretch_short  edge rank   5/349   <- incumbent short, genuinely strong
    sr_round100_break     edge rank  71/349   <- incumbent LONG is the weak link
    mf_wkpiv_long         edge rank  89/349   <- the old "best long in the registry"
    tt_turtle_s2_long     edge rank 162/349   <- NEGATIVE edge
    ww_psar_short         edge rank 272/349   <- NEGATIVE edge

So every candidate list this project has built came from a metric that was mostly
reading the market. This pairs the top of the correct list instead.

The long side is the target: the incumbent long contributes edge +4.77 while eleven
other longs clear +9.9, several with comparable or larger trade counts.

⚠ IN-SAMPLE CAVEAT, stated up front: the edge ranking was computed on this same
holdout, so picking its winners and scoring them here is partly circular. The
recent 5 months are reported alongside as the only untouched data, and any survivor
still needs the 36-config paired toggle that killed three candidates today.

Usage: python pair_edge.py --slice 0/8 --out pe_0.csv
"""
from __future__ import annotations

import argparse
import itertools
import os

import numpy as np
import pandas as pd

import funded_search as fs
import funded_1yr as f1
import lucid_fast as LF
import sim_trace as ST

WIN = (9.75, 11.0)
# brackets: the incumbent, plus the two leaders from the exit sweep
BRACKETS = ((2.0, 3.0), (3.0, 4.0), (3.0, 5.0))
SIZES = ((440, 300), (440, 500))

# top of the clean-edge ranking, filtered to >= 100 trades so the estimate is not
# resting on 60-odd samples. Incumbents kept in as the benchmark.
LONGS = ["sr_round100_break", "vwap_avwap_pdhigh_reclaim_long", "qm_ep_long",
         "ic_sweep_fvg_long", "lw_gsv_long", "wy_lps_long",
         "sr_pivot_s1_bounce", "ms_kfade_long"]
SHORTS = ["vol_lw_stretch_short", "lw_gsv_short", "ms_kfade_short",
          "rh_irb_gated_short", "ms_pctb_short", "cn_connors_rsi2_short",
          "sc_vsa_upthrust_short", "tt_turtle_s2_short"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slice", default=None)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    df = fs.load_enriched()
    pl = f1.load_plugins(df)
    end = df.index[-1]
    cut = end - pd.DateOffset(months=5)
    FRAMES = (("hold", df[df.index < cut]), ("recent", df[df.index >= cut]))

    def resolve(frame, name):
        e, _ = pl[name] if name in pl else fs.sig(df, name)
        return pd.Series(e).reindex(frame.index).fillna(False).to_numpy(bool)

    pairs = list(itertools.product(LONGS, SHORTS))
    if args.slice:
        i, k = (int(x) for x in args.slice.split("/"))
        pairs = pairs[i::k]
    print(f"{len(pairs)} pairings in this slice", flush=True)

    first = not os.path.exists(args.out)
    for ln, sn in pairs:
        rows = []
        try:
            preps = {w: LF.prep(f, resolve(f, ln), resolve(f, sn), WIN)
                     for w, f in FRAMES}
        except Exception as exc:
            print(f"  !! {ln}+{sn}: {exc}", flush=True)
            continue
        for (sl, tp), (cap, bud) in itertools.product(BRACKETS, SIZES):
            row = dict(long=ln, short=sn, sl=sl, tp=tp, cap=cap, budget=bud)
            ok = True
            for w in ("hold", "recent"):
                P = preps[w]
                res = [ST.trace(P, k, cap, bud, sl=sl, tp=tp)
                       for k in range(0, len(P["per"]), 4)
                       if len(P["per"]) - k >= 20]
                if not res:
                    ok = False
                    break
                m = ST.summarise(res)
                for key in ("paid", "bust", "mean", "med", "days"):
                    row[f"{w}_{key}"] = m[key]
            if ok:
                rows.append(row)
        if rows:
            pd.DataFrame(rows).to_csv(args.out, mode="a", header=first, index=False)
            first = False
        print(f"  {ln} + {sn}", flush=True)


if __name__ == "__main__":
    main()

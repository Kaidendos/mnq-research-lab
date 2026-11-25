"""BROAD sweep — day-of-week x time-window x pairing x brackets x sizing.

Dimensions never systematically explored before this:
  * DAY OF WEEK as a filter. Only Friday was ever tested, in isolation, on the
    live strategy. Monday-only, no-Friday, midweek-only etc. are untouched.
  * FINE-GRAINED time windows. Prior sweeps used 3-5 hand-picked windows; the
    regime work showed the 14:00 hour inverted (-0.2661 ATR vs +0.1170
    historically) while late morning strengthened, so window edges matter.
  * The interaction between the two, which is where day-specific session
    structure would actually show up.

Scored under the verified LucidPro 25K rules via lucid_fast, ranked on dead_pct
(busted OR never paid) because floor-aware sizing makes bust_pct gameable.
Selection = last 5 months, holdout = everything before, reported side by side.
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

# (label, set of weekday numbers)  Mon=0 .. Fri=4
DOWS = [
    ("all", {0, 1, 2, 3, 4}),
    ("Mon", {0}), ("Tue", {1}), ("Wed", {2}), ("Thu", {3}), ("Fri", {4}),
    ("noMon", {1, 2, 3, 4}), ("noFri", {0, 1, 2, 3}),
    ("midweek", {1, 2, 3}), ("MonTue", {0, 1}), ("ThuFri", {3, 4}),
]
WINS = [
    (9.75, 11.0), (9.75, 12.0), (9.75, 15.5),
    (10.0, 11.5), (10.0, 12.0), (10.0, 13.0),
    (10.5, 12.5), (11.0, 13.0), (11.0, 14.0),
    (12.0, 14.0), (13.0, 15.0), (13.0, 15.5), (14.0, 15.75),
]
PAIRS = [
    ("sr_round100_break", "vol_lw_stretch_short"),
    ("rsi_bounce35_long", "vol_lw_stretch_short"),
    ("ema20_50_long", "vol_lw_stretch_short"),
    ("sr_round100_break", "mr_rsi2_short"),
    ("so_k21_th30", "vol_lw_stretch_short"),
    ("sr_pivot_s1_bounce", "vol_lw_stretch_short"),
]
SLS, TPS = (1.0, 1.5, 2.0), (1.5, 2.0, 3.0)
RFS = (0.5, 1.0)
SIZES = ((300, 300, 5), (440, 300, 10))


def prep_dow(df, el, es, win, dow):
    """Same as lucid_fast.prep but only keeps sessions on the allowed weekdays."""
    P = LF.prep(df, el, es, win)
    if len(dow) == 5:
        return P
    keep = [i for i, d in enumerate(P["dates"]) if d.dayofweek in dow]
    if len(keep) < 30:
        return None
    P2 = dict(P)
    P2["per"] = [P["per"][i] for i in keep]
    P2["dates"] = P["dates"][keep]
    return P2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slice", default=None)
    ap.add_argument("--out", default="ev.csv")
    args = ap.parse_args()

    df = fs.load_enriched()
    pl = f1.load_plugins(df)
    end = df.index[-1]
    w5 = end - pd.DateOffset(months=5)
    sel, hold = df[df.index >= w5], df[df.index < w5]
    print(f"SEL {sel['_day'].nunique()} sessions | HOLD {hold['_day'].nunique()}",
          flush=True)

    def get(frame, n):
        e, _ = pl[n] if n in pl else fs.sig(df, n)
        return pd.Series(e).reindex(frame.index).fillna(False).to_numpy(bool)

    combos = list(itertools.product(PAIRS, WINS))
    if args.slice:
        i, k = (int(x) for x in args.slice.split("/"))
        combos = combos[i::k]
    print(f"{len(combos)} pairing x window combos", flush=True)

    rows, t0 = [], time.time()
    for (ln, sn), win in combos:
        els, ess = get(sel, ln), get(sel, sn)
        elh, esh = get(hold, ln), get(hold, sn)
        for dlbl, dset in DOWS:
            Ps = prep_dow(sel, els, ess, win, dset)
            if Ps is None:
                continue
            Ph = prep_dow(hold, elh, esh, win, dset)
            if Ph is None:
                continue
            for sl, tp, rf, (cap, bud, mc) in itertools.product(SLS, TPS, RFS, SIZES):
                ms = LF.evaluate(Ps, sl, tp, cap, bud, mc, rf, 0.0,
                                 horizon=150, stride=2)
                if ms["n"] < 12:
                    continue
                mh = LF.evaluate(Ph, sl, tp, cap, bud, mc, rf, 0.0,
                                 horizon=150, stride=12)
                rows.append(dict(
                    long=ln, short=sn, dow=dlbl,
                    win=f"{win[0]:.2f}-{win[1]:.2f}", sl=sl, tp=tp, rf=rf,
                    cap=cap, maxc=mc,
                    sel_n=ms["n"], sel_mean=ms["mean_out"], sel_med=ms["med_out"],
                    sel_pay=ms["pay_pct"], sel_dead=ms["dead_pct"],
                    sel_zomb=ms["zombie_pct"],
                    hold_mean=mh["mean_out"], hold_med=mh["med_out"],
                    hold_pay=mh["pay_pct"], hold_dead=mh["dead_pct"]))
        print(f"  {ln[:18]}+{sn[:16]} {win} -> {len(rows)} rows "
              f"{time.time()-t0:.0f}s", flush=True)

    pd.DataFrame(rows).to_csv(args.out, index=False)
    print(f"{len(rows):,} scored -> {args.out}")


if __name__ == "__main__":
    main()

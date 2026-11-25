"""Re-rank ALL 326 families by EDGE OVER A CLEAN CONTROL, not by raw P&L.

Every ranking in this project so far (`rank_sides.csv`, `harvest_tp.py`, the whole
finalist pipeline) sorted families by net points or mean withdrawn. Today's control
work showed why that is the wrong metric:

  * MNQ drifts up over most of the sample, so ANY long-biased rule prints a
    positive net. `sr_round100_break` earns +12.25 pts/trade — but a shuffled
    control on the same trade count earns +0.39, so only the difference is real.
  * A rule that trades rarely on volatile days inherits the session's variance and
    looks strong on net while adding nothing.

So a family's net tells you mostly which market it lived in. Its edge over a
control that trades the same number of times, on shuffled sessions, at random
bars, tells you what the RULE contributes. Those are different orderings, and the
project has never seen the second one.

This recomputes every family that way. Expect the ranking to change substantially;
families that only ever harvested drift should collapse toward zero edge, and
anything that survives is a genuinely different candidate list to pair from.

Usage:  python rank_clean.py --slice 0/10 --out rc_0.csv     (writes incrementally)
"""
from __future__ import annotations

import argparse
import os

import numpy as np
import pandas as pd

import funded_search as fs
import funded_1yr as f1
import lucid_fast as LF

SL, TP = 2.0, 3.0
WINDOWS = ((9.75, 11.0), (9.75, 15.5))
SEEDS = 8
MIN_TRADES = 40


def points(frame, el, es, win):
    P = LF.prep(frame, el, es, win)
    hi, lo, cl, atr, ethv = P["hi"], P["lo"], P["cl"], P["atr"], P["eth"]
    tot, n, wins = 0.0, 0, 0
    for s, e, idxs, sides in P["per"]:
        j, today = 0, 0
        while j < len(idxs) and today < 6:
            i, sd = idxs[j], int(sides[j])
            a, entry = atr[i], cl[i]
            stop_px, targ_px = entry - sd * a * SL, entry + sd * a * TP
            px, m = None, i + 1
            while m < e:
                if sd > 0:
                    if lo[m] <= stop_px: px = stop_px; break
                    if hi[m] >= targ_px: px = targ_px; break
                else:
                    if hi[m] >= stop_px: px = stop_px; break
                    if lo[m] <= targ_px: px = targ_px; break
                if ethv[m] >= 16.0 or m == e - 1:
                    px = cl[m]; break
                m += 1
            if px is None:
                px, m = cl[e - 1], e - 1
            r = sd * (px - entry)
            tot += r; n += 1; wins += r > 0; today += 1
            while j < len(idxs) and idxs[j] <= m:
                j += 1
    return tot, n, wins


def shuffle_mask(mask, starts, ends, ok, rng):
    """Permute the per-session in-window fire count across sessions, random bars."""
    prof = [int((mask[s:e] & ok[s:e]).sum()) for s, e in zip(starts, ends)]
    order = rng.permutation(len(prof))
    out = np.zeros(len(mask), bool)
    for pos, (s, e) in enumerate(zip(starts, ends)):
        k = prof[order[pos]]
        if not k:
            continue
        slot = np.flatnonzero(ok[s:e])
        if not len(slot):
            continue
        out[s + rng.choice(slot, size=min(k, len(slot)), replace=False)] = True
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slice", default=None)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    df = fs.load_enriched()
    pl = f1.load_plugins(df)
    end = df.index[-1]
    hold = df[df.index < end - pd.DateOffset(months=5)]

    d = pd.factorize(hold["_day"])[0]
    starts = np.flatnonzero(np.r_[True, d[1:] != d[:-1]])
    ends = np.r_[starts[1:], len(d)]
    eth = hold["eth"].to_numpy(float)
    atr_ok = hold["atr"].to_numpy(float) > 0

    names = sorted(set(fs.FAMILIES) | set(pl))
    if args.slice:
        i, k = (int(x) for x in args.slice.split("/"))
        names = names[i::k]
    print(f"{len(names)} families in this slice", flush=True)

    first = not os.path.exists(args.out)
    for nm in names:
        try:
            e, side = pl[nm] if nm in pl else fs.sig(df, nm)
            mask = pd.Series(e).reindex(hold.index).fillna(False).to_numpy(bool)
        except Exception as exc:
            print(f"  !! {nm}: {exc}", flush=True)
            continue
        rows = []
        for win in WINDOWS:
            ok = (eth >= win[0]) & (eth <= win[1]) & atr_ok
            zero = np.zeros(len(mask), bool)
            el, es = (mask, zero) if side > 0 else (zero, mask)
            tot, n, wins = points(hold, el, es, win)
            if n < MIN_TRADES:
                continue
            real = tot / n
            ctl = []
            for sd_ in range(SEEDS):
                rng = np.random.default_rng(sd_)
                sh = shuffle_mask(mask, starts, ends, ok, rng)
                sel, ses = (sh, zero) if side > 0 else (zero, sh)
                t2, n2, _ = points(hold, sel, ses, win)
                if n2:
                    ctl.append(t2 / n2)
            if not ctl:
                continue
            ctl = np.array(ctl)
            rows.append(dict(family=nm, side=side, win=f"{win[0]}-{win[1]}",
                             trades=n, win_pct=round(100 * wins / n, 1),
                             real_ppt=round(real, 2),
                             ctl_ppt=round(float(np.median(ctl)), 2),
                             edge=round(real - float(np.median(ctl)), 2),
                             beaten=int((ctl >= real).sum()), seeds=len(ctl),
                             total_pts=round(tot)))
        if rows:
            pd.DataFrame(rows).to_csv(args.out, mode="a", header=first, index=False)
            first = False
        print(f"  {nm}", flush=True)


if __name__ == "__main__":
    main()

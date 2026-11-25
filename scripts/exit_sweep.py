"""Sweep the EXIT logic — the least-explored part of the whole strategy.

Every run in this project has used the same exit: a fixed ATR stop, a fixed ATR
target, and otherwise hold to the session close. That is one point in a large space,
and it was never chosen — it was inherited. Given the clean control showed the
ENTRY contributes only part of the result, the exit deserves a proper look.

Worth noting what the current exit implies: a trade opened at 10:00 that hits
neither level is held for SIX HOURS, to 16:00. Nothing has ever tested whether
that is helping or whether the edge is gone by lunchtime.

Variants swept:
  stop / target   the ATR multiples, wider and narrower than 2.0/3.0
  time stop       close the trade after N bars regardless
  breakeven       move the stop to entry once the trade is N x ATR in profit
  trailing stop   trail N x ATR behind the best price reached

All causal: the excursion is tracked bar by bar as it would be live, and a stop
that has been moved can only be hit on a LATER bar than the one that moved it.

Ranked on points per trade, but every candidate also carries its per-year record,
because a single-window exit improvement is exactly the kind of finding that has
failed the paired test three times today.

Usage: python exit_sweep.py --slice 0/6 --out ex_0.csv
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

WIN = (9.75, 11.0)
LONG_SIG, SHORT_SIG = "sr_round100_break", "vol_lw_stretch_short"

SLS = (1.5, 2.0, 2.5, 3.0)
TPS = (2.0, 3.0, 4.0, 5.0)
TIME_STOPS = (None, 12, 24, 48)          # bars; 12 = 1 hour on 5-min
BREAKEVENS = (None, 1.0, 1.5)            # x ATR of favourable excursion
TRAILS = (None, 1.5, 2.5)                # x ATR behind the best price


def walk(P, sl, tp, tstop, be, trail):
    """Replay every signal with the given exit logic. Returns pts/trade etc."""
    hi, lo, cl, atr, ethv, per = P["hi"], P["lo"], P["cl"], P["atr"], P["eth"], P["per"]
    dates = P["dates"]
    tot, n, wins = 0.0, 0, 0
    by_year = {}
    for si, (s, e, idxs, sides) in enumerate(per):
        yr = dates[si].year
        j, today = 0, 0
        while j < len(idxs) and today < 6:
            i, sd = idxs[j], int(sides[j])
            a, entry = atr[i], cl[i]
            stop_px = entry - sd * a * sl
            targ_px = entry + sd * a * tp
            best = entry                    # best price reached, in trade direction
            moved_be = False
            px, m = None, i + 1
            limit = e if tstop is None else min(e, i + 1 + tstop)
            while m < limit:
                # ── stop first: pessimistic on bars that span both levels ──
                if sd > 0:
                    if lo[m] <= stop_px: px = stop_px; break
                    if hi[m] >= targ_px: px = targ_px; break
                else:
                    if hi[m] >= stop_px: px = stop_px; break
                    if lo[m] <= targ_px: px = targ_px; break
                # ── update excursion from THIS bar, affecting only later bars ──
                best = max(best, hi[m]) if sd > 0 else min(best, lo[m])
                excursion = sd * (best - entry)
                if be is not None and not moved_be and excursion >= be * a:
                    stop_px = entry
                    moved_be = True
                if trail is not None and excursion >= trail * a:
                    cand = best - sd * trail * a
                    stop_px = max(stop_px, cand) if sd > 0 else min(stop_px, cand)
                if ethv[m] >= 16.0 or m == limit - 1:
                    px = cl[m]; break
                m += 1
            if px is None:
                m = min(limit, e) - 1
                px = cl[max(m, i + 1)] if m > i else cl[i]
            r = sd * (px - entry)
            tot += r; n += 1; wins += r > 0; today += 1
            by_year.setdefault(yr, [0.0, 0])
            by_year[yr][0] += r
            by_year[yr][1] += 1
            while j < len(idxs) and idxs[j] <= m:
                j += 1
    if not n:
        return None
    yr_ppt = {y: v[0] / v[1] for y, v in by_year.items() if v[1] >= 20}
    return dict(trades=n, win_pct=round(100 * wins / n, 1),
                ppt=round(tot / n, 2), total=round(tot),
                yrs_pos=sum(v > 0 for v in yr_ppt.values()), yrs=len(yr_ppt),
                worst_yr=round(min(yr_ppt.values()), 2) if yr_ppt else 0.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slice", default=None)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    df = fs.load_enriched()
    pl = f1.load_plugins(df)
    end = df.index[-1]
    hold = df[df.index < end - pd.DateOffset(months=5)]

    def g(name):
        e, _ = pl[name] if name in pl else fs.sig(df, name)
        return pd.Series(e).reindex(hold.index).fillna(False).to_numpy(bool)

    P = LF.prep(hold, g(LONG_SIG), g(SHORT_SIG), WIN)

    combos = list(itertools.product(SLS, TPS, TIME_STOPS, BREAKEVENS, TRAILS))
    if args.slice:
        i, k = (int(x) for x in args.slice.split("/"))
        combos = combos[i::k]
    print(f"{len(combos)} exit combos in this slice", flush=True)

    first = not os.path.exists(args.out)
    buf = []
    for c, (sl, tp, ts, be, tr) in enumerate(combos):
        r = walk(P, sl, tp, ts, be, tr)
        if r:
            buf.append(dict(sl=sl, tp=tp, time_stop=ts if ts else 0,
                            breakeven=be if be else 0, trail=tr if tr else 0, **r))
        if len(buf) >= 10 or c == len(combos) - 1:
            pd.DataFrame(buf).to_csv(args.out, mode="a", header=first, index=False)
            first = False
            buf = []
            print(f"  {c+1}/{len(combos)}", flush=True)


if __name__ == "__main__":
    main()

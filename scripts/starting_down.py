"""Starting in a hole: what a $500 deficit does, and whether to size down for it.

This is the user's real position — the live account is already down. On an
end-of-day TRAILING drawdown account a deficit costs twice:

  1. ROOM. The floor trails the highest CLOSING balance and never retreats. The
     account peaked at $25,000, so the floor is $24,000 no matter what happens
     next. Down $500 means $500 of room, not $1,000 — half the survival margin.
  2. DISTANCE. The payout buffer is fixed at $26,100, so the climb is $1,600
     instead of $1,100 — 45% further, from half the base.

And the sizing rule does NOT automatically compensate: `budget = min($300, room)`
still returns the full $300 while room is $500, so a wounded account keeps taking
full-size trades with half the cushion. Whether that is survivable is the question.

Swept: starting deficit x daily loss budget, so the answer is not just "how bad is
it" but "what should the budget be, given where the account actually is".
"""
from __future__ import annotations

import itertools

import numpy as np
import pandas as pd

import funded_search as fs
import funded_1yr as f1
import lucid_fast as LF

WIN, SL, TP, CAP, MC = (9.75, 11.0), 2.0, 3.0, 440, 10
LONG_SIG, SHORT_SIG = "sr_round100_break", "vol_lw_stretch_short"
DEFICITS = (0, 250, 500, 750)
BUDGETS = (300, 200, 150, 100)

df = fs.load_enriched()
pl = f1.load_plugins(df)
end = df.index[-1]
hold = df[df.index < end - pd.DateOffset(months=5)]
recent = df[df.index >= end - pd.DateOffset(months=5)]


def resolve(frame, name):
    e, _ = pl[name] if name in pl else fs.sig(df, name)
    return pd.Series(e).reindex(frame.index).fillna(False).to_numpy(bool)


def run(P, start_k, deficit, bud, maxdays=365):
    """Floor stays at START-MLL: it trailed the $25,000 peak and never retreats."""
    hi, lo, cl, atr, eth, per = P["hi"], P["lo"], P["cl"], P["atr"], P["eth"], P["per"]
    dates = P["dates"]
    bal = LF.START - deficit
    floor = LF.START - LF.MLL
    locked = False
    cyc_d, cyc_p, cyc_b = 0, 0.0, 0.0
    wd, npay, first = 0.0, 0, None
    t0 = dates[start_k]
    for k in range(start_k, len(per)):
        d = (dates[k] - t0).days
        if d > maxdays:
            break
        s, e, idxs, sides = per[k]
        room = bal - floor
        if room <= 0:
            return dict(fate="BUST", wd=wd, first=first, final=bal)
        budget = min(bud, room)
        net, ntr, j = 0.0, 0, 0
        while j < len(idxs) and ntr < 6:
            i, sd = idxs[j], int(sides[j])
            a, entry = atr[i], cl[i]
            n = min(MC, int((budget + net) / (a * SL * LF.PV)),
                    int((CAP - net) / (a * TP * LF.PV)))
            if n < 1:
                j += 1
                continue
            stop_px, targ_px = entry - sd * a * SL, entry + sd * a * TP
            px, m = None, i + 1
            while m < e:
                if sd > 0:
                    if lo[m] <= stop_px: px = stop_px; break
                    if hi[m] >= targ_px: px = targ_px; break
                else:
                    if hi[m] >= stop_px: px = stop_px; break
                    if lo[m] <= targ_px: px = targ_px; break
                if eth[m] >= 16.0 or m == e - 1:
                    px = cl[m]; break
                m += 1
            if px is None:
                px, m = cl[e - 1], e - 1
            net += sd * (px - entry) * LF.PV * n - LF.FEE * n
            ntr += 1
            while j < len(idxs) and idxs[j] <= m:
                j += 1
        if ntr == 0:
            continue
        bal += net
        cyc_d += 1; cyc_p += net; cyc_b = max(cyc_b, net)
        if bal <= floor:
            return dict(fate="BUST", wd=wd, first=first, final=bal)
        if not locked:
            floor = max(floor, bal - LF.MLL)
            if bal >= LF.BUFFER:
                floor, locked = LF.LOCK_FLOOR, True
        if bal > LF.BUFFER and cyc_d >= LF.MIN_DAYS and cyc_p > 0 \
                and cyc_b <= LF.CONSISTENCY * cyc_p:
            amt = min(bal - LF.BUFFER, LF.CAP_FIRST if npay == 0 else LF.CAP_AFTER)
            if amt >= 250:
                bal -= amt; wd += amt; npay += 1
                if first is None:
                    first = d
                cyc_d, cyc_p, cyc_b = 0, 0.0, 0.0
    return dict(fate="PAID" if npay else "STALLED", wd=wd, first=first, final=bal)


for wname, frame in (("HOLDOUT 2021-2026", hold), ("LAST 5 MONTHS", recent)):
    P = LF.prep(frame, resolve(frame, LONG_SIG), resolve(frame, SHORT_SIG), WIN)
    starts = [k for k in range(0, len(P["per"]), 4) if len(P["per"]) - k >= 20]
    rows = []
    for deficit, bud in itertools.product(DEFICITS, BUDGETS):
        res = [run(P, k, deficit, bud) for k in starts]
        r = pd.DataFrame(res)
        f = r["first"].dropna()
        rows.append(dict(down=f"-${deficit}", budget=f"${bud}",
                         room=f"${1000-deficit}",
                         paid=round(100 * (r.fate == "PAID").mean(), 1),
                         bust=round(100 * (r.fate == "BUST").mean(), 1),
                         stalled=round(100 * (r.fate == "STALLED").mean(), 1),
                         mean=round(r.wd.mean()), med=round(r.wd.median()),
                         days=int(f.median()) if len(f) else -1))
    out = pd.DataFrame(rows)
    pd.set_option("display.width", 170)
    print("=" * 108)
    print(f"STARTING IN A HOLE — {wname}   ({len(starts)} simulated accounts per row)")
    print("floor stays at $24,000 throughout: it trailed the $25,000 peak and never retreats")
    print("=" * 108)
    print(out.to_string(index=False))
    print()

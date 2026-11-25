"""Sweep the WITHDRAWAL THRESHOLD — take a payout as soon as $X is available.

The harness currently withdraws whenever >= $250 is available above the $26,100
buffer. That is one policy among many:

    $250  -> grab it early, drop straight back to the buffer, stay exposed
    $800  -> wait for a near-full payout, keep a cushion while waiting
    $1000 -> hold for the cap

The trade-off is real in both directions: waiting means more of the account sits
above the buffer (safer, since the floor is locked at $25,100 and distance from it
is what keeps you alive) but also means a run that turns over before you hit the
threshold pays nothing at all.
"""
from __future__ import annotations

import itertools

import numpy as np
import pandas as pd

import funded_search as fs
import funded_1yr as f1
import lucid_fast as LF

LONG, SHORT = "sr_round100_break", "vol_lw_stretch_short"
WIN, SL, TP, RF = (9.75, 11.0), 2.0, 3.0, 1.0

df = fs.load_enriched()
pl = f1.load_plugins(df)
g = lambda n: pd.Series((pl[n] if n in pl else fs.sig(df, n))[0]).reindex(df.index).fillna(False).to_numpy(bool)
end = df.index[-1]
hold = df[df.index < end - pd.DateOffset(months=5)]
P = LF.prep(hold, g(LONG)[:len(hold)], g(SHORT)[:len(hold)], WIN)


def trace(start, cap, bud, mc, min_wd, maxdays=365):
    hi, lo, cl, atr, eth, per = P["hi"], P["lo"], P["cl"], P["atr"], P["eth"], P["per"]
    dates = P["dates"]
    bal, floor, locked = LF.START, LF.START - LF.MLL, False
    cyc_d, cyc_p, cyc_b = 0, 0.0, 0.0
    wd, np_, fd = 0.0, 0, None
    t0 = dates[start]
    for k in range(start, len(per)):
        d = (dates[k] - t0).days
        if d > maxdays:
            break
        s, e, idxs, sides = per[k]
        room = bal - floor
        if room <= 0:
            return dict(fate="BUST", wd=wd, pays=np_, first=fd, final=bal)
        budget = min(bud, room * RF)
        net, ntr, j = 0.0, 0, 0
        while j < len(idxs) and ntr < 6:
            i, sd = idxs[j], int(sides[j])
            a = atr[i]
            n = min(mc, int((budget + net) / (a * SL * LF.PV)),
                    int((cap - net) / (a * TP * LF.PV)))
            if n < 1:
                j += 1; continue
            entry = cl[i]
            slp, tpp = entry - sd * a * SL, entry + sd * a * TP
            px, m = None, i + 1
            while m < e:
                if sd > 0:
                    if lo[m] <= slp: px = slp; break
                    if hi[m] >= tpp: px = tpp; break
                else:
                    if hi[m] >= slp: px = slp; break
                    if lo[m] <= tpp: px = tpp; break
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
            return dict(fate="BUST", wd=wd, pays=np_, first=fd, final=bal)
        if not locked:
            floor = max(floor, bal - LF.MLL)
            if bal >= LF.BUFFER:
                floor, locked = LF.LOCK_FLOOR, True
        if bal > LF.BUFFER and cyc_d >= LF.MIN_DAYS and cyc_p > 0 \
                and cyc_b <= LF.CONSISTENCY * cyc_p:
            avail = min(bal - LF.BUFFER, LF.CAP_FIRST if np_ == 0 else LF.CAP_AFTER)
            if avail >= min_wd:
                bal -= avail; wd += avail; np_ += 1
                if fd is None:
                    fd = d
                cyc_d, cyc_p, cyc_b = 0, 0.0, 0.0
    return dict(fate="PAID" if np_ else "STALLED", wd=wd, pays=np_, first=fd,
                final=bal)


rows = []
for (cap, bud), min_wd in itertools.product(((250, 400), (440, 300)),
                                            (250, 400, 600, 800, 1000)):
    res = [trace(k, cap, bud, 10, min_wd)
           for k in range(0, len(P["per"]), 4) if len(P["per"]) - k >= 30]
    r = pd.DataFrame(res)
    n = len(r)
    firsts = r.first.dropna()
    rows.append(dict(cap=cap, budget=bud, min_withdraw=min_wd, n=n,
                     paid=round(100 * (r.fate == "PAID").mean(), 1),
                     stalled=round(100 * (r.fate == "STALLED").mean(), 1),
                     bust=round(100 * (r.fate == "BUST").mean(), 1),
                     mean_wd=round(r.wd.mean()), med_wd=round(r.wd.median()),
                     p75_wd=round(r.wd.quantile(.75)),
                     avg_pays=round(r.pays.mean(), 2),
                     med_days=int(firsts.median()) if len(firsts) else -1))

out = pd.DataFrame(rows)
out.to_csv("withdraw_policy.csv", index=False)
pd.set_option("display.width", 200)
print("=" * 128)
print("WITHDRAWAL THRESHOLD SWEEP — holdout, 1-year horizon, 288 accounts each")
print("=" * 128)
for (cap, bud), grp in out.groupby(["cap", "budget"], sort=False):
    print(f"\n  ### cap ${cap} / budget ${bud}")
    print(grp[["min_withdraw", "paid", "stalled", "bust", "mean_wd", "med_wd",
               "p75_wd", "avg_pays", "med_days"]].to_string(index=False))

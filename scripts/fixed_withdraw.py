"""FIXED-SIZE withdrawals: bank $X and leave the rest in the account.

Every policy tested so far takes EVERYTHING available above the $26,100 buffer
(capped at $1,000/$1,500). That drops the balance straight back to the buffer,
leaving no cushion above the locked $25,100 floor.

Banking a fixed amount and leaving the excess is different: the account keeps a
growing buffer, which is what stops it stalling. The cost is slower cash out.

    take_all  : withdraw min(bal - 26,100, cap)      <- what every earlier run did
    fixed_400 : withdraw exactly $400, leave the rest
    fixed_600 : withdraw exactly $600, leave the rest
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


def trace(start, cap, bud, mc, mode, amt_fixed=None, maxdays=365):
    hi, lo, cl, atr, eth, per = P["hi"], P["lo"], P["cl"], P["atr"], P["eth"], P["per"]
    dates = P["dates"]
    bal, floor, locked = LF.START, LF.START - LF.MLL, False
    cyc_d, cyc_p, cyc_b = 0, 0.0, 0.0
    wd, np_, fd = 0.0, 0, None
    peak_cush = 0.0
    t0 = dates[start]
    for k in range(start, len(per)):
        d = (dates[k] - t0).days
        if d > maxdays:
            break
        s, e, idxs, sides = per[k]
        room = bal - floor
        if room <= 0:
            return dict(fate="BUST", wd=wd, pays=np_, first=fd, final=bal,
                        cush=peak_cush)
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
            return dict(fate="BUST", wd=wd, pays=np_, first=fd, final=bal,
                        cush=peak_cush)
        if not locked:
            floor = max(floor, bal - LF.MLL)
            if bal >= LF.BUFFER:
                floor, locked = LF.LOCK_FLOOR, True
        peak_cush = max(peak_cush, bal - LF.BUFFER)
        if bal > LF.BUFFER and cyc_d >= LF.MIN_DAYS and cyc_p > 0 \
                and cyc_b <= LF.CONSISTENCY * cyc_p:
            room_above = bal - LF.BUFFER
            capn = LF.CAP_FIRST if np_ == 0 else LF.CAP_AFTER
            if mode == "take_all":
                take = min(room_above, capn)
                ok = take >= 250
            else:                              # fixed: only if the full amount is there
                take = min(amt_fixed, capn)
                ok = room_above >= amt_fixed
            if ok:
                bal -= take; wd += take; np_ += 1
                if fd is None:
                    fd = d
                cyc_d, cyc_p, cyc_b = 0, 0.0, 0.0
    return dict(fate="PAID" if np_ else "STALLED", wd=wd, pays=np_, first=fd,
                final=bal, cush=peak_cush)


rows = []
CONFIGS = ((250, 400), (440, 300))
POLICIES = [("take_all", None), ("fixed", 400), ("fixed", 600), ("fixed", 800)]
for (cap, bud), (mode, amt) in itertools.product(CONFIGS, POLICIES):
    res = [trace(k, cap, bud, 10, mode, amt)
           for k in range(0, len(P["per"]), 4) if len(P["per"]) - k >= 30]
    r = pd.DataFrame(res)
    n = len(r)
    f = r["first"].dropna()
    rows.append(dict(cap=cap, budget=bud,
                     policy=("take all" if mode == "take_all" else f"bank ${amt}"),
                     paid=round(100 * (r.fate == "PAID").mean(), 1),
                     stalled=round(100 * (r.fate == "STALLED").mean(), 1),
                     bust=round(100 * (r.fate == "BUST").mean(), 1),
                     mean_wd=round(r.wd.mean()), med_wd=round(r.wd.median()),
                     p75_wd=round(r.wd.quantile(.75)),
                     avg_pays=round(r.pays.mean(), 2),
                     med_days=int(f.median()) if len(f) else -1,
                     med_final=round(r.final.median())))

out = pd.DataFrame(rows)
out.to_csv("fixed_withdraw.csv", index=False)
pd.set_option("display.width", 200)
print("=" * 132)
print("BANK A FIXED AMOUNT AND LEAVE THE REST  vs  TAKE EVERYTHING")
print("holdout, 1-year horizon, 288 accounts per row")
print("=" * 132)
for (cap, bud), grp in out.groupby(["cap", "budget"], sort=False):
    print(f"\n  ### cap ${cap} / budget ${bud}")
    print(grp[["policy", "paid", "stalled", "bust", "mean_wd", "med_wd", "p75_wd",
               "avg_pays", "med_days", "med_final"]].to_string(index=False))

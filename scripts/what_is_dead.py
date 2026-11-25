"""What actually happens to the 24.7% that never pay?

'dead' has been lumping together two very different fates:
  BUST     — breached the $25,100 floor. The account is gone.
  STALLED  — survived the whole year but never got above $26,350, so nothing
             could be withdrawn. You still HAVE the account; it just earned nothing.
This separates them and shows where the stalled accounts actually end up.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import funded_search as fs
import funded_1yr as f1
import lucid_fast as LF

LONG, SHORT = "sr_round100_break", "vol_lw_stretch_short"
WIN, SL, TP, RF, CAP, BUD, MC = (9.75, 11.0), 2.0, 3.0, 1.0, 250, 400, 10

df = fs.load_enriched()
pl = f1.load_plugins(df)
g = lambda n: pd.Series((pl[n] if n in pl else fs.sig(df, n))[0]).reindex(df.index).fillna(False).to_numpy(bool)
end = df.index[-1]
hold = df[df.index < end - pd.DateOffset(months=5)]
P = LF.prep(hold, g(LONG)[:len(hold)], g(SHORT)[:len(hold)], WIN)


def trace(start, maxdays=365):
    hi, lo, cl, atr, eth, per = P["hi"], P["lo"], P["cl"], P["atr"], P["eth"], P["per"]
    dates = P["dates"]
    bal, floor, locked = LF.START, LF.START - LF.MLL, False
    cyc_d, cyc_p, cyc_b = 0, 0.0, 0.0
    wd, np_ = 0.0, 0
    peak = bal
    t0 = dates[start]
    for k in range(start, len(per)):
        d = (dates[k] - t0).days
        if d > maxdays:
            break
        s, e, idxs, sides = per[k]
        room = bal - floor
        if room <= 0:
            return dict(fate="BUST", final=bal, peak=peak, wd=wd, pays=np_)
        budget = min(BUD, room * RF)
        net, ntr, j = 0.0, 0, 0
        while j < len(idxs) and ntr < 6:
            i, sd = idxs[j], int(sides[j])
            a = atr[i]
            n = min(MC, int((budget + net) / (a * SL * LF.PV)),
                    int((CAP - net) / (a * TP * LF.PV)))
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
        peak = max(peak, bal)
        cyc_d += 1; cyc_p += net; cyc_b = max(cyc_b, net)
        if bal <= floor:
            return dict(fate="BUST", final=bal, peak=peak, wd=wd, pays=np_)
        if not locked:
            floor = max(floor, bal - LF.MLL)
            if bal >= LF.BUFFER:
                floor, locked = LF.LOCK_FLOOR, True
        if bal > LF.BUFFER and cyc_d >= LF.MIN_DAYS and cyc_p > 0 \
                and cyc_b <= LF.CONSISTENCY * cyc_p:
            amt = min(bal - LF.BUFFER, LF.CAP_FIRST if np_ == 0 else LF.CAP_AFTER)
            if amt >= 250:
                bal -= amt; wd += amt; np_ += 1
                cyc_d, cyc_p, cyc_b = 0, 0.0, 0.0
    return dict(fate="PAID" if np_ else "STALLED", final=bal, peak=peak,
                wd=wd, pays=np_)


res = [trace(k) for k in range(0, len(P["per"]), 4) if len(P["per"]) - k >= 30]
r = pd.DataFrame(res)
n = len(r)
print("=" * 84)
print(f"CAP $250 / BUDGET $400 — {n} simulated accounts, 1-year horizon")
print("=" * 84)
for f in ("PAID", "STALLED", "BUST"):
    s = r[r.fate == f]
    print(f"  {f:<9}{len(s):>5}  ({100*len(s)/n:>5.1f}%)")

print("\n" + "=" * 84)
print("THE STALLED ACCOUNTS — where do they actually end up?")
print("=" * 84)
st = r[r.fate == "STALLED"]
if len(st):
    print(f"  count {len(st)}")
    print(f"  final balance : median ${st.final.median():,.0f}   "
          f"p25 ${st.final.quantile(.25):,.0f}   p75 ${st.final.quantile(.75):,.0f}")
    print(f"  PEAK reached  : median ${st.peak.median():,.0f}   "
          f"max ${st.peak.max():,.0f}   (needed $26,350 to withdraw)")
    print(f"  still above the $25,100 floor : "
          f"{100*(st.final > LF.LOCK_FLOOR).mean():.0f}%")
    print(f"  still above the $25,000 start : "
          f"{100*(st.final > LF.START).mean():.0f}%")
    print(f"  how close did they get? median shortfall from $26,350: "
          f"${26350 - st.peak.median():,.0f}")

print("\n" + "=" * 84)
print("THE BUSTED ACCOUNTS")
print("=" * 84)
b = r[r.fate == "BUST"]
print(f"  count {len(b)}  ({100*len(b)/n:.1f}%)")
if len(b):
    print(f"  final balance : median ${b.final.median():,.0f}")
    print(f"  peak reached  : median ${b.peak.median():,.0f}")

print("\n" + "=" * 84)
print("PLAIN ENGLISH")
print("=" * 84)
print(f"  Out of {n} accounts started:")
print(f"    {100*(r.fate=='PAID').mean():.1f}% paid you money")
print(f"    {100*(r.fate=='STALLED').mean():.1f}% still exist and still trade, but never")
print(f"        cleared $26,350 in the year, so nothing could be withdrawn")
print(f"    {100*(r.fate=='BUST').mean():.1f}% actually lost the account")

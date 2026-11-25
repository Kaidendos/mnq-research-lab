"""Is pay_pct real? Trace actual balance paths and check the 26,100 gate.

Challenge: a payout requires the balance ABOVE 26,100 (buffer = 25,000 + 1,000 MLL
+ 100). So how can 53% of accounts get paid? Verify by tracing, not by asserting.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import funded_search as fs
import funded_1yr as f1
import lucid_fast as LF

LONG, SHORT = "sr_round100_break", "vol_lw_stretch_short"
WIN, SL, TP, RF, CAP, MC = (9.75, 11.0), 2.0, 3.0, 1.0, 440, 10

df = fs.load_enriched()
pl = f1.load_plugins(df)
g = lambda n: pd.Series((pl[n] if n in pl else fs.sig(df, n))[0]).reindex(df.index).fillna(False).to_numpy(bool)
end = df.index[-1]
w5 = end - pd.DateOffset(months=5)
hold = df[df.index < w5]
P = LF.prep(hold, g(LONG)[:len(hold)], g(SHORT)[:len(hold)], WIN)

print("=" * 92)
print("THE GATE, restated from the code")
print("=" * 92)
print(f"  START        = ${LF.START:,.0f}")
print(f"  MLL          = ${LF.MLL:,.0f}")
print(f"  BUFFER       = ${LF.BUFFER:,.0f}   <- balance must EXCEED this")
print(f"  min request  = $250")
print(f"  => a payout needs balance >= ${LF.BUFFER + 250:,.0f}, i.e. "
      f"+${LF.BUFFER + 250 - LF.START:,.0f} profit")
print(f"  plus: >= {LF.MIN_DAYS} trading days in the cycle")
print(f"  plus: biggest green day <= {LF.CONSISTENCY:.0%} of cycle profit")


def trace(first, maxdays=150):
    """Replay one account, recording the daily balance path."""
    hi, lo, cl, atr, eth, per = P["hi"], P["lo"], P["cl"], P["atr"], P["eth"], P["per"]
    dates = P["dates"]
    bal, floor, locked = LF.START, LF.START - LF.MLL, False
    cyc_d, cyc_p, cyc_b = 0, 0.0, 0.0
    payouts, withdrawn = 0, 0.0
    path, events = [], []
    t0 = dates[first]
    for k in range(first, len(per)):
        if (dates[k] - t0).days > maxdays:
            break
        s, e, idxs, sides = per[k]
        room = bal - floor
        if room <= 0:
            events.append(("BUST", dates[k], bal)); break
        budget = min(300, room * RF)
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
        cyc_d += 1; cyc_p += net; cyc_b = max(cyc_b, net)
        path.append((dates[k], bal))
        if bal <= floor:
            events.append(("BUST", dates[k], bal)); break
        if not locked:
            floor = max(floor, bal - LF.MLL)
            if bal >= LF.BUFFER:
                floor, locked = LF.LOCK_FLOOR, True
                events.append(("LOCK", dates[k], bal))
        if bal > LF.BUFFER and cyc_d >= LF.MIN_DAYS and cyc_p > 0 \
                and cyc_b <= LF.CONSISTENCY * cyc_p:
            amt = min(bal - LF.BUFFER, LF.CAP_FIRST if payouts == 0 else LF.CAP_AFTER)
            if amt >= 250:
                bal -= amt; withdrawn += amt; payouts += 1
                events.append(("PAYOUT", dates[k], amt))
                cyc_d, cyc_p, cyc_b = 0, 0.0, 0.0
    return path, events, payouts, withdrawn


print("\n" + "=" * 92)
print("PEAK BALANCE REACHED — across many account starts (150-day horizon)")
print("=" * 92)
peaks, paid_flags, n = [], [], 0
for k in range(0, len(P["per"]), 10):
    if len(P["per"]) - k < 15:
        continue
    path, ev, pay, wd = trace(k)
    if not path:
        continue
    peaks.append(max(b for _, b in path))
    paid_flags.append(pay >= 1)
    n += 1
peaks = np.array(peaks)
paid = np.array(paid_flags)
print(f"  accounts traced        : {n}")
print(f"  reached > $26,100      : {100*(peaks > LF.BUFFER).mean():>5.1f}%")
print(f"  reached >= $26,350     : {100*(peaks >= LF.BUFFER+250).mean():>5.1f}%")
print(f"  reached >= $27,100     : {100*(peaks >= 27100).mean():>5.1f}%")
print(f"  actually got a payout  : {100*paid.mean():>5.1f}%")
print(f"  peak balance: median ${np.median(peaks):,.0f}  "
      f"p25 ${np.percentile(peaks,25):,.0f}  p75 ${np.percentile(peaks,75):,.0f}  "
      f"max ${peaks.max():,.0f}")

print("\n  SANITY: 'got a payout' must be <= 'reached >= $26,350'.")
ok = (100*paid.mean()) <= (100*(peaks >= LF.BUFFER+250).mean()) + 0.01
print(f"  consistent: {ok}")

print("\n" + "=" * 92)
print("ONE FULL ACCOUNT TRACE (first paying account found)")
print("=" * 92)
for k in range(0, len(P["per"]), 10):
    path, ev, pay, wd = trace(k)
    if pay >= 1:
        print(f"  start {P['dates'][k]:%Y-%m-%d}   payouts {pay}   withdrawn ${wd:,.0f}")
        print(f"  {'date':<13}{'balance':>11}")
        for dt, b in path[:26]:
            mark = ""
            for typ, edt, val in ev:
                if edt == dt:
                    mark = f"   <- {typ}" + (f" ${val:,.0f}" if typ == "PAYOUT" else f" (bal ${val:,.0f})")
            print(f"  {dt:%Y-%m-%d}{b:>11,.0f}{mark}")
        break

print("\n" + "=" * 92)
print("WITHDRAWAL SIZE DISTRIBUTION — how much does a 'payout' actually pay?")
print("=" * 92)
amts = []
for k in range(0, len(P["per"]), 6):
    if len(P["per"]) - k < 15:
        continue
    path, ev, pay, wd = trace(k)
    amts += [v for t, _, v in ev if t == "PAYOUT"]
if amts:
    a = np.array(amts)
    print(f"  payout events {len(a)}   median ${np.median(a):,.0f}   "
          f"mean ${a.mean():,.0f}   min ${a.min():,.0f}   max ${a.max():,.0f}")
    for lo_, hi_ in ((250, 500), (500, 750), (750, 1000), (1000, 1001)):
        c = ((a >= lo_) & (a < hi_)).sum() if hi_ > lo_ + 1 else (a >= 1000).sum()
        lbl = f"${lo_}-{hi_}" if hi_ > lo_ + 1 else "$1,000 (cap)"
        print(f"    {lbl:<14}{c:>5}  ({100*c/len(a):>4.1f}%)")

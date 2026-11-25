"""When do the payouts actually arrive? Full timeline, not just the first.

'avg_pays 3.61' is the mean over a 1-YEAR horizon and includes the accounts that
got zero. 'med_days 92' is the median wait for the FIRST payout only. Those two
numbers describe different things and should not be read together.
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
    pays = []
    t0 = dates[start]
    for k in range(start, len(per)):
        d = (dates[k] - t0).days
        if d > maxdays:
            break
        s, e, idxs, sides = per[k]
        room = bal - floor
        if room <= 0:
            return "BUST", pays
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
        cyc_d += 1; cyc_p += net; cyc_b = max(cyc_b, net)
        if bal <= floor:
            return "BUST", pays
        if not locked:
            floor = max(floor, bal - LF.MLL)
            if bal >= LF.BUFFER:
                floor, locked = LF.LOCK_FLOOR, True
        if bal > LF.BUFFER and cyc_d >= LF.MIN_DAYS and cyc_p > 0 \
                and cyc_b <= LF.CONSISTENCY * cyc_p:
            amt = min(bal - LF.BUFFER, LF.CAP_FIRST if not pays else LF.CAP_AFTER)
            if amt >= 250:
                bal -= amt
                pays.append((d, amt))
                cyc_d, cyc_p, cyc_b = 0, 0.0, 0.0
    return ("PAID" if pays else "STALLED"), pays


res = [trace(k) for k in range(0, len(P["per"]), 4) if len(P["per"]) - k >= 30]
n = len(res)
payers = [p for f, p in res if p]
print("=" * 88)
print(f"CAP $250 / BUDGET $400 / take-all — {n} accounts, 1-YEAR horizon")
print("=" * 88)
print(f"  got >=1 payout : {len(payers)}/{n}  ({100*len(payers)/n:.1f}%)")
cnt = np.array([len(p) for f, p in res])
print(f"\n  PAYOUTS PER ACCOUNT over the year:")
print(f"    across ALL accounts   : mean {cnt.mean():.2f}  median {int(np.median(cnt))}")
pc = np.array([len(p) for p in payers])
print(f"    among PAYERS only     : mean {pc.mean():.2f}  median {int(np.median(pc))}"
      f"  max {pc.max()}")
print(f"\n  distribution (all accounts):")
for k in range(0, 9):
    c = (cnt == k).sum() if k < 8 else (cnt >= 8).sum()
    lbl = f"{k}" if k < 8 else "8+"
    print(f"    {lbl:>3} payouts : {c:>4}  ({100*c/n:>5.1f}%)")

print("\n" + "=" * 88)
print("WHEN DO THEY ARRIVE?  (median day of the Nth payout, payers only)")
print("=" * 88)
print(f"  {'payout #':<10}{'accounts reaching it':>22}{'median day':>13}{'median $':>11}")
for i in range(6):
    got = [p[i] for p in payers if len(p) > i]
    if not got:
        break
    days = np.array([d for d, _ in got])
    amts = np.array([a for _, a in got])
    print(f"  {i+1:<10}{len(got):>22}{int(np.median(days)):>13}{np.median(amts):>11,.0f}")

print("\n" + "=" * 88)
print("CUMULATIVE — % of ALL accounts paid by day X")
print("=" * 88)
firsts = np.array([p[0][0] for p in payers])
for w in (30, 60, 92, 120, 180, 270, 365):
    print(f"    by day {w:>3}: {100*(firsts <= w).sum()/n:>5.1f}% of all accounts "
          f"have had a first payout")

print("\n" + "=" * 88)
print("IN THE FIRST 92 DAYS SPECIFICALLY")
print("=" * 88)
in92 = [[x for x in p if x[0] <= 92] for p in payers]
c92 = np.array([len(x) for x in in92])
tot92 = np.array([sum(a for _, a in x) for x in in92])
allc92 = np.zeros(n); allc92[:len(c92)] = c92
print(f"  payouts within 92 days, among payers : mean {c92.mean():.2f}  "
      f"median {int(np.median(c92))}  max {c92.max()}")
print(f"  cash within 92 days, among payers    : median ${np.median(tot92):,.0f}  "
      f"mean ${tot92.mean():,.0f}")
print(f"  across ALL {n} accounts              : mean ${tot92.sum()/n:,.0f}")

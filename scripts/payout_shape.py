"""Reconciling "first payout in 27 days" with "median $334 a year".

They look contradictory and are not — they are computed over different populations:

  "27 days"  is the median wait among accounts that EVER GET PAID (56% of them).
             The 44% that never pay contribute nothing to it; they have no wait
             to measure.
  "$334"     is the median over ALL accounts, including every account that got
             $0. With 44% earning nothing, the 50th percentile sits just barely
             inside the paying group — so the median account is one that scrapes
             a single small payout, not one that collects all year.

Both are honest; quoting them side by side without saying which population each
covers is what makes them read as a contradiction.

This prints the full distribution so the shape is visible instead of inferred:
percentiles across all accounts, the same conditioned on paying, and what the
first payout is actually worth.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import funded_search as fs
import funded_1yr as f1
import lucid_fast as LF

WIN, SL, TP, CAP, BUD, MC = (9.75, 11.0), 2.0, 3.0, 440, 300, 10
LONG_SIG, SHORT_SIG = "sr_round100_break", "vol_lw_stretch_short"

df = fs.load_enriched()
pl = f1.load_plugins(df)
end = df.index[-1]
hold = df[df.index < end - pd.DateOffset(months=5)]


def resolve(frame, name):
    e, _ = pl[name] if name in pl else fs.sig(df, name)
    return pd.Series(e).reindex(frame.index).fillna(False).to_numpy(bool)


P = LF.prep(hold, resolve(hold, LONG_SIG), resolve(hold, SHORT_SIG), WIN)


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
        budget = min(BUD, room)
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


res = [trace(k) for k in range(0, len(P["per"]), 4) if len(P["per"]) - k >= 20]
n = len(res)
totals = np.array([sum(a for _, a in p) for _, p in res])
payers = [p for f, p in res if p]

print("=" * 92)
print(f"cap $440 / budget $300 — {n} accounts, 1-year horizon, holdout")
print("=" * 92)
print(f"  PAID {100*len(payers)/n:.1f}%   "
      f"STALLED {100*sum(f == 'STALLED' for f, _ in res)/n:.1f}%   "
      f"BUST {100*sum(f == 'BUST' for f, _ in res)/n:.1f}%")

print(f"\n  TOTAL WITHDRAWN IN A YEAR — across ALL {n} accounts")
for q in (10, 25, 40, 50, 60, 75, 90, 95):
    print(f"    {q:>3}th percentile : ${np.percentile(totals, q):>8,.0f}")
print(f"    {'mean':>15} : ${totals.mean():>8,.0f}")
print(f"\n    accounts earning exactly $0 : {100*(totals == 0).mean():.1f}%")
print("    ^ this is why the MEDIAN is low: it is measured over everyone,")
print("      and the 50th percentile account has only just started earning.")

pt = totals[totals > 0]
print(f"\n  SAME FIGURE, but only over the {len(pt)} accounts that DID get paid")
for q in (25, 50, 75, 90):
    print(f"    {q:>3}th percentile : ${np.percentile(pt, q):>8,.0f}")
print(f"    {'mean':>15} : ${pt.mean():>8,.0f}")

print(f"\n  THE FIRST PAYOUT ITSELF (payers only)")
firsts = np.array([p[0][1] for p in payers])
fdays = np.array([p[0][0] for p in payers])
print(f"    median day    : {int(np.median(fdays))}   <- this is the '27 days' figure")
print(f"    median amount : ${np.median(firsts):,.0f}")
print(f"    mean amount   : ${firsts.mean():,.0f}")

print(f"\n  HOW MANY PAYOUTS IN THE YEAR")
cnt = np.array([len(p) for _, p in res])
for k in range(0, 6):
    c = int((cnt == k).sum()) if k < 5 else int((cnt >= 5).sum())
    print(f"    {('5+' if k == 5 else k):>3} payouts : {c:>4}  ({100*c/n:>5.1f}%)")
print(f"\n    median payouts across ALL accounts : {int(np.median(cnt))}")
print(f"    median payouts among PAYERS        : "
      f"{int(np.median([len(p) for p in payers]))}")

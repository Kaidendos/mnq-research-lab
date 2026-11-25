"""Starting a fresh account today: how long until the first payout?

Recommended config, verified LucidPro 25K rules. Reports the FULL distribution,
including the accounts that never pay — an average over survivors only would be a
lie by omission.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import funded_search as fs
import funded_1yr as f1
import lucid_fast as LF

LONG, SHORT = "sr_round100_break", "vol_lw_stretch_short"
WIN, SL, TP, RF, CAP, MC, BUD = (9.75, 11.0), 2.0, 3.0, 1.0, 440, 10, 300

df = fs.load_enriched()
pl = f1.load_plugins(df)
g = lambda n: pd.Series((pl[n] if n in pl else fs.sig(df, n))[0]).reindex(df.index).fillna(False).to_numpy(bool)
EL, ES = g(LONG), g(SHORT)


def trace(frame, el, es, first, maxdays):
    P = LF.prep(frame, el, es, WIN)
    hi, lo, cl, atr, eth, per = P["hi"], P["lo"], P["cl"], P["atr"], P["eth"], P["per"]
    dates = P["dates"]
    if first >= len(per):
        return None
    bal, floor, locked = LF.START, LF.START - LF.MLL, False
    cyc_d, cyc_p, cyc_b = 0, 0.0, 0.0
    payouts = []
    t0 = dates[first]
    for k in range(first, len(per)):
        d = (dates[k] - t0).days
        if d > maxdays:
            break
        s, e, idxs, sides = per[k]
        room = bal - floor
        if room <= 0:
            return dict(outcome="BUST", days=d, payouts=payouts)
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
            return dict(outcome="BUST", days=d, payouts=payouts)
        if not locked:
            floor = max(floor, bal - LF.MLL)
            if bal >= LF.BUFFER:
                floor, locked = LF.LOCK_FLOOR, True
        if bal > LF.BUFFER and cyc_d >= LF.MIN_DAYS and cyc_p > 0 \
                and cyc_b <= LF.CONSISTENCY * cyc_p:
            amt = min(bal - LF.BUFFER, LF.CAP_FIRST if not payouts else LF.CAP_AFTER)
            if amt >= 250:
                bal -= amt
                payouts.append((d, amt))
                cyc_d, cyc_p, cyc_b = 0, 0.0, 0.0
    return dict(outcome="ALIVE" if payouts else "NO PAYOUT", days=maxdays,
                payouts=payouts)


for lbl, frame, el, es in (("HOLDOUT (2021-08 -> 2026-03, 1181 sessions)",
                            df[df.index < df.index[-1] - pd.DateOffset(months=5)],
                            EL, ES),):
    n = len(frame)
    el2, es2 = EL[:n], ES[:n]
    P = LF.prep(frame, el2, es2, WIN)
    res = []
    for k in range(0, len(P["per"]), 4):
        if len(P["per"]) - k < 30:
            continue
        r = trace(frame, el2, es2, k, 365)
        if r:
            res.append(r)
    print("=" * 90)
    print(f"STARTING A FRESH ACCOUNT — {lbl}")
    print(f"{len(res)} simulated starts, 1-year horizon")
    print("=" * 90)
    first = [r["payouts"][0][0] for r in res if r["payouts"]]
    firstamt = [r["payouts"][0][1] for r in res if r["payouts"]]
    nopay = sum(1 for r in res if not r["payouts"])
    bust = sum(1 for r in res if r["outcome"] == "BUST")
    print(f"  got at least one payout : {len(first)}/{len(res)}  "
          f"({100*len(first)/len(res):.1f}%)")
    print(f"  never paid              : {nopay}/{len(res)}  "
          f"({100*nopay/len(res):.1f}%)   [of which busted: {bust}]")
    if first:
        a = np.array(first)
        print(f"\n  DAYS TO FIRST PAYOUT (only the {len(first)} that got one):")
        print(f"    median {int(np.median(a))}   p25 {int(np.percentile(a,25))}   "
              f"p75 {int(np.percentile(a,75))}   p90 {int(np.percentile(a,90))}   "
              f"max {a.max()}")
        for w in (14, 30, 60, 90, 180):
            print(f"    within {w:>3} days: {100*(a<=w).mean()*len(first)/len(res):>5.1f}% "
                  f"of ALL accounts   ({100*(a<=w).mean():>5.1f}% of payers)")
        b = np.array(firstamt)
        print(f"\n  SIZE OF THAT FIRST PAYOUT: median ${np.median(b):,.0f}  "
              f"mean ${b.mean():,.0f}  min ${b.min():,.0f}  max ${b.max():,.0f}")
        tot = [sum(x[1] for x in r["payouts"]) for r in res]
        t = np.array(tot)
        print(f"\n  TOTAL withdrawn in the year: median ${np.median(t):,.0f}  "
              f"mean ${t.mean():,.0f}  p75 ${np.percentile(t,75):,.0f}")

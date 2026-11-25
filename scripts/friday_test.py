"""Backtest the LIVE strategy on Fridays only, whole day, last 5 months.

Live config = StochReclaim30 as actually deployed (159D4485):
    raw %K(14) crosses UP through 30, bar closes in its upper half, LONG only
    stop 0.75*ATR(14), target 0.5*ATR(14)
    <=10 MNQ, DayMaxProfit $440, DayMaxLoss $300, StopWhenGreen, max 6 trades/day
"whole day" = 09:30-16:00 ET (the live entry window is 09:45-11:35; overridden here).

~21 Fridays in 5 months is a tiny sample, so every other weekday and a longer
Friday history are shown alongside — a single-day number in isolation is unreadable.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import funded_search as fs
import funded_1yr as f1

LIVE = dict(sl=0.75, tp=0.5, win=(9.5, 16.0), gate=None, cap=440, budget=300, maxc=10)
DAYS = {0: "Monday", 1: "Tuesday", 2: "Wednesday", 3: "Thursday", 4: "Friday"}

df = fs.load_enriched()
entry, side = fs.sig(df, "stoch30_long")
entry = entry.reindex(df.index).fillna(False)
end = df.index[-1]

def run(d, ent):
    return fs.replay(d, ent.reindex(d.index).fillna(False), side,
                     LIVE["sl"], LIVE["tp"], LIVE["win"], LIVE["gate"],
                     LIVE["cap"], LIVE["budget"], maxc=LIVE["maxc"])

def stats(daily, ntr, nwin, label, sessions):
    if ntr == 0:
        print(f"  {label:<26}{sessions:>6}{0:>8}{'-':>8}{'-':>11}{'-':>10}{'-':>9}{'-':>9}")
        return
    g = daily[daily > 0]; r = daily[daily < 0]
    print(f"  {label:<26}{sessions:>6}{ntr:>8}{100*nwin/ntr:>7.1f}%"
          f"{daily.sum():>11,.0f}{daily.mean():>10,.0f}"
          f"{(g.mean() if len(g) else 0):>9,.0f}{(r.mean() if len(r) else 0):>9,.0f}")

for months, tag in ((5, "LAST 5 MONTHS"), (60, "FULL 5 YEARS")):
    w = end - pd.DateOffset(months=months)
    d = df[df.index >= w]
    print("\n" + "=" * 96)
    print(f"{tag}   ({d.index[0]:%Y-%m-%d} -> {d.index[-1]:%Y-%m-%d})   LIVE CONFIG, whole day 09:30-16:00")
    print("=" * 96)
    print(f"  {'':<26}{'sess':>6}{'trades':>8}{'win%':>8}{'net $':>11}{'$/day':>10}"
          f"{'avg grn':>9}{'avg red':>9}")
    daily_all, ntr, nwin = run(d, entry)
    stats(daily_all, ntr, nwin, "ALL DAYS", d["_day"].nunique())
    print("  " + "-" * 78)
    for dow, name in DAYS.items():
        sub = d[d.index.dayofweek == dow]
        if not len(sub):
            continue
        dl, nt, nw = run(sub, entry)
        stats(dl, nt, nw, name, sub["_day"].nunique())

# ── Friday deep-dive, last 5 months ──
w5 = end - pd.DateOffset(months=5)
fri = df[(df.index >= w5) & (df.index.dayofweek == 4)]
dl, nt, nw = run(fri, entry)
print("\n" + "=" * 96)
print(f"FRIDAY DEEP-DIVE — last 5 months ({fri['_day'].nunique()} Fridays, {nt} trades)")
print("=" * 96)
if nt:
    print(f"  net ${dl.sum():,.0f} | win {100*nw/nt:.1f}% | traded days {len(dl)} | "
          f"green {int((dl>0).sum())} red {int((dl<0).sum())}")
    print(f"  best day ${dl.max():,.0f}   worst day ${dl.min():,.0f}   median ${dl.median():,.0f}")
    print(f"\n  {'date':<14}{'net $':>10}  equity")
    eq = 0.0
    for dt, v in dl.items():
        eq += v
        print(f"  {dt:%Y-%m-%d}{v:>10,.0f}  {eq:>8,.0f}")
    # is Friday actually different, or is this small-sample noise?
    others = df[(df.index >= w5) & (df.index.dayofweek != 4)]
    ol, ont, onw = run(others, entry)
    print(f"\n  Friday   : {len(dl)} traded days, ${dl.mean():,.0f}/day, win {100*nw/nt:.1f}%")
    print(f"  Mon-Thu  : {len(ol)} traded days, ${ol.mean():,.0f}/day, win {100*onw/ont:.1f}%")
    # bootstrap: could a random 21-day subset look this good?
    rng = np.random.default_rng(7)
    pool = pd.concat([dl, ol])
    draws = [rng.choice(pool.values, size=len(dl), replace=True).mean() for _ in range(5000)]
    pct = 100 * (np.array(draws) < dl.mean()).mean()
    print(f"\n  Bootstrap: a random {len(dl)}-day sample from the same pool beats "
          f"Friday's ${dl.mean():,.0f}/day {100-pct:.1f}% of the time")
    print(f"  -> Friday sits at the {pct:.0f}th percentile of pure chance")
else:
    print("  no trades")

"""EVAL config vs FUNDED config — same signal, different risk settings.

EVAL   (StochReclaim30_2026-07-15_pre-session_2F4842DD):
    DayMaxLoss $500, DayMaxProfit $1500, StopAfterWin FALSE
FUNDED (StochReclaim30_2026-07-22_funded_budget300_159D4485, live now):
    DayMaxLoss $300, DayMaxProfit  $440, StopWhenGreen TRUE

Identical otherwise: %K(14) cross up 30, upper-half close, long only,
0.75*ATR stop / 0.5*ATR target, <=10 MNQ, 6 trades/day, entries 09:45-11:35 ET.

Because sizing is n ~= budget/(ATR*SL*PV), the eval's larger budget scales BOTH
the win and the loss by 500/300 = 1.67x. The reward:risk ratio is unchanged --
it is the same strategy with the volume turned up.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import funded_search as fs
import funded_1yr as f1

WIN = (9.6667, 11.5)          # bar-close 09:45-11:35
CFGS = {
    "EVAL  (500/1500/no-stop)":  dict(budget=500, cap=1500, stop_green=False),
    "FUNDED (300/440/stop-green)": dict(budget=300, cap=440, stop_green=True),
}

df = fs.load_enriched()
entry, side = fs.sig(df, "stoch30_long")
entry = entry.reindex(df.index).fillna(False)
end = df.index[-1]

print("STRUCTURAL CEILING (ATR cancels; win = budget/1.5, loss = budget)")
print("=" * 78)
for atr in (30, 45, 60):
    print(f"  ATR {atr}:")
    for lbl, c in CFGS.items():
        su, tu = atr * 0.75 * 2, atr * 0.5 * 2
        n = min(10, int(c["budget"] // su), int(c["cap"] // tu))
        print(f"    {lbl:<28} n={n:<3} win ${n*tu:>5.0f}  loss ${n*su:>5.0f}")

def run(d, c, span):
    daily, ntr, nwin = fs.replay(d, entry.reindex(d.index).fillna(False), side,
                                 0.75, 0.5, WIN, None, c["cap"], c["budget"],
                                 stop_green=c["stop_green"], maxc=10)
    m = f1.score(daily, span)
    return daily, ntr, nwin, m

for months, tag in ((5, "LAST 5 MONTHS"), (12, "LAST 12 MONTHS"), (60, "FULL 5 YEARS")):
    w = end - pd.DateOffset(months=months)
    d = df[df.index >= w]
    span = (d.index[-1] - d.index[0]).days
    print("\n" + "=" * 100)
    print(f"{tag}  ({d.index[0]:%Y-%m-%d} -> {d.index[-1]:%Y-%m-%d}, {d['_day'].nunique()} sessions)")
    print("=" * 100)
    print(f"  {'config':<30}{'trades':>8}{'win%':>7}{'net $':>11}{'avg win':>9}"
          f"{'avg loss':>10}{'payouts':>9}{'busts':>7}{'bust%':>8}{'cal/pay':>9}")
    for lbl, c in CFGS.items():
        daily, ntr, nwin, m = run(d, c, span)
        g, r = daily[daily > 0], daily[daily < 0]
        print(f"  {lbl:<30}{ntr:>8}{100*nwin/ntr if ntr else 0:>6.1f}%"
              f"{daily.sum():>11,.0f}{(g.mean() if len(g) else 0):>9,.0f}"
              f"{(r.mean() if len(r) else 0):>10,.0f}{m['payouts']:>9}{m['busts']:>7}"
              f"{m['bust_pct']:>7.1f}%{m['cal_per_payout']:>9}")
        if lbl.startswith("EVAL"):
            print(f"    worst day ${daily.min():>8,.0f}   best day ${daily.max():>8,.0f}   "
                  f"days losing >$400: {int((daily < -400).sum())}")
        else:
            print(f"    worst day ${daily.min():>8,.0f}   best day ${daily.max():>8,.0f}")

# Fridays only, 5 months
print("\n" + "=" * 100)
print("FRIDAYS ONLY, LAST 5 MONTHS")
print("=" * 100)
w5 = end - pd.DateOffset(months=5)
fri = df[(df.index >= w5) & (df.index.dayofweek == 4)]
span = (fri.index[-1] - fri.index[0]).days
print(f"  {'config':<30}{'trades':>8}{'win%':>7}{'net $':>11}{'worst day':>12}{'best day':>11}")
for lbl, c in CFGS.items():
    daily, ntr, nwin, m = run(fri, c, span)
    print(f"  {lbl:<30}{ntr:>8}{100*nwin/ntr if ntr else 0:>6.1f}%{daily.sum():>11,.0f}"
          f"{daily.min():>12,.0f}{daily.max():>11,.0f}")

print("\n" + "=" * 100)
print("THE RISK THE EVAL SETTINGS CARRY AGAINST A $1,000 TRAILING DRAWDOWN")
print("=" * 100)
d5 = df[df.index >= end - pd.DateOffset(months=60)]
span = (d5.index[-1] - d5.index[0]).days
for lbl, c in CFGS.items():
    daily, ntr, nwin, m = run(d5, c, span)
    worst2 = daily.rolling(2).sum().min()
    worst3 = daily.rolling(3).sum().min()
    print(f"  {lbl}")
    print(f"    single worst day  ${daily.min():>8,.0f}  ({100*abs(daily.min())/1000:.0f}% of the $1k DD)")
    print(f"    worst 2 days      ${worst2:>8,.0f}")
    print(f"    worst 3 days      ${worst3:>8,.0f}")

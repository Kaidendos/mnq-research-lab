"""Round 3: final books — combine the round-2 survivors into complete
long/short regime-switched strategies, then stress the winner vs Combine
limits (worst day x lots vs $1k DLL, EOD-trailing $2k MLL pass sim).

Sleeves (all entries at signal close, 1 contract, $1.22 fee):
  LONG (only when daily EMA50 gate ON):
    stoch runner : %K14 reclaim 30 + svol>0, 9:40-11:30, SL 1.5*ATR, EOD exit
    ORB runner   : first close above 9:30-10:00 range high, 10:00-14:00,
                   SL 1*ATR, EOD exit (optionally svol>0, tp 2*ATR variants)
  SHORT (only when gate OFF):
    BD tp3   : close < 20-bar low, SL 1.5*ATR, TP 3*ATR, max 2/day
    BD trail : same entry, no TP, 2*ATR trailing stop
"""

import numpy as np
import pandas as pd

import strat_refine as sr
from strat_search_5y import load
from backtest_1yr import combine_pass_stats

sr.R.clear()
strat = sr.strat
MORN = (9.6667, 11.5)


def stoch_ok(x, i):
    return (9.6667 <= x["eth"][i] <= 11.5 and x["K"][i-1] <= 30
            and x["K"][i] > 30 and x["sv"][i] > 0)


def orb_ok(x, i):
    return (10.0 <= x["eth"][i] <= 14.0 and not np.isnan(x["orH"][i])
            and x["c"][i-1] <= x["orH"][i] and x["c"][i] > x["orH"][i])


def bd_ok(x, i):
    return not np.isnan(x["ll20"][i]) and x["c"][i] < x["ll20"][i]


def stoch_runner(x, i):
    return dict(dir=1, sl=x["c"][i] - 1.5 * x["atr"][i], tp=None)


def orb_runner(x, i):
    return dict(dir=1, sl=x["c"][i] - x["atr"][i], tp=None)


def orb_tp2(x, i):
    return dict(dir=1, sl=x["c"][i] - x["atr"][i], tp=x["c"][i] + 2 * x["atr"][i])


def bd_tp3(x, i):
    return dict(dir=-1, sl=x["c"][i] + 1.5 * x["atr"][i], tp=x["c"][i] - 3 * x["atr"][i])


def bd_trail(x, i):
    return dict(dir=-1, sl=x["c"][i] + 1.5 * x["atr"][i], tp=None, trail=2.0)


@strat("B1 stoch/BDtp3 (r2 ref)", (9.5833, 15.0), 3)
def b1(x, i):
    if x["gate"][i]:
        if stoch_ok(x, i): return stoch_runner(x, i)
    elif bd_ok(x, i):
        return bd_tp3(x, i)

@strat("B2 stoch+ORBrun/BDtp3", (9.5833, 15.0), 3)
def b2(x, i):
    if x["gate"][i]:
        if stoch_ok(x, i): return stoch_runner(x, i)
        if orb_ok(x, i): return orb_runner(x, i)
    elif bd_ok(x, i):
        return bd_tp3(x, i)

@strat("B3 stoch+ORBrun/BDtrail", (9.5833, 15.0), 3)
def b3(x, i):
    if x["gate"][i]:
        if stoch_ok(x, i): return stoch_runner(x, i)
        if orb_ok(x, i): return orb_runner(x, i)
    elif bd_ok(x, i):
        return bd_trail(x, i)

@strat("B4 ORBsvol-tp2/BDtrail", (9.5833, 15.0), 3)
def b4(x, i):
    if x["gate"][i]:
        if x["sv"][i] > 0 and orb_ok(x, i): return orb_tp2(x, i)
    elif bd_ok(x, i):
        return bd_trail(x, i)

@strat("B5 stoch/BDtrail", (9.5833, 15.0), 3)
def b5(x, i):
    if x["gate"][i]:
        if stoch_ok(x, i): return stoch_runner(x, i)
    elif bd_ok(x, i):
        return bd_trail(x, i)

@strat("B6 ORBrun/BDtp3", (9.5833, 15.0), 3)
def b6(x, i):
    if x["gate"][i]:
        if orb_ok(x, i): return orb_runner(x, i)
    elif bd_ok(x, i):
        return bd_tp3(x, i)


def stats(t):
    daily = t.groupby("date")["pnl"].sum()
    eq = daily.cumsum(); dd = (eq - eq.cummax()).min()
    gw = t.loc[t["pnl"] > 0, "pnl"].sum(); gl = -t.loc[t["pnl"] <= 0, "pnl"].sum()
    pf = gw / gl if gl else float("inf")
    yr = daily.groupby(daily.index.year).sum()
    return daily, dict(net=daily.sum(), tr=len(t), win=100 * t["win"].mean(),
                       pf=pf, wd=daily.min(), dd=dd, posyrs=int((yr > 0).sum()),
                       yrs=yr)


def main():
    d = load()
    books = sr.run_all(d)
    results = {}
    print(f"{'book':26s} {'net$':>9s} {'tr':>5s} {'win%':>5s} {'PF':>5s} "
          f"{'worstDay':>8s} {'maxDD':>8s} {'+yr':>3s}  per-year")
    for name, t in books.items():
        if t.empty:
            continue
        daily, s = stats(t)
        results[name] = (daily, s)
        ys = " ".join(f"{y}:{v:+,.0f}" for y, v in s["yrs"].items())
        print(f"{name:26s} {s['net']:+9,.0f} {s['tr']:5d} {s['win']:5.1f} "
              f"{s['pf']:5.2f} {s['wd']:+8,.0f} {s['dd']:+8,.0f} {s['posyrs']:3d}  {ys}")

    best = max(results, key=lambda k: (results[k][1]["posyrs"], results[k][1]["pf"]))
    daily, s = results[best]
    print(f"\n=== deep dive: {best} ===")
    print(f"active days     : {daily.size} of ~1250 sessions "
          f"({s['tr']/daily.size:.2f} trades/active day)")
    last12 = daily.loc["2025-07-17":]
    print(f"last 12 months  : ${last12.sum():+,.0f} at 1 lot "
          f"({(last12 > 0).sum()}/{last12.size} up days)")
    print("last-12mo monthly:", "  ".join(
        f"{m}:{v:+,.0f}" for m, v in
        last12.resample('ME').sum().items() if v != 0))
    for lots in (2, 3, 5):
        dl = daily * lots
        eq = dl.cumsum(); dd = (eq - eq.cummax()).min()
        rate, passes = combine_pass_stats(dl)
        med = int(np.median(passes)) if passes else -1
        p90 = int(np.percentile(passes, 90)) if passes else -1
        print(f"at {lots} lots: net ${dl.sum():+,.0f}  worst day ${dl.min():+,.0f} "
              f"(DLL $1k {'OK' if dl.min() > -1000 else 'BREACH'})  "
              f"maxDD ${dd:+,.0f}  Combine: {rate:.0f}% pass"
              + (f", median {med}d, p90 {p90}d" if passes else ""))


if __name__ == "__main__":
    main()

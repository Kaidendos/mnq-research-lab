"""1-year backtest (2025-07-17 -> 2026-07-16) of the two finalists with FULL
Combine rules, at $2,000 trailing MLL (50K account) and a tighter $1,000 MLL.
Target +$3k, DLL $1k clip, 50% consistency, fees $1.22/ctr, EOD-trailing MLL.
"""

import numpy as np
import pandas as pd

from strat_search_5y import load
from strat_eval_tune import run_book_capped
from strat_sized import b3
from strat_mega import BOOKS, run_book

YEAR_START = "2025-07-17"


def attempt_spans(daily, target=3000.0, mll=2000.0, dll=1000.0, frac=0.5):
    vals = np.maximum(daily.values, -dll)
    dates = daily.index
    passes, busts, unresolved = [], [], 0
    for s in range(len(vals)):
        cum = peak = best = 0.0
        done = False
        for j in range(s, len(vals)):
            v = vals[j]
            cum += v
            best = max(best, v)
            peak = max(peak, cum)
            cal = (dates[j] - dates[s]).days + 1
            if peak - cum >= mll:
                busts.append((j - s + 1, cal)); done = True; break
            if cum >= target and best <= frac * cum:
                passes.append((j - s + 1, cal)); done = True; break
        if not done:
            unresolved += 1
    return passes, busts, unresolved


def mll_line(daily, mll):
    passes, busts, unres = attempt_spans(daily, mll=mll)
    resolved = len(passes) + len(busts)
    rate = 100 * len(passes) / resolved if resolved else float("nan")
    out = (f"    MLL ${mll:,.0f}: {rate:.0f}% pass ({len(passes)}P/{len(busts)}B"
           + (f", {unres} unresolved" if unres else "") + ")")
    if passes:
        td = np.median([p[0] for p in passes]); cd = np.median([p[1] for p in passes])
        out += f" — median pass {int(td)} traded d / {int(cd)} cal d (~{cd/7:.1f} wk)"
        p = rate / 100
        out += f"; ~{1/p:.1f} attempts expected"
    print(out)


def report(name, t):
    t = t[t["date"] >= YEAR_START]
    daily = t.groupby("date")["pnl"].sum()
    eq = daily.cumsum(); dd = (eq - eq.cummax()).min()
    gw = t.loc[t["pnl"] > 0, "pnl"].sum(); gl = -t.loc[t["pnl"] <= 0, "pnl"].sum()
    pf = gw / gl if gl else float("inf")
    print(f"\n{name} — {YEAR_START} -> 2026-07-16")
    print(f"  net ${daily.sum():+,.0f}  PF {pf:.2f}  {len(t)} trades on "
          f"{daily.size} days ({100*t['win'].mean():.0f}%w, avg {t['n'].mean():.1f} lots)")
    print(f"  worst day ${daily.min():+,.0f}  best day ${daily.max():+,.0f}  "
          f"maxDD ${dd:+,.0f}")
    mon = daily.resample("ME").sum()
    print("  monthly: " + "  ".join(f"{m.strftime('%y-%b')}:{v:+,.0f}"
                                    for m, v in mon.items() if v != 0))
    print("  Combine (full rules, both drawdown variants):")
    mll_line(daily, 2000.0)
    mll_line(daily, 1000.0)


def main():
    d = load().loc["2025-06-01":]
    t_b3 = run_book_capped(d, b3, 10, cap=1500, budget=500.0)
    report("B3 stoch+ORB/BDtrail  x10 cap$1500", t_b3)
    t_m2 = run_book(d, BOOKS["M2 or15+orb / bd"], 5, cap=1500, budget=500.0)
    report("M2 or15+orb30/BD      x5 cap$1500", t_m2)
    t_m2b = run_book(d, BOOKS["M2 or15+orb / bd"], 10, cap=1500, budget=500.0)
    report("M2 or15+orb30/BD      x10 cap$1500 (bonus)", t_m2b)


if __name__ == "__main__":
    main()

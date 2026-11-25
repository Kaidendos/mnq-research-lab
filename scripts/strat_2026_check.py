"""Best-3 books (B6, B3, B1) — 2026-alone performance at live cap-fitted
sizing (max 10 MNQ, -$500 day budget), fees in, full Combine rules.
"""

import numpy as np
import pandas as pd

from strat_search_5y import load
from strat_sized import run_book, b6, b3
from combine_rules import describe


def b1(x, i):
    """stoch runner long (gate ON) / BD tp3 short (gate OFF)."""
    if x["gate"][i]:
        if (9.6667 <= x["eth"][i] <= 11.5 and x["K"][i-1] <= 30
                and x["K"][i] > 30 and x["sv"][i] > 0):
            return dict(dir=1, sl=x["c"][i] - 1.5 * x["atr"][i], tp=None)
    elif not np.isnan(x["ll20"][i]) and x["c"][i] < x["ll20"][i]:
        return dict(dir=-1, sl=x["c"][i] + 1.5 * x["atr"][i],
                    tp=x["c"][i] - 3 * x["atr"][i])


def report_2026(name, t):
    t = t[t["date"] >= "2026-01-01"]
    if t.empty:
        print(f"{name}: no 2026 trades")
        return
    daily = t.groupby("date")["pnl"].sum()
    eq = daily.cumsum(); dd = (eq - eq.cummax()).min()
    gw = t.loc[t["pnl"] > 0, "pnl"].sum(); gl = -t.loc[t["pnl"] <= 0, "pnl"].sum()
    pf = gw / gl if gl else float("inf")
    print(f"\n{name} — 2026 (Jan 1 – Jul 16)")
    print(f"  net ${daily.sum():+,.0f}  PF {pf:.2f}  {len(t)} trades "
          f"({100*t['win'].mean():.0f}%w, avg size {t['n'].mean():.1f})")
    print(f"  worst day ${daily.min():+,.0f}  best day ${daily.max():+,.0f}  "
          f"maxDD ${dd:+,.0f}")
    mon = daily.resample("ME").sum()
    print("  monthly  : " + "  ".join(
        f"{m.strftime('%b')}:{v:+,.0f}" for m, v in mon.items() if v != 0))
    print(describe(daily))


def main():
    d = load()
    for name, fn in [("B6 ORBrunner/BDtp3", b6),
                     ("B3 stoch+ORB/BDtrail", b3),
                     ("B1 stoch/BDtp3", b1)]:
        t = run_book(d, fn, 10)
        report_2026(name + "  x10", t)


if __name__ == "__main__":
    main()

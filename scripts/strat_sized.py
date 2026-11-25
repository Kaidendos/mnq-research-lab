"""Round 4: the winning books (B6, B3) run through the LIVE bot's cap-fitted
sizing — contracts per trade so a full stop-out fits the remaining -$500 day
budget (day locks emerge naturally when the budget is spent). No profit cap
(runners need room; consistency mode is a post-funding concern). Fee $1.22/ctr.
"""

import numpy as np
import pandas as pd

from strat_search_5y import load, day_ctx, FEE, PT
from backtest_1yr import combine_pass_stats

DAY_BUDGET = 500.0


def b6(x, i):
    """gate ON: ORB runner long | gate OFF: 20-bar breakdown short tp3."""
    if x["gate"][i]:
        if (10.0 <= x["eth"][i] <= 14.0 and not np.isnan(x["orH"][i])
                and x["c"][i-1] <= x["orH"][i] and x["c"][i] > x["orH"][i]):
            return dict(dir=1, sl=x["c"][i] - x["atr"][i], tp=None)
    elif not np.isnan(x["ll20"][i]) and x["c"][i] < x["ll20"][i]:
        return dict(dir=-1, sl=x["c"][i] + 1.5 * x["atr"][i],
                    tp=x["c"][i] - 3 * x["atr"][i])


def b3(x, i):
    """B6 + stoch runner long sleeve, BD short uses 2*ATR trail instead."""
    if x["gate"][i]:
        if (9.6667 <= x["eth"][i] <= 11.5 and x["K"][i-1] <= 30
                and x["K"][i] > 30 and x["sv"][i] > 0):
            return dict(dir=1, sl=x["c"][i] - 1.5 * x["atr"][i], tp=None)
        if (10.0 <= x["eth"][i] <= 14.0 and not np.isnan(x["orH"][i])
                and x["c"][i-1] <= x["orH"][i] and x["c"][i] > x["orH"][i]):
            return dict(dir=1, sl=x["c"][i] - x["atr"][i], tp=None)
    elif not np.isnan(x["ll20"][i]) and x["c"][i] < x["ll20"][i]:
        return dict(dir=-1, sl=x["c"][i] + 1.5 * x["atr"][i], tp=None, trail=2.0)


def run_book(d, fn, max_lots, maxpd=3):
    rows = []
    for dnorm, day in d.groupby(d.index.normalize(), sort=True):
        if len(day) < 25:
            continue
        x = day_ctx(day)
        n = len(day)
        pos = None
        taken = 0
        net = 0.0
        for i in range(1, n):
            last = i == n - 1
            if pos is not None:
                ex = None
                if pos["dir"] > 0:
                    if x["l"][i] <= pos["sl"]: ex = pos["sl"]
                    elif pos["tp"] is not None and x["h"][i] >= pos["tp"]: ex = pos["tp"]
                else:
                    if x["h"][i] >= pos["sl"]: ex = pos["sl"]
                    elif pos["tp"] is not None and x["l"][i] <= pos["tp"]: ex = pos["tp"]
                if ex is None and last:
                    ex = x["c"][i]
                if ex is not None:
                    pts = (ex - pos["entry"]) * pos["dir"]
                    pnl = pts * PT * pos["n"] - FEE * pos["n"]
                    net += pnl
                    rows.append({"date": dnorm, "pnl": pnl, "win": pts > 0,
                                 "n": pos["n"]})
                    pos = None
                else:
                    if pos.get("trail"):
                        if pos["dir"] > 0:
                            pos["hw"] = max(pos["hw"], x["h"][i])
                            pos["sl"] = max(pos["sl"], pos["hw"] - pos["trail"] * pos["atr0"])
                        else:
                            pos["hw"] = min(pos["hw"], x["l"][i])
                            pos["sl"] = min(pos["sl"], pos["hw"] + pos["trail"] * pos["atr0"])
            if (pos is None and not last and taken < maxpd
                    and x["atr"][i] > 0 and not np.isnan(x["atr"][i])):
                sig = fn(x, i)
                if sig is None or np.isnan(sig["sl"]):
                    continue
                stop_usd = abs(x["c"][i] - sig["sl"]) * PT
                if stop_usd <= 0:
                    continue
                lots = min(max_lots, int((DAY_BUDGET + net) / stop_usd))
                if lots < 1:
                    continue
                pos = dict(sig, entry=x["c"][i], n=lots, atr0=x["atr"][i],
                           hw=x["c"][i])
                taken += 1
    return pd.DataFrame(rows)


def report(name, t):
    daily = t.groupby("date")["pnl"].sum()
    eq = daily.cumsum(); dd = (eq - eq.cummax()).min()
    gw = t.loc[t["pnl"] > 0, "pnl"].sum(); gl = -t.loc[t["pnl"] <= 0, "pnl"].sum()
    yr = daily.groupby(daily.index.year).sum()
    rate, passes = combine_pass_stats(daily)
    last12 = daily.loc["2025-07-17":]
    print(f"\n{name}")
    print(f"  net ${daily.sum():+,.0f}  PF {gw/gl:.2f}  {len(t)} trades  "
          f"avg size {t['n'].mean():.1f}")
    print(f"  worst day ${daily.min():+,.0f} (DLL $1k "
          f"{'OK' if daily.min() > -1000 else 'BREACH'})  best day ${daily.max():+,.0f}  "
          f"maxDD ${dd:+,.0f}")
    print("  per-year : " + " ".join(f"{y}:{v:+,.0f}" for y, v in yr.items()))
    print(f"  last 12mo: ${last12.sum():+,.0f}")
    med = int(np.median(passes)) if passes else -1
    p90 = int(np.percentile(passes, 90)) if passes else -1
    print(f"  $50K Combine: {rate:.0f}% pass"
          + (f", median {med} traded days, p90 {p90}" if passes else ""))


def main():
    d = load()
    for max_lots in (5, 10):
        print(f"\n===== cap-fitted sizing, max {max_lots} MNQ, -$500 day budget =====")
        report(f"B6 ORBrunner/BDtp3   x{max_lots}", run_book(d, b6, max_lots))
        report(f"B3 stoch+ORB/BDtrail x{max_lots}", run_book(d, b3, max_lots))


if __name__ == "__main__":
    main()

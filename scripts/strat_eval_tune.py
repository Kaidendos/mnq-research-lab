"""Eval-tuning sweep: B6/B1/B3 books x (max lots, day profit cap, day budget).

The profit cap FLATTENS the position and locks the day when day P&L (marked
at bar close) reaches the cap — tames monster days so the 50% consistency
rule doesn't stall the pass. Fees $1.22/ctr everywhere. Full Combine rules.
"""

import numpy as np
import pandas as pd

from strat_search_5y import load, day_ctx, FEE, PT
from strat_sized import b6, b3
from strat_2026_check import b1
from combine_rules import combine_sim


def run_book_capped(d, fn, max_lots, cap=None, budget=500.0, maxpd=3):
    rows = []
    for dnorm, day in d.groupby(d.index.normalize(), sort=True):
        if len(day) < 25:
            continue
        x = day_ctx(day)
        n = len(day)
        pos = None
        taken = 0
        net = 0.0
        locked = False
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
                if ex is None and cap is not None:
                    mark = net + ((x["c"][i] - pos["entry"]) * pos["dir"] * PT
                                  - FEE) * pos["n"]
                    if mark >= cap:
                        ex = x["c"][i]          # cap flatten at bar close
                        locked = True
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
            if locked or (cap is not None and net >= cap):
                locked = True
                continue
            if (pos is None and not last and taken < maxpd
                    and x["atr"][i] > 0 and not np.isnan(x["atr"][i])):
                sig = fn(x, i)
                if sig is None or np.isnan(sig["sl"]):
                    continue
                stop_usd = abs(x["c"][i] - sig["sl"]) * PT
                if stop_usd <= 0:
                    continue
                lots = min(max_lots, int((budget + net) / stop_usd))
                if lots < 1:
                    continue
                pos = dict(sig, entry=x["c"][i], n=lots, atr0=x["atr"][i],
                           hw=x["c"][i])
                taken += 1
    return pd.DataFrame(rows)


def line(tag, t):
    daily = t.groupby("date")["pnl"].sum()
    eq = daily.cumsum(); dd = (eq - eq.cummax()).min()
    gw = t.loc[t["pnl"] > 0, "pnl"].sum(); gl = -t.loc[t["pnl"] <= 0, "pnl"].sum()
    pf = gw / gl if gl else float("inf")
    r5, p5, b5_, _ = combine_sim(daily)
    d26 = daily.loc["2026-01-01":]
    r26, p26, b26, _ = combine_sim(d26)
    med5 = int(np.median(p5)) if p5 else -1
    med26 = int(np.median(p26)) if p26 else -1
    print(f"{tag:34s} net ${daily.sum():+9,.0f} PF {pf:4.2f} wd ${daily.min():+6,.0f} "
          f"DD ${dd:+8,.0f} | C5y {r5:3.0f}% m{med5:>2d} | 2026 ${d26.sum():+8,.0f} "
          f"C26 {r26:3.0f}% m{med26:>2d}")


def main():
    d = load()
    print(f"{'config':34s} {'5y net':>13s} {'PF':>7s} {'worst':>9s} {'maxDD':>11s} "
          f"| Combine5y | 2026 net + Combine26")
    for name, fn in [("B6", b6), ("B1", b1), ("B3", b3)]:
        for lots, cap, bud in [(10, None, 500), (10, 1500, 500), (5, 1500, 500),
                               (5, 1000, 500), (3, 1000, 500), (10, 1500, 750)]:
            caps = f"cap{cap}" if cap else "nocap"
            line(f"{name} x{lots} {caps} bud{int(bud)}",
                 run_book_capped(d, fn, lots, cap, bud))
        print()


if __name__ == "__main__":
    main()

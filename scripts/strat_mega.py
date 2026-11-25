"""Round 6: MEGA books — best sleeves stacked, cap-fitted sizing, full
Combine rules, 5y + 2026 views.

Long sleeves (gate ON, priority order given): or15 runner, ORB30 runner,
first-hour runner, gap-up-and-go, stoch runner (M4 only).
Short sleeves (gate OFF): 20-bar breakdown tp3, first-hour breakdown tp3.
"""

import numpy as np
import pandas as pd

from strat_search_5y import load, day_ctx, FEE, PT
from strat_round5 import day_extras
from combine_rules import combine_sim


def sig_or15(x, i):
    if 9.75 <= x["eth"][i] <= 14.0 and not np.isnan(x["or15H"][i]) \
            and x["c"][i-1] <= x["or15H"][i] and x["c"][i] > x["or15H"][i]:
        return dict(dir=1, sl=x["c"][i] - x["atr"][i], tp=None)

def sig_orb30(x, i):
    if 10.0 <= x["eth"][i] <= 14.0 and not np.isnan(x["orH"][i]) \
            and x["c"][i-1] <= x["orH"][i] and x["c"][i] > x["orH"][i]:
        return dict(dir=1, sl=x["c"][i] - x["atr"][i], tp=None)

def sig_fh(x, i):
    if 10.5 <= x["eth"][i] <= 14.5 and not np.isnan(x["fhH"][i]) \
            and x["c"][i-1] <= x["fhH"][i] and x["c"][i] > x["fhH"][i]:
        return dict(dir=1, sl=x["c"][i] - x["atr"][i], tp=None)

def sig_gapgo(x, i):
    if 9.5833 <= x["eth"][i] <= 10.5 and not np.isnan(x["prevH"][i]) \
            and x["dayopen"][i] > x["prevH"][i] \
            and x["c"][i-1] <= x["h0"][i] and x["c"][i] > x["h0"][i]:
        return dict(dir=1, sl=x["c"][i] - x["atr"][i], tp=None)

def sig_stoch(x, i):
    if 9.6667 <= x["eth"][i] <= 11.5 and x["K"][i-1] <= 30 and x["K"][i] > 30 \
            and x["sv"][i] > 0:
        return dict(dir=1, sl=x["c"][i] - 1.5 * x["atr"][i], tp=None)

def sig_bd(x, i):
    if not np.isnan(x["ll20"][i]) and x["c"][i] < x["ll20"][i]:
        return dict(dir=-1, sl=x["c"][i] + 1.5 * x["atr"][i],
                    tp=x["c"][i] - 3 * x["atr"][i])

def sig_fhb(x, i):
    if 10.5 <= x["eth"][i] <= 15.0 and not np.isnan(x["fhL"][i]) \
            and x["c"][i-1] >= x["fhL"][i] and x["c"][i] < x["fhL"][i]:
        return dict(dir=-1, sl=x["c"][i] + 1.5 * x["atr"][i],
                    tp=x["c"][i] - 3 * x["atr"][i])


def make_book(longs, shorts):
    def book(x, i):
        if x["gate"][i]:
            for fn in longs:
                s = fn(x, i)
                if s is not None:
                    return s
        else:
            for fn in shorts:
                s = fn(x, i)
                if s is not None:
                    return s
    return book


BOOKS = {
    "M1 or15+orb+fh / bd+fhb": make_book([sig_or15, sig_orb30, sig_fh],
                                         [sig_bd, sig_fhb]),
    "M2 or15+orb / bd": make_book([sig_or15, sig_orb30], [sig_bd]),
    "M3 or15+orb+gap / bd+fhb": make_book([sig_or15, sig_orb30, sig_gapgo],
                                          [sig_bd, sig_fhb]),
    "M4 M3+stoch": make_book([sig_or15, sig_orb30, sig_gapgo, sig_stoch],
                             [sig_bd, sig_fhb]),
}


def run_book(d, fn, max_lots, cap=None, budget=500.0, maxpd=3):
    rows = []
    for dnorm, day in d.groupby(d.index.normalize(), sort=True):
        if len(day) < 25:
            continue
        x = day_extras(day_ctx(day))
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
                        ex = x["c"][i]
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
                pos = dict(sig, entry=x["c"][i], n=lots)
                taken += 1
    return pd.DataFrame(rows)


def line(tag, t):
    daily = t.groupby("date")["pnl"].sum()
    eq = daily.cumsum(); dd = (eq - eq.cummax()).min()
    gw = t.loc[t["pnl"] > 0, "pnl"].sum(); gl = -t.loc[t["pnl"] <= 0, "pnl"].sum()
    pf = gw / gl if gl else float("inf")
    yr = daily.groupby(daily.index.year).sum()
    posyrs = int((yr > 0).sum())
    r5, p5, _, _ = combine_sim(daily)
    d26 = daily.loc["2026-01-01":]
    r26, p26, _, _ = combine_sim(d26)
    med5 = int(np.median(p5)) if p5 else -1
    med26 = int(np.median(p26)) if p26 else -1
    print(f"{tag:36s} ${daily.sum():+9,.0f} PF{pf:5.2f} wd${daily.min():+6,.0f} "
          f"DD${dd:+8,.0f} +yr{posyrs} | C5y {r5:3.0f}%/m{med5:<3d} "
          f"| 26 ${d26.sum():+8,.0f} C26 {r26:3.0f}%/m{med26}")


def main():
    d = load()
    for bname, book in BOOKS.items():
        for lots, cap in [(10, None), (10, 1500), (5, 1500)]:
            caps = f"cap{cap}" if cap else "nocap"
            line(f"{bname} x{lots} {caps}", run_book(d, book, lots, cap))
        print()


if __name__ == "__main__":
    main()

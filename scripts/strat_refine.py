"""Round 2: refine the round-1 survivors (ORB long, stoch runner, breakdown
short) with trailing stops, breakeven moves, the daily EMA50 gate, and
gate-switched long/short books. Same experiment rules: 1 contract, $1.22 fee,
SL-before-TP, EOD flat, 5 years.

Engine extends round 1 with:  trail (ATR mult from high-water) and
be (move stop to entry after +N ATR).
"""

import numpy as np
import pandas as pd

from strat_search_5y import load, day_ctx, FEE, PT

MORNING = (9.6667, 11.5)
R = {}


def strat(name, window=(9.5833, 15.0), maxpd=4):
    def deco(fn):
        R[name] = {"fn": fn, "win": window, "maxpd": maxpd}
        return fn
    return deco


def _stoch_sig(x, i):
    return x["K"][i - 1] <= 30 and x["K"][i] > 30 and x["sv"][i] > 0


def _orb_sig(x, i):
    return (not np.isnan(x["orH"][i]) and x["c"][i - 1] <= x["orH"][i]
            and x["c"][i] > x["orH"][i])


def _bd_sig(x, i):
    return not np.isnan(x["ll20"][i]) and x["c"][i] < x["ll20"][i]


# dict entries may add: trail=<ATR mult>, be=<ATR mult>
@strat("ORB-L tp3", (10.0, 14.0), 1)
def r1(x, i):
    if _orb_sig(x, i):
        return dict(dir=1, sl=x["c"][i] - x["atr"][i], tp=x["c"][i] + 3 * x["atr"][i])

@strat("ORB-L runner", (10.0, 14.0), 1)
def r2(x, i):
    if _orb_sig(x, i):
        return dict(dir=1, sl=x["c"][i] - x["atr"][i], tp=None)

@strat("ORB-L runner+trail2", (10.0, 14.0), 1)
def r3(x, i):
    if _orb_sig(x, i):
        return dict(dir=1, sl=x["c"][i] - x["atr"][i], tp=None, trail=2.0)

@strat("ORB-L +gate", (10.0, 14.0), 1)
def r4(x, i):
    if x["gate"][i] and _orb_sig(x, i):
        return dict(dir=1, sl=x["c"][i] - x["atr"][i], tp=x["c"][i] + 2 * x["atr"][i])

@strat("ORB-L +svol", (10.0, 14.0), 1)
def r5(x, i):
    if x["sv"][i] > 0 and _orb_sig(x, i):
        return dict(dir=1, sl=x["c"][i] - x["atr"][i], tp=x["c"][i] + 2 * x["atr"][i])

@strat("ORB-L morning-only", (10.0, 11.5), 1)
def r6(x, i):
    if _orb_sig(x, i):
        return dict(dir=1, sl=x["c"][i] - x["atr"][i], tp=x["c"][i] + 2 * x["atr"][i])

@strat("ORB-L sl0.75 tp2.5", (10.0, 14.0), 1)
def r7(x, i):
    if _orb_sig(x, i):
        return dict(dir=1, sl=x["c"][i] - 0.75 * x["atr"][i],
                    tp=x["c"][i] + 2.5 * x["atr"][i])

@strat("stoch runner+gate", MORNING)
def r8(x, i):
    if x["gate"][i] and _stoch_sig(x, i):
        return dict(dir=1, sl=x["c"][i] - 1.5 * x["atr"][i], tp=None)

@strat("stoch runner+trail1.5", MORNING)
def r9(x, i):
    if _stoch_sig(x, i):
        return dict(dir=1, sl=x["c"][i] - 1.5 * x["atr"][i], tp=None, trail=1.5)

@strat("stoch runner+be1", MORNING)
def r10(x, i):
    if _stoch_sig(x, i):
        return dict(dir=1, sl=x["c"][i] - 1.5 * x["atr"][i], tp=None, be=1.0)

@strat("stoch runner+gate+trail", MORNING)
def r11(x, i):
    if x["gate"][i] and _stoch_sig(x, i):
        return dict(dir=1, sl=x["c"][i] - 1.5 * x["atr"][i], tp=None, trail=1.5)

@strat("stoch runner sl2", MORNING)
def r12(x, i):
    if _stoch_sig(x, i):
        return dict(dir=1, sl=x["c"][i] - 2.0 * x["atr"][i], tp=None)

@strat("BD-short gate-OFF only", (9.5833, 15.0), 2)
def r13(x, i):
    if not x["gate"][i] and _bd_sig(x, i):
        return dict(dir=-1, sl=x["c"][i] + 1.5 * x["atr"][i],
                    tp=x["c"][i] - 3 * x["atr"][i])

@strat("BD-short gateOFF trail2", (9.5833, 15.0), 2)
def r14(x, i):
    if not x["gate"][i] and _bd_sig(x, i):
        return dict(dir=-1, sl=x["c"][i] + 1.5 * x["atr"][i], tp=None, trail=2.0)

@strat("SWITCH stoch/BD", (9.5833, 15.0), 3)
def r15(x, i):
    if x["gate"][i]:
        if 9.6667 <= x["eth"][i] <= 11.5 and _stoch_sig(x, i):
            return dict(dir=1, sl=x["c"][i] - 1.5 * x["atr"][i], tp=None)
    elif _bd_sig(x, i):
        return dict(dir=-1, sl=x["c"][i] + 1.5 * x["atr"][i],
                    tp=x["c"][i] - 3 * x["atr"][i])

@strat("SWITCH ORB/BD", (9.5833, 15.0), 2)
def r16(x, i):
    if x["gate"][i]:
        if 10.0 <= x["eth"][i] <= 14.0 and _orb_sig(x, i):
            return dict(dir=1, sl=x["c"][i] - x["atr"][i], tp=x["c"][i] + 2 * x["atr"][i])
    elif _bd_sig(x, i):
        return dict(dir=-1, sl=x["c"][i] + 1.5 * x["atr"][i],
                    tp=x["c"][i] - 3 * x["atr"][i])

@strat("SWITCH both/BD", (9.5833, 15.0), 3)
def r17(x, i):
    if x["gate"][i]:
        if 10.0 <= x["eth"][i] <= 14.0 and _orb_sig(x, i):
            return dict(dir=1, sl=x["c"][i] - x["atr"][i], tp=x["c"][i] + 2 * x["atr"][i])
        if 9.6667 <= x["eth"][i] <= 11.5 and _stoch_sig(x, i):
            return dict(dir=1, sl=x["c"][i] - 1.5 * x["atr"][i], tp=None)
    elif _bd_sig(x, i):
        return dict(dir=-1, sl=x["c"][i] + 1.5 * x["atr"][i],
                    tp=x["c"][i] - 3 * x["atr"][i])

@strat("VWAP-trend runner", (10.0, 14.5))
def r18(x, i):
    if x["gate"][i] and x["c"][i - 1] < x["vwap"][i - 1] and x["c"][i] > x["vwap"][i]:
        return dict(dir=1, sl=x["c"][i] - 1.25 * x["atr"][i], tp=None, trail=2.0)


def run_all(d):
    books = {name: [] for name in R}
    for dnorm, day in d.groupby(d.index.normalize(), sort=True):
        if len(day) < 25:
            continue
        x = day_ctx(day)
        n = len(day)
        for name, spec in R.items():
            trades = books[name]
            lo, hi = spec["win"]
            pos = None
            taken = 0
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
                        trades.append({"date": dnorm, "pnl": pts * PT - FEE,
                                       "win": pts > 0})
                        pos = None
                    else:
                        # post-bar stop management (uses bar i extremes)
                        if pos["dir"] > 0:
                            pos["hw"] = max(pos["hw"], x["h"][i])
                            if pos.get("trail"):
                                pos["sl"] = max(pos["sl"], pos["hw"] - pos["trail"] * pos["atr0"])
                            if pos.get("be") and x["h"][i] >= pos["entry"] + pos["be"] * pos["atr0"]:
                                pos["sl"] = max(pos["sl"], pos["entry"])
                        else:
                            pos["hw"] = min(pos["hw"], x["l"][i])
                            if pos.get("trail"):
                                pos["sl"] = min(pos["sl"], pos["hw"] + pos["trail"] * pos["atr0"])
                            if pos.get("be") and x["l"][i] <= pos["entry"] - pos["be"] * pos["atr0"]:
                                pos["sl"] = min(pos["sl"], pos["entry"])
                if (pos is None and not last and lo <= x["eth"][i] <= hi
                        and taken < spec["maxpd"]
                        and x["atr"][i] > 0 and not np.isnan(x["atr"][i])):
                    sig = spec["fn"](x, i)
                    if sig is not None and not np.isnan(sig["sl"]) \
                            and (sig["tp"] is None or not np.isnan(sig["tp"])):
                        pos = dict(sig, entry=x["c"][i], atr0=x["atr"][i],
                                   hw=x["c"][i])
                        taken += 1
    return {k: pd.DataFrame(v) for k, v in books.items()}


def main():
    d = load()
    books = run_all(d)
    rows = []
    for name, t in books.items():
        if t.empty:
            continue
        daily = t.groupby("date")["pnl"].sum()
        eq = daily.cumsum(); dd = (eq - eq.cummax()).min()
        gw = t.loc[t["pnl"] > 0, "pnl"].sum(); gl = -t.loc[t["pnl"] <= 0, "pnl"].sum()
        pf = gw / gl if gl else float("inf")
        yr = daily.groupby(daily.index.year).sum()
        rows.append({"name": name, "net": daily.sum(), "trades": len(t),
                     "win": 100 * t["win"].mean(), "pf": pf, "dd": dd,
                     "posyrs": int((yr > 0).sum()), "yrs": yr})
    rows.sort(key=lambda r: (r["posyrs"], r["pf"]), reverse=True)
    print(f"{'strategy':26s} {'net$':>9s} {'tr':>5s} {'win%':>5s} {'PF':>5s} "
          f"{'maxDD':>8s} {'+yr':>3s}  per-year")
    for r in rows:
        ys = " ".join(f"{y}:{v:+,.0f}" for y, v in r["yrs"].items())
        print(f"{r['name']:26s} {r['net']:+9,.0f} {r['trades']:5d} {r['win']:5.1f} "
              f"{r['pf']:5.2f} {r['dd']:+8,.0f} {r['posyrs']:3d}  {ys}")


if __name__ == "__main__":
    main()

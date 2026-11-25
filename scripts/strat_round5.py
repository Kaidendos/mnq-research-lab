"""Round 5: 20 NEW non-stoch strategies. 1 contract, $1.22 fee, 5 years.
All long sleeves require the daily EMA50 gate ON, shorts gate OFF (the one
robust regime finding). Leaderboard: 5y stats + 2026-alone column.
"""

import numpy as np
import pandas as pd

from strat_search_5y import load, day_ctx, FEE, PT

N = {}


def strat(name, window=(9.5833, 15.0), maxpd=2):
    def deco(fn):
        N[name] = {"fn": fn, "win": window, "maxpd": maxpd}
        return fn
    return deco


def rng_pos(x, i):
    r = x["h"][i] - x["l"][i]
    return (x["c"][i] - x["l"][i]) / r if r > 0 else 0.5


# ── longs (gate ON) ──────────────────────────────────────────────────────────

@strat("L or15 runner", (9.75, 14.0), 1)
def n1(x, i):
    if x["gate"][i] and not np.isnan(x["or15H"][i]) \
            and x["c"][i-1] <= x["or15H"][i] and x["c"][i] > x["or15H"][i]:
        return dict(dir=1, sl=x["c"][i] - x["atr"][i], tp=None)

@strat("L firsthour runner", (10.5, 14.5), 1)
def n2(x, i):
    if x["gate"][i] and not np.isnan(x["fhH"][i]) \
            and x["c"][i-1] <= x["fhH"][i] and x["c"][i] > x["fhH"][i]:
        return dict(dir=1, sl=x["c"][i] - x["atr"][i], tp=None)

@strat("L vwap-hold pullback", (10.5, 14.0), 2)
def n4(x, i):
    if x["gate"][i] and x["vwapMin"][i] > 0 \
            and x["l"][i] - x["vwap"][i] < 0.5 * x["atr"][i] \
            and x["c"][i] > x["vwap"][i]:
        return dict(dir=1, sl=x["c"][i] - 1.25 * x["atr"][i], tp=None)

@strat("L 3-down-close buy", (9.6667, 14.5))
def n5(x, i):
    if x["gate"][i] and i >= 4 and x["c"][i-1] < x["c"][i-2] < x["c"][i-3] \
            and x["c"][i] > x["c"][i-1] and x["c"][i] > x["vwap"][i]:
        return dict(dir=1, sl=x["c"][i] - x["atr"][i], tp=x["c"][i] + 2 * x["atr"][i])

@strat("L rsi2 dip", (9.6667, 14.5))
def n6(x, i):
    if x["gate"][i] and x["rsi2"][i-1] < 10 and x["rsi2"][i] >= 10 \
            and x["c"][i] > x["e50"][i]:
        return dict(dir=1, sl=x["c"][i] - x["atr"][i], tp=x["c"][i] + 1.5 * x["atr"][i])

@strat("L inside-bar break", (9.75, 14.5))
def n7(x, i):
    if x["gate"][i] and i >= 2 and x["h"][i-1] <= x["h"][i-2] \
            and x["l"][i-1] >= x["l"][i-2] and x["c"][i] > x["h"][i-1]:
        return dict(dir=1, sl=x["c"][i] - x["atr"][i], tp=x["c"][i] + 2 * x["atr"][i])

@strat("L atr-expansion", (9.6667, 14.5))
def n9(x, i):
    if x["gate"][i] and (x["h"][i] - x["l"][i]) > 2 * x["atr"][i] and rng_pos(x, i) > 0.75:
        return dict(dir=1, sl=x["c"][i] - 1.25 * x["atr"][i], tp=None)

@strat("L strong-yday pullback", (9.6667, 11.0))
def n11(x, i):
    pr = x["prevH"][i] - x["prevL"][i]
    if x["gate"][i] and not np.isnan(pr) and pr > 0 \
            and (x["prevC"][i] - x["prevL"][i]) / pr > 0.75 and x["c"][i] < x["o"][i]:
        return dict(dir=1, sl=x["c"][i] - x["atr"][i], tp=x["c"][i] + 2 * x["atr"][i])

@strat("L gap-up-and-go", (9.5833, 10.5), 1)
def n12(x, i):
    if x["gate"][i] and not np.isnan(x["prevH"][i]) and x["dayopen"][i] > x["prevH"][i] \
            and x["c"][i-1] <= x["h0"][i] and x["c"][i] > x["h0"][i]:
        return dict(dir=1, sl=x["c"][i] - x["atr"][i], tp=None)

@strat("L midday break tp2", (13.0, 14.5), 1)
def n14(x, i):
    if x["gate"][i] and not np.isnan(x["mdH"][i]) \
            and x["c"][i-1] <= x["mdH"][i] and x["c"][i] > x["mdH"][i]:
        return dict(dir=1, sl=x["c"][i] - x["atr"][i], tp=x["c"][i] + 2 * x["atr"][i])

@strat("L 20low spring", (9.6667, 14.5))
def n18(x, i):
    if x["gate"][i] and not np.isnan(x["ll20"][i]) \
            and min(x["l"][i-1], x["l"][i]) < x["ll20"][i] and x["c"][i] > x["ll20"][i]:
        return dict(dir=1, sl=x["c"][i] - x["atr"][i], tp=x["c"][i] + 2 * x["atr"][i])

@strat("L close-drive 14h", (14.0, 14.084), 1)
def n19(x, i):
    dr = x["dayHi"][i] - x["dayLo"][i]
    if x["gate"][i] and dr > 0 and (x["c"][i] - x["dayLo"][i]) / dr > 0.7:
        return dict(dir=1, sl=x["c"][i] - x["atr"][i], tp=None)

@strat("L PDH break runner", (9.6667, 14.0), 1)
def n20(x, i):
    if x["gate"][i] and not np.isnan(x["prevH"][i]) \
            and x["c"][i-1] <= x["prevH"][i] and x["c"][i] > x["prevH"][i]:
        return dict(dir=1, sl=x["c"][i] - x["atr"][i], tp=None)

# ── shorts (gate OFF) ────────────────────────────────────────────────────────

@strat("S firsthour break", (10.5, 15.0), 2)
def n3(x, i):
    if not x["gate"][i] and not np.isnan(x["fhL"][i]) \
            and x["c"][i-1] >= x["fhL"][i] and x["c"][i] < x["fhL"][i]:
        return dict(dir=-1, sl=x["c"][i] + 1.5 * x["atr"][i],
                    tp=x["c"][i] - 3 * x["atr"][i])

@strat("S inside-bar break", (9.75, 14.5))
def n8(x, i):
    if not x["gate"][i] and i >= 2 and x["h"][i-1] <= x["h"][i-2] \
            and x["l"][i-1] >= x["l"][i-2] and x["c"][i] < x["l"][i-1]:
        return dict(dir=-1, sl=x["c"][i] + x["atr"][i], tp=x["c"][i] - 2 * x["atr"][i])

@strat("S atr-expansion", (9.6667, 14.5))
def n10(x, i):
    if not x["gate"][i] and (x["h"][i] - x["l"][i]) > 2 * x["atr"][i] and rng_pos(x, i) < 0.25:
        return dict(dir=-1, sl=x["c"][i] + 1.25 * x["atr"][i],
                    tp=x["c"][i] - 2.5 * x["atr"][i])

@strat("S gap-down-and-go", (9.5833, 10.5), 1)
def n13(x, i):
    if not x["gate"][i] and not np.isnan(x["prevL"][i]) \
            and x["dayopen"][i] < x["prevL"][i] \
            and x["c"][i-1] >= x["l0"][i] and x["c"][i] < x["l0"][i]:
        return dict(dir=-1, sl=x["c"][i] + 1.5 * x["atr"][i],
                    tp=x["c"][i] - 3 * x["atr"][i])

@strat("S midday break", (13.0, 15.0), 1)
def n15(x, i):
    if not x["gate"][i] and not np.isnan(x["mdL"][i]) \
            and x["c"][i-1] >= x["mdL"][i] and x["c"][i] < x["mdL"][i]:
        return dict(dir=-1, sl=x["c"][i] + 1.5 * x["atr"][i],
                    tp=x["c"][i] - 3 * x["atr"][i])

@strat("S vwap-tag fade", (10.0, 14.5))
def n16(x, i):
    if not x["gate"][i] and x["c"][i-1] < x["vwap"][i-1] and x["h"][i] >= x["vwap"][i] \
            and x["c"][i] < x["vwap"][i] and x["c"][i] < x["o"][i]:
        return dict(dir=-1, sl=x["c"][i] + 1.25 * x["atr"][i],
                    tp=x["c"][i] - 2.5 * x["atr"][i])

@strat("S e21 bear-flag", (9.6667, 14.5))
def n17(x, i):
    if not x["gate"][i] and x["c"][i] < x["e50"][i] and x["h"][i] >= x["e21"][i] \
            and x["c"][i] < x["o"][i]:
        return dict(dir=-1, sl=x["c"][i] + x["atr"][i], tp=x["c"][i] - 2 * x["atr"][i])


def add_extras(d: pd.DataFrame) -> pd.DataFrame:
    delta = d["close"].diff()
    d["rsi2"] = 100 - 100 / (1 + delta.clip(lower=0).ewm(alpha=0.5, adjust=False).mean()
                             / (-delta).clip(lower=0).ewm(alpha=0.5, adjust=False).mean()
                             .replace(0, np.nan))
    return d


def day_extras(x: dict) -> dict:
    eth = x["eth"]; h = x["h"]; l = x["l"]; c = x["c"]
    n = len(eth)
    def span_max(mask):
        return h[mask].max() if mask.any() else np.nan
    def span_min(mask):
        return l[mask].min() if mask.any() else np.nan
    x["or15H"] = np.full(n, span_max(eth < 9.75))
    x["fhH"] = np.full(n, span_max(eth < 10.5))
    x["fhL"] = np.full(n, span_min(eth < 10.5))
    md = (eth >= 11.5) & (eth < 13.0)
    x["mdH"] = np.full(n, span_max(md))
    x["mdL"] = np.full(n, span_min(md))
    x["h0"] = np.full(n, h[0]); x["l0"] = np.full(n, l[0])
    x["dayHi"] = np.maximum.accumulate(h)
    x["dayLo"] = np.minimum.accumulate(l)
    x["vwapMin"] = np.minimum.accumulate(c - x["vwap"])
    return x


def run_all(d):
    books = {k: [] for k in N}
    for dnorm, day in d.groupby(d.index.normalize(), sort=True):
        if len(day) < 25:
            continue
        x = day_extras(day_ctx(day))
        x["rsi2"] = day["rsi2"].values
        n = len(day)
        for name, spec in N.items():
            lo, hi = spec["win"]
            trades = books[name]
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
                if (pos is None and not last and lo <= x["eth"][i] <= hi
                        and taken < spec["maxpd"]
                        and x["atr"][i] > 0 and not np.isnan(x["atr"][i])):
                    sig = spec["fn"](x, i)
                    if sig is not None and not np.isnan(sig["sl"]) \
                            and (sig["tp"] is None or not np.isnan(sig["tp"])):
                        pos = dict(sig, entry=x["c"][i])
                        taken += 1
    return {k: pd.DataFrame(v) for k, v in books.items()}


def main():
    d = add_extras(load())
    books = run_all(d)
    rows = []
    for name, t in books.items():
        if t.empty or len(t) < 50:
            continue
        daily = t.groupby("date")["pnl"].sum()
        eq = daily.cumsum(); dd = (eq - eq.cummax()).min()
        gw = t.loc[t["pnl"] > 0, "pnl"].sum(); gl = -t.loc[t["pnl"] <= 0, "pnl"].sum()
        pf = gw / gl if gl else float("inf")
        yr = daily.groupby(daily.index.year).sum()
        d26 = daily.loc["2026-01-01":].sum()
        rows.append({"name": name, "net": daily.sum(), "tr": len(t),
                     "win": 100 * t["win"].mean(), "pf": pf, "dd": dd,
                     "posyrs": int((yr > 0).sum()), "y26": d26, "yrs": yr})
    rows.sort(key=lambda r: (r["posyrs"], r["pf"]), reverse=True)
    print(f"{'strategy':24s} {'net$':>8s} {'tr':>5s} {'win%':>5s} {'PF':>5s} "
          f"{'maxDD':>8s} {'+yr':>3s} {'2026$':>7s}  per-year")
    for r in rows:
        ys = " ".join(f"{y}:{v:+,.0f}" for y, v in r["yrs"].items())
        print(f"{r['name']:24s} {r['net']:+8,.0f} {r['tr']:5d} {r['win']:5.1f} "
              f"{r['pf']:5.2f} {r['dd']:+8,.0f} {r['posyrs']:3d} {r['y26']:+7,.0f}  {ys}")


if __name__ == "__main__":
    main()

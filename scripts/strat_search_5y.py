"""Strategy search: 25 strategies x 5 years of real MNQ 5-min bars, fees in.

Experiment rules (user-approved): fixed 1 contract, no day P&L caps, max
trades/day per spec. Fee $1.22 RT. Entries at signal-bar close, exits from
next bar (SL checked before TP), EOD flat. Long AND short edges.

Ranking favors CONSISTENCY (positive years) over raw net — the live
strategy's failure mode was one hot regime paying for four bad ones.
"""

from pathlib import Path

import numpy as np
import pandas as pd

DATA_CSV = Path(__file__).parent / "data" / "databento" / "mnq_5min_2021-2026.csv"
TZ = "America/New_York"
FEE = 1.22
PT = 2.0
START = "2021-07-18"


# ── data prep ────────────────────────────────────────────────────────────────

def wilder(s, n):
    return s.ewm(alpha=1.0 / n, adjust=False).mean()


def load() -> pd.DataFrame:
    df = pd.read_csv(DATA_CSV)
    df["ts_et"] = pd.to_datetime(df["ts_et"], utc=True).dt.tz_convert(TZ)
    df = df.set_index("ts_et").sort_index()
    hrs = df.index.hour + df.index.minute / 60.0
    d = df[(hrs >= 9.5) & (hrs < 16.0)].copy()

    prev_c = d["close"].shift(1)
    tr = pd.concat([d["high"] - d["low"], (d["high"] - prev_c).abs(),
                    (d["low"] - prev_c).abs()], axis=1).max(axis=1)
    d["atr"] = wilder(tr, 14)
    ll = d["low"].rolling(14).min(); hh = d["high"].rolling(14).max()
    d["K"] = 100 * (d["close"] - ll) / (hh - ll).replace(0, np.nan)
    delta = d["close"].diff()
    d["rsi"] = 100 - 100 / (1 + wilder(delta.clip(lower=0), 14) /
                            wilder((-delta).clip(lower=0), 14).replace(0, np.nan))
    m = d["close"].rolling(20).mean(); sd = d["close"].rolling(20).std()
    d["bbM"], d["bbU"], d["bbL"] = m, m + 2 * sd, m - 2 * sd
    for n in (9, 21, 50):
        d[f"e{n}"] = d["close"].ewm(span=n, adjust=False).mean()
    pressure = ((d["close"] - d["low"]) /
                (d["high"] - d["low"]).replace(0, np.nan)).fillna(0.5)
    d["sv"] = d["volume"] * (2 * pressure - 1)
    d["hh20"] = d["high"].rolling(20).max().shift(1)
    d["ll20"] = d["low"].rolling(20).min().shift(1)

    day = d.index.normalize()
    tpv = ((d["high"] + d["low"] + d["close"]) / 3) * d["volume"]
    d["vwap"] = tpv.groupby(day).cumsum() / d["volume"].groupby(day).cumsum()
    d["cminL"] = d["low"].groupby(day).cummin().shift(1)

    daily_close = d["close"].groupby(day).last()
    daily_high = d["high"].groupby(day).max()
    daily_low = d["low"].groupby(day).min()
    ema50d = daily_close.ewm(span=50, adjust=False).mean()
    gate = (daily_close > ema50d).shift(1).fillna(False)
    hrs2 = d.index.hour + d.index.minute / 60.0
    orh = d["high"][hrs2 < 10.0].groupby(day[hrs2 < 10.0]).max()
    orl = d["low"][hrs2 < 10.0].groupby(day[hrs2 < 10.0]).min()
    for col, s in [("prevC", daily_close.shift(1)), ("prevH", daily_high.shift(1)),
                   ("prevL", daily_low.shift(1)), ("gate", gate),
                   ("orH", orh), ("orL", orl)]:
        d[col] = day.map(s)
    d["dayopen"] = d["open"].groupby(d.index.normalize()).transform("first")
    d["eth"] = d.index.hour + d.index.minute / 60.0
    return d.loc[START:]


# ── strategies: entry(x, i) -> None | (dir, sl_price, tp_price|None) ─────────
# x = dict of numpy arrays for one day

def _x(v, i):
    return not np.isnan(v[i])

S = {}

def strat(name, window=(9.5833, 15.0), maxpd=4):
    def deco(fn):
        S[name] = {"fn": fn, "win": window, "maxpd": maxpd}
        return fn
    return deco

MORNING = (9.6667, 11.5)

@strat("stoch30 rebal 1.0/1.0", MORNING)
def s1(x, i):
    if x["K"][i-1] <= 30 and x["K"][i] > 30 and x["sv"][i] > 0:
        return (1, x["c"][i] - x["atr"][i], x["c"][i] + x["atr"][i])

@strat("stoch30 runner sl1.5/EOD", MORNING)
def s2(x, i):
    if x["K"][i-1] <= 30 and x["K"][i] > 30 and x["sv"][i] > 0:
        return (1, x["c"][i] - 1.5 * x["atr"][i], None)

@strat("stoch30 wide+EMA50gate", MORNING)
def s3(x, i):
    if x["gate"][i] and x["K"][i-1] <= 30 and x["K"][i] > 30 and x["sv"][i] > 0:
        return (1, x["c"][i] - 1.25 * x["atr"][i], x["c"][i] + 1.0 * x["atr"][i])

@strat("rsi30 reclaim 1.0/1.5")
def s4(x, i):
    if x["rsi"][i-1] <= 30 and x["rsi"][i] > 30:
        return (1, x["c"][i] - x["atr"][i], x["c"][i] + 1.5 * x["atr"][i])

@strat("BB lower reclaim->mid")
def s5(x, i):
    if _x(x["bbL"], i) and x["c"][i-1] < x["bbL"][i-1] and x["c"][i] > x["bbL"][i] \
            and x["bbM"][i] > x["c"][i]:
        return (1, x["c"][i] - x["atr"][i], x["bbM"][i])

@strat("VWAP deep reclaim")
def s6(x, i):
    lvl_p = x["vwap"][i-1] - 2 * x["atr"][i-1]
    lvl = x["vwap"][i] - 2 * x["atr"][i]
    if x["c"][i-1] < lvl_p and x["c"][i] > lvl and x["vwap"][i] > x["c"][i]:
        return (1, x["c"][i] - 1.25 * x["atr"][i], x["vwap"][i])

@strat("gap-down fill long", (9.5833, 10.5), 1)
def s7(x, i):
    if _x(x["prevC"], i) and x["dayopen"][i] < x["prevC"][i] * 0.9975 \
            and x["c"][i] < x["prevC"][i]:
        return (1, x["c"][i] - 1.5 * x["atr"][i], x["prevC"][i])

@strat("OR-low sweep reclaim", (10.0, 14.0), 2)
def s8(x, i):
    if _x(x["orL"], i) and _x(x["cminL"], i) and x["cminL"][i] < x["orL"][i] \
            and x["c"][i-1] <= x["orL"][i] and x["c"][i] > x["orL"][i]:
        return (1, x["c"][i] - x["atr"][i], x["c"][i] + 1.5 * x["atr"][i])

@strat("ORB30 long", (10.0, 14.0), 1)
def s9(x, i):
    if _x(x["orH"], i) and x["c"][i-1] <= x["orH"][i] and x["c"][i] > x["orH"][i]:
        return (1, x["c"][i] - x["atr"][i], x["c"][i] + 2 * x["atr"][i])

@strat("ORB30 short", (10.0, 14.0), 1)
def s10(x, i):
    if _x(x["orL"], i) and x["c"][i-1] >= x["orL"][i] and x["c"][i] < x["orL"][i]:
        return (-1, x["c"][i] + x["atr"][i], x["c"][i] - 2 * x["atr"][i])

@strat("20bar-high break long", (9.5833, 15.0), 2)
def s11(x, i):
    if _x(x["hh20"], i) and x["c"][i] > x["hh20"][i]:
        return (1, x["c"][i] - 1.5 * x["atr"][i], x["c"][i] + 3 * x["atr"][i])

@strat("20bar-low break short", (9.5833, 15.0), 2)
def s12(x, i):
    if _x(x["ll20"], i) and x["c"][i] < x["ll20"][i]:
        return (-1, x["c"][i] + 1.5 * x["atr"][i], x["c"][i] - 3 * x["atr"][i])

@strat("prev-day-high break", (9.5833, 14.5), 1)
def s13(x, i):
    if _x(x["prevH"], i) and x["c"][i-1] <= x["prevH"][i] and x["c"][i] > x["prevH"][i]:
        return (1, x["c"][i] - x["atr"][i], x["c"][i] + 2 * x["atr"][i])

@strat("prev-day-low break short", (9.5833, 14.5), 1)
def s14(x, i):
    if _x(x["prevL"], i) and x["c"][i-1] >= x["prevL"][i] and x["c"][i] < x["prevL"][i]:
        return (-1, x["c"][i] + x["atr"][i], x["c"][i] - 2 * x["atr"][i])

@strat("ignition 2-strong-close")
def s15(x, i):
    rng = x["h"][i] - x["l"][i]; rngp = x["h"][i-1] - x["l"][i-1]
    if rng > 0 and rngp > 0 and (x["c"][i] - x["l"][i]) / rng > 0.75 \
            and (x["c"][i-1] - x["l"][i-1]) / rngp > 0.75 \
            and x["v"][i] > x["v"][i-1] and x["c"][i] > x["c"][i-1]:
        return (1, x["c"][i] - x["atr"][i], x["c"][i] + 2 * x["atr"][i])

@strat("EMA9x21 cross long")
def s16(x, i):
    if x["e9"][i-1] <= x["e21"][i-1] and x["e9"][i] > x["e21"][i] \
            and x["c"][i] > x["e50"][i]:
        return (1, x["c"][i] - 1.25 * x["atr"][i], x["c"][i] + 2.5 * x["atr"][i])

@strat("EMA21 pullback in trend")
def s17(x, i):
    if x["gate"][i] and x["c"][i] > x["e50"][i] and x["l"][i] <= x["e21"][i] \
            and x["c"][i] > x["o"][i]:
        return (1, x["c"][i] - x["atr"][i], x["c"][i] + 2 * x["atr"][i])

@strat("VWAP reclaim in trend", (10.0, 14.5))
def s18(x, i):
    if x["gate"][i] and x["c"][i-1] < x["vwap"][i-1] and x["c"][i] > x["vwap"][i]:
        return (1, x["c"][i] - 1.25 * x["atr"][i], x["c"][i] + 2.5 * x["atr"][i])

@strat("stoch70 short mirror", MORNING)
def s19(x, i):
    if x["K"][i-1] >= 70 and x["K"][i] < 70 and x["sv"][i] < 0:
        return (-1, x["c"][i] + 0.75 * x["atr"][i], x["c"][i] - 0.5 * x["atr"][i])

@strat("stoch70 short wide")
def s20(x, i):
    if x["K"][i-1] >= 70 and x["K"][i] < 70 and x["sv"][i] < 0:
        return (-1, x["c"][i] + 1.25 * x["atr"][i], x["c"][i] - 1.0 * x["atr"][i])

@strat("BB upper fade short")
def s21(x, i):
    if _x(x["bbU"], i) and x["c"][i-1] > x["bbU"][i-1] and x["c"][i] < x["bbU"][i]:
        return (-1, x["c"][i] + x["atr"][i], x["c"][i] - 1.5 * x["atr"][i])

@strat("power-hour momo", (15.0, 15.25), 1)
def s22(x, i):
    if x["c"][i] > x["vwap"][i]:
        return (1, x["c"][i] - x["atr"][i], None)

@strat("lunch stoch30 1.25/1.0", (12.0, 13.5))
def s23(x, i):
    if x["K"][i-1] <= 30 and x["K"][i] > 30 and x["sv"][i] > 0:
        return (1, x["c"][i] - 1.25 * x["atr"][i], x["c"][i] + 1.0 * x["atr"][i])

@strat("pm stoch30 1.25/1.0", (13.0, 15.0))
def s24(x, i):
    if x["K"][i-1] <= 30 and x["K"][i] > 30 and x["sv"][i] > 0:
        return (1, x["c"][i] - 1.25 * x["atr"][i], x["c"][i] + 1.0 * x["atr"][i])

@strat("20bar break L+S combo", (9.5833, 15.0), 3)
def s25(x, i):
    r = s11(x, i)
    return r if r is not None else s12(x, i)


# ── engine ───────────────────────────────────────────────────────────────────

COLS = {"o": "open", "h": "high", "l": "low", "c": "close", "v": "volume",
        "atr": "atr", "K": "K", "rsi": "rsi", "bbM": "bbM", "bbU": "bbU",
        "bbL": "bbL", "e9": "e9", "e21": "e21", "e50": "e50", "sv": "sv",
        "hh20": "hh20", "ll20": "ll20", "vwap": "vwap", "cminL": "cminL",
        "prevC": "prevC", "prevH": "prevH", "prevL": "prevL",
        "orH": "orH", "orL": "orL", "dayopen": "dayopen", "eth": "eth"}


def day_ctx(day: pd.DataFrame) -> dict:
    x = {k: day[c].values for k, c in COLS.items()}
    x["gate"] = day["gate"].values.astype(bool)
    return x


def run_all(d: pd.DataFrame) -> dict[str, pd.DataFrame]:
    books = {name: [] for name in S}
    for dnorm, day in d.groupby(d.index.normalize(), sort=True):
        if len(day) < 25:
            continue
        x = day_ctx(day)
        n = len(day)
        for name, spec in S.items():
            lo, hi = spec["win"]
            trades = books[name]
            pos = None
            taken = 0
            start_len = len(trades)
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
                                       "win": pts > 0, "dir": pos["dir"]})
                        pos = None
                if (pos is None and not last and lo <= x["eth"][i] <= hi
                        and taken < spec["maxpd"]
                        and x["atr"][i] > 0 and not np.isnan(x["atr"][i])):
                    sig = spec["fn"](x, i)
                    if sig is not None:
                        dr, sl, tp = sig
                        if not np.isnan(sl) and (tp is None or not np.isnan(tp)):
                            pos = {"dir": dr, "entry": x["c"][i], "sl": sl, "tp": tp}
                            taken += 1
            _ = start_len
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
    print(f"{'strategy':28s} {'net$':>9s} {'tr':>5s} {'win%':>5s} {'PF':>5s} "
          f"{'maxDD':>8s} {'+yr':>3s}  per-year")
    for r in rows:
        ys = " ".join(f"{y}:{v:+,.0f}" for y, v in r["yrs"].items())
        print(f"{r['name']:28s} {r['net']:+9,.0f} {r['trades']:5d} {r['win']:5.1f} "
              f"{r['pf']:5.2f} {r['dd']:+8,.0f} {r['posyrs']:3d}  {ys}")


if __name__ == "__main__":
    main()

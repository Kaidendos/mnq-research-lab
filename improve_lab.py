"""Improvement lab: test regime gates + bracket geometry for the live strategy
on the FULL 5-year Databento MNQ dataset, fees included ($1.22 RT).

Experiments (all keep the live entry: stoch %K14 reclaim 30, 9:40-11:30 ET,
svol>0, cap-fitted sizing, 6 trades/day, -$500/+$1,500 day caps):

  A. Baseline live config, per-year breakdown
  B. Daily trend gates: trade only when yesterday's RTH close > yesterday's
     EMA(N) of daily closes (N = 20, 50) — no lookahead
  C. Rolling edge-health gates: shadow-resolve EVERY signal (as the live bot
     already does); trade live only when the last 20 shadow outcomes show
     >= K wins (K = 11, 12) or positive summed points
  D. Bracket grid: SL x TP in ATR multiples, live filters + sizing, 5 years

News guard not modeled (no historical calendar before 2026 — affects all
configs equally).
"""

from pathlib import Path

import numpy as np
import pandas as pd

from backtest_1yr import (
    DATA_CSV, TZ, STOCH_TH, ENTRY_START, ENTRY_END, MORNING_END, POINT_VALUE,
    MAX_CONTRACTS, DAY_MAX_LOSS, DAY_MAX_PROFIT, DAY_MAX_TRADES, enrich,
    combine_pass_stats,
)

FEE = 1.22
WARMUP = "2021-06-01"
START = "2021-07-18"


def load() -> pd.DataFrame:
    df = pd.read_csv(DATA_CSV)
    df["ts_et"] = pd.to_datetime(df["ts_et"], utc=True).dt.tz_convert(TZ)
    df = df.set_index("ts_et").sort_index()
    hrs = df.index.hour + df.index.minute / 60.0
    return enrich(df[(hrs >= 9.5) & (hrs < 16.0)])


def size_for(atr_val: float, day_pnl: float, sl: float, tp: float) -> int:
    stop_usd = atr_val * sl * POINT_VALUE
    tp_usd = atr_val * tp * POINT_VALUE
    n = min(MAX_CONTRACTS, int((DAY_MAX_LOSS + day_pnl) / stop_usd))
    n = min(n, int((DAY_MAX_PROFIT - day_pnl) / tp_usd))
    return max(n, 0)


def replay_day(day, sl, tp, paper=False):
    """Live control flow; paper=True -> every signal at n=1, no fees (shadow)."""
    if len(day) < 3:
        return []
    h = day["high"].values; l = day["low"].values; c = day["close"].values
    atr = day["atr"].values; K = day["stochK"].values; sv = day["svol"].values
    eth = (day.index.hour + day.index.minute / 60.0).values
    times = day.index
    trades = []; net = 0.0; pos = None
    for i in range(1, len(day)):
        last = i == len(day) - 1
        if pos is not None:
            ex = None
            if l[i] <= pos["sl"]: ex = pos["sl"]
            elif h[i] >= pos["tp"]: ex = pos["tp"]
            elif eth[i] >= 16.0 or last: ex = c[i]
            if ex is not None:
                pts = ex - pos["entry"]
                pnl = pts * POINT_VALUE * pos["n"] - (0 if paper else FEE * pos["n"])
                net += pnl
                trades.append({"ts": pos["ts"], "date": times[i].normalize(),
                               "pts": pts, "n": pos["n"], "pnl": pnl,
                               "win": pnl > 0, "stop_pts": pos["stop_pts"],
                               "tp_pts": pos["tp_pts"]})
                pos = None
        if (pos is None and not last and ENTRY_START <= eth[i] <= ENTRY_END
                and eth[i] <= MORNING_END and len(trades) < DAY_MAX_TRADES):
            if (K[i - 1] <= STOCH_TH and K[i] > STOCH_TH
                    and atr[i] > 0 and not np.isnan(atr[i]) and sv[i] > 0):
                n = 1 if paper else size_for(atr[i], net, sl, tp)
                if n < 1:
                    continue
                pos = {"entry": c[i], "sl": c[i] - atr[i] * sl,
                       "tp": c[i] + atr[i] * tp, "n": n, "ts": times[i],
                       "stop_pts": atr[i] * sl, "tp_pts": atr[i] * tp}
    return trades


def run(d, sl=0.75, tp=0.5, day_allowed=None):
    out = []
    for dnorm, day in d.groupby(d.index.normalize(), sort=True):
        if day_allowed is not None and not day_allowed.get(dnorm, False):
            continue
        out.extend(replay_day(day, sl, tp))
    return pd.DataFrame(out)


def edge_gate_run(stream: pd.DataFrame, mode: str, window=20, k=12):
    """stream = paper (n=1) signal outcomes in time order. Gate each candidate
    trade on the PRIOR `window` shadow outcomes; taken trades re-sized live-style."""
    wins = stream["win_paper"].values
    pts = stream["pts"].values
    rows = []
    day_pnl = 0.0; cur_day = None; day_trades = 0
    for i in range(len(stream)):
        r = stream.iloc[i]
        if r["date"] != cur_day:
            cur_day = r["date"]; day_pnl = 0.0; day_trades = 0
        if i < window or day_trades >= DAY_MAX_TRADES:
            continue
        wnd = slice(i - window, i)
        ok = (wins[wnd].sum() >= k) if mode == "wr" else (pts[wnd].sum() > 0)
        if not ok:
            continue
        n = min(MAX_CONTRACTS,
                int((DAY_MAX_LOSS + day_pnl) / (r["stop_pts"] * POINT_VALUE)),
                int((DAY_MAX_PROFIT - day_pnl) / (r["tp_pts"] * POINT_VALUE)))
        if n < 1:
            continue
        pnl = r["pts"] * POINT_VALUE * n - FEE * n
        day_pnl += pnl; day_trades += 1
        rows.append({"date": r["date"], "pnl": pnl, "win": pnl > 0})
    return pd.DataFrame(rows)


def report(name, t, per_year=True):
    if t.empty:
        print(f"{name:34s}  NO TRADES")
        return None
    daily = t.groupby("date")["pnl"].sum()
    eq = daily.cumsum(); dd = (eq - eq.cummax()).min()
    gw = t.loc[t["pnl"] > 0, "pnl"].sum(); gl = -t.loc[t["pnl"] <= 0, "pnl"].sum()
    pf = gw / gl if gl else float("inf")
    wr = 100 * t["win"].mean()
    line = (f"{name:34s} net ${daily.sum():+9,.0f}  {len(t):4d}tr "
            f"{wr:5.1f}%w  PF {pf:4.2f}  wd ${daily.min():+6,.0f}  DD ${dd:+8,.0f}")
    if per_year:
        yr = daily.groupby(daily.index.year).sum()
        line += "  | " + " ".join(f"{y}:{v:+,.0f}" for y, v in yr.items())
    print(line)
    return daily


def main():
    d = load()
    d_test = d.loc[START:]

    print("=" * 60)
    print("A. BASELINE — exact live config, fees in, 5 years")
    print("=" * 60)
    base = run(d_test)
    base_daily = report("live config (0.75SL/0.5TP)", base)

    print()
    print("=" * 60)
    print("B. DAILY TREND GATES (yesterday close > yesterday EMA-N)")
    print("=" * 60)
    daily_close = d["close"].groupby(d.index.normalize()).last()
    for n in (20, 50):
        ema = daily_close.ewm(span=n, adjust=False).mean()
        allowed = (daily_close > ema).shift(1).fillna(False)
        t = run(d_test, day_allowed=allowed.to_dict())
        report(f"trend gate EMA{n}", t)

    print()
    print("=" * 60)
    print("C. ROLLING EDGE-HEALTH GATES (shadow all signals, trade when hot)")
    print("=" * 60)
    stream_rows = []
    for _, day in d_test.groupby(d_test.index.normalize(), sort=True):
        stream_rows.extend(replay_day(day, 0.75, 0.5, paper=True))
    stream = pd.DataFrame(stream_rows).sort_values("ts").reset_index(drop=True)
    stream["win_paper"] = stream["pts"] > 0
    print(f"(shadow stream: {len(stream)} signals, "
          f"{100*stream['win_paper'].mean():.1f}% raw win)")
    for k in (11, 12):
        report(f"edge gate: >={k}/20 recent wins", edge_gate_run(stream, "wr", 20, k))
    report("edge gate: last-20 pts > 0", edge_gate_run(stream, "pnl", 20))

    print()
    print("=" * 60)
    print("D. BRACKET GRID (SL x TP, ATR mult) — net $ / PF / win%")
    print("=" * 60)
    for sl in (0.5, 0.75, 1.0, 1.25):
        cells = []
        for tp in (0.5, 0.75, 1.0):
            t = run(d_test, sl=sl, tp=tp)
            daily = t.groupby("date")["pnl"].sum()
            gw = t.loc[t["pnl"] > 0, "pnl"].sum(); gl = -t.loc[t["pnl"] <= 0, "pnl"].sum()
            pf = gw / gl if gl else float("inf")
            cells.append(f"TP{tp}: ${daily.sum():+8,.0f} PF{pf:4.2f} "
                         f"{100*t['win'].mean():4.1f}%w wd${daily.min():+4,.0f}")
        print(f"  SL {sl:4.2f} | " + " | ".join(cells))

    print()
    print("=" * 60)
    print("E. BEST GATE x LAST 12 MONTHS + COMBINE SIM")
    print("=" * 60)
    ema50 = daily_close.ewm(span=50, adjust=False).mean()
    allowed50 = (daily_close > ema50).shift(1).fillna(False)
    d_1yr = d.loc["2025-07-17":]
    t = run(d_1yr, day_allowed=allowed50.to_dict())
    daily = report("EMA50 gate, last 12 months", t)
    if daily is not None and len(daily):
        rate, passes = combine_pass_stats(daily)
        med = int(np.median(passes)) if passes else -1
        print(f"    Combine sim: {rate:.1f}% pass" +
              (f", median {med} traded days" if passes else ""))
    t = run(d_1yr)
    daily = report("no gate,   last 12 months", t)
    if daily is not None and len(daily):
        rate, passes = combine_pass_stats(daily)
        med = int(np.median(passes)) if passes else -1
        print(f"    Combine sim: {rate:.1f}% pass" +
              (f", median {med} traded days" if passes else ""))


if __name__ == "__main__":
    main()

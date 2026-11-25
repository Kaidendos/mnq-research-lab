"""Does widening StochReclaim30's target fix its negative expectancy? 5 years, exact fills.

THE PROBLEM BEING ATTACKED
--------------------------
The live bot risks 0.75 ATR to make 0.5 ATR. Break-even is SL/(SL+TP) = 60.0% wins,
and it measures 58.7% — below the line, with a random-entry control at 59.4%. Day
selection cannot fix that; only the bracket can. Widening the target lowers the bar:

    TP 0.50 -> need 60.0%      TP 1.25 -> need 37.5%
    TP 0.75 -> need 50.0%      TP 1.50 -> need 33.3%
    TP 1.00 -> need 42.9%      TP 2.00 -> need 27.3%

The question is whether the win rate decays SLOWER than the break-even line falls.
It will decay — a further target is genuinely harder to reach — so the whole test is
which of the two curves wins.

FILL RESOLUTION — the part that decides the answer
--------------------------------------------------
With TP closer than SL, a single 5-min bar frequently spans both, and on 5-min data
you cannot tell which filled first. Guessing optimistically manufactures edge. So
every exit here is resolved on the 1-MINUTE series, walking forward tick-by-bar until
one level is actually touched first.

⚠ BAR ALIGNMENT: 5-min timestamps are bar START (verified 400/400 previously). A bar
stamped 09:45 covers [09:45, 09:50), so entering at its close means entering at 09:50.
The 1-min scan therefore starts at ts + 5min. Getting this wrong previously produced a
spurious "the backtest is 32% optimistic" result.

Everything else is transcribed from the deployed NinjaScript: entries for bar closes
09:45-11:35, sizing n = min(10, floor((300+dayPnl)/stopUsd), floor((440-dayPnl)/tpUsd)),
6-trade day cap, StopWhenGreen, flat 16:00.
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

import funded_search as fs

PV = 2.0            # $ per MNQ point per contract
FEE = 1.22          # per contract, round turn
TICK = 0.25
STOCH_TH = 30.0
DAY_MAX_LOSS = 300.0
DAY_MAX_PROFIT = 440.0
DAY_MAX_TRADES = 6
MAXC = 10
STOP_WHEN_GREEN = True
BOD_LO, BOD_HI = 2, 24      # bar closes 09:45 .. 11:35
FLAT_BOD = 78               # 16:00

ONE_MIN = fs.D / "mnq_2021-2026_1min.csv.gz"


def load_one_min() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """1-min bars as (epoch_ns, high, low) sorted — the fill referee."""
    m = pd.read_csv(ONE_MIN, usecols=["ts_et", "high", "low"])
    ts = pd.to_datetime(m["ts_et"], utc=True, format="mixed")
    order = np.argsort(ts.values)
    return (ts.values[order].astype("datetime64[ns]"),
            m["high"].to_numpy(float)[order],
            m["low"].to_numpy(float)[order])


def resolve_exit(t1: np.ndarray, h1: np.ndarray, l1: np.ndarray,
                 start_ns: np.datetime64, stop: float, target: float,
                 deadline_ns: np.datetime64, fallback: float):
    """Walk 1-min bars from `start_ns`; return (price, reason, EXIT TIME).

    A single 1-min bar spanning both is far rarer than a 5-min one; when it happens
    the STOP is assumed (the conservative choice — never invent the good fill).

    The exit time is returned so the caller can block re-entry for the trade's real
    duration. NinjaTrader does `if (Position != Flat) return;` — without that block
    the replay can stack overlapping positions and inflate the trade count.
    """
    i = int(np.searchsorted(t1, start_ns, side="left"))
    n = len(t1)
    while i < n and t1[i] <= deadline_ns:
        hit_sl = l1[i] <= stop
        hit_tp = h1[i] >= target
        if hit_sl and hit_tp:
            return stop, "both-1m", t1[i]
        if hit_sl:
            return stop, "stop", t1[i]
        if hit_tp:
            return target, "target", t1[i]
        i += 1
    return fallback, "flat", deadline_ns


def replay(df: pd.DataFrame, one_min, sl_atr: float, tp_atr: float) -> dict:
    t1, h1, l1 = one_min
    k = df["stochK"].to_numpy(float)
    kp = np.r_[np.nan, k[:-1]]
    o = df["open"].to_numpy(float)
    h = df["high"].to_numpy(float)
    lo = df["low"].to_numpy(float)
    c = df["close"].to_numpy(float)
    atr = df["atr"].to_numpy(float)
    day_ids = pd.factorize(df["_day"])[0]
    bod = df.groupby("_day").cumcount().to_numpy()
    ts = df.index.values.astype("datetime64[ns]")
    yrs = df.index.year.to_numpy()

    # session boundaries
    starts = np.flatnonzero(np.r_[True, day_ids[1:] != day_ids[:-1]])
    ends = np.r_[starts[1:], len(day_ids)]

    trades = []
    for s, e in zip(starts, ends):
        day_pnl, day_trades, day_won = 0.0, 0, False
        busy_until = np.datetime64("1970-01-01", "ns")
        for i in range(s, e):
            if not (BOD_LO <= bod[i] <= BOD_HI):
                continue
            if day_trades >= DAY_MAX_TRADES or day_won:
                continue
            if ts[i] < busy_until:           # a position is still open
                continue
            a = atr[i]
            if not np.isfinite(a) or a <= 0 or not np.isfinite(kp[i]):
                continue
            if not (kp[i] <= STOCH_TH < k[i]):
                continue
            if c[i] <= (h[i] + lo[i]) / 2.0:
                continue

            stop_usd = a * sl_atr * PV
            tp_usd = a * tp_atr * PV
            n = min(MAXC, int((DAY_MAX_LOSS + day_pnl) // stop_usd))
            if DAY_MAX_PROFIT > 0:
                n = min(n, int((DAY_MAX_PROFIT - day_pnl) // tp_usd))
            if n < 1:
                continue

            entry = c[i]
            sl_px = entry - max(1, round(a * sl_atr / TICK)) * TICK
            tp_px = entry + max(1, round(a * tp_atr / TICK)) * TICK
            # entry fills at this bar's CLOSE == ts + 5 min; scan 1-min from there
            start_ns = ts[i] + np.timedelta64(5, "m")
            deadline = ts[e - 1] + np.timedelta64(5, "m")
            px, why, exit_ns = resolve_exit(t1, h1, l1, start_ns, sl_px, tp_px,
                                            deadline, c[e - 1])
            gross = (px - entry) * PV * n
            net = gross - FEE * n
            trades.append((yrs[i], net, why, n, gross))
            day_pnl += net
            day_trades += 1
            if STOP_WHEN_GREEN and day_pnl > 0:
                day_won = True
            busy_until = exit_ns        # no overlapping positions, as in NinjaTrader

    if not trades:
        return dict(n=0)
    arr = np.array([t[1] for t in trades])
    grs = np.array([t[4] for t in trades])
    yr = np.array([t[0] for t in trades])
    return dict(
        n=len(trades),
        win=100.0 * (grs > 0).mean(),      # win on the PRICE move, before fees
        breakeven=100.0 * sl_atr / (sl_atr + tp_atr),
        net=arr.sum(),
        gross=grs.sum(),
        fees=grs.sum() - arr.sum(),
        per_year={int(y): float(arr[yr == y].sum()) for y in np.unique(yr)},
        flats=sum(1 for t in trades if t[2] == "flat"),
        both1m=sum(1 for t in trades if t[2] == "both-1m"),
        avg_ct=float(np.mean([t[3] for t in trades])),
    )


def main() -> None:
    print("loading 5-min enriched frame ...", flush=True)
    df = fs.load_enriched()
    print(f"  {len(df):,} RTH bars  {df.index[0].date()} .. {df.index[-1].date()}")
    print("loading 1-min fill referee ...", flush=True)
    one_min = load_one_min()
    print(f"  {len(one_min[0]):,} 1-min bars", flush=True)

    years = sorted({int(y) for y in df.index.year})
    grid = [(0.75, tp) for tp in (0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0)]
    grid += [(1.0, 1.5), (1.0, 2.0), (1.0, 3.0), (1.5, 3.0), (2.0, 3.0)]

    print("\n" + "=" * 118)
    print("StochReclaim30 — reward:risk sweep, 5 years of MNQ, exits resolved on 1-min bars")
    print("=" * 118)
    hdr = (f"  {'SL':>5}{'TP':>6}{'R:R':>6}{'trades':>8}{'win%':>8}"
           f"{'need':>8}{'edge':>7}{'gross $':>10}{'fees':>9}{'net $':>10}")
    hdr += "".join(f"{y:>9}" for y in years)
    print(hdr)
    rows = []
    for sl, tp in grid:
        r = replay(df, one_min, sl, tp)
        if not r["n"]:
            continue
        edge = r["win"] - r["breakeven"]
        line = (f"  {sl:>5.2f}{tp:>6.2f}{tp / sl:>6.2f}{r['n']:>8}"
                f"{r['win']:>8.1f}{r['breakeven']:>8.1f}{edge:>+7.1f}"
                f"{r['gross']:>10,.0f}{-r['fees']:>9,.0f}{r['net']:>10,.0f}")
        line += "".join(f"{r['per_year'].get(y, 0):>9,.0f}" for y in years)
        print(line)
        rows.append((sl, tp, r, edge))

    print("\n  edge = win% minus the break-even it needs. POSITIVE is the whole point.")
    best = max(rows, key=lambda x: x[2]["net"])
    live = next((x for x in rows if x[0] == 0.75 and x[1] == 0.5), None)
    print("\n" + "=" * 118)
    print("VERDICT")
    print("=" * 118)
    if live:
        print(f"  LIVE  SL 0.75 / TP 0.50 : win {live[2]['win']:.1f}% vs need "
              f"{live[2]['breakeven']:.1f}%  ->  edge {live[3]:+.1f} pts, "
              f"net ${live[2]['net']:,.0f} over 5 years")
    print(f"  BEST  SL {best[0]:.2f} / TP {best[1]:.2f} : win {best[2]['win']:.1f}% "
          f"vs need {best[2]['breakeven']:.1f}%  ->  edge {best[3]:+.1f} pts, "
          f"net ${best[2]['net']:,.0f}")
    pos = [x for x in rows if x[3] > 0]
    print(f"\n  {len(pos)} of {len(rows)} bracket combos clear their own break-even.")
    if pos:
        yrs_all = sorted({y for x in pos for y in x[2]['per_year']})
        print("  Of those, consistency across years (a combo that only works in one "
              "year is noise):")
        for sl, tp, r, edge in sorted(pos, key=lambda x: -x[2]["net"]):
            wins = sum(1 for y in yrs_all if r["per_year"].get(y, 0) > 0)
            print(f"    SL {sl:.2f}/TP {tp:.2f}  positive in {wins}/{len(yrs_all)} "
                  f"years  net ${r['net']:>9,.0f}  edge {edge:+.1f}")


if __name__ == "__main__":
    sys.exit(main())

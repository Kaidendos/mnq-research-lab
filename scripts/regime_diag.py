"""Regime diagnosis for StochReclaim30.

Question: did the edge decay, or does it simply have no defense in a downtrend?

Faithful re-implementation of the live NT strategy
(nt_strategy_backups/StochReclaim30_2026-07-22_funded_budget300_159D4485.cs):
  * raw %K(14) = 100*(C-LL14)/(HH14-LL14)   [NOT NT's smoothed Stochastics]
  * entry when %K crosses UP through 30, on a bar closing in its upper half
  * long only, stop 0.75*ATR(14), target 0.5*ATR(14)
  * entry window 09:45-11:35 ET (bar close), flatten 16:00 ET
  * <=6 trades/day, day locks once net green (StopWhenGreen)
  * size = min(10, floor((300+dayPnl)/stopUsd), floor((440-dayPnl)/tpUsd))

Usage:  python regime_diag.py [mnq|nq]
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

D = Path(__file__).parent / "data" / "databento"
PV = 2.0                 # MNQ $/point
COMM = 0.74              # round-turn commission per contract
SLIP_TICKS = 2           # per side, ticks
TICK = 0.25

# strategy params (live funded config)
STOCH_N, THRESH = 14, 30.0
ATR_N = 14
SL_ATR, TP_ATR = 0.75, 0.5
ENTRY_START, ENTRY_END = 9 * 60 + 45, 11 * 60 + 35   # minutes since midnight ET
FLAT_MIN = 16 * 60
DAY_MAX_TRADES = 6
DAY_MAX_LOSS, DAY_MAX_PROFIT = 300.0, 440.0
MAX_CT = 10


def load(sym: str) -> pd.DataFrame:
    df = pd.read_csv(D / f"{sym}_2021-2026_5min.csv", parse_dates=["ts_et"])
    df["ts_et"] = pd.to_datetime(df["ts_et"], utc=True).dt.tz_convert("America/New_York")
    df["min"] = df["ts_et"].dt.hour * 60 + df["ts_et"].dt.minute
    # RTH only: bar close 09:35..16:00 (a 5-min bar stamped 09:30 covers 09:30-09:35)
    df = df[(df["min"] >= 9 * 60 + 30) & (df["min"] < FLAT_MIN)].copy()
    df["day"] = df["ts_et"].dt.normalize()
    return df.sort_values("ts_et").reset_index(drop=True)


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    ll = df["low"].rolling(STOCH_N).min()
    hh = df["high"].rolling(STOCH_N).max()
    rng = hh - ll
    df["k"] = np.where(rng > 0, 100.0 * (df["close"] - ll) / rng, np.nan)
    # Wilder ATR
    pc = df["close"].shift(1)
    tr = pd.concat([df["high"] - df["low"],
                    (df["high"] - pc).abs(),
                    (df["low"] - pc).abs()], axis=1).max(axis=1)
    df["atr"] = tr.ewm(alpha=1.0 / ATR_N, adjust=False).mean()
    df["kprev"] = df["k"].shift(1)
    df["upper_half"] = df["close"] > (df["high"] + df["low"]) / 2.0
    return df


def daily_regime(df: pd.DataFrame) -> pd.DataFrame:
    """Classify each session by the prevailing daily trend (no lookahead)."""
    d = df.groupby("day").agg(close=("close", "last")).reset_index()
    d["sma50"] = d["close"].rolling(50).mean()
    d["sma50_prev"] = d["sma50"].shift(5)
    # shift(1): only information available BEFORE the session starts
    # shift produces NaN on row 0 -> fill before inverting, else ~ hits a float
    above = (d["close"] > d["sma50"]).shift(1).fillna(False).astype(bool)
    rising = (d["sma50"] > d["sma50_prev"]).shift(1).fillna(False).astype(bool)
    d["regime"] = np.select(
        [above & rising, ~above & ~rising],
        ["uptrend", "downtrend"], default="chop")
    d.loc[d["sma50"].shift(1).isna(), "regime"] = "warmup"
    return d[["day", "regime"]]


def simulate(df: pd.DataFrame) -> pd.DataFrame:
    slip = SLIP_TICKS * TICK
    trades = []
    for day, g in df.groupby("day", sort=True):
        g = g.reset_index(drop=True)
        day_pnl, day_trades, day_won = 0.0, 0, False
        i = 0
        while i < len(g):
            r = g.iloc[i]
            if day_won or day_trades >= DAY_MAX_TRADES:
                break
            if not (ENTRY_START <= r["min"] <= ENTRY_END):
                i += 1
                continue
            if not (r["kprev"] <= THRESH < r["k"]) or not r["upper_half"]:
                i += 1
                continue
            atr = r["atr"]
            if not np.isfinite(atr) or atr <= 0 or not np.isfinite(r["kprev"]):
                i += 1
                continue

            stop_usd = atr * SL_ATR * PV
            tp_usd = atr * TP_ATR * PV
            n = min(MAX_CT, int((DAY_MAX_LOSS + day_pnl) // stop_usd),
                    int((DAY_MAX_PROFIT - day_pnl) // tp_usd))
            if n < 1:
                break

            entry = r["close"] + slip            # pay the spread going in
            stop_px = entry - atr * SL_ATR
            targ_px = entry + atr * TP_ATR

            exit_px, reason = None, None
            for j in range(i + 1, len(g)):
                b = g.iloc[j]
                hit_stop = b["low"] <= stop_px
                hit_targ = b["high"] >= targ_px
                if hit_stop and hit_targ:        # ambiguous bar -> assume the loss
                    exit_px, reason = stop_px - slip, "stop(amb)"
                elif hit_stop:
                    exit_px, reason = stop_px - slip, "stop"
                elif hit_targ:
                    exit_px, reason = targ_px - slip, "target"
                if exit_px is not None:
                    i = j
                    break
            if exit_px is None:                  # EOD flatten
                exit_px, reason = g.iloc[-1]["close"] - slip, "eod"
                i = len(g)

            pnl = (exit_px - entry) * n * PV - COMM * n
            day_pnl += pnl
            day_trades += 1
            if pnl > 0 and day_pnl > 0:
                day_won = True
            trades.append(dict(day=day, time=r["ts_et"], n=n, entry=entry,
                               exit=exit_px, atr=atr, reason=reason, pnl=pnl))
            i += 1
    return pd.DataFrame(trades)


def report(t: pd.DataFrame, reg: pd.DataFrame, label: str) -> None:
    t = t.merge(reg, on="day", how="left")
    print(f"\n{'='*78}\n{label}\n{'='*78}")
    print(f"trades {len(t):,}   net ${t['pnl'].sum():,.0f}   "
          f"win {100*(t['pnl']>0).mean():.1f}%   avg ${t['pnl'].mean():.2f}")
    print(f"break-even win rate for 0.75/0.5 R:R = {100*SL_ATR/(SL_ATR+TP_ATR):.0f}%")

    print(f"\n{'BY REGIME':-<78}")
    print(f"{'regime':<12}{'trades':>8}{'win%':>8}{'net $':>12}{'avg $':>9}{'$/day':>9}")
    for rg in ("uptrend", "chop", "downtrend"):
        s = t[t["regime"] == rg]
        if not len(s):
            continue
        nd = s["day"].nunique()
        print(f"{rg:<12}{len(s):>8}{100*(s['pnl']>0).mean():>8.1f}"
              f"{s['pnl'].sum():>12,.0f}{s['pnl'].mean():>9.2f}{s['pnl'].sum()/nd:>9.2f}")

    print(f"\n{'BY YEAR':-<78}")
    print(f"{'year':<12}{'trades':>8}{'win%':>8}{'net $':>12}{'avg $':>9}")
    t["year"] = t["day"].dt.year
    for y, s in t.groupby("year"):
        print(f"{y:<12}{len(s):>8}{100*(s['pnl']>0).mean():>8.1f}"
              f"{s['pnl'].sum():>12,.0f}{s['pnl'].mean():>9.2f}")

    print(f"\n{'LAST 6 MONTHS BY MONTH':-<78}")
    t["ym"] = t["day"].dt.to_period("M")
    for ym, s in list(t.groupby("ym"))[-6:]:
        print(f"{str(ym):<12}{len(s):>8}{100*(s['pnl']>0).mean():>8.1f}"
              f"{s['pnl'].sum():>12,.0f}{s['pnl'].mean():>9.2f}")

    print(f"\n{'EXIT REASONS':-<78}")
    for rsn, s in t.groupby("reason"):
        print(f"  {rsn:<12}{len(s):>7}  net {s['pnl'].sum():>10,.0f}")


if __name__ == "__main__":
    sym = sys.argv[1] if len(sys.argv) > 1 else "mnq"
    df = add_indicators(load(sym))
    reg = daily_regime(df)
    tr = simulate(df)
    tr.to_csv(D / f"regime_diag_{sym}_trades.csv", index=False)
    report(tr, reg, f"StochReclaim30 (live funded config) on {sym.upper()} "
                    f"5-min, {df['day'].min():%Y-%m-%d} -> {df['day'].max():%Y-%m-%d}")
    print(f"\nsaved: regime_diag_{sym}_trades.csv")

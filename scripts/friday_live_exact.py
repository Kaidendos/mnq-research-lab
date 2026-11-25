"""EXACT live NinjaTrader strategy, FRIDAYS ONLY, last 5 months. Trade by trade.

Parameters taken verbatim from the deployed file
nt_strategy_backups/StochReclaim30_2026-07-22_funded_budget300_159D4485.cs:

    StochPeriod 14, StochThreshold 30      -> raw %K(14) crosses UP through 30
    entry bar must close in its UPPER HALF (svol > 0), LONG only
    SlAtr 0.75, TpAtr 0.5   (ATR(14) Wilder)
    EntryStartEt 09:45:00, EntryEndEt 11:35:00   (ET *bar-close* times)
    FlatTimeEt 16:00:00
    MaxContracts 10, DayMaxLossUsd 300, DayMaxProfitUsd 440
    DayMaxTrades 6, StopWhenGreen true
    sizing n = min(10, floor((300+dayPnl)/stop$), floor((440-dayPnl)/tp$))

Bars are open-labelled, so a bar CLOSING 09:45 opens 09:40 -> eth window 9.6667-11.5,
matching the project's own backtest_1yr.py constants.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import funded_search as fs

PV, FEE = 2.0, 1.22
SL_ATR, TP_ATR = 0.75, 0.5
MAXC, DAY_LOSS, DAY_PROFIT, DAY_TRADES = 10, 300.0, 440.0, 6
LIVE_WIN = (9.6667, 11.5)      # bar-close 09:45 - 11:35
FULL_WIN = (9.5, 16.0)         # "whole day", for comparison only


def replay_trades(df, entry, win):
    """Same rules as the live strategy; returns the individual trades."""
    hi, lo, cl = df["high"].values, df["low"].values, df["close"].values
    atr, eth = df["atr"].values, df["eth"].values
    ent = np.asarray(entry, dtype=bool)
    dayid = df["_day"].values
    ws, we = win
    starts = np.flatnonzero(np.r_[True, dayid[1:] != dayid[:-1]])
    ends = np.r_[starts[1:], len(df)]
    trades = []
    for s, e in zip(starts, ends):
        net, ntr, day_won, pos = 0.0, 0, False, None
        for i in range(s, e):
            last = i == e - 1
            if pos is not None:
                px, why = None, None
                if lo[i] <= pos["sl"]:
                    px, why = pos["sl"], "stop"
                elif hi[i] >= pos["tp"]:
                    px, why = pos["tp"], "target"
                elif eth[i] >= 16.0 or last:
                    px, why = cl[i], "EOD"
                if px is not None:
                    pnl = (px - pos["entry"]) * PV * pos["n"] - FEE * pos["n"]
                    net += pnl
                    ntr += 1
                    trades.append(dict(day=df.index[s].normalize(), t_in=pos["ts"],
                                       t_out=df.index[i], n=pos["n"],
                                       entry=pos["entry"], exit=px, why=why,
                                       pnl=pnl, day_net=net))
                    if net > 0:
                        day_won = True
                    pos = None
            if (pos is None and not last and not day_won and ent[i]
                    and ws <= eth[i] <= we and atr[i] > 0 and not np.isnan(atr[i])
                    and ntr < DAY_TRADES):
                stop_usd, tp_usd = atr[i] * SL_ATR * PV, atr[i] * TP_ATR * PV
                n = min(MAXC, int((DAY_LOSS + net) / stop_usd),
                        int((DAY_PROFIT - net) / tp_usd))
                if n < 1:
                    continue
                pos = dict(entry=cl[i], n=n, ts=df.index[i],
                           sl=cl[i] - atr[i] * SL_ATR, tp=cl[i] + atr[i] * TP_ATR)
    return pd.DataFrame(trades)


df = fs.load_enriched()
entry, _ = fs.sig(df, "stoch30_long")
entry = entry.reindex(df.index).fillna(False)
end = df.index[-1]
w5 = end - pd.DateOffset(months=5)

fri = df[(df.index >= w5) & (df.index.dayofweek == 4)]
n_fri = fri["_day"].nunique()

for win, label in ((LIVE_WIN, "LIVE WINDOW 09:45-11:35 (as deployed)"),
                   (FULL_WIN, "WHOLE DAY 09:30-16:00 (comparison)")):
    t = replay_trades(fri, entry.reindex(fri.index).fillna(False), win)
    print("\n" + "=" * 92)
    print(f"FRIDAYS ONLY | {label}")
    print(f"{fri.index[0]:%Y-%m-%d} -> {fri.index[-1]:%Y-%m-%d}  |  {n_fri} Fridays")
    print("=" * 92)
    if t.empty:
        print("  NO TRADES")
        continue
    wins = int((t.pnl > 0).sum())
    print(f"  trades {len(t)} | win {100*wins/len(t):.1f}% ({wins}W/{len(t)-wins}L) | "
          f"NET ${t.pnl.sum():,.2f}")
    print(f"  avg win ${t[t.pnl>0].pnl.mean() if wins else 0:,.2f} | "
          f"avg loss ${t[t.pnl<0].pnl.mean() if wins<len(t) else 0:,.2f} | "
          f"biggest win ${t.pnl.max():,.2f} | biggest loss ${t.pnl.min():,.2f}")
    daily = t.groupby("day").pnl.sum()
    print(f"  Fridays traded {len(daily)} of {n_fri} | "
          f"green {int((daily>0).sum())} red {int((daily<0).sum())}")
    pf = t[t.pnl > 0].pnl.sum() / abs(t[t.pnl < 0].pnl.sum()) if wins < len(t) else float("inf")
    print(f"  profit factor {pf:.2f}")
    print(f"\n  {'entry':<18}{'exit':<18}{'qty':>4}{'in':>10}{'out':>10}{'why':>8}{'P&L':>10}")
    for _, r in t.iterrows():
        print(f"  {r.t_in:%Y-%m-%d %H:%M}  {r.t_out:%Y-%m-%d %H:%M}{r.n:>4}"
              f"{r.entry:>10.2f}{r.exit:>10.2f}{r.why:>8}{r.pnl:>+10.2f}")
    eq = daily.cumsum()
    print(f"\n  {'Friday':<14}{'day P&L':>10}{'equity':>10}")
    for d, v in daily.items():
        print(f"  {d:%Y-%m-%d}{v:>10,.0f}{eq[d]:>10,.0f}")
    print(f"  {'MAX DRAWDOWN':<14}{'':>10}{(eq - eq.cummax()).min():>10,.0f}")

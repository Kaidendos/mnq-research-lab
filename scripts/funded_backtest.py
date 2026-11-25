"""Backtest the FUNDED LucidPro configs before they go on real funded money.

Replays the live NT strategy (StochReclaim30) with the funded sizing knobs the
user is deciding between, fees in ($1.22 RT), then simulates the LucidPro $25k
payout path from EVERY possible start day over 5 years:

  * $1,000 trailing max drawdown  -> bust if it's ever breached
  * 40% consistency               -> biggest day <= 40% of total at withdrawal
  * $1,100 buffer                 -> need +$1,100 cumulative net to withdraw
  * 3 trading-day minimum

Two candidate paces:
  $250 pace : cap $250 / loss budget $375 / stop-after-win
  $200 pace : cap $200 / loss budget $300 / stop-after-win

Reports pass rate (reaches a compliant payout), trading days to get there, and
bust rate — both over the full 5 years and over the last 12 months.
"""

import numpy as np
import pandas as pd

import improve_lab as il
from backtest_1yr import (
    STOCH_TH, ENTRY_START, ENTRY_END, MORNING_END, POINT_VALUE,
    MAX_CONTRACTS, DAY_MAX_TRADES,
)

FEE = 1.22
BUFFER = 1100          # +$1,100 net to reach the $26,100 withdrawal buffer
CONSISTENCY = 0.40     # biggest day <= 40% of total profit at withdrawal
MIN_DAYS = 3           # LucidPro minimum trading days
TRAIL_DD = 1000        # trailing max drawdown


def replay_day(day, cap, budget, stop_after_win, sl=0.75, tp=0.5):
    """One RTH session with funded sizing. Returns net $ for the day (fees in)."""
    if len(day) < 3:
        return 0.0
    h = day["high"].values; l = day["low"].values; c = day["close"].values
    atr = day["atr"].values; K = day["stochK"].values; sv = day["svol"].values
    eth = (day.index.hour + day.index.minute / 60.0).values
    net = 0.0; pos = None; ntrades = 0; day_won = False
    for i in range(1, len(day)):
        last = i == len(day) - 1
        if pos is not None:
            ex = None
            if l[i] <= pos["sl"]: ex = pos["sl"]
            elif h[i] >= pos["tp"]: ex = pos["tp"]
            elif eth[i] >= 16.0 or last: ex = c[i]
            if ex is not None:
                pnl = (ex - pos["entry"]) * POINT_VALUE * pos["n"] - FEE * pos["n"]
                net += pnl; ntrades += 1
                if pnl > 0 and stop_after_win:
                    day_won = True
                pos = None
        if (pos is None and not last and not day_won
                and ENTRY_START <= eth[i] <= ENTRY_END and eth[i] <= MORNING_END
                and ntrades < DAY_MAX_TRADES):
            if (K[i - 1] <= STOCH_TH and K[i] > STOCH_TH
                    and atr[i] > 0 and not np.isnan(atr[i]) and sv[i] > 0):
                stop_usd = atr[i] * sl * POINT_VALUE
                tp_usd = atr[i] * tp * POINT_VALUE
                n = min(MAX_CONTRACTS, int((budget + net) / stop_usd))
                if cap > 0:
                    n = min(n, int((cap - net) / tp_usd))
                if n < 1:
                    continue
                pos = {"entry": c[i], "sl": c[i] - atr[i] * sl,
                       "tp": c[i] + atr[i] * tp, "n": n}
    return net


def daily_series(d, cap, budget, stop_after_win, day_allowed=None):
    rows = []
    for dnorm, day in d.groupby(d.index.normalize(), sort=True):
        if day_allowed is not None and not day_allowed.get(dnorm, False):
            continue
        rows.append((dnorm, replay_day(day, cap, budget, stop_after_win)))
    s = pd.Series({k: v for k, v in rows}).sort_index()
    return s[s != 0.0]   # active (traded) days only


def payout_sim(daily):
    """From each active start day walk forward until a compliant payout or bust.
    Trailing DD floor never locks (Apex-style, the strict reading)."""
    vals = daily.values
    days_to_payout = []; busts = 0; attempts = 0; unresolved = 0
    for s in range(len(vals)):
        cum = 0.0; peak = 0.0; biggest = 0.0; d = 0; outcome = None
        for j in range(s, len(vals)):
            cum += vals[j]; d += 1
            peak = max(peak, cum)
            biggest = max(biggest, vals[j])   # biggest single GREEN day
            if peak - cum >= TRAIL_DD:
                outcome = "bust"; break
            if (d >= MIN_DAYS and cum >= BUFFER
                    and biggest <= CONSISTENCY * cum):
                outcome = d; break
        if outcome is None:
            unresolved += 1; continue
        attempts += 1
        if outcome == "bust":
            busts += 1
        else:
            days_to_payout.append(outcome)
    return attempts, days_to_payout, busts, unresolved


def describe_days(daily, label):
    g = daily[daily > 0]; r = daily[daily < 0]
    print(f"  [{label}] {len(daily)} active days | "
          f"{100*len(g)/len(daily):.0f}% green | "
          f"avg green +${g.mean():.0f} | avg red ${r.mean():.0f} | "
          f"worst ${daily.min():+.0f} | best ${daily.max():+.0f}")


def run_config(name, d, cap, budget, saw, label, day_allowed=None):
    daily = daily_series(d, cap, budget, saw, day_allowed)
    if daily.empty:
        print(f"{name}: no trades"); return
    describe_days(daily, label)
    att, dtp, busts, unres = payout_sim(daily)
    net = daily.sum()
    print(f"  net over window ${net:+,.0f} | payout attempts {att} "
          f"(+{unres} ran out of data)")
    if att:
        pr = 100 * len(dtp) / att
        print(f"  PAYOUT before bust: {pr:.1f}%   |   BUST: {100*busts/att:.1f}%")
        if dtp:
            print(f"  trading days to payout: median {int(np.median(dtp))}, "
                  f"p90 {int(np.percentile(dtp,90))}, worst {max(dtp)}, "
                  f"best {min(dtp)}")
    print()


def main():
    d = il.load()
    full = d.loc[il.START:]
    yr = d.loc["2025-07-17":]

    # EMA50 daily-trend gate (no lookahead): trade a day only when yesterday's
    # RTH close was above the 50-day EMA of daily closes.
    daily_close = d["close"].groupby(d.index.normalize()).last()
    ema50 = daily_close.ewm(span=50, adjust=False).mean()
    gate = (daily_close > ema50).shift(1).fillna(False).to_dict()

    headline = [
        ("$250 pace  (cap 250 / budget 375 / stop-after-win)", 250, 375, True),
        ("$200 pace  (cap 200 / budget 300 / stop-after-win)", 200, 300, True),
        ("current eval config (cap 1500 / budget 500 / no stop)", 1500, 500, False),
    ]
    # size sweep, keeping the forced 1.5x budget:cap ratio, all stop-after-win
    sweep = [(250, 375), (200, 300), (150, 225), (120, 180), (100, 150), (75, 113)]

    for win_name, dd in (("FULL 5 YEARS  (2021-07-18 -> 2026-07-16)", full),
                         ("LAST 12 MONTHS  (2025-07-17 -> 2026-07-16)", yr)):
        print("=" * 68); print(win_name); print("=" * 68)
        for name, cap, bud, saw in headline:
            print(name + "  [NO gate]")
            run_config(name, dd, cap, bud, saw, "raw")

    for win_name, dd in (("FULL 5 YEARS — EMA50 GATE — SIZE SWEEP", full),
                         ("LAST 12 MONTHS — EMA50 GATE — SIZE SWEEP", yr)):
        print("=" * 68); print(win_name); print("=" * 68)
        for cap, bud in sweep:
            print(f"cap ${cap} / budget ${bud} / stop-after-win  [EMA50 gate]")
            run_config("", dd, cap, bud, True, "gated", day_allowed=gate)


if __name__ == "__main__":
    main()

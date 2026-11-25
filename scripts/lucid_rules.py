"""CORRECTED LucidPro 25K simulator — the real rules, not the strict-Apex guess.

Verified against vendor documentation 2026-08-08:
  * start $25,000, max loss limit (MLL) $1,000
  * drawdown is END-OF-DAY: the floor moves up only on the highest CLOSING balance
  * the floor LOCKS PERMANENTLY at $25,100 once a closing balance clears $26,100
      -> after that the account is effectively bust-proof above $25,100
  * payout buffer $26,100 (start + MLL + $100); you withdraw only what is ABOVE it
  * max payout $1,000 on the FIRST cycle, $1,500 on every cycle after
  * 40% consistency per funded cycle (biggest green day <= 40% of cycle profit)
  * minimum 3 trading days per payout cycle
  * no daily loss limit on the 25K

The old model in funded_backtest.py trailed forever (too harsh) AND paid out at
$26,100 (too generous). Both are fixed here.

The account is CONTINUOUS: it is not "reach target, reset". You keep trading and
withdraw periodically, and the locked floor changes the risk profile completely.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

START = 25_000.0
MLL = 1_000.0
BUFFER = START + MLL + 100.0        # 26,100
LOCK_FLOOR = START + 100.0          # 25,100
LOCK_TRIGGER = BUFFER               # closing balance must clear 26,100
CONSISTENCY = 0.40
MIN_DAYS = 3
CAP_FIRST, CAP_AFTER = 1_000.0, 1_500.0


def simulate(daily: pd.Series, min_withdraw=None, verbose=False):
    """min_withdraw: don't request a payout until at least this much is available.
    Withdrawing the instant you clear $26,100 nets ~$100 and puts you straight back
    on the floor — waiting to accumulate is both realistic and safer."""
    """Run one continuous funded account over a daily P&L series.

    Returns dict with payouts taken, total withdrawn, whether/when it busted.
    """
    bal = START
    floor = START - MLL              # 24,000
    locked = False
    cycle_days, cycle_profit, cycle_big = 0, 0.0, 0.0
    payouts, withdrawn, events = [], 0.0, []

    for dt, pnl in daily.items():
        bal += pnl
        cycle_days += 1
        cycle_profit += pnl
        cycle_big = max(cycle_big, pnl)

        # EOD bust check
        if bal <= floor:
            events.append(("BUST", dt, bal))
            return dict(busted=True, bust_date=dt, payouts=len(payouts),
                        withdrawn=withdrawn, final=bal, events=events,
                        days_survived=len(events))

        # floor trails on the highest CLOSING balance, then locks
        if not locked:
            floor = max(floor, bal - MLL)
            if bal >= LOCK_TRIGGER:
                floor = LOCK_FLOOR
                locked = True
                events.append(("LOCKED", dt, bal))

        # payout: only the amount ABOVE the buffer, subject to cap + consistency
        if bal > BUFFER and cycle_days >= MIN_DAYS and cycle_profit > 0:
            if cycle_big <= CONSISTENCY * cycle_profit:
                cap = CAP_FIRST if not payouts else CAP_AFTER
                amt = min(bal - BUFFER, cap)
                floor_amt = min_withdraw if min_withdraw is not None else 100
                if amt >= floor_amt:
                    bal -= amt
                    withdrawn += amt
                    payouts.append((dt, amt))
                    events.append(("PAYOUT", dt, amt))
                    cycle_days, cycle_profit, cycle_big = 0, 0.0, 0.0

    return dict(busted=False, bust_date=None, payouts=len(payouts),
                withdrawn=withdrawn, final=bal, events=events,
                days_survived=len(daily))


def rolling_starts(daily: pd.Series, horizon_days=None, min_withdraw=None):
    """Start a fresh account on every day; report outcome distribution."""
    idx = daily.index
    out = []
    for s in range(len(daily)):
        sub = daily.iloc[s:]
        if horizon_days is not None:
            sub = sub[sub.index <= idx[s] + pd.Timedelta(days=horizon_days)]
        if len(sub) < MIN_DAYS:
            continue
        r = simulate(sub, min_withdraw=min_withdraw)
        first_pay = r["events"] and next((e for e in r["events"] if e[0] == "PAYOUT"), None)
        out.append(dict(
            start=idx[s], busted=r["busted"], payouts=r["payouts"],
            withdrawn=r["withdrawn"],
            days_to_first=(first_pay[1] - idx[s]).days if first_pay else -1,
            locked=any(e[0] == "LOCKED" for e in r["events"]),
        ))
    return pd.DataFrame(out)

"""INTEGRATED account simulator — sizing that knows where the floor is.

Every harness so far separated two things that are not separable:
    stage 1: replay trades with a FIXED daily budget -> daily P&L
    stage 2: feed that P&L into the account rules -> payouts / bust

That is wrong. Real risk depends on ACCOUNT STATE. Risking $300 with $1,050 of
room left is a very different act from risking $300 with $5,000 of room, and the
split-stage design cannot express the difference. This merges them.

Two new levers, both aimed squarely at bust rate:

  RISK_FRAC   never risk more than this share of the remaining room in one day.
              day_budget = min(base_budget, (balance - floor) * risk_frac)
              Near the floor the size collapses automatically, which is exactly
              when a fixed budget would kill the account.

  CUSHION     do not withdraw down to the bare buffer. Build to
              BUFFER + cushion and withdraw only the excess, so the account keeps
              permanent room instead of returning to the edge after every payout.

LucidPro 25K rules as verified: EOD trail on highest closing balance, floor locks
permanently at 25,100 once a closing balance clears 26,100, withdraw only above
26,100, cap 1,000 first cycle then 1,500, 40% consistency per cycle, 3-day minimum.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

START, MLL = 25_000.0, 1_000.0
BUFFER = START + MLL + 100.0        # 26,100
LOCK_FLOOR = START + 100.0          # 25,100
CONSISTENCY, MIN_DAYS = 0.40, 3
CAP_FIRST, CAP_AFTER = 1_000.0, 1_500.0
PV, FEE = 2.0, 1.22


def run_account(df, ent_l, ent_s, sl, tp, win, cap_day, base_budget, maxc,
                risk_frac=1.0, cushion=0.0, horizon_days=None, start_i=0):
    """Trade the account forward with floor-aware sizing. One position at a time."""
    hi, lo, cl = df["high"].values, df["low"].values, df["close"].values
    atr, eth = df["atr"].values, df["eth"].values
    el, es = np.asarray(ent_l, bool), np.asarray(ent_s, bool)
    both = el & es
    el, es = el & ~both, es & ~both
    dayid = df["_day"].values
    idx = df.index
    ws, we = win

    starts = np.flatnonzero(np.r_[True, dayid[1:] != dayid[:-1]])
    ends = np.r_[starts[1:], len(df)]
    if start_i:
        keep = starts >= start_i
        starts, ends = starts[keep], ends[keep]
    if len(starts) == 0:
        return dict(busted=False, payouts=0, withdrawn=0.0, final=START, days=0)

    t0 = idx[starts[0]]
    bal, floor, locked = START, START - MLL, False
    cyc_days = cyc_prof = cyc_big = 0.0
    cyc_days = 0
    payouts, withdrawn = 0, 0.0

    for s, e in zip(starts, ends):
        if horizon_days is not None and (idx[s] - t0).days > horizon_days:
            break
        room = bal - floor
        if room <= 0:
            return dict(busted=True, payouts=payouts, withdrawn=withdrawn,
                        final=bal, days=(idx[s] - t0).days)
        budget = min(base_budget, room * risk_frac)
        net, ntr, day_won, pos = 0.0, 0, False, None
        for i in range(s, e):
            last = i == e - 1
            if pos is not None:
                sd = pos["side"]
                px = None
                if sd > 0:
                    if lo[i] <= pos["sl"]: px = pos["sl"]
                    elif hi[i] >= pos["tp"]: px = pos["tp"]
                else:
                    if hi[i] >= pos["sl"]: px = pos["sl"]
                    elif lo[i] <= pos["tp"]: px = pos["tp"]
                if px is None and (eth[i] >= 16.0 or last):
                    px = cl[i]
                if px is not None:
                    net += sd * (px - pos["entry"]) * PV * pos["n"] - FEE * pos["n"]
                    ntr += 1
                    if net > 0:
                        day_won = True
                    pos = None
            if (pos is None and not last and not day_won
                    and ws <= eth[i] <= we and atr[i] > 0 and not np.isnan(atr[i])
                    and ntr < 6 and (el[i] or es[i])):
                sd = 1 if el[i] else -1
                su, tu = atr[i] * sl * PV, atr[i] * tp * PV
                n = min(maxc, int((budget + net) / su), int((cap_day - net) / tu))
                if n < 1:
                    continue
                pos = dict(side=sd, entry=cl[i], n=n,
                           sl=cl[i] - sd * atr[i] * sl, tp=cl[i] + sd * atr[i] * tp)

        if ntr == 0:
            continue
        bal += net
        cyc_days += 1
        cyc_prof += net
        cyc_big = max(cyc_big, net)

        if bal <= floor:
            return dict(busted=True, payouts=payouts, withdrawn=withdrawn,
                        final=bal, days=(idx[s] - t0).days)
        if not locked:
            floor = max(floor, bal - MLL)
            if bal >= BUFFER:
                floor, locked = LOCK_FLOOR, True

        thresh = BUFFER + cushion
        if bal > thresh and cyc_days >= MIN_DAYS and cyc_prof > 0 \
                and cyc_big <= CONSISTENCY * cyc_prof:
            amt = min(bal - thresh, CAP_FIRST if payouts == 0 else CAP_AFTER)
            if amt >= 250:
                bal -= amt
                withdrawn += amt
                payouts += 1
                cyc_days, cyc_prof, cyc_big = 0, 0.0, 0.0

    return dict(busted=False, payouts=payouts, withdrawn=withdrawn, final=bal,
                days=(idx[ends[-1] - 1] - t0).days)


def evaluate(df, ent_l, ent_s, sl, tp, win, cap_day, base_budget, maxc,
             risk_frac, cushion, horizon=365, stride=4):
    """Score across many staggered account starts."""
    dayid = df["_day"].values
    starts = np.flatnonzero(np.r_[True, dayid[1:] != dayid[:-1]])
    outs, bust, paid, n = [], 0, 0, 0
    for k in range(0, len(starts), stride):
        r = run_account(df, ent_l, ent_s, sl, tp, win, cap_day, base_budget, maxc,
                        risk_frac=risk_frac, cushion=cushion,
                        horizon_days=horizon, start_i=starts[k])
        if r["days"] < 20:
            continue
        outs.append(r["withdrawn"])
        bust += r["busted"]
        paid += r["payouts"] >= 1
        n += 1
    if not n:
        return dict(n=0, mean_out=0, med_out=0, pay_pct=0, bust_pct=100)
    a = np.array(outs)
    return dict(n=n, mean_out=round(float(a.mean())), med_out=round(float(np.median(a))),
                p75_out=round(float(np.percentile(a, 75))),
                pay_pct=round(100 * paid / n, 1), bust_pct=round(100 * bust / n, 1))

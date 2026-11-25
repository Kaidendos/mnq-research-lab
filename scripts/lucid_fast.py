"""Fast integrated account simulator — same rules, ~15x less work.

The slow version re-walked all ~78 bars of every session for every account start.
But signal TIMING never depends on account state; only position SIZE does. So the
candidate entry bars are precomputed once, and each account start only visits
signal bars plus the bars between entry and exit.

Rules identical to lucid_integrated (verified LucidPro 25K):
EOD trail on highest closing balance, floor locks at 25,100 once 26,100 clears,
withdraw only above 26,100 (+cushion), cap 1,000 then 1,500, 40% consistency,
3-day minimum. Levers: risk_frac (share of remaining room riskable per day) and
cushion (room kept above the buffer after each payout).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

START, MLL = 25_000.0, 1_000.0
BUFFER = START + MLL + 100.0
LOCK_FLOOR = START + 100.0
CONSISTENCY, MIN_DAYS = 0.40, 3
CAP_FIRST, CAP_AFTER = 1_000.0, 1_500.0
PV, FEE = 2.0, 1.22


def prep(df, ent_l, ent_s, win):
    """Precompute session boundaries and the candidate signal bars inside each."""
    hi = df["high"].to_numpy(float)
    lo = df["low"].to_numpy(float)
    cl = df["close"].to_numpy(float)
    atr = df["atr"].to_numpy(float)
    eth = df["eth"].to_numpy(float)
    el, es = np.asarray(ent_l, bool), np.asarray(ent_s, bool)
    both = el & es
    el, es = el & ~both, es & ~both
    ws, we = win
    ok = (eth >= ws) & (eth <= we) & (atr > 0) & np.isfinite(atr)
    sigs = np.where(el & ok, 1, np.where(es & ok, -1, 0)).astype(np.int8)

    dayid = df["_day"].to_numpy()
    starts = np.flatnonzero(np.r_[True, dayid[1:] != dayid[:-1]])
    ends = np.r_[starts[1:], len(df)]
    per = []
    for s, e in zip(starts, ends):
        idxs = np.flatnonzero(sigs[s:e]) + s
        per.append((s, e, idxs, sigs[idxs] if len(idxs) else np.empty(0, np.int8)))
    return dict(hi=hi, lo=lo, cl=cl, atr=atr, eth=eth, per=per,
                dates=df.index[starts])


def run_account(P, sl, tp, cap_day, base_budget, maxc, risk_frac, cushion,
                horizon_days=None, first=0):
    hi, lo, cl, atr, eth, per = P["hi"], P["lo"], P["cl"], P["atr"], P["eth"], P["per"]
    dates = P["dates"]
    t0 = dates[first]
    bal, floor, locked = START, START - MLL, False
    cyc_days, cyc_prof, cyc_big = 0, 0.0, 0.0
    payouts, withdrawn = 0, 0.0
    last_day = 0

    for k in range(first, len(per)):
        s, e, idxs, sides = per[k]
        # BUGFIX 2026-08-09: last_day used to be assigned ONLY inside the
        # horizon branch, so it held the day an account DIED. evaluate() then
        # dropped any run with days < 20 — silently deleting every account that
        # busted in its first 20 days, i.e. exactly the failures. That produced
        # 0-4% bust where the honest figure is ~95%. Always track elapsed days.
        d = (dates[k] - t0).days
        if horizon_days is not None and d > horizon_days:
            break
        last_day = d
        room = bal - floor
        if room <= 0:
            return True, payouts, withdrawn, last_day
        budget = min(base_budget, room * risk_frac)

        net, ntr, day_won = 0.0, 0, False
        j = 0
        while j < len(idxs) and ntr < 6 and not day_won:
            i = idxs[j]
            sd = int(sides[j])
            a = atr[i]
            su, tu = a * sl * PV, a * tp * PV
            n = min(maxc, int((budget + net) / su), int((cap_day - net) / tu))
            if n < 1:
                j += 1
                continue
            entry = cl[i]
            slp = entry - sd * a * sl
            tpp = entry + sd * a * tp
            px = None
            m = i + 1
            while m < e:
                if sd > 0:
                    if lo[m] <= slp: px = slp; break
                    if hi[m] >= tpp: px = tpp; break
                else:
                    if hi[m] >= slp: px = slp; break
                    if lo[m] <= tpp: px = tpp; break
                if eth[m] >= 16.0 or m == e - 1:
                    px = cl[m]; break
                m += 1
            if px is None:
                px = cl[e - 1]
                m = e - 1
            net += sd * (px - entry) * PV * n - FEE * n
            ntr += 1
            if net > 0:
                day_won = True
            while j < len(idxs) and idxs[j] <= m:
                j += 1

        if ntr == 0:
            continue
        bal += net
        cyc_days += 1
        cyc_prof += net
        cyc_big = max(cyc_big, net)

        if bal <= floor:
            return True, payouts, withdrawn, last_day
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

    return False, payouts, withdrawn, last_day


def evaluate(P, sl, tp, cap_day, base_budget, maxc, risk_frac, cushion,
             horizon=270, stride=10):
    """BUGFIX 2026-08-09: the old `days < 20` filter dropped accounts that BUSTED
    early, because `days` measures how long the account survived. That deleted the
    failures and reported ~0% bust. The filter must gate on how much DATA was
    available after the start index, never on the outcome."""
    dates = P["dates"]
    outs, bust, paid, zombie, n = [], 0, 0, 0, 0
    for k in range(0, len(P["per"]), stride):
        # need enough remaining history for the account to have had a fair run
        if (dates[-1] - dates[k]).days < 20:
            continue
        busted, pay, wd, days = run_account(P, sl, tp, cap_day, base_budget, maxc,
                                            risk_frac, cushion,
                                            horizon_days=horizon, first=k)
        outs.append(wd)
        bust += busted
        paid += pay >= 1
        # ZOMBIE: survived the floor but never withdrew a cent. Floor-aware sizing
        # shrinks positions to nothing near the floor, so an account can avoid a
        # technical bust while being economically dead. Counting only bust_pct
        # hides these entirely — which is how this harness once reported 0% bust.
        zombie += (not busted) and pay == 0
        n += 1
    if not n:
        return dict(n=0, mean_out=0, med_out=0, p75_out=0, pay_pct=0.0,
                    bust_pct=100.0, zombie_pct=100.0, dead_pct=100.0)
    a = np.array(outs)
    return dict(n=n, mean_out=round(float(a.mean())), med_out=round(float(np.median(a))),
                p75_out=round(float(np.percentile(a, 75))),
                pay_pct=round(100 * paid / n, 1), bust_pct=round(100 * bust / n, 1),
                zombie_pct=round(100 * zombie / n, 1),
                # the metric that cannot be gamed: busted OR never paid
                dead_pct=round(100 * (bust + zombie) / n, 1))

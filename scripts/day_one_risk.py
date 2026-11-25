"""What actually happens on day 1 — and in the first days — of a fresh account?

"Failing on the first day" has a precise meaning on this account: the balance
closing at or below the $24,000 floor, i.e. losing $1,000 in one session. Worth
separating from the thing people usually mean, which is "having a bad first day".

Measured directly by replaying a fresh $25,000 account starting on EVERY session
in the data and recording what day 1 did — no horizon, no withdrawal logic, just
the first session's realised P&L. Then the same for the first 5 and 20 sessions,
because the risk that matters is not really day 1, it is the drawdown before the
floor locks at $25,100.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import funded_search as fs
import funded_1yr as f1
import lucid_fast as LF

WIN, SL, TP, CAP, BUD, MC = (9.75, 11.0), 2.0, 3.0, 440, 300, 10
LONG_SIG, SHORT_SIG = "sr_round100_break", "vol_lw_stretch_short"

df = fs.load_enriched()
pl = f1.load_plugins(df)


def resolve(frame, name):
    e, _ = pl[name] if name in pl else fs.sig(df, name)
    return pd.Series(e).reindex(frame.index).fillna(False).to_numpy(bool)


def day_pnl(P, k, bal, floor):
    """Realised P&L of session k for an account at `bal` with floor `floor`."""
    hi, lo, cl, atr, eth, per = P["hi"], P["lo"], P["cl"], P["atr"], P["eth"], P["per"]
    s, e, idxs, sides = per[k]
    room = bal - floor
    if room <= 0:
        return 0.0, 0
    budget = min(BUD, room)
    net, ntr, j = 0.0, 0, 0
    while j < len(idxs) and ntr < 6:
        i, sd = idxs[j], int(sides[j])
        a, entry = atr[i], cl[i]
        n = min(MC, int((budget + net) / (a * SL * LF.PV)),
                int((CAP - net) / (a * TP * LF.PV)))
        if n < 1:
            j += 1
            continue
        stop_px, targ_px = entry - sd * a * SL, entry + sd * a * TP
        px, m = None, i + 1
        while m < e:
            if sd > 0:
                if lo[m] <= stop_px: px = stop_px; break
                if hi[m] >= targ_px: px = targ_px; break
            else:
                if hi[m] >= stop_px: px = stop_px; break
                if lo[m] <= targ_px: px = targ_px; break
            if eth[m] >= 16.0 or m == e - 1:
                px = cl[m]; break
            m += 1
        if px is None:
            px, m = cl[e - 1], e - 1
        net += sd * (px - entry) * LF.PV * n - LF.FEE * n
        ntr += 1
        while j < len(idxs) and idxs[j] <= m:
            j += 1
    return net, ntr


for label, frame in (("FULL 5 YEARS", df),
                     ("LAST 5 MONTHS (current regime)",
                      df[df.index >= df.index[-1] - pd.DateOffset(months=5)])):
    P = LF.prep(frame, resolve(frame, LONG_SIG), resolve(frame, SHORT_SIG), WIN)
    n_sess = len(P["per"])

    d1 = np.array([day_pnl(P, k, LF.START, LF.START - LF.MLL)[0]
                   for k in range(n_sess)])
    trades = np.array([day_pnl(P, k, LF.START, LF.START - LF.MLL)[1]
                       for k in range(n_sess)])

    print("=" * 92)
    print(f"DAY ONE — {label}   ({n_sess} possible start dates)")
    print("=" * 92)
    notrade = trades == 0
    print(f"  no trade at all on day 1      : {100*notrade.mean():>5.1f}%")
    print(f"  day 1 finishes UP             : {100*(d1 > 0).mean():>5.1f}%")
    print(f"  day 1 finishes DOWN           : {100*(d1 < 0).mean():>5.1f}%")
    print(f"  mean day-1 P&L                : ${d1.mean():>+8.0f}")
    print(f"  median day-1 P&L              : ${np.median(d1):>+8.0f}")
    print(f"  worst day 1 ever seen         : ${d1.min():>+8.0f}")
    print(f"  best  day 1 ever seen         : ${d1.max():>+8.0f}")
    print(f"\n  BUSTED on day 1 (lost $1,000) : "
          f"{int((d1 <= -LF.MLL).sum())}/{n_sess}  ({100*(d1 <= -LF.MLL).mean():.2f}%)")
    for thr in (200, 300, 400, 500, 750):
        print(f"    lost more than ${thr:<5}        : {100*(d1 <= -thr).mean():>5.1f}%")

    # first N sessions, running an actual account
    print(f"\n  CUMULATIVE RISK over the first sessions")
    for horizon in (1, 5, 10, 20):
        busts, lows = 0, []
        starts = range(0, max(n_sess - horizon, 1))
        for k0 in starts:
            bal, floor, locked = LF.START, LF.START - LF.MLL, False
            worst = 0.0
            for k in range(k0, min(k0 + horizon, n_sess)):
                net, ntr = day_pnl(P, k, bal, floor)
                if ntr == 0:
                    continue
                bal += net
                worst = min(worst, bal - LF.START)
                if bal <= floor:
                    busts += 1
                    break
                if not locked:
                    floor = max(floor, bal - LF.MLL)
                    if bal >= LF.BUFFER:
                        floor, locked = LF.LOCK_FLOOR, True
            lows.append(worst)
        lows = np.array(lows)
        print(f"    first {horizon:>2} sessions: bust {100*busts/len(list(starts)):>5.2f}%   "
              f"median worst drawdown ${np.median(lows):>+7.0f}   "
              f"5th pct ${np.percentile(lows, 5):>+7.0f}")
    print()

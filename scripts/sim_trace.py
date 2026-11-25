"""Single account replay, shared by every money-management script.

This logic was copy-pasted into speed_test / withdraw_policy / fixed_withdraw /
payout_timeline / foldin_* and had started to drift between copies, which is how
the earlier slippage test silently did nothing (a constant was patched in one
module while the replay read its own). One definition, imported everywhere.

Same rules as `lucid_fast.run_account` with one deliberate difference, kept
because every published number in CONTINUE.md was produced this way: there is no
`day_won` early stop, so a session runs until `max_trades` or the window ends.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import lucid_fast as LF

MAX_TRADES_DAY = 6
CLOSE_ETH = 16.0


def trace(P, start, cap, bud, sl=2.0, tp=3.0, rf=1.0, maxc=10,
          maxdays=365, max_trades=MAX_TRADES_DAY):
    """Replay one funded account from session index `start`.

    Returns fate ("PAID" / "STALLED" / "BUST"), total withdrawn, payout count,
    day of the FIRST payout, final balance and trade count.
    """
    hi, lo, cl, atr, eth, per = P["hi"], P["lo"], P["cl"], P["atr"], P["eth"], P["per"]
    dates = P["dates"]
    bal, floor, locked = LF.START, LF.START - LF.MLL, False
    cyc_d, cyc_p, cyc_b = 0, 0.0, 0.0
    wd, npay, first_day, ntr_tot = 0.0, 0, None, 0
    t0 = dates[start]

    def result(fate):
        return dict(fate=fate, wd=wd, pays=npay, first=first_day, final=bal,
                    trades=ntr_tot)

    for k in range(start, len(per)):
        d = (dates[k] - t0).days
        if d > maxdays:
            break
        s, e, idxs, sides = per[k]
        room = bal - floor
        if room <= 0:
            return result("BUST")
        budget = min(bud, room * rf)

        net, ntr, j = 0.0, 0, 0
        while j < len(idxs) and ntr < max_trades:
            i, sd = idxs[j], int(sides[j])
            a = atr[i]
            n = min(maxc, int((budget + net) / (a * sl * LF.PV)),
                    int((cap - net) / (a * tp * LF.PV)))
            if n < 1:
                j += 1
                continue
            entry = cl[i]
            stop_px, targ_px = entry - sd * a * sl, entry + sd * a * tp
            px, m = None, i + 1
            while m < e:
                if sd > 0:
                    if lo[m] <= stop_px: px = stop_px; break
                    if hi[m] >= targ_px: px = targ_px; break
                else:
                    if hi[m] >= stop_px: px = stop_px; break
                    if lo[m] <= targ_px: px = targ_px; break
                if eth[m] >= CLOSE_ETH or m == e - 1:
                    px = cl[m]; break
                m += 1
            if px is None:
                px, m = cl[e - 1], e - 1
            net += sd * (px - entry) * LF.PV * n - LF.FEE * n
            ntr += 1
            while j < len(idxs) and idxs[j] <= m:
                j += 1

        if ntr == 0:
            continue
        ntr_tot += ntr
        bal += net
        cyc_d += 1
        cyc_p += net
        cyc_b = max(cyc_b, net)

        if bal <= floor:
            return result("BUST")
        if not locked:
            floor = max(floor, bal - LF.MLL)
            if bal >= LF.BUFFER:
                floor, locked = LF.LOCK_FLOOR, True

        if bal > LF.BUFFER and cyc_d >= LF.MIN_DAYS and cyc_p > 0 \
                and cyc_b <= LF.CONSISTENCY * cyc_p:
            amt = min(bal - LF.BUFFER, LF.CAP_FIRST if npay == 0 else LF.CAP_AFTER)
            if amt >= 250:
                bal -= amt
                wd += amt
                npay += 1
                if first_day is None:
                    first_day = d
                cyc_d, cyc_p, cyc_b = 0, 0.0, 0.0

    return result("PAID" if npay else "STALLED")


def build(frame, longs, shorts, win, resolve):
    """OR the named long/short signals together and hand back a prepped struct."""
    el = np.zeros(len(frame), bool)
    es = np.zeros(len(frame), bool)
    for n in longs:
        el |= resolve(frame, n)
    for n in shorts:
        es |= resolve(frame, n)
    return LF.prep(frame, el, es, win)


def summarise(rows, extra=None):
    r = pd.DataFrame(rows)
    f = r["first"].dropna()
    out = dict(n=len(r),
               paid=round(100 * (r.fate == "PAID").mean(), 1),
               stalled=round(100 * (r.fate == "STALLED").mean(), 1),
               bust=round(100 * (r.fate == "BUST").mean(), 1),
               mean=round(r.wd.mean()), med=round(r.wd.median()),
               p75=round(r.wd.quantile(.75)),
               avg_pays=round(r.pays.mean(), 2),
               days=int(f.median()) if len(f) else -1)
    if extra:
        out.update(extra)
    return out

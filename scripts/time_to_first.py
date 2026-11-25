"""How long until the FIRST payout, starting today — as a cumulative probability.

"On average" is the wrong summary for this question and would mislead badly. The
median wait among accounts that GET paid is ~27-35 days, but a large fraction never
pay at all, and averaging only over the winners silently drops them. The honest form
is a cumulative curve: by day X, what fraction of ALL accounts have been paid?

Run for a fresh $25,000 account and for the user's real position ($500 down, floor
pinned at $24,000 because it trailed the $25,000 peak and never retreats), on both
the 4.5-year holdout and the recent 5 months — the latter being the regime an account
started today would actually begin in, though only ~23 independent starts exist there.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import funded_search as fs
import funded_1yr as f1
import lucid_fast as LF

WIN, SL, TP, CAP, BUD, MC = (9.75, 11.0), 2.0, 3.0, 440, 300, 10
LONG_SIG, SHORT_SIG = "sr_round100_break", "vol_lw_stretch_short"
MARKS = (14, 30, 60, 90, 120, 180, 270, 365)

df = fs.load_enriched()
pl = f1.load_plugins(df)
end = df.index[-1]
cut = end - pd.DateOffset(months=5)


def sig(frame, name):
    e, _ = pl[name] if name in pl else fs.sig(df, name)
    return pd.Series(e).reindex(frame.index).fillna(False).to_numpy(bool)


def first_payout_day(P, start, deficit, maxdays=365):
    hi, lo, cl, atr, eth, per = P["hi"], P["lo"], P["cl"], P["atr"], P["eth"], P["per"]
    dates = P["dates"]
    bal = LF.START - deficit
    floor, locked = LF.START - LF.MLL, False
    cyc_d, cyc_p, cyc_b = 0, 0.0, 0.0
    t0 = dates[start]
    for k in range(start, len(per)):
        d = (dates[k] - t0).days
        if d > maxdays:
            return None, "ALIVE"
        s, e, idxs, sides = per[k]
        room = bal - floor
        if room <= 0:
            return None, "BUST"
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
        if ntr == 0:
            continue
        bal += net
        cyc_d += 1; cyc_p += net; cyc_b = max(cyc_b, net)
        if bal <= floor:
            return None, "BUST"
        if not locked:
            floor = max(floor, bal - LF.MLL)
            if bal >= LF.BUFFER:
                floor, locked = LF.LOCK_FLOOR, True
        if bal > LF.BUFFER and cyc_d >= LF.MIN_DAYS and cyc_p > 0 \
                and cyc_b <= LF.CONSISTENCY * cyc_p:
            amt = min(bal - LF.BUFFER, LF.CAP_FIRST)
            if amt >= 250:
                return d, "PAID"
    return None, "ALIVE"


for wname, frame in (("HOLDOUT 2021-2026", df[df.index < cut]),
                     ("RECENT 5 MONTHS (the regime you'd start in)", df[df.index >= cut])):
    P = LF.prep(frame, sig(frame, LONG_SIG), sig(frame, SHORT_SIG), WIN)
    print("=" * 100)
    print(f"{wname}")
    print("=" * 100)
    print(f"  {'start':>10}" + "".join(f"{'d' + str(m):>8}" for m in MARKS)
          + f"{'never':>9}{'med(paid)':>11}")
    for deficit, label in ((0.0, "fresh"), (500.0, "-$500")):
        days, busts, n = [], 0, 0
        for k in range(0, len(P["per"]), 2):
            if len(P["per"]) - k < 20:
                continue
            d, fate = first_payout_day(P, k, deficit)
            n += 1
            busts += fate == "BUST"
            days.append(d)
        arr = np.array([d if d is not None else 10 ** 6 for d in days])
        paid = [d for d in days if d is not None]
        row = "".join(f"{100*(arr <= m).mean():>7.0f}%" for m in MARKS)
        med = int(np.median(paid)) if paid else -1
        print(f"  {label:>10}{row}{100*(arr > 365).mean():>8.0f}%{med:>11}")
    print()
print("  Each cell = % of ALL accounts that have received a first payout by that day.")
print("  'med(paid)' = median wait among the ones that DO get paid — the number that")
print("  is usually quoted, and the one that hides everybody who never gets there.")

"""Why do lucid_rules and lucid_fast disagree by ~70 points of bust rate?

Both claim the same verified LucidPro 25K rules. lucid_rules says 75-81% bust for
the top pairings; lucid_fast says 0-4%. One of them is wrong and the flattering
one is under suspicion.

Strategy: feed BOTH the identical daily P&L series with matched settings, then walk
forward account-by-account to find the first point where they diverge.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import funded_search as fs
import funded_1yr as f1
import lucid_rules as LR
import lucid_fast as LF
from funded_longshort import replay_2s

LONG, SHORT = "sr_round100_break", "vol_lw_stretch_short"
SL, TP, WIN, CAP, BUD, MAXC = 2.0, 1.5, (9.75, 15.5), 440, 300, 10

df = fs.load_enriched()
pl = f1.load_plugins(df)
g = lambda n: pd.Series((pl[n] if n in pl else fs.sig(df, n))[0]).reindex(df.index).fillna(False)
L, S = g(LONG), g(SHORT)

print("=" * 84)
print("STEP 1 — do they even see the same trades?")
print("=" * 84)
# lucid_rules path: replay_2s produces a daily series, then simulate() runs the account
daily, tt, ww, nl, ns = replay_2s(df, L, S, SL, TP, WIN, None, CAP, BUD, maxc=MAXC)
print(f"  replay_2s (fixed budget)     : {tt} trades, {len(daily)} active days, "
      f"net ${daily.sum():,.0f}")

# lucid_fast path: sizing depends on account state, so trades differ by construction
P = LF.prep(df, L.to_numpy(bool), S.to_numpy(bool), WIN)
busted, pays, wd, days = LF.run_account(P, SL, TP, CAP, BUD, MAXC,
                                        risk_frac=1.0, cushion=0.0, first=0)
print(f"  lucid_fast single run        : busted={busted}, payouts={pays}, "
      f"withdrawn=${wd:,.0f}, days={days}")
print("  NOTE: lucid_fast sizes off remaining room, so its trade sequence is NOT")
print("  the same as replay_2s's fixed-budget sequence. That alone can move bust.")

print("\n" + "=" * 84)
print("STEP 2 — matched settings: same min_withdraw, same stride, same horizon")
print("=" * 84)
print(f"  {'min_withdraw':<14}{'stride':>8}{'horizon':>9}{'LR bust%':>11}{'LF bust%':>11}"
      f"{'LR mean':>10}{'LF mean':>10}")
for mw in (250, 1000):
    for stride in (10,):
        for hz in (365,):
            r = LR.rolling_starts(daily, horizon_days=hz, min_withdraw=mw)
            lr_bust = 100 * r.busted.mean() if len(r) else -1
            lr_mean = r.withdrawn.mean() if len(r) else -1
            # lucid_fast: force the same withdrawal floor by using cushion=0 and
            # comparing only when its internal >=250 gate matches
            m = LF.evaluate(P, SL, TP, CAP, BUD, MAXC, 1.0, 0.0,
                            horizon=hz, stride=stride)
            print(f"  {mw:<14}{stride:>8}{hz:>9}{lr_bust:>10.1f}%{m['bust_pct']:>10.1f}%"
                  f"{lr_mean:>10,.0f}{m['mean_out']:>10,.0f}")

print("\n" + "=" * 84)
print("STEP 3 — feed lucid_fast's OWN daily series into lucid_rules")
print("=" * 84)
print("  If the bust rates agree once the trade sequence is identical, the gap is")
print("  caused by floor-aware SIZING (a real effect). If they still disagree, one")
print("  of the two account-rule implementations has a bug.")

# reconstruct lucid_fast's realised daily series by running it with risk_frac=1.0
# from day 0 and recording per-day P&L
hi, lo, cl = P["hi"], P["lo"], P["cl"]
atr, eth, per = P["atr"], P["eth"], P["per"]
bal, floor, locked = LF.START, LF.START - LF.MLL, False
rows = []
for k in range(len(per)):
    s, e, idxs, sides = per[k]
    room = bal - floor
    if room <= 0:
        break
    budget = min(BUD, room * 1.0)
    net, ntr, day_won, j = 0.0, 0, False, 0
    while j < len(idxs) and ntr < 6 and not day_won:
        i, sd = idxs[j], int(sides[j])
        a = atr[i]
        n = min(MAXC, int((budget + net) / (a * SL * LF.PV)),
                int((CAP - net) / (a * TP * LF.PV)))
        if n < 1:
            j += 1
            continue
        entry = cl[i]
        slp, tpp = entry - sd * a * SL, entry + sd * a * TP
        px, m2 = None, i + 1
        while m2 < e:
            if sd > 0:
                if lo[m2] <= slp: px = slp; break
                if hi[m2] >= tpp: px = tpp; break
            else:
                if hi[m2] >= slp: px = slp; break
                if lo[m2] <= tpp: px = tpp; break
            if eth[m2] >= 16.0 or m2 == e - 1:
                px = cl[m2]; break
            m2 += 1
        if px is None:
            px, m2 = cl[e - 1], e - 1
        net += sd * (px - entry) * LF.PV * n - LF.FEE * n
        ntr += 1
        if net > 0:
            day_won = True
        while j < len(idxs) and idxs[j] <= m2:
            j += 1
    if ntr == 0:
        continue
    bal += net
    rows.append((P["dates"][k], net))
    if bal <= floor:
        break
    if not locked:
        floor = max(floor, bal - LF.MLL)
        if bal >= LF.BUFFER:
            floor, locked = LF.LOCK_FLOOR, True

lf_daily = pd.Series(dict(rows)).sort_index()
print(f"  lucid_fast realised series: {len(lf_daily)} active days, "
      f"net ${lf_daily.sum():,.0f}   (vs replay_2s {len(daily)} days, ${daily.sum():,.0f})")
r2 = LR.rolling_starts(lf_daily, horizon_days=365, min_withdraw=250)
print(f"  lucid_rules on THAT series : bust {100*r2.busted.mean():.1f}%, "
      f"mean withdrawn ${r2.withdrawn.mean():,.0f}")
m2 = LF.evaluate(P, SL, TP, CAP, BUD, MAXC, 1.0, 0.0, horizon=365, stride=10)
print(f"  lucid_fast on same config  : bust {m2['bust_pct']:.1f}%, "
      f"mean withdrawn ${m2['mean_out']:,.0f}")

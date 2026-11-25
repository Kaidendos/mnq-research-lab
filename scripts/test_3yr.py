"""The strategy over the last 3 years, end to end.

Window: 2023-08-09 -> 2026-08-07, i.e. three years back from today.

⚠ NOT a fresh out-of-sample test. This window overlaps data the strategy was
already selected against — the pairing was chosen on a 5-year sweep and the last
5 months of this window are the only part never used for selection. Read it as
"how has it behaved recently", not as independent confirmation.

Reported at both levels, because they answer different questions:
  TRADE level   — is there an edge at all, against the clean shuffled control
  ACCOUNT level — does that edge survive the LucidPro rules into actual payouts
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import funded_search as fs
import funded_1yr as f1
import lucid_fast as LF
from clean_control import build, points, shuffled

WIN, SL, TP, CAP, BUD, MC = (9.75, 11.0), 2.0, 3.0, 440, 300, 10
LONG_SIG, SHORT_SIG = "sr_round100_break", "vol_lw_stretch_short"
SEEDS = range(20)

df = fs.load_enriched()
pl = f1.load_plugins(df)
start3 = df.index[-1] - pd.DateOffset(years=3)
w3 = df[df.index >= start3]
print(f"window: {w3.index[0].date()} -> {w3.index[-1].date()}  "
      f"({len(w3):,} bars, {w3['_day'].nunique()} sessions)\n")


def resolve(frame, name):
    e, _ = pl[name] if name in pl else fs.sig(df, name)
    return pd.Series(e).reindex(frame.index).fillna(False).to_numpy(bool)


# ── 1. TRADE LEVEL vs the clean control ──
print("=" * 96)
print("1. TRADE LEVEL — points per trade vs the clean shuffled control")
print("=" * 96)
for label, frame in [("LAST 3 YEARS", w3)] + [
        (f"  {y}", df[df.index.year == y]) for y in (2024, 2025, 2026)]:
    starts, ends, ok, sl_, ss_ = build(frame)
    ppt, n, w, tot = points(frame, sl_ & ok, ss_ & ok)
    ctl = []
    for s in SEEDS:
        rng = np.random.default_rng(s)
        el, es = shuffled(starts, ends, ok, sl_, ss_, rng, False)
        ctl.append(points(frame, el, es)[0])
    ctl = np.array(ctl)
    print(f"  {label:<16} {n:>5} trades  win {w:>5.1f}%  real {ppt:>+7.2f} "
          f"vs ctl {np.median(ctl):>+7.2f}  edge {ppt-np.median(ctl):>+7.2f}  "
          f"beaten by {int((ctl >= ppt).sum())}/{len(ctl)}")


# ── 2. ACCOUNT LEVEL ──
def trace(P, start, maxdays=365):
    hi, lo, cl, atr, eth, per = P["hi"], P["lo"], P["cl"], P["atr"], P["eth"], P["per"]
    dates = P["dates"]
    bal, floor, locked = LF.START, LF.START - LF.MLL, False
    cyc_d, cyc_p, cyc_b = 0, 0.0, 0.0
    pays, worst = [], 0.0
    t0 = dates[start]
    for k in range(start, len(per)):
        d = (dates[k] - t0).days
        if d > maxdays:
            break
        s, e, idxs, sides = per[k]
        room = bal - floor
        if room <= 0:
            return "BUST", pays, worst
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
        worst = min(worst, bal - LF.START)
        cyc_d += 1; cyc_p += net; cyc_b = max(cyc_b, net)
        if bal <= floor:
            return "BUST", pays, worst
        if not locked:
            floor = max(floor, bal - LF.MLL)
            if bal >= LF.BUFFER:
                floor, locked = LF.LOCK_FLOOR, True
        if bal > LF.BUFFER and cyc_d >= LF.MIN_DAYS and cyc_p > 0 \
                and cyc_b <= LF.CONSISTENCY * cyc_p:
            amt = min(bal - LF.BUFFER, LF.CAP_FIRST if not pays else LF.CAP_AFTER)
            if amt >= 250:
                bal -= amt
                pays.append((d, amt))
                cyc_d, cyc_p, cyc_b = 0, 0.0, 0.0
    return ("PAID" if pays else "STALLED"), pays, worst


P = LF.prep(w3, resolve(w3, LONG_SIG), resolve(w3, SHORT_SIG), WIN)
res = [trace(P, k) for k in range(0, len(P["per"]), 2)
       if len(P["per"]) - k >= 20]
n = len(res)
totals = np.array([sum(a for _, a in p) for _, p, _ in res])
worsts = np.array([w for _, _, w in res])
payers = [p for f, p, _ in res if p]

print("\n" + "=" * 96)
print(f"2. ACCOUNT LEVEL — {n} accounts started across the 3 years, 1-yr horizon each")
print(f"   cap ${CAP} / budget ${BUD}, fresh $25,000 start")
print("=" * 96)
print(f"  PAID    {100*len(payers)/n:>5.1f}%")
print(f"  STALLED {100*sum(f == 'STALLED' for f, _, _ in res)/n:>5.1f}%")
print(f"  BUST    {100*sum(f == 'BUST' for f, _, _ in res)/n:>5.1f}%")
print(f"\n  withdrawn in a year, ALL accounts:")
for q in (25, 50, 75, 90):
    print(f"    {q:>3}th pct : ${np.percentile(totals, q):>8,.0f}")
print(f"    {'mean':>8} : ${totals.mean():>8,.0f}")
print(f"    earning $0 : {100*(totals == 0).mean():.1f}%")
if payers:
    fd = np.array([p[0][0] for p in payers])
    fa = np.array([p[0][1] for p in payers])
    print(f"\n  first payout: median day {int(np.median(fd))}, "
          f"median amount ${np.median(fa):,.0f}")
    print(f"  median payouts per year among payers: "
          f"{int(np.median([len(p) for p in payers]))}")
print(f"\n  worst drawdown from $25,000 during the year:")
print(f"    median ${np.median(worsts):>+8,.0f}   "
      f"25th pct ${np.percentile(worsts, 25):>+8,.0f}   "
      f"5th pct ${np.percentile(worsts, 5):>+8,.0f}")

# ── 3. STARTING DOWN $500 in this window ──
print("\n" + "=" * 96)
print("3. THE SAME 3 YEARS, STARTING $500 DOWN (floor still $24,000)")
print("=" * 96)
import starting_down as SD
res2 = [SD.run(P, k, 500, BUD) for k in range(0, len(P["per"]), 2)
        if len(P["per"]) - k >= 20]
r2 = pd.DataFrame(res2)
f2 = r2["first"].dropna()
print(f"  PAID {100*(r2.fate == 'PAID').mean():>5.1f}%   "
      f"STALLED {100*(r2.fate == 'STALLED').mean():>5.1f}%   "
      f"BUST {100*(r2.fate == 'BUST').mean():>5.1f}%")
print(f"  mean ${r2.wd.mean():>7,.0f}   median ${r2.wd.median():>7,.0f}   "
      f"first payout median day {int(f2.median()) if len(f2) else -1}")

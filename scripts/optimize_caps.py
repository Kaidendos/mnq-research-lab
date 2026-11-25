"""Optimise the daily PROFIT CAP and daily LOSS BUDGET for the chosen strategy.

These are the two money-management knobs, and there is a trap in the profit cap:
$440 is exactly 40% of the $1,100 buffer, i.e. it is calibrated to the consistency
rule (biggest green day <= 40% of cycle profit). Raise the cap and a single big day
can block your OWN payout. This measures that directly instead of assuming it.

Also instruments WHY a payout does not happen:
  below_buffer  — balance never got above $26,100 + $250
  consistency   — balance was high enough but one day was too large a share
  too_few_days  — fewer than the 3-day minimum in the cycle
"""
from __future__ import annotations

import itertools

import numpy as np
import pandas as pd

import funded_search as fs
import funded_1yr as f1
import lucid_fast as LF

LONG, SHORT = "sr_round100_break", "vol_lw_stretch_short"
WIN, SL, TP, RF = (9.75, 11.0), 2.0, 3.0, 1.0

CAPS = (250, 300, 350, 440, 550, 700, 900, 1200)
BUDGETS = (150, 200, 250, 300, 400, 500)
MAXCS = (5, 10, 15)

df = fs.load_enriched()
pl = f1.load_plugins(df)
g = lambda n: pd.Series((pl[n] if n in pl else fs.sig(df, n))[0]).reindex(df.index).fillna(False).to_numpy(bool)
end = df.index[-1]
w5 = end - pd.DateOffset(months=5)
hold = df[df.index < w5]
sel = df[df.index >= w5]
EL_h, ES_h = g(LONG)[:len(hold)], g(SHORT)[:len(hold)]
P_h = LF.prep(hold, EL_h, ES_h, WIN)
n_sel = len(sel)
P_s = LF.prep(sel, g(LONG)[-n_sel:], g(SHORT)[-n_sel:], WIN)


def run(P, cap, bud, mc, maxdays=365, stride=4):
    """Returns per-account outcomes plus the reason payouts were blocked."""
    hi, lo, cl, atr, eth, per = P["hi"], P["lo"], P["cl"], P["atr"], P["eth"], P["per"]
    dates = P["dates"]
    outs, paid, bust, n = [], 0, 0, 0
    blocked_cons, blocked_buf, first_days = 0, 0, []
    for start in range(0, len(per), stride):
        if len(per) - start < 30:
            continue
        bal, floor, locked = LF.START, LF.START - LF.MLL, False
        cyc_d, cyc_p, cyc_b = 0, 0.0, 0.0
        wd, np_, fd = 0.0, 0, None
        t0 = dates[start]
        hit_cons, hit_buf = False, False
        for k in range(start, len(per)):
            d = (dates[k] - t0).days
            if d > maxdays:
                break
            s, e, idxs, sides = per[k]
            room = bal - floor
            if room <= 0:
                bust += 1; break
            budget = min(bud, room * RF)
            net, ntr, j = 0.0, 0, 0
            while j < len(idxs) and ntr < 6:
                i, sd = idxs[j], int(sides[j])
                a = atr[i]
                cts = min(mc, int((budget + net) / (a * SL * LF.PV)),
                          int((cap - net) / (a * TP * LF.PV)))
                if cts < 1:
                    j += 1; continue
                entry = cl[i]
                slp, tpp = entry - sd * a * SL, entry + sd * a * TP
                px, m = None, i + 1
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
                    px, m = cl[e - 1], e - 1
                net += sd * (px - entry) * LF.PV * cts - LF.FEE * cts
                ntr += 1
                while j < len(idxs) and idxs[j] <= m:
                    j += 1
            if ntr == 0:
                continue
            bal += net
            cyc_d += 1; cyc_p += net; cyc_b = max(cyc_b, net)
            if bal <= floor:
                bust += 1; break
            if not locked:
                floor = max(floor, bal - LF.MLL)
                if bal >= LF.BUFFER:
                    floor, locked = LF.LOCK_FLOOR, True
            if bal > LF.BUFFER and cyc_d >= LF.MIN_DAYS and cyc_p > 0:
                if cyc_b <= LF.CONSISTENCY * cyc_p:
                    amt = min(bal - LF.BUFFER, LF.CAP_FIRST if np_ == 0 else LF.CAP_AFTER)
                    if amt >= 250:
                        bal -= amt; wd += amt; np_ += 1
                        if fd is None:
                            fd = d
                        cyc_d, cyc_p, cyc_b = 0, 0.0, 0.0
                    else:
                        hit_buf = True
                else:
                    hit_cons = True
            elif bal <= LF.BUFFER:
                hit_buf = True
        outs.append(wd)
        paid += np_ >= 1
        if np_ == 0:
            blocked_cons += hit_cons
            blocked_buf += hit_buf and not hit_cons
        if fd is not None:
            first_days.append(fd)
        n += 1
    if not n:
        return None
    a = np.array(outs)
    return dict(n=n, mean=round(float(a.mean())), med=round(float(np.median(a))),
                pay=round(100 * paid / n, 1), dead=round(100 * (n - paid) / n, 1),
                bust=round(100 * bust / n, 1),
                med_days=int(np.median(first_days)) if first_days else -1,
                blk_cons=round(100 * blocked_cons / n, 1),
                blk_buf=round(100 * blocked_buf / n, 1))


rows = []
for cap, bud, mc in itertools.product(CAPS, BUDGETS, MAXCS):
    h = run(P_h, cap, bud, mc)
    if not h:
        continue
    s = run(P_s, cap, bud, mc, stride=2)
    rows.append(dict(cap=cap, budget=bud, maxc=mc,
                     h_mean=h["mean"], h_med=h["med"], h_pay=h["pay"],
                     h_dead=h["dead"], h_bust=h["bust"], h_days=h["med_days"],
                     blk_cons=h["blk_cons"], blk_buf=h["blk_buf"],
                     s_mean=s["mean"] if s else 0, s_pay=s["pay"] if s else 0))
out = pd.DataFrame(rows)
out.to_csv("optimize_caps.csv", index=False)
pd.set_option("display.width", 210)

C = ["cap", "budget", "maxc", "h_mean", "h_med", "h_pay", "h_dead", "h_bust",
     "h_days", "blk_cons", "blk_buf", "s_mean", "s_pay"]
print("=" * 150)
print("CURRENT SETTINGS (cap 440 / budget 300 / 10 ct)")
print("=" * 150)
print(out[(out.cap == 440) & (out.budget == 300) & (out.maxc == 10)][C].to_string(index=False))

print("\n" + "=" * 150)
print("TOP 15 BY HOLDOUT MEAN WITHDRAWN")
print("=" * 150)
print(out.sort_values("h_mean", ascending=False)[C].head(15).to_string(index=False))

print("\n" + "=" * 150)
print("TOP 15 BY PAYOUT RATE")
print("=" * 150)
print(out.sort_values("h_pay", ascending=False)[C].head(15).to_string(index=False))

print("\n" + "=" * 150)
print("DOES A HIGHER CAP BREAK THE 40% CONSISTENCY RULE? (blk_cons = % blocked by it)")
print("=" * 150)
print(out.groupby("cap").agg(n=("h_mean", "size"), mean=("h_mean", "mean"),
                             pay=("h_pay", "mean"), dead=("h_dead", "mean"),
                             blocked_by_consistency=("blk_cons", "mean"),
                             days=("h_days", "median")).round(1).to_string())

print("\n" + "=" * 150)
print("EFFECT OF THE DAILY LOSS BUDGET")
print("=" * 150)
print(out.groupby("budget").agg(n=("h_mean", "size"), mean=("h_mean", "mean"),
                                pay=("h_pay", "mean"), dead=("h_dead", "mean"),
                                bust=("h_bust", "mean"),
                                days=("h_days", "median")).round(1).to_string())

print("\n" + "=" * 150)
print("EFFECT OF MAX CONTRACTS")
print("=" * 150)
print(out.groupby("maxc").agg(n=("h_mean", "size"), mean=("h_mean", "mean"),
                              pay=("h_pay", "mean"), dead=("h_dead", "mean"),
                              bust=("h_bust", "mean")).round(1).to_string())

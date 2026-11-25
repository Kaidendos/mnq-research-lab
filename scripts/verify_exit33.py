"""Paired test of the one exit variant that survived: SL 3.0 / TP 3.0.

`exit_account.py` found exactly 1 of 40 combos beating the incumbent on holdout
mean AND median with bust no worse AND not worse in the recent window:

    SL 3.0 / TP 3.0, cap $440, budget $400
      hold   paid 61.5% (vs 56.0)  bust 2.1% (=)  mean $2,716 (vs $2,352)
             median $1,230 (vs $334)  29 days (vs 27)
      recent mean $452 (vs $324)

Note this contradicts the POINTS sweep, which wanted TP 5.0. It shouldn't be
surprising: the daily cap sizes positions by `(cap - net)/(ATR × TP × $2)`, so a
wider target shrinks the position that pays for it. Points and dollars optimise
differently, and dollars is what matters.

But 1-of-40 is a best-of-grid pick, and three such picks have already failed today.
So the same paired toggle is applied here: change ONLY the bracket, hold window,
cap, budget and signal pair fixed, across 81 cells. A real exit improvement should
win nearly everywhere, because an exit is not tuned to any particular signal.

Bar to clear: `%K 14->21` won 96.2% of 840 matched configs and was trusted.
`wy_lps_long` won 67% and was rejected. The fold-in won 47% and was retracted.
"""
from __future__ import annotations

import itertools

import numpy as np
import pandas as pd

import funded_search as fs
import funded_1yr as f1
import lucid_fast as LF
import sim_trace as ST

BASE_BRACKET = (2.0, 3.0)
NEW_BRACKET = (3.0, 3.0)
WINDOWS = ((9.75, 11.0), (9.75, 12.0), (9.75, 15.5))
CAPS = (440, 250, 600)
BUDGETS = (300, 400, 500)
PAIRS = [("sr_round100_break", "vol_lw_stretch_short"),
         ("wy_lps_long", "vol_lw_stretch_short"),
         ("sr_round100_break", "lw_gsv_short")]

df = fs.load_enriched()
pl = f1.load_plugins(df)
end = df.index[-1]
hold = df[df.index < end - pd.DateOffset(months=5)]


def resolve(frame, name):
    e, _ = pl[name] if name in pl else fs.sig(df, name)
    return pd.Series(e).reindex(frame.index).fillna(False).to_numpy(bool)


PREP = {}
for (ln, sn), win in itertools.product(PAIRS, WINDOWS):
    PREP[(ln, sn, win)] = LF.prep(hold, resolve(hold, ln), resolve(hold, sn), win)


def score(key, sl, tp, cap, bud):
    P = PREP[key]
    res = [ST.trace(P, k, cap, bud, sl=sl, tp=tp)
           for k in range(0, len(P["per"]), 4) if len(P["per"]) - k >= 20]
    return ST.summarise(res)


rows = []
for (ln, sn), win, cap, bud in itertools.product(PAIRS, WINDOWS, CAPS, BUDGETS):
    key = (ln, sn, win)
    a = score(key, *BASE_BRACKET, cap, bud)
    b = score(key, *NEW_BRACKET, cap, bud)
    rows.append(dict(long=ln.replace("_long", ""), short=sn.replace("_short", ""),
                     win=f"{win[1]}", cap=cap, bud=bud,
                     base_mean=a["mean"], new_mean=b["mean"],
                     base_med=a["med"], new_med=b["med"],
                     base_paid=a["paid"], new_paid=b["paid"],
                     base_bust=a["bust"], new_bust=b["bust"],
                     base_days=a["days"], new_days=b["days"]))
    print(f"  {ln[:14]}+{sn[:14]} win{win[1]} cap{cap} bud{bud}", flush=True)

g = pd.DataFrame(rows)
g["d_mean"] = g.new_mean - g.base_mean
g["d_med"] = g.new_med - g.base_med
g["d_bust"] = g.new_bust - g.base_bust
g.to_csv("verify_exit33.csv", index=False)
pd.set_option("display.width", 210)

print("\n" + "=" * 130)
print(f"PAIRED: SL{NEW_BRACKET[0]}/TP{NEW_BRACKET[1]} vs "
      f"SL{BASE_BRACKET[0]}/TP{BASE_BRACKET[1]} across {len(g)} matched cells")
print("=" * 130)
print(f"  wins on mean   : {(g.d_mean > 0).sum():>3}/{len(g)}  "
      f"({100*(g.d_mean > 0).mean():.0f}%)   median delta ${g.d_mean.median():+,.0f}")
print(f"  wins on median : {(g.d_med > 0).sum():>3}/{len(g)}  "
      f"({100*(g.d_med > 0).mean():.0f}%)   median delta ${g.d_med.median():+,.0f}")
print(f"  wins on paid%  : {(g.new_paid > g.base_paid).sum():>3}/{len(g)}")
print(f"  bust WORSE in  : {(g.d_bust > 0).sum():>3}/{len(g)}  "
      f"median delta {g.d_bust.median():+.1f} pts")
print(f"  slower (days)  : {(g.new_days > g.base_days).sum():>3}/{len(g)}")

print("\n  BY SIGNAL PAIR (an exit improvement should hold for pairs it was not found on)")
for (l, s), sub in g.groupby(["long", "short"]):
    print(f"    {l:<28}+{s:<22} mean wins {(sub.d_mean > 0).sum():>2}/{len(sub)}"
          f"   median delta ${sub.d_mean.median():+,.0f}")
print("\n  BY WINDOW")
for w, sub in g.groupby("win"):
    print(f"    to {w:<6} mean wins {(sub.d_mean > 0).sum():>2}/{len(sub)}"
          f"   median delta ${sub.d_mean.median():+,.0f}")
print("\n  BY BUDGET (the finding was budget-$400 specific — does it generalise?)")
for b, sub in g.groupby("bud"):
    print(f"    ${b} mean wins {(sub.d_mean > 0).sum():>2}/{len(sub)}"
          f"   median delta ${sub.d_mean.median():+,.0f}")

print("\n" + "=" * 130)
print("FULL GRID")
print("=" * 130)
print(g.to_string(index=False))

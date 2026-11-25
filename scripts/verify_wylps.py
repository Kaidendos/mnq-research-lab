"""Paired verification of the one candidate that survived the new-trader sweep.

Of 20 candidate additions/replacements from the 9 new methodologies, exactly ZERO
cleared the strict bar (higher holdout mean AND bust no worse). One near-miss:

    add_L wy_lps_long   (Wyckoff "last point of support" OR'd into the base long)
      cap 440 holdout : paid 57.7 vs 56.0, mean $2,532 vs $2,352, med $407 vs $334,
                        26d vs 27d  —  but BUST 4.8% vs 2.1%
      cap 440 recent  : mean $596 vs $324

It is the only candidate that improves BOTH the 4.5-year holdout median and the
recent 5-month window. That could easily be a best-of-20 selection artifact, and
one bracket at n=23 recent accounts proves nothing.

THREE TESTS, all immune to the way it was found:
  1. PAIRED ACROSS THE GRID — same 36 brackets, only the extra signal toggled.
     Multiple comparisons cannot help a config that has to win everywhere.
  2. PER YEAR — an edge concentrated in one year is a regime artifact.
  3. SLIPPAGE — an earlier candidate flipped negative at 1 tick.
"""
from __future__ import annotations

import itertools

import numpy as np
import pandas as pd

import funded_search as fs
import funded_1yr as f1
import lucid_fast as LF
import sim_trace as ST

BASE_L, BASE_S = "sr_round100_break", "vol_lw_stretch_short"
EXTRA = "wy_lps_long"

WINS = ((9.75, 11.0), (9.75, 12.0), (9.75, 15.5))
BRACKETS = ((2.0, 3.0), (2.0, 1.5), (1.5, 2.0), (1.0, 1.5))
SIZES = ((440, 300), (250, 400), (440, 400))

df = fs.load_enriched()
pl = f1.load_plugins(df)
end = df.index[-1]
hold = df[df.index < end - pd.DateOffset(months=5)]


def resolve(frame, name):
    e, _ = pl[name] if name in pl else fs.sig(df, name)
    return pd.Series(e).reindex(frame.index).fillna(False).to_numpy(bool)


def run(frame, longs, win, sl, tp, cap, bud, slip_ticks=0.0):
    P = ST.build(frame, longs, [BASE_S], win, resolve)
    if slip_ticks:
        # a tick is 0.25 pts on MNQ at $2/pt -> $0.50 per tick per contract per side
        LF.FEE_SAVE = getattr(LF, "FEE_SAVE", LF.FEE)
        LF.FEE = LF.FEE_SAVE + slip_ticks * 0.25 * LF.PV * 2
    else:
        LF.FEE = getattr(LF, "FEE_SAVE", LF.FEE)
    res = [ST.trace(P, k, cap, bud, sl=sl, tp=tp)
           for k in range(0, len(P["per"]), 4) if len(P["per"]) - k >= 20]
    return ST.summarise(res)


# ── 1. PAIRED ACROSS THE GRID ──
rows = []
for win, (sl, tp), (cap, bud) in itertools.product(WINS, BRACKETS, SIZES):
    a = run(hold, [BASE_L], win, sl, tp, cap, bud)
    b = run(hold, [BASE_L, EXTRA], win, sl, tp, cap, bud)
    rows.append(dict(win=f"{win[0]}-{win[1]}", sl=sl, tp=tp, cap=cap, bud=bud,
                     base_mean=a["mean"], add_mean=b["mean"],
                     base_med=a["med"], add_med=b["med"],
                     base_paid=a["paid"], add_paid=b["paid"],
                     base_bust=a["bust"], add_bust=b["bust"]))
    print(f"  grid {win} {sl}/{tp} cap{cap}", flush=True)

g = pd.DataFrame(rows)
g["d_mean"] = g.add_mean - g.base_mean
g["d_med"] = g.add_med - g.base_med
g["d_bust"] = g.add_bust - g.base_bust
g.to_csv("verify_wylps_grid.csv", index=False)
pd.set_option("display.width", 200)
print("\n" + "=" * 120)
print(f"1. PAIRED ACROSS {len(g)} MATCHED CONFIGS — only `{EXTRA}` toggled")
print("=" * 120)
print(f"  wins on mean   : {(g.d_mean > 0).sum():>3}/{len(g)}  "
      f"({100*(g.d_mean > 0).mean():.0f}%)   median delta ${g.d_mean.median():+,.0f}")
print(f"  wins on median : {(g.d_med > 0).sum():>3}/{len(g)}  "
      f"({100*(g.d_med > 0).mean():.0f}%)   median delta ${g.d_med.median():+,.0f}")
print(f"  wins on paid%  : {(g.add_paid > g.base_paid).sum():>3}/{len(g)}")
print(f"  bust WORSE in  : {(g.d_bust > 0).sum():>3}/{len(g)}  "
      f"median delta {g.d_bust.median():+.1f} pts")
print("\n" + g.to_string(index=False))

# ── 2. PER YEAR ──
print("\n" + "=" * 120)
print("2. PER YEAR (cap 440 / bud 300, 9:45-11:00, SL2/TP3, 180-day horizon)")
print("=" * 120)
yr_rows = []
for y in sorted(df.index.year.unique()):
    sub = df[df.index.year == y]
    if len(sub) < 4000:
        continue
    a = run(sub, [BASE_L], (9.75, 11.0), 2.0, 3.0, 440, 300)
    b = run(sub, [BASE_L, EXTRA], (9.75, 11.0), 2.0, 3.0, 440, 300)
    yr_rows.append(dict(year=y, n=a["n"],
                        base_mean=a["mean"], add_mean=b["mean"],
                        base_paid=a["paid"], add_paid=b["paid"],
                        base_bust=a["bust"], add_bust=b["bust"]))
yr = pd.DataFrame(yr_rows)
yr["d_mean"] = yr.add_mean - yr.base_mean
print(yr.to_string(index=False))
print(f"\n  years where the addition helps: {(yr.d_mean > 0).sum()}/{len(yr)}")

# ── 3. SLIPPAGE ──
print("\n" + "=" * 120)
print("3. SLIPPAGE (cap 440, holdout) — ticks per side charged on top of fees")
print("=" * 120)
sl_rows = []
for ticks in (0, 1, 2, 4):
    a = run(hold, [BASE_L], (9.75, 11.0), 2.0, 3.0, 440, 300, slip_ticks=ticks)
    b = run(hold, [BASE_L, EXTRA], (9.75, 11.0), 2.0, 3.0, 440, 300, slip_ticks=ticks)
    sl_rows.append(dict(ticks=ticks, base_mean=a["mean"], add_mean=b["mean"],
                        base_paid=a["paid"], add_paid=b["paid"],
                        base_bust=a["bust"], add_bust=b["bust"]))
LF.FEE = getattr(LF, "FEE_SAVE", LF.FEE)
print(pd.DataFrame(sl_rows).to_string(index=False))

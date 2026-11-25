"""Harvest tp_*.csv — the 100 named-trader pairings that were left in flight.

The question this answers: does Mark Fisher's ACD weekly pivot (mf_wkpiv_long),
which beat the incumbent long by 43% on a standalone basis, also beat it when
PAIRED with the Larry Williams stretch short?

Standalone ranking and paired ranking are different questions. A family that is
strong alone can be redundant in a pair (fires in the same conditions as its
partner, so drawdowns stack instead of offsetting).

Ranked on holdout, never on selection. sel_* columns are shown only so the
selection/holdout gap is visible.
"""
from __future__ import annotations

import glob

import pandas as pd

df = pd.concat([pd.read_csv(f) for f in sorted(glob.glob("tp_*.csv"))],
               ignore_index=True)
print(f"{len(df)} rows, {df.long.nunique()} longs x {df.short.nunique()} shorts")

pd.set_option("display.width", 220)
COLS = ["long", "short", "win", "sl", "tp", "rf", "cap",
        "sel_mean", "sel_pay", "hold_mean", "hold_med", "hold_pay", "hold_dead"]

print("\n" + "=" * 150)
print("TOP 25 BY HOLDOUT MEAN")
print("=" * 150)
print(df.nlargest(25, "hold_mean")[COLS].to_string(index=False))

print("\n" + "=" * 150)
print("TOP 25 BY HOLDOUT MEDIAN  (the typical account, not the tail)")
print("=" * 150)
print(df.nlargest(25, "hold_med")[COLS].to_string(index=False))

print("\n" + "=" * 150)
print("BEST CONFIG PER PAIRING, ranked by holdout mean — top 30 pairings")
print("=" * 150)
best = df.loc[df.groupby(["long", "short"])["hold_mean"].idxmax()]
print(best.nlargest(30, "hold_mean")[COLS].to_string(index=False))

print("\n" + "=" * 150)
print("PER-FAMILY AVERAGE ACROSS ALL ITS PAIRINGS  (is the family good, or one config lucky?)")
print("=" * 150)
for role in ("long", "short"):
    agg = (df.groupby(role)
             .agg(n=("hold_mean", "size"),
                  hold_mean=("hold_mean", "mean"),
                  hold_med=("hold_med", "mean"),
                  hold_pay=("hold_pay", "mean"),
                  hold_dead=("hold_dead", "mean"),
                  best=("hold_mean", "max"))
             .sort_values("hold_mean", ascending=False).round(1))
    print(f"\n  ### {role.upper()}S")
    print(agg.to_string())

print("\n" + "=" * 150)
print("HEAD TO HEAD — incumbent vs Fisher, matched on every other parameter")
print("=" * 150)
key = ["short", "win", "sl", "tp", "rf", "cap", "maxc"]
inc = df[df.long == "sr_round100_break"].set_index(key)
fis = df[df.long == "mf_wkpiv_long"].set_index(key)
common = inc.index.intersection(fis.index)
if len(common):
    a, b = inc.loc[common], fis.loc[common]
    print(f"  {len(common)} matched configs")
    print(f"    incumbent sr_round100_break : mean ${a.hold_mean.mean():,.0f}  "
          f"med ${a.hold_med.mean():,.0f}  pay {a.hold_pay.mean():.1f}%  "
          f"dead {a.hold_dead.mean():.1f}%")
    print(f"    Fisher    mf_wkpiv_long     : mean ${b.hold_mean.mean():,.0f}  "
          f"med ${b.hold_med.mean():,.0f}  pay {b.hold_pay.mean():.1f}%  "
          f"dead {b.hold_dead.mean():.1f}%")
    w = (b.hold_mean.values > a.hold_mean.values).mean()
    print(f"    Fisher wins on hold_mean in {100*w:.0f}% of matched configs")

print("\n" + "=" * 150)
print("THE INCUMBENT'S OWN ROWS (sr_round100_break + vol_lw_stretch_short)")
print("=" * 150)
own = df[(df.long == "sr_round100_break") & (df.short == "vol_lw_stretch_short")]
print(own.sort_values("hold_mean", ascending=False)[COLS].to_string(index=False))

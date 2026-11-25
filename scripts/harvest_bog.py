"""Read out the best-of-grid random control.

The comparison is MAX vs MAX. For the real signals and for each random seed, the
identical grid is run (6 longs x 6 shorts x 3 windows x 3 brackets x 2 sizes) and
the single best cell is taken. Comparing the real maximum against the DISTRIBUTION
of random maxima is the only fair form of this test, because the real config was
itself chosen as a maximum — comparing it to an average random draw would flatter
it enormously.

Read the result this way:
  real max well outside the random max range  -> the edge is real
  real max inside the random max range        -> the search manufactured it
"""
from __future__ import annotations

import glob

import numpy as np
import pandas as pd

frames = []
for f in sorted(glob.glob("bogc_*.csv")):
    try:
        frames.append(pd.read_csv(f))
    except Exception as exc:
        print(f"  skip {f}: {exc}")
d = pd.concat(frames, ignore_index=True)
d = d[d.n > 0]
print(f"{len(d)} grid cells across {d.tag.nunique()} tags")
print(d.groupby("tag").size().to_string())

METRICS = [("mean", "mean withdrawn"), ("med", "median withdrawn"),
           ("paid", "% paid"), ("avg_pays", "payouts/yr")]

pd.set_option("display.width", 200)
print("\n" + "=" * 110)
print("BEST-OF-GRID: real maximum vs the distribution of random maxima")
print("=" * 110)

summary = []
for col, label in METRICS:
    mx = d.groupby("tag")[col].max()
    real = mx.get("REAL", np.nan)
    rnd = mx.drop(labels=["REAL"], errors="ignore")
    beat = int((rnd >= real).sum())
    summary.append(dict(metric=label, real=round(real, 2),
                        rnd_best=round(rnd.max(), 2),
                        rnd_median=round(rnd.median(), 2),
                        rnd_min=round(rnd.min(), 2),
                        seeds_matching_real=f"{beat}/{len(rnd)}"))
print(pd.DataFrame(summary).to_string(index=False))

print("\n" + "=" * 110)
print("PER-SEED MAXIMA (each is the best cell that seed's whole grid could produce)")
print("=" * 110)
per = d.groupby("tag").agg(best_mean=("mean", "max"), best_med=("med", "max"),
                           best_paid=("paid", "max"), cells=("mean", "size"))
print(per.sort_values("best_mean", ascending=False).to_string())

print("\n" + "=" * 110)
print("THE REAL GRID'S OWN TOP CELLS")
print("=" * 110)
r = d[d.tag == "REAL"]
cols = ["long", "short", "win", "sl", "tp", "cap", "paid", "bust", "mean", "med", "days"]
print(r.nlargest(12, "mean")[cols].to_string(index=False))

print("\n" + "=" * 110)
print("HOW MANY RANDOM CELLS BEAT THE REAL WINNER OUTRIGHT?")
print("=" * 110)
for col, label in METRICS[:2]:
    real_best = r[col].max()
    rnd_cells = d[d.tag != "REAL"]
    n = int((rnd_cells[col] >= real_best).sum())
    print(f"  {label:<20} real best {real_best:>8.0f}   "
          f"random cells at or above it: {n}/{len(rnd_cells)} "
          f"({100*n/max(len(rnd_cells),1):.2f}%)")

"""Does the k14 -> k21 improvement hold in EVERY year, or is it one lucky period?

The paired test showed k21 beating k14 in 96% of 840 matched configs on the holdout.
But those 840 configs share one signal over one span of history, so the effective
evidence is a single observation. Splitting by calendar year gives 5 semi-independent
looks: if k21 wins in every year, that is far harder to attribute to luck.
"""
from __future__ import annotations

import itertools

import numpy as np
import pandas as pd

import funded_search as fs
import funded_1yr as f1

df = fs.load_enriched()
plugins = f1.load_plugins(df)

sig14 = pd.Series(plugins["so_k14_th30"][0]).reindex(df.index).fillna(False)
sig21 = pd.Series(plugins["so_k21_th30"][0]).reindex(df.index).fillna(False)
print(f"k14 fires {int(sig14.sum()):,}   k21 fires {int(sig21.sum()):,}")

years = sorted(df.index.year.unique())
rows = []
n = 0
for sl, tp, win, gate, (cap, bud) in itertools.product(
        f1.SLS, f1.TPS, f1.WINS, f1.GATES, f1.SIZES):
    if tp < sl * 0.5:
        continue
    n += 1
    rec = dict(sl=sl, tp=tp, win=f"{win[0]}-{win[1]}", gate=gate or "-", cap=cap)
    for tag, sg in (("k14", sig14), ("k21", sig21)):
        daily, _, _ = fs.replay(df, sg, +1, sl, tp, win, gate, cap, bud)
        for y in years:
            sub = daily[daily.index.year == y]
            rec[f"{tag}_{y}"] = float(sub.sum()) if len(sub) else 0.0
    rows.append(rec)
    if n % 100 == 0:
        print(f"  {n} configs...", flush=True)

out = pd.DataFrame(rows)
out.to_csv("k14_vs_k21_yearly.csv", index=False)

print("\n" + "=" * 88)
print("PAIRED BY YEAR — across all 840 configs, how often does k21 beat k14?")
print("=" * 88)
print(f"{'year':<8}{'k21 wins':>12}{'of':>6}{'pct':>8}{'median delta':>16}"
      f"{'k14 median':>14}{'k21 median':>14}")
allwin = []
for y in years:
    a, b = out[f"k14_{y}"], out[f"k21_{y}"]
    wins = int((b > a).sum())
    allwin.append(wins / len(out))
    print(f"{y:<8}{wins:>12}{len(out):>6}{100*wins/len(out):>7.1f}%"
          f"{np.median(b - a):>+16,.0f}{a.median():>+14,.0f}{b.median():>+14,.0f}")

print("\n" + "=" * 88)
won = sum(1 for w in allwin if w > 0.5)
print(f"years where k21 beats k14 in the MAJORITY of configs: {won}/{len(years)}")
print("=" * 88)

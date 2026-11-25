"""Rank the optimisation output and produce the top 5, with an honest split
between 'highest mean' and 'most reliable'."""
from __future__ import annotations

import glob
import pandas as pd

d = pd.concat([pd.read_csv(x) for x in sorted(glob.glob("opt_*.csv"))], ignore_index=True)
pd.set_option("display.width", 280)
print(f"scored configs: {len(d):,}   pairings: {d.groupby(['long','short']).ngroups}")

cols = ["long", "short", "sl", "tp", "win", "gate", "cap", "maxc", "trades",
        "win_pct", "nl", "ns", "net", "mean_out", "med_out", "p75_out",
        "pay_pct", "bust_pct"]

real = d[(d.trades >= 80) & (d.n >= 200)]
print(f"with >=80 trades and >=200 simulated accounts: {len(real):,}\n")

print("=" * 140)
print("TOP 10 BY MEAN DOLLARS WITHDRAWN PER ACCOUNT")
print("=" * 140)
print(real.sort_values("mean_out", ascending=False)[cols].head(10).to_string(index=False))

print("\n" + "=" * 140)
print("TOP 10 BY MEDIAN (a typical account, not the lucky tail)")
print("=" * 140)
print(real.sort_values(["med_out", "mean_out"], ascending=False)[cols].head(10).to_string(index=False))

print("\n" + "=" * 140)
print("TOP 10 BY SHARE OF ACCOUNTS GETTING PAID AT ALL")
print("=" * 140)
print(real.sort_values(["pay_pct", "mean_out"], ascending=False)[cols].head(10).to_string(index=False))

print("\n" + "=" * 140)
print("SINGLE-SIDED vs TWO-SIDED  (median of mean_out by structure)")
print("=" * 140)
def kind(r):
    if r["long"] == "NONE":
        return "short only"
    if r["short"] == "NONE":
        return "long only"
    return "two-sided"
real = real.copy()
real["kind"] = real.apply(kind, axis=1)
print(real.groupby("kind").agg(n=("mean_out", "size"), med_mean=("mean_out", "median"),
                               best_mean=("mean_out", "max"),
                               med_pay=("pay_pct", "median"),
                               best_med=("med_out", "max")).to_string())

print("\n" + "=" * 140)
print("THE TOP 5  — balanced: mean_out, then require the median not be zero")
print("=" * 140)
solid = real[real.med_out > 0].sort_values("mean_out", ascending=False)
print(f"configs with a NON-ZERO median: {len(solid)} of {len(real)}")
top5 = solid.head(5) if len(solid) >= 5 else real.sort_values("mean_out", ascending=False).head(5)
for i, (_, r) in enumerate(top5.iterrows(), 1):
    print(f"\n  #{i}  {r['long']}  +  {r['short']}")
    print(f"      stop {r['sl']}xATR / target {r['tp']}xATR | window {r['win']} | "
          f"gate {r['gate']} | cap ${r['cap']} | max {r['maxc']} ct")
    print(f"      trades {r['trades']} ({r['nl']}L/{r['ns']}S) | win {r['win_pct']}% | "
          f"5yr net ${r['net']:,}")
    print(f"      per account: mean ${r['mean_out']:,} | median ${r['med_out']:,} | "
          f"p75 ${r['p75_out']:,} | paid {r['pay_pct']}% | bust {r['bust_pct']}%")

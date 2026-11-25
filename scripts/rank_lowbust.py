"""Rank the risk_frac / cushion sweep. Bar: bust < 30% AND non-zero median."""
from __future__ import annotations

import glob
import pandas as pd

d = pd.concat([pd.read_csv(x) for x in sorted(glob.glob("lb3_*.csv"))], ignore_index=True)
pd.set_option("display.width", 250)
print(f"configs {len(d):,}  pairings {d.groupby(['long','short']).ngroups}\n")

cols = ["long", "short", "sl", "tp", "win", "risk_frac", "cushion", "cap", "maxc",
        "n", "mean_out", "med_out", "p75_out", "pay_pct", "bust_pct"]

print("=" * 128)
print("DOES risk_frac WORK?  median bust% by risk_frac")
print("=" * 128)
print(d.groupby("risk_frac").agg(n=("bust_pct", "size"), med_bust=("bust_pct", "median"),
                                 med_mean_out=("mean_out", "median"),
                                 med_pay=("pay_pct", "median"),
                                 best_mean=("mean_out", "max")).to_string())

print("\n" + "=" * 128)
print("DOES cushion WORK?  median bust% by cushion")
print("=" * 128)
print(d.groupby("cushion").agg(n=("bust_pct", "size"), med_bust=("bust_pct", "median"),
                               med_mean_out=("mean_out", "median"),
                               med_pay=("pay_pct", "median"),
                               best_mean=("mean_out", "max")).to_string())

print("\n" + "=" * 128)
print("THE BAR: bust < 30%  AND  median withdrawal > 0")
print("=" * 128)
hit = d[(d.bust_pct < 30) & (d.med_out > 0)]
print(f"count: {len(hit)} of {len(d):,}")
if len(hit):
    print(hit.sort_values("mean_out", ascending=False)[cols].head(20).to_string(index=False))

print("\n" + "=" * 128)
print("bust < 30% (any median) — best by mean withdrawn")
print("=" * 128)
b30 = d[d.bust_pct < 30]
print(f"count: {len(b30)}")
if len(b30):
    print(b30.sort_values("mean_out", ascending=False)[cols].head(20).to_string(index=False))

print("\n" + "=" * 128)
print("bust < 20%")
print("=" * 128)
b20 = d[d.bust_pct < 20]
print(f"count: {len(b20)}   best mean_out ${b20.mean_out.max() if len(b20) else 0:,.0f}")
if len(b20):
    print(b20.sort_values("mean_out", ascending=False)[cols].head(12).to_string(index=False))

print("\n" + "=" * 128)
print("TOP 5 OVERALL by mean withdrawn, with bust shown")
print("=" * 128)
print(d.sort_values("mean_out", ascending=False)[cols].head(12).to_string(index=False))

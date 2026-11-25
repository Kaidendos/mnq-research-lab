"""Does the best long + best short beat the incumbent pairing?

BEST LONG  : mf_wkpiv_long        (Mark Fisher ACD weekly pivot)  holdout $8,726 / 37.5% bust
BEST SHORT : vol_lw_stretch_short (Larry Williams stretch)        holdout $10,635 / 35.3% bust
INCUMBENT  : sr_round100_break + vol_lw_stretch_short -> holdout mean $1,458, 45.9% paid
"""
import glob
import pandas as pd

pd.set_option("display.width", 230)
fs_ = sorted(glob.glob("tp_*.csv"))
if not fs_:
    raise SystemExit("no tp_*.csv yet")
d = pd.concat([pd.read_csv(f) for f in fs_], ignore_index=True)
print(f"configs so far {len(d):,}   pairings {d.groupby(['long','short']).ngroups}")

C = ["long", "short", "win", "sl", "tp", "rf", "cap", "maxc",
     "sel_mean", "sel_med", "sel_pay", "sel_dead",
     "hold_mean", "hold_med", "hold_pay", "hold_dead"]

print("\n" + "=" * 140)
print("THE PAIRING IN QUESTION — mf_wkpiv_long + vol_lw_stretch_short")
print("=" * 140)
q = d[(d.long == "mf_wkpiv_long") & (d.short == "vol_lw_stretch_short")]
if len(q):
    print(q.sort_values("hold_mean", ascending=False)[C].head(12).to_string(index=False))
else:
    print("  not scored yet")

print("\n" + "=" * 140)
print("INCUMBENT — sr_round100_break + vol_lw_stretch_short")
print("=" * 140)
inc = d[(d.long == "sr_round100_break") & (d.short == "vol_lw_stretch_short")]
print(inc.sort_values("hold_mean", ascending=False)[C].head(6).to_string(index=False)
      if len(inc) else "  not scored yet")

print("\n" + "=" * 140)
print("TOP 20 OVERALL BY HOLDOUT MEAN (net-positive in BOTH periods)")
print("=" * 140)
g = d[(d.sel_mean > 0) & (d.hold_mean > 0)]
print(f"net-positive both: {len(g):,} of {len(d):,}")
if len(g):
    print(g.sort_values("hold_mean", ascending=False)[C].head(20).to_string(index=False))

print("\n" + "=" * 140)
print("BEST BY PAIRING (max holdout mean per long+short)")
print("=" * 140)
if len(g):
    idx = g.groupby(["long", "short"])["hold_mean"].idxmax()
    b = g.loc[idx].sort_values("hold_mean", ascending=False)
    print(b[C].head(20).to_string(index=False))

print("\n" + "=" * 140)
print("LOWEST dead_pct IN BOTH PERIODS (survivability, not just profit)")
print("=" * 140)
z = g[(g.sel_dead < 55) & (g.hold_dead < 55)] if len(g) else g
print(f"count {len(z)}")
if len(z):
    print(z.sort_values("hold_dead")[C].head(15).to_string(index=False))

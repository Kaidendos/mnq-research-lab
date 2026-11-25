"""Read out the clean-control family ranking and compare it to the old net ranking.

The interesting output is not just "which families have an edge" but HOW DIFFERENT
this ordering is from the net-P&L ordering the whole project has used. If the two
agree, nothing was lost by ranking on net. If they disagree badly, then every
candidate list built so far was built on the wrong signal.
"""
from __future__ import annotations

import glob

import numpy as np
import pandas as pd

d = pd.concat([pd.read_csv(f) for f in sorted(glob.glob("rc_*.csv"))],
              ignore_index=True)
d = d[d.trades >= 40]
pd.set_option("display.width", 200)
print(f"{len(d)} family-window rows, {d.family.nunique()} distinct families")

COLS = ["family", "side", "win", "trades", "win_pct", "real_ppt", "ctl_ppt",
        "edge", "beaten", "seeds"]

print("\n" + "=" * 128)
print("TOP 30 BY EDGE OVER THE CLEAN CONTROL  (edge = real pts/trade - shuffled median)")
print("'beaten' = how many of 8 shuffles matched or beat it. 0 is what you want.")
print("=" * 128)
print(d.nlargest(30, "edge")[COLS].to_string(index=False))

print("\n" + "=" * 128)
print("STRONGEST: edge > 5 pts AND beaten by 0 of 8 shuffles")
print("=" * 128)
strong = d[(d.edge > 5) & (d.beaten == 0)].sort_values("edge", ascending=False)
print(strong[COLS].to_string(index=False) if len(strong) else "  none")
print(f"\n  {len(strong)} of {len(d)} rows clear that bar "
      f"({100*len(strong)/len(d):.1f}%)")

print("\n" + "=" * 128)
print("HOW MUCH OF RAW P&L IS JUST DRIFT / SESSION SELECTION?")
print("=" * 128)
print(f"  median real pts/trade across all families : {d.real_ppt.median():+.2f}")
print(f"  median control pts/trade                 : {d.ctl_ppt.median():+.2f}")
print(f"  median EDGE                              : {d.edge.median():+.2f}")
print(f"  families with real_ppt > 0               : "
      f"{100*(d.real_ppt > 0).mean():.1f}%")
print(f"  families with edge > 0                   : "
      f"{100*(d.edge > 0).mean():.1f}%")
print("\n  If most families look profitable on real_ppt but only a minority have a")
print("  positive edge, the raw number was measuring the market, not the rule.")

print("\n" + "=" * 128)
print("DOES THE OLD NET RANKING AGREE WITH THE EDGE RANKING?")
print("=" * 128)
try:
    old = pd.read_csv("rank_sides.csv")
    m = d.merge(old[["family", "hold_net"]], on="family", how="inner")
    m = m.drop_duplicates("family")
    if len(m) > 10:
        r = m[["hold_net", "edge"]].corr(method="spearman").iloc[0, 1]
        print(f"  Spearman correlation, old hold_net vs clean edge: {r:+.3f}"
              f"   (n={len(m)})")
        print("\n  TOP 10 BY OLD hold_net, showing where they land on edge:")
        t = m.nlargest(10, "hold_net")[["family", "hold_net", "real_ppt", "edge", "beaten"]]
        t["edge_rank"] = [int((m.edge > e).sum()) + 1 for e in t.edge]
        print(t.to_string(index=False))
        print(f"\n  (edge_rank is out of {len(m)} families)")
except FileNotFoundError:
    print("  rank_sides.csv not found")

print("\n" + "=" * 128)
print("THE INCUMBENT PAIR'S OWN ROWS")
print("=" * 128)
inc = d[d.family.isin(["sr_round100_break", "vol_lw_stretch_short"])]
print(inc[COLS].to_string(index=False))

d.sort_values("edge", ascending=False).to_csv("rank_clean_sorted.csv", index=False)
print("\n  full sorted ranking -> rank_clean_sorted.csv")

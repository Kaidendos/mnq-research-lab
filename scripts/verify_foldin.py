"""Hold the fold-in to the SAME bar that rejected wy_lps_long.

`wy_lps_long` was rejected for winning "only" 67% of 36 matched configs. The
fold-in (`+L ema20_50_long`, and the 3L2S stack) was accepted on the strength of
ONE bracket — 9:45-11:00, SL2.0/TP3.0 — which is precisely the evidence standard
that produced the earlier false positives. If the fold-in cannot clear the same
paired test, it does not go in either, however good that one cell looks.

Two candidates, each toggled against a fixed base across the same 36-config grid:
    +L ema20_50_long              the single best stage-1 addition
    3L2S ema20_50 + mf_wkpiv + lw_oops    the best stage-2 combination

Reported per cap config, because the whole point of the earlier finding is that
the fold-in helps cap $250 and hurts cap $440 — a split that must survive the
grid, not just one bracket.
"""
from __future__ import annotations

import itertools

import numpy as np
import pandas as pd

import funded_search as fs
import funded_1yr as f1
import sim_trace as ST

BASE_L, BASE_S = "sr_round100_break", "vol_lw_stretch_short"
CANDIDATES = [
    ("+L ema20_50", ["ema20_50_long"], []),
    ("3L2S full", ["ema20_50_long", "mf_wkpiv_long"], ["lw_oops_short"]),
]
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


def run(longs, shorts, win, sl, tp, cap, bud):
    P = ST.build(hold, longs, shorts, win, resolve)
    res = [ST.trace(P, k, cap, bud, sl=sl, tp=tp)
           for k in range(0, len(P["per"]), 4) if len(P["per"]) - k >= 20]
    return ST.summarise(res)


rows = []
for label, add_l, add_s in CANDIDATES:
    for win, (sl, tp), (cap, bud) in itertools.product(WINS, BRACKETS, SIZES):
        a = run([BASE_L], [BASE_S], win, sl, tp, cap, bud)
        b = run([BASE_L] + add_l, [BASE_S] + add_s, win, sl, tp, cap, bud)
        rows.append(dict(cand=label, win=f"{win[0]}-{win[1]}", sl=sl, tp=tp,
                         cap=cap, bud=bud,
                         base_mean=a["mean"], add_mean=b["mean"],
                         base_med=a["med"], add_med=b["med"],
                         base_paid=a["paid"], add_paid=b["paid"],
                         base_bust=a["bust"], add_bust=b["bust"]))
    print(f"  {label} done", flush=True)

g = pd.DataFrame(rows)
g["d_mean"] = g.add_mean - g.base_mean
g["d_med"] = g.add_med - g.base_med
g["d_bust"] = g.add_bust - g.base_bust
g.to_csv("verify_foldin.csv", index=False)
pd.set_option("display.width", 200)

print("\n" + "=" * 120)
print("FOLD-IN, PAIRED ACROSS 36 MATCHED CONFIGS  (bar to clear: wy_lps managed 67%)")
print("=" * 120)
for cand, grp in g.groupby("cand", sort=False):
    print(f"\n  ### {cand}   ({len(grp)} configs)")
    print(f"    wins on mean   : {(grp.d_mean > 0).sum():>3}/{len(grp)}  "
          f"({100*(grp.d_mean > 0).mean():.0f}%)  median delta ${grp.d_mean.median():+,.0f}")
    print(f"    wins on median : {(grp.d_med > 0).sum():>3}/{len(grp)}  "
          f"({100*(grp.d_med > 0).mean():.0f}%)  median delta ${grp.d_med.median():+,.0f}")
    print(f"    bust WORSE in  : {(grp.d_bust > 0).sum():>3}/{len(grp)}  "
          f"median delta {grp.d_bust.median():+.1f} pts")
    for cap, sub in grp.groupby("cap"):
        print(f"      cap ${cap}: mean wins {(sub.d_mean > 0).sum()}/{len(sub)}, "
              f"median delta ${sub.d_mean.median():+,.0f}, "
              f"bust delta {sub.d_bust.median():+.1f}")

print("\n" + "=" * 120)
print("FULL GRID")
print("=" * 120)
print(g.to_string(index=False))

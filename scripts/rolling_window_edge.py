"""Is "the wide window is better now" a REGIME SHIFT or just a 23-account wobble?

`window_regime.py` found, on the last 5 months at cap $440:
    9:45-11:00  mean $324    9:45-13:30  mean $917    9:45-15:30  mean $1,053
and on the 4.5-year holdout the ranking is reversed, decisively:
    9:45-11:00  mean $2,352 / med $334 / bust 2.1%
    9:45-15:30  mean $1,907 / med $0   / bust 7.6%

The recent number rests on 23 accounts. Before anything is changed on that basis,
the question is whether the narrow/wide ranking has flipped back and forth over
the years. If it has, "the edge moved to the afternoon" is a story told about
noise, and the last 5 months are one more flip. If the wide window has been
losing consistently for years and has only just taken the lead, that is a
different and much more interesting claim.

Method: walk the whole 5 years in non-overlapping 5-month blocks — the same size
as the live window — and score narrow vs wide identically in each. Small n per
block is unavoidable and is the point: it shows how much a 5-month verdict moves
around by chance, which is the only way to judge whether the latest one means
anything.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import funded_search as fs
import funded_1yr as f1
import sim_trace as ST

BASE_L, BASE_S = "sr_round100_break", "vol_lw_stretch_short"
NARROW, WIDE = (9.75, 11.0), (9.75, 15.5)
CAP, BUD = 440, 300
BLOCK_MONTHS = 5

df = fs.load_enriched()
pl = f1.load_plugins(df)


def resolve(frame, name):
    e, _ = pl[name] if name in pl else fs.sig(df, name)
    return pd.Series(e).reindex(frame.index).fillna(False).to_numpy(bool)


def score(frame, win):
    P = ST.build(frame, [BASE_L], [BASE_S], win, resolve)
    starts = [k for k in range(0, len(P["per"]), 2) if len(P["per"]) - k >= 20]
    if len(starts) < 8:
        return None
    return ST.summarise([ST.trace(P, k, CAP, BUD) for k in starts])


edges = []
t = df.index[-1]
while t > df.index[0]:
    edges.append(t)
    t = t - pd.DateOffset(months=BLOCK_MONTHS)
edges = list(reversed(edges))

rows = []
for lo, hi in zip(edges[:-1], edges[1:]):
    blk = df[(df.index >= lo) & (df.index < hi)]
    if len(blk) < 3000:
        continue
    n_res, w_res = score(blk, NARROW), score(blk, WIDE)
    if n_res is None or w_res is None:
        continue
    rows.append(dict(block=f"{lo.date()} -> {hi.date()}", n=n_res["n"],
                     narrow_mean=n_res["mean"], wide_mean=w_res["mean"],
                     narrow_med=n_res["med"], wide_med=w_res["med"],
                     narrow_paid=n_res["paid"], wide_paid=w_res["paid"],
                     narrow_bust=n_res["bust"], wide_bust=w_res["bust"],
                     winner="WIDE" if w_res["mean"] > n_res["mean"] else "narrow"))
    print(f"  {rows[-1]['block']}  {rows[-1]['winner']}", flush=True)

out = pd.DataFrame(rows)
out.to_csv("rolling_window_edge.csv", index=False)
pd.set_option("display.width", 200)
print("\n" + "=" * 130)
print(f"NARROW 9:45-11:00 vs WIDE 9:45-15:30, cap ${CAP}, in {BLOCK_MONTHS}-month blocks")
print("=" * 130)
print(out.to_string(index=False))
w = (out.winner == "WIDE").sum()
print(f"\n  WIDE wins {w} of {len(out)} blocks")
print(f"  the LAST block is: {out.iloc[-1].winner}")
print("\n  If WIDE wins a scattered ~half of blocks, the recent result is noise and")
print("  the 4.5-year holdout ranking stands. If WIDE has only started winning in")
print("  the most recent blocks, that is a genuine shift worth acting on.")

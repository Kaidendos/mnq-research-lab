"""Is the recent +0.22 pts/trade a broken edge, or a normal bad patch?

The clean control settled the direction question:
    holdout  REAL +12.25 vs shuffled-random +0.39   (0/20 seeds beat it)
    recent   REAL  +0.22 vs shuffled-random +2.03   (10/20 seeds beat it)

So the signal has a real edge over 4.5 years and none at all in the last 5 months.
But that recent number rests on 104 trades, and the 5-month block analysis already
showed this system's 5-month outcomes swing from $76 to $2,839. Before concluding
the edge has decayed, the recent block has to be placed against the other ten.

Per block: the signal's points per trade, and the shuffled-random baseline for the
SAME block, so each period is judged against its own market rather than against a
5-year average that no single period resembles.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import funded_search as fs
import funded_1yr as f1
from clean_control import build, points, shuffled

BLOCK_MONTHS = 5
SEEDS = range(10)

df = fs.load_enriched()

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
    starts, ends, ok, sl_, ss_ = build(blk)
    ppt, n, w, tot = points(blk, sl_ & ok, ss_ & ok)
    ctl = []
    for s in SEEDS:
        rng = np.random.default_rng(s)
        el, es = shuffled(starts, ends, ok, sl_, ss_, rng, False)
        ctl.append(points(blk, el, es)[0])
    ctl = np.array(ctl)
    rows.append(dict(block=f"{lo.date()}", trades=n, win=round(w, 1),
                     real=round(ppt, 2), ctl_med=round(float(np.median(ctl)), 2),
                     edge=round(ppt - float(np.median(ctl)), 2),
                     beat=f"{int((ctl >= ppt).sum())}/{len(ctl)}"))
    print(f"  {rows[-1]['block']} done", flush=True)

out = pd.DataFrame(rows)
out.to_csv("edge_by_block.csv", index=False)
pd.set_option("display.width", 160)
print("\n" + "=" * 110)
print("SIGNAL EDGE BY 5-MONTH BLOCK — real pts/trade vs the shuffled control in the SAME block")
print("'beat' = how many of 10 random shuffles matched or beat the real signal (low is good)")
print("=" * 110)
print(out.to_string(index=False))

e = out.edge.to_numpy()
print(f"\n  blocks with a positive edge : {(e > 0).sum()}/{len(e)}")
print(f"  median edge across blocks   : {np.median(e):+.2f} pts/trade")
print(f"  worst block                 : {out.iloc[int(np.argmin(e))].block}  ({e.min():+.2f})")
print(f"  most recent block           : {out.iloc[-1].block}  ({e[-1]:+.2f}), "
      f"rank {int((e < e[-1]).sum()) + 1} of {len(e)}")

"""Can the dead patches be seen COMING? The most decision-relevant question left.

The block analysis established that the edge is real in 9 of 11 five-month blocks
but absent in the current one — the worst of the eleven. That is only actionable if
a dead patch is visible BEFORE it costs money. Two ways it could be:

  1. PERSISTENCE — does last period's edge predict the next one? If edge is
     autocorrelated, a bad stretch is a reason to stand down. If it is not (and for
     most real edges it is not), then reacting to a drawdown is just as likely to
     make you sit out the recovery — 2024-12 was negative and was followed by the
     best block in the sample.

  2. MARKET STATE — is the edge conditional on something observable in advance?
     Realised volatility, trend strength, ATR level, average daily range. If the
     edge only appears when volatility is high, that is a tradable filter; the
     state is known at the start of the period, not after.

Both are tested on 2.5-month half-blocks (about 22 of them) rather than 5-month
blocks, to get enough observations for the correlation to mean anything. All
features are computed from the PRIOR block, never the current one.

Also reported: what fraction of the edge would have been captured by a simple
"stand down after a losing block" rule, versus just holding through.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import funded_search as fs
import funded_1yr as f1
from clean_control import build, points, shuffled

BLOCK_MONTHS = 2.5
SEEDS = range(8)

df = fs.load_enriched()

# half-blocks of ~2.5 months
edges_t = []
t = df.index[-1]
while t > df.index[0]:
    edges_t.append(t)
    t = t - pd.DateOffset(days=76)
edges_t = list(reversed(edges_t))

rows = []
for lo, hi in zip(edges_t[:-1], edges_t[1:]):
    blk = df[(df.index >= lo) & (df.index < hi)]
    if len(blk) < 1200:
        continue
    starts, ends, ok, sl_, ss_ = build(blk)
    ppt, n, w, tot = points(blk, sl_ & ok, ss_ & ok)
    if n < 25:
        continue
    ctl = []
    for s in SEEDS:
        rng = np.random.default_rng(s)
        el, es = shuffled(starts, ends, ok, sl_, ss_, rng, False)
        ctl.append(points(blk, el, es)[0])
    # market state features, from THIS block (used only as the PRIOR block later)
    c = blk["close"]
    dc = c.groupby(blk["_day"]).last()
    dh = blk["high"].groupby(blk["_day"]).max()
    dl = blk["low"].groupby(blk["_day"]).min()
    rows.append(dict(start=lo.date(), trades=n, win=round(w, 1),
                     real=round(ppt, 2), ctl=round(float(np.median(ctl)), 2),
                     edge=round(ppt - float(np.median(ctl)), 2),
                     atr=round(blk["atr"].mean(), 1),
                     trend=round(float(dc.iloc[-1] - dc.iloc[0]), 0),
                     rng=round(float((dh - dl).mean()), 1),
                     updays=round(100 * float((dc.diff() > 0).mean()), 1),
                     vol=round(float(dc.pct_change().std() * 100), 2)))
    print(f"  {lo.date()} edge {rows[-1]['edge']:+.2f}", flush=True)

o = pd.DataFrame(rows)
o.to_csv("regime_predict.csv", index=False)
pd.set_option("display.width", 170)
print("\n" + "=" * 118)
print(f"EDGE BY {BLOCK_MONTHS}-MONTH BLOCK, with market state measured IN that block")
print("=" * 118)
print(o.to_string(index=False))

print("\n" + "=" * 118)
print("1. PERSISTENCE — does one block's edge predict the NEXT block's?")
print("=" * 118)
o["next_edge"] = o.edge.shift(-1)
v = o.dropna(subset=["next_edge"])
if len(v) > 4:
    r = v[["edge", "next_edge"]].corr().iloc[0, 1]
    rs = v[["edge", "next_edge"]].corr(method="spearman").iloc[0, 1]
    print(f"  Pearson  {r:+.3f}    Spearman {rs:+.3f}    (n={len(v)})")
    neg = v[v.edge < 0]
    pos = v[v.edge > 0]
    print(f"\n  after a NEGATIVE block (n={len(neg)}): next edge mean "
          f"{neg.next_edge.mean():+.2f}, positive {100*(neg.next_edge > 0).mean():.0f}% of the time")
    print(f"  after a POSITIVE block (n={len(pos)}): next edge mean "
          f"{pos.next_edge.mean():+.2f}, positive {100*(pos.next_edge > 0).mean():.0f}% of the time")
    print("\n  If those two lines are similar, a losing block carries NO information")
    print("  and standing down after one is as likely to miss the recovery.")

print("\n" + "=" * 118)
print("2. MARKET STATE — does the PRIOR block's state predict THIS block's edge?")
print("=" * 118)
for f in ("atr", "trend", "rng", "updays", "vol"):
    o[f"prev_{f}"] = o[f].shift(1)
v2 = o.dropna(subset=[f"prev_{f}" for f in ("atr", "trend", "rng", "updays", "vol")])
if len(v2) > 5:
    for f in ("atr", "trend", "rng", "updays", "vol"):
        r = v2[[f"prev_{f}", "edge"]].corr().iloc[0, 1]
        print(f"  prior {f:<8} vs this block's edge : {r:+.3f}")
    print("\n  Same-block (NOT tradable, shown only to see if the edge is state-linked at all):")
    for f in ("atr", "trend", "rng", "updays", "vol"):
        r = o[[f, "edge"]].corr().iloc[0, 1]
        print(f"  same  {f:<8} vs edge : {r:+.3f}")

print("\n" + "=" * 118)
print("3. WOULD 'STAND DOWN AFTER A LOSING BLOCK' HAVE HELPED?")
print("=" * 118)
if len(v) > 4:
    hold_all = o.edge.sum()
    # trade a block only if the previous block's edge was positive
    gated = o[(o.edge.shift(1) > 0) | (o.index == 0)].edge.sum()
    blocks_traded = int(((o.edge.shift(1) > 0) | (o.index == 0)).sum())
    print(f"  hold through everything : total edge {hold_all:+.1f} over {len(o)} blocks")
    print(f"  skip after a loss       : total edge {gated:+.1f} over {blocks_traded} blocks")
    print(f"  per-block average       : hold {hold_all/len(o):+.2f}  "
          f"vs gated {gated/max(blocks_traded,1):+.2f}")

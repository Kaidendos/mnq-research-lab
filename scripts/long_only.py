"""Long-only: drop the short side entirely and run a single long signal.

Never tested at account level this session — every configuration so far has been
two-sided. Worth answering directly, because the short side is what makes the book
78% long by trade count look balanced, and because Mark Fisher's ACD weekly pivot
(`mf_wkpiv_long`) was once ranked the best long in the entire 271-family registry
at $8,726 holdout net.

What is already known about that ranking, and why this is not a contradiction:
  - `mf_wkpiv_long` topped the NET ranking, which mostly reads the market
  - on CLEAN EDGE it ranks 89 of 349 (+3.22) versus `sr_round100_break` (+4.77)
  - when PAIRED it lost 91% of 1,080 matched head-to-heads
so the expectation is that it underperforms. But "worse when paired" and "worse
alone" are different claims, and long-only removes the partner that beat it.

Each long is run alone against the incumbent PAIR and against the incumbent's own
two sides run separately, so the value of the short side is measured rather than
assumed. Clean-control edge is reported next to the account result because a
long-only book in a rising index is the exact configuration most flattered by drift.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import funded_search as fs
import funded_1yr as f1
import lucid_fast as LF
import sim_trace as ST

WIN, CAP, BUD = (9.75, 11.0), 440, 300
YRS = (2022, 2023, 2024, 2025, 2026)

CONFIGS = [
    ("PAIR: sr_round + lw_stretch", ["sr_round100_break"], ["vol_lw_stretch_short"]),
    ("LONG ONLY sr_round100_break", ["sr_round100_break"], []),
    ("LONG ONLY mf_wkpiv (Fisher)", ["mf_wkpiv_long"], []),
    ("LONG ONLY wy_lps (Wyckoff)", ["wy_lps_long"], []),
    ("LONG ONLY lw_gsv (Williams)", ["lw_gsv_long"], []),
    ("LONG ONLY qm_ep (Qullamaggie)", ["qm_ep_long"], []),
    ("LONG ONLY tt_turtle_s2", ["tt_turtle_s2_long"], []),
    ("SHORT ONLY lw_stretch", [], ["vol_lw_stretch_short"]),
    ("PAIR: mf_wkpiv + lw_stretch", ["mf_wkpiv_long"], ["vol_lw_stretch_short"]),
]

df = fs.load_enriched()
pl = f1.load_plugins(df)
end = df.index[-1]
cut = end - pd.DateOffset(months=5)
FRAMES = {"hold": df[df.index < cut], "recent": df[df.index >= cut]}
for y in YRS:
    FRAMES[f"y{y}"] = df[df.index.year == y]


def resolve(frame, name):
    e, _ = pl[name] if name in pl else fs.sig(df, name)
    return pd.Series(e).reindex(frame.index).fillna(False).to_numpy(bool)


def masks(frame, longs, shorts):
    el = np.zeros(len(frame), bool)
    es = np.zeros(len(frame), bool)
    for n in longs:
        el |= resolve(frame, n)
    for n in shorts:
        es |= resolve(frame, n)
    return el, es


def acct(frame, longs, shorts, horizon=365):
    el, es = masks(frame, longs, shorts)
    P = LF.prep(frame, el, es, WIN)
    res = [ST.trace(P, k, CAP, BUD, maxdays=horizon)
           for k in range(0, len(P["per"]), 4) if len(P["per"]) - k >= 20]
    return ST.summarise(res) if res else None


# clean-control edge for each configuration
hold = FRAMES["hold"]
d_ids = pd.factorize(hold["_day"])[0]
starts = np.flatnonzero(np.r_[True, d_ids[1:] != d_ids[:-1]])
ends = np.r_[starts[1:], len(d_ids)]
eth = hold["eth"].to_numpy(float)
ok = (eth >= WIN[0]) & (eth <= WIN[1]) & (hold["atr"].to_numpy(float) > 0)
from clean_control import points as cc_points, shuffled

print("=" * 122)
print(f"LONG-ONLY vs TWO-SIDED — holdout, {WIN[0]}-{WIN[1]}, SL2/TP3, cap${CAP}/bud${BUD}")
print("=" * 122)
print(f"  {'config':<32}{'trades':>7}{'edge':>8}{'beat':>6}"
      f"{'paid':>7}{'bust':>7}{'mean':>9}{'med':>8}{'days':>6}{'rec_mean':>10}")
rows = {}
for name, longs, shorts in CONFIGS:
    el, es = masks(hold, longs, shorts)
    ppt, n, w, tot = cc_points(hold, el & ok, es & ok)
    ctl = []
    for s in range(10):
        rng = np.random.default_rng(s)
        a, b = shuffled(starts, ends, ok, el, es, rng, False)
        ctl.append(cc_points(hold, a, b)[0])
    ctl = np.array(ctl)
    edge = ppt - float(np.median(ctl))
    h = acct(hold, longs, shorts)
    r = acct(FRAMES["recent"], longs, shorts)
    rows[name] = dict(h=h, r=r, edge=edge, n=n)
    print(f"  {name:<32}{n:>7}{edge:>+8.2f}{int((ctl >= ppt).sum()):>4}/10"
          f"{h['paid']:>7.1f}{h['bust']:>7.1f}{h['mean']:>9,.0f}{h['med']:>8,.0f}"
          f"{h['days']:>6}{r['mean']:>10,.0f}")

print("\n" + "=" * 122)
print("PER YEAR — mean $ per account (180-day horizon)")
print("=" * 122)
print(f"  {'config':<32}" + "".join(f"{y:>11}" for y in YRS))
for name, longs, shorts in CONFIGS:
    vals = []
    for y in YRS:
        m = acct(FRAMES[f"y{y}"], longs, shorts, horizon=180)
        vals.append(m["mean"] if m else 0)
    print(f"  {name:<32}" + "".join(f"{v:>11,.0f}" for v in vals))

print("\n" + "=" * 122)
print("IS THE SHORT SIDE PULLING ITS WEIGHT?")
print("=" * 122)
p = rows["PAIR: sr_round + lw_stretch"]["h"]
lo_ = rows["LONG ONLY sr_round100_break"]["h"]
sh = rows["SHORT ONLY lw_stretch"]["h"]
print(f"  long only  : mean ${lo_['mean']:>6,.0f}  paid {lo_['paid']:>5.1f}%  bust {lo_['bust']:>4.1f}%")
print(f"  short only : mean ${sh['mean']:>6,.0f}  paid {sh['paid']:>5.1f}%  bust {sh['bust']:>4.1f}%")
print(f"  BOTH       : mean ${p['mean']:>6,.0f}  paid {p['paid']:>5.1f}%  bust {p['bust']:>4.1f}%")
print(f"\n  sum of the parts ${lo_['mean']+sh['mean']:,.0f} vs the pair ${p['mean']:,.0f}"
      f"  ->  {'SYNERGY' if p['mean'] > lo_['mean']+sh['mean'] else 'no synergy'}")

"""Fold-in, third attempt — candidates chosen by TOTAL EDGE this time.

The first fold-in picked second signals by standalone net (`speed_test.py`) and was
wrong. The second picked by paired account mean (`foldin_2l2s.py`) and its winner
failed the 36-config toggle at 47%. Neither used total edge, which is the metric
established today as the one the account experiences.

There is also a specific, physical reason to expect the SHORT side to be where the
gain is, and it is the same reason the clean control was so damaging:

    the book is 78% LONG by trade count, and essentially all of its profit rides
    MNQ's upward drift.

The shorts dominate the total-edge ranking — `lw_gsv_short` is rank 1 in the entire
registry at 4,648, ahead of the incumbent's 4,473 — so adding a second short should
both add edge AND cut the drift dependence that made the strategy look like a beta
harvest. That is a mechanism, not a data-mined story, which is what the seven dead
candidates lacked.

Paired toggle across 27 cells (3 windows x 3 caps x 3 budgets), plus per year, plus
the untouched recent window. Bar to clear: 96.2% is what a trusted change looked
like; 67% and 47% were rejected.
"""
from __future__ import annotations

import itertools

import numpy as np
import pandas as pd

import funded_search as fs
import funded_1yr as f1
import lucid_fast as LF
import sim_trace as ST

BASE_L, BASE_S = "sr_round100_break", "vol_lw_stretch_short"
WINDOWS = ((9.75, 11.0), (9.75, 12.0), (9.75, 15.5))
CAPS = (440, 250, 600)
BUDGETS = (300, 400, 500)

# ranked by TOTAL edge (edge x trades) from rank_clean_sorted.csv
ADD_SHORTS = ["lw_gsv_short", "rh_irb_gated_short", "macd_x_short",
              "donch20_short", "tm_open_newlow", "wy_sow_short"]
ADD_LONGS = ["ic_fvg_long", "vwap_reclaim_long", "bs_avwap_2day_long"]

df = fs.load_enriched()
pl = f1.load_plugins(df)
end = df.index[-1]
cut = end - pd.DateOffset(months=5)
FRAMES = {"hold": df[df.index < cut], "recent": df[df.index >= cut]}
for y in (2022, 2023, 2024, 2025, 2026):
    FRAMES[f"y{y}"] = df[df.index.year == y]


def resolve(frame, name):
    e, _ = pl[name] if name in pl else fs.sig(df, name)
    return pd.Series(e).reindex(frame.index).fillna(False).to_numpy(bool)


VARIANTS = [("DEFAULT", [], [])]
for s in ADD_SHORTS:
    VARIANTS.append((f"+S {s}", [], [s]))
for l in ADD_LONGS:
    VARIANTS.append((f"+L {l}", [l], []))
VARIANTS.append(("+S lw_gsv +L ic_fvg", ["ic_fvg_long"], ["lw_gsv_short"]))

PREP = {}
for vname, al, ash in VARIANTS:
    for fname, frame in FRAMES.items():
        el = resolve(frame, BASE_L)
        es = resolve(frame, BASE_S)
        for n in al:
            el = el | resolve(frame, n)
        for n in ash:
            es = es | resolve(frame, n)
        for win in WINDOWS:
            PREP[(vname, fname, win)] = LF.prep(frame, el, es, win)
    print(f"  prepped {vname}", flush=True)


def score(vname, fname, win, cap, bud, horizon=365):
    P = PREP[(vname, fname, win)]
    res = [ST.trace(P, k, cap, bud, maxdays=horizon)
           for k in range(0, len(P["per"]), 4) if len(P["per"]) - k >= 20]
    return ST.summarise(res) if res else None


cells = list(itertools.product(WINDOWS, CAPS, BUDGETS))
base = {c: score("DEFAULT", "hold", *c) for c in cells}

print("\n" + "=" * 122)
print("PAIRED ACROSS 27 CELLS, HOLDOUT — second signal chosen by TOTAL EDGE")
print("=" * 122)
rows = []
for vname, _, _ in VARIANTS[1:]:
    dm, dmed, dbust, wins, wmed = [], [], [], 0, 0
    for cell in cells:
        a, b = base[cell], score(vname, "hold", *cell)
        if a is None or b is None:
            continue
        dm.append(b["mean"] - a["mean"])
        dmed.append(b["med"] - a["med"])
        dbust.append(b["bust"] - a["bust"])
        wins += b["mean"] > a["mean"]
        wmed += b["med"] > a["med"]
    n = max(len(dm), 1)
    rows.append(dict(variant=vname, n=len(dm), mean_wins=wins,
                     mean_pct=round(100 * wins / n),
                     med_wins=wmed, d_mean=round(float(np.median(dm))),
                     d_med=round(float(np.median(dmed))),
                     d_bust=round(float(np.median(dbust)), 1)))
    print(f"  {vname:<26} mean wins {wins:>2}/{len(dm)} ({100*wins/n:>3.0f}%)  "
          f"med wins {wmed:>2}/{len(dm)}  d_mean ${np.median(dm):>+6.0f}  "
          f"d_med ${np.median(dmed):>+6.0f}  d_bust {np.median(dbust):>+5.1f}")

pd.DataFrame(rows).to_csv("foldin_total.csv", index=False)

CELL = ((9.75, 11.0), 440, 300)
print("\n" + "=" * 122)
print("PER YEAR at cap440/bud300/9:45-11:00 (mean $ per account)")
print("=" * 122)
YRS = (2022, 2023, 2024, 2025, 2026)
print(f"  {'variant':<26}" + "".join(f"{y:>9}" for y in YRS) + f"{'yrs>base':>11}")
base_yr = {y: score("DEFAULT", f"y{y}", *CELL, horizon=180) for y in YRS}
for vname, _, _ in VARIANTS:
    vals, better = [], 0
    for y in YRS:
        r = score(vname, f"y{y}", *CELL, horizon=180)
        m = r["mean"] if r else 0
        vals.append(m)
        if vname != "DEFAULT" and base_yr[y] and m > base_yr[y]["mean"]:
            better += 1
    tag = f"{better:>10}/5" if vname != "DEFAULT" else f"{'baseline':>11}"
    print(f"  {vname:<26}" + "".join(f"{v:>9,.0f}" for v in vals) + tag)

print("\n" + "=" * 122)
print("RECENT 5 MONTHS (untouched), cap440/bud300")
print("=" * 122)
for vname, _, _ in VARIANTS:
    r = score(vname, "recent", *CELL)
    if r:
        print(f"  {vname:<26} paid {r['paid']:>5.1f}%  bust {r['bust']:>4.1f}%  "
              f"mean ${r['mean']:>6,.0f}  med ${r['med']:>6,.0f}  days {r['days']}")

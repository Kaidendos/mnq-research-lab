"""Paired account-level verification of the parameter changes from `param_sweep.py`.

One-at-a-time on total edge, holdout, vs the defaults (long total edge 2,975 /
short 4,474):

    BREAK_BUF_ATR 0.15 -> 0.10   total edge 2,975 -> 5,272  (+77%)  0/8 beaten
    RVOL_THRESH   1.0  -> 0.8    total edge 2,975 -> 4,816  (+62%)  0/8 beaten
    VOL_LOOKBACK  20   -> 40     total edge 2,975 -> 5,009  (+68%)  1/8 beaten
    LW_K          0.50 -> 0.35   total edge 4,474 -> 5,096  (+14%)  1/8 beaten
    ROUND_STEP    100 is a genuine optimum — 25/50/200/250 are all worse. Keep it.

Every one of these loosens a filter, which is coherent: all three long filters were
costing more in lost trades than they earned in selectivity. That is a believable
mechanism rather than a curve-fit story, and it is the same shape as the one real
improvement this project ever found (`%K 14 -> 21`).

But RVOL is NON-MONOTONIC (1.0 -> 2,975, 1.2 -> 452, 1.5 -> 2,454), which is a noise
signature, and seven candidates have already died today after looking this good on a
one-at-a-time grid. So: the paired account-level toggle across 27 cells, plus per
year, plus the combination of all changes together.

Bar to clear: `%K 14->21` won 96.2% of matched configs and 6/6 years. 67% and 47%
were rejected.
"""
from __future__ import annotations

import itertools

import numpy as np
import pandas as pd

import funded_search as fs
import funded_1yr as f1
import lucid_fast as LF
import sim_trace as ST

WINDOWS = ((9.75, 11.0), (9.75, 12.0), (9.75, 15.5))
CAPS = (440, 250, 600)
BUDGETS = (300, 400, 500)

df = fs.load_enriched()
end = df.index[-1]
cut = end - pd.DateOffset(months=5)


def build_signals(frame, step=100.0, buf=0.15, rvol_th=1.0, vol_look=20, k=0.5):
    c, o = frame["close"], frame["open"]
    v, atr, day = frame["volume"], frame["atr"], frame["_day"]
    pc = c.shift(1)
    same = (day == day.shift(1))
    lvl = np.floor(c / step)
    rvol = v / v.rolling(vol_look).mean()
    el = (same & (lvl > np.floor(pc / step))
          & (c >= lvl * step + buf * atr) & (c > o)
          & (rvol > rvol_th)).fillna(False).to_numpy(bool)
    sess_open = o.groupby(day).transform("first")
    prev_range = (frame["pdh"] - frame["pdl"]).abs()
    bod = frame.groupby(day).cumcount()
    hit = ((c < sess_open - k * prev_range) & (bod > 0)).fillna(False)
    es = (hit & (hit.groupby(day).cumsum() == 1)).to_numpy(bool)
    return el, es


VARIANTS = [
    ("DEFAULT", {}),
    ("buf 0.15->0.10", dict(buf=0.10)),
    ("rvol 1.0->0.8", dict(rvol_th=0.8)),
    ("vol_look 20->40", dict(vol_look=40)),
    ("LW_K 0.50->0.35", dict(k=0.35)),
    ("LW_K 0.50->0.45", dict(k=0.45)),
    ("ALL FOUR", dict(buf=0.10, rvol_th=0.8, vol_look=40, k=0.35)),
    ("LONG THREE only", dict(buf=0.10, rvol_th=0.8, vol_look=40)),
]

FRAMES = {"hold": df[df.index < cut], "recent": df[df.index >= cut]}
for y in (2022, 2023, 2024, 2025, 2026):
    FRAMES[f"y{y}"] = df[df.index.year == y]

PREP = {}
for vname, kw in VARIANTS:
    for fname, frame in FRAMES.items():
        el, es = build_signals(frame, **kw)
        for win in WINDOWS:
            PREP[(vname, fname, win)] = LF.prep(frame, el, es, win)
    print(f"  prepped {vname}", flush=True)


def score(vname, fname, win, cap, bud, horizon=365):
    P = PREP[(vname, fname, win)]
    res = [ST.trace(P, k, cap, bud, maxdays=horizon)
           for k in range(0, len(P["per"]), 4) if len(P["per"]) - k >= 20]
    return ST.summarise(res) if res else None


# ── 1. PAIRED across 27 cells on the holdout ──
print("\n" + "=" * 118)
print("1. PAIRED ACROSS 27 CELLS (3 windows x 3 caps x 3 budgets), HOLDOUT")
print("   bar to clear: %K 14->21 managed 96.2%. 67% and 47% were rejected.")
print("=" * 118)
cells = list(itertools.product(WINDOWS, CAPS, BUDGETS))
base = {c: score("DEFAULT", "hold", *c) for c in cells}
summary = []
for vname, _ in VARIANTS[1:]:
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
    n = len(dm)
    summary.append(dict(variant=vname, n=n,
                        mean_wins=f"{wins}/{n}", mean_pct=round(100*wins/n),
                        med_wins=f"{wmed}/{n}",
                        d_mean=round(float(np.median(dm))),
                        d_med=round(float(np.median(dmed))),
                        d_bust=round(float(np.median(dbust)), 1)))
    print(f"  {vname:<20} mean wins {wins:>2}/{n} ({100*wins/n:>3.0f}%)  "
          f"median wins {wmed:>2}/{n}  d_mean ${np.median(dm):>+6.0f}  "
          f"d_med ${np.median(dmed):>+6.0f}  d_bust {np.median(dbust):>+5.1f}")

pd.DataFrame(summary).to_csv("verify_params_paired.csv", index=False)

# ── 2. PER YEAR at the recommended cell ──
print("\n" + "=" * 118)
print("2. PER YEAR at cap 440 / budget 300 / 9:45-11:00 (holdout mean $)")
print("=" * 118)
CELL = ((9.75, 11.0), 440, 300)
hdr = f"  {'variant':<20}" + "".join(f"{y:>9}" for y in (2022, 2023, 2024, 2025, 2026)) \
      + f"{'yrs>base':>10}"
print(hdr)
base_yr = {y: score("DEFAULT", f"y{y}", *CELL, horizon=180) for y in (2022, 2023, 2024, 2025, 2026)}
for vname, _ in VARIANTS:
    vals, better = [], 0
    for y in (2022, 2023, 2024, 2025, 2026):
        r = score(vname, f"y{y}", *CELL, horizon=180)
        m = r["mean"] if r else 0
        vals.append(m)
        if vname != "DEFAULT" and base_yr[y] and m > base_yr[y]["mean"]:
            better += 1
    print(f"  {vname:<20}" + "".join(f"{v:>9,.0f}" for v in vals)
          + (f"{better:>10}/5" if vname != "DEFAULT" else f"{'—':>11}"))

# ── 3. RECENT 5 MONTHS ──
print("\n" + "=" * 118)
print("3. RECENT 5 MONTHS (untouched by the parameter search), cap440/bud300")
print("=" * 118)
for vname, _ in VARIANTS:
    r = score(vname, "recent", *CELL)
    if r:
        print(f"  {vname:<20} paid {r['paid']:>5.1f}%  bust {r['bust']:>4.1f}%  "
              f"mean ${r['mean']:>6,.0f}  med ${r['med']:>6,.0f}  days {r['days']}")

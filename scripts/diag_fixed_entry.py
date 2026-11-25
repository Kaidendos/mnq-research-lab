"""If the signal bar is worse than a random bar, what IS the right bar?

`diag_entry_edge.py` showed the entry trigger loses to random bar selection in
59 of 60 comparisons. Crucially, the randomisation preserves the per-session fire
COUNT, so it preserves WHICH SESSIONS trade and only destroys WHICH BAR. The
finding is therefore precise:

    the day-selection may carry value; the intraday bar-selection destroys it.

That points at a concrete alternative rather than just a negative: keep whatever
the signal says about the day, throw away its opinion about the minute, and enter
at a fixed clock time instead. "Random" is an average over bars and not tradable;
a fixed time is.

Compared on identical sessions and identical trade counts:
    signal   the entry bar the rule actually picks          (the incumbent)
    random   a uniformly random eligible bar                (the control)
    first    the first eligible bar of the window (09:45)   (tradable)
    t1000    the bar nearest 10:00                          (tradable)
    t1030    the bar nearest 10:30                          (tradable)

Points per trade, no fees, no sizing, no account rules.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import funded_search as fs
import funded_1yr as f1
import lucid_fast as LF
from bog_control import randomise

WIN, SL, TP = (9.75, 11.0), 2.0, 3.0
PAIR = ("sr_round100_break", "vol_lw_stretch_short")

df = fs.load_enriched()
pl = f1.load_plugins(df)
end = df.index[-1]
hold = df[df.index < end - pd.DateOffset(months=5)]
day_ids = pd.factorize(hold["_day"])[0]
eth = hold["eth"].to_numpy(float)
elig = (eth >= WIN[0]) & (eth <= WIN[1]) & (hold["atr"].to_numpy(float) > 0)


def get(name):
    e, _ = pl[name] if name in pl else fs.sig(df, name)
    return pd.Series(e).reindex(hold.index).fillna(False).to_numpy(bool)


def at_clock(mask, target):
    """Same per-session fire count, but placed at the bars nearest `target`."""
    out = np.zeros(len(mask), bool)
    starts = np.flatnonzero(np.r_[True, day_ids[1:] != day_ids[:-1]])
    ends = np.r_[starts[1:], len(mask)]
    for s, e in zip(starts, ends):
        slot = np.flatnonzero(elig[s:e])
        k = int((mask[s:e] & elig[s:e]).sum())
        if k and len(slot):
            order = np.argsort(np.abs(eth[s + slot] - target), kind="stable")
            out[s + slot[np.sort(order[:min(k, len(slot))])]] = True
    return out


def points(el, es):
    P = LF.prep(hold, el, es, WIN)
    hi, lo, cl, atr, ethv = P["hi"], P["lo"], P["cl"], P["atr"], P["eth"]
    tot, n, wins = 0.0, 0, 0
    for s, e, idxs, sides in P["per"]:
        j, today = 0, 0
        while j < len(idxs) and today < 6:
            i, sd = idxs[j], int(sides[j])
            a, entry = atr[i], cl[i]
            stop_px, targ_px = entry - sd * a * SL, entry + sd * a * TP
            px, m = None, i + 1
            while m < e:
                if sd > 0:
                    if lo[m] <= stop_px: px = stop_px; break
                    if hi[m] >= targ_px: px = targ_px; break
                else:
                    if hi[m] >= stop_px: px = stop_px; break
                    if lo[m] <= targ_px: px = targ_px; break
                if ethv[m] >= 16.0 or m == e - 1:
                    px = cl[m]; break
                m += 1
            if px is None:
                px, m = cl[e - 1], e - 1
            r = sd * (px - entry)
            tot += r; n += 1; wins += r > 0; today += 1
            while j < len(idxs) and idxs[j] <= m:
                j += 1
    return tot / max(n, 1), n, 100 * wins / max(n, 1)


rl, rs = get(PAIR[0]), get(PAIR[1])
rows = []

ppt, n, w = points(rl, rs)
rows.append(("signal (incumbent)", ppt, n, w))

rnd = [points(randomise(rl, day_ids, np.random.default_rng(s), elig),
              randomise(rs, day_ids, np.random.default_rng(s), elig))
       for s in range(10)]
rows.append(("random (control)", float(np.median([r[0] for r in rnd])),
             int(np.median([r[1] for r in rnd])),
             float(np.median([r[2] for r in rnd]))))

for label, t in (("first bar 09:45", 9.75), ("10:00", 10.0), ("10:30", 10.5)):
    ppt, n, w = points(at_clock(rl, t), at_clock(rs, t))
    rows.append((f"fixed {label}", ppt, n, w))

print("=" * 96)
print("ENTRY BAR SELECTION — identical sessions, identical trade counts")
print(f"holdout 2021-2026, {WIN[0]}-{WIN[1]}, SL{SL}/TP{TP}, points per trade")
print("=" * 96)
print(f"  {'entry rule':<24}{'pts/trade':>12}{'trades':>9}{'win%':>8}")
for label, ppt, n, w in rows:
    print(f"  {label:<24}{ppt:>+12.2f}{n:>9}{w:>8.1f}")
print("\n  A fixed clock time is tradable; 'random' is not. If a fixed time matches")
print("  or beats the signal, the entry rule is contributing nothing and the")
print("  simpler rule should replace it.")

"""Does the entry TIMING add anything, once drift and trade count are held fixed?

`diag_control.py` found, with in-window signal count AND trade count matched:

    REAL   799 trades  win 50.2%  +12.25 pts/trade
    RND0   799 trades  win 56.4%  +24.40 pts/trade
    RND1   791 trades  win 55.6%  +22.48 pts/trade
    RND2   791 trades  win 54.6%  +22.96 pts/trade

i.e. randomising WHICH BAR is entered, while keeping how many, which side, and
when in the session, roughly DOUBLES the return. That says the entry rule is worse
than a coin flip at picking bars.

The likely mechanism: the book is 78% long by signal count, and MNQ trends up over
most of the holdout, so a long-biased position with a 3:2 reward:risk earns from
DRIFT no matter when it is opened. `sr_round100_break` buys closes above round
numbers — local highs — which is a systematically bad moment to open a long that
would otherwise profit from drift.

This is too important to accept on 3 seeds at one bracket. Confirmed here across:
  - 10 seeds, so the real value can be placed in the random distribution
  - each side separately, because a long-only artifact and a genuine two-sided
    failure are different diagnoses
  - each year, because one bad year could carry it
  - a second bracket, in case 2.0/3.0 is special

No account rules anywhere here — pure points per trade. The account simulator is
deliberately excluded so this cannot be another simulator artifact.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import funded_search as fs
import funded_1yr as f1
import lucid_fast as LF
from bog_control import randomise

WIN = (9.75, 11.0)
PAIR = ("sr_round100_break", "vol_lw_stretch_short")
SEEDS = range(10)

df = fs.load_enriched()
pl = f1.load_plugins(df)
end = df.index[-1]
hold = df[df.index < end - pd.DateOffset(months=5)]


def get(frame, name):
    e, _ = pl[name] if name in pl else fs.sig(df, name)
    return pd.Series(e).reindex(frame.index).fillna(False).to_numpy(bool)


def points(frame, el, es, sl, tp):
    """Total points and trade count. No sizing, no account rules, no fees."""
    P = LF.prep(frame, el, es, WIN)
    hi, lo, cl, atr, ethv = P["hi"], P["lo"], P["cl"], P["atr"], P["eth"]
    tot, n, wins = 0.0, 0, 0
    for s, e, idxs, sides in P["per"]:
        j, today = 0, 0
        while j < len(idxs) and today < 6:
            i, sd = idxs[j], int(sides[j])
            a = atr[i]
            entry = cl[i]
            stop_px, targ_px = entry - sd * a * sl, entry + sd * a * tp
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
    return tot, n, wins


def compare(frame, label, sl=2.0, tp=3.0, sides="both"):
    day_ids = pd.factorize(frame["_day"])[0]
    eth = frame["eth"].to_numpy(float)
    elig = (eth >= WIN[0]) & (eth <= WIN[1]) & (frame["atr"].to_numpy(float) > 0)
    rl, rs = get(frame, PAIR[0]), get(frame, PAIR[1])
    if sides == "long":
        rs = np.zeros_like(rs)
    elif sides == "short":
        rl = np.zeros_like(rl)

    t, n, w = points(frame, rl, rs, sl, tp)
    real_ppt = t / max(n, 1)
    rnd = []
    for seed in SEEDS:
        rng = np.random.default_rng(seed)
        a = randomise(rl, day_ids, rng, elig) if rl.any() else rl
        b = randomise(rs, day_ids, rng, elig) if rs.any() else rs
        tt, nn, ww = points(frame, a, b, sl, tp)
        rnd.append(tt / max(nn, 1))
    rnd = np.array(rnd)
    beat = int((rnd >= real_ppt).sum())
    print(f"  {label:<26} trades={n:>5}  real={real_ppt:>+7.2f}  "
          f"rnd_med={np.median(rnd):>+7.2f}  rnd_min={rnd.min():>+7.2f}  "
          f"rnd_max={rnd.max():>+7.2f}   seeds beating real: {beat}/{len(rnd)}")
    return real_ppt, rnd


print("=" * 118)
print("POINTS PER TRADE — real entry timing vs the same trades at random bars")
print("(no fees, no sizing, no account rules — pure entry quality)")
print("=" * 118)
print("\n  ## BOTH SIDES, SL2.0/TP3.0")
compare(hold, "holdout 2021-2026")
print("\n  ## EACH SIDE ALONE")
compare(hold, "LONG only (sr_round100)", sides="long")
compare(hold, "SHORT only (lw_stretch)", sides="short")
print("\n  ## A SECOND BRACKET, in case 2.0/3.0 is special")
compare(hold, "SL2.0/TP1.5", sl=2.0, tp=1.5)
compare(hold, "SL1.0/TP1.5", sl=1.0, tp=1.5)
print("\n  ## PER YEAR (both sides, SL2.0/TP3.0)")
for y in sorted(df.index.year.unique()):
    sub = df[df.index.year == y]
    if len(sub) < 4000:
        continue
    compare(sub, f"year {y}")

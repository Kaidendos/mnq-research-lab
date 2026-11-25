"""THE decisive test: does the signal contribute anything, or is this pure drift?

`diag_fixed_entry.py` found that entering at the 09:45 bar — on the sessions and
in the directions the signal picks — returns +39.38 pts/trade against the signal's
own +12.25. That leaves exactly one question worth asking, and it decides whether
there is a strategy here at all:

    Is "09:45 on SIGNAL days, in the SIGNAL's direction" any better than
    "09:45 EVERY day, always long"?

If they match, the signal contributes nothing: the whole result is MNQ drifting up
while a 3:2 bracket sits on it. Drift harvesting is not fundable against a $1,000
trailing drawdown — one bad month ends the account, and there is no edge to recover
with. If signal-days genuinely beat all-days, then the day/direction filter is the
real asset and the entry TRIGGER was just noise on top of it.

Everything is measured five ways, because a positive here would be the first
survivor in this whole project and must not be another single-cell artifact:
  A  selection   — signal days/direction vs all days, matched entry bar
  B  costs       — fees and slippage, which nothing above has charged
  C  out-of-sample — the last 5 months, untouched by any of this
  D  control     — random bar, same days, using the FIXED randomiser
  E  benchmark   — raw drift: what the market gave from 09:45 to the close
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import funded_search as fs
import funded_1yr as f1
import lucid_fast as LF
from bog_control import randomise

WIN, SL, TP = (9.75, 11.0), 2.0, 3.0
LONG_SIG, SHORT_SIG = "sr_round100_break", "vol_lw_stretch_short"
FEE_PTS = 1.22 / 2.0             # $1.22 round-turn at $2/pt
TICK_PTS = 0.25

df = fs.load_enriched()
pl = f1.load_plugins(df)
end = df.index[-1]
cut = end - pd.DateOffset(months=5)
FRAMES = (("holdout", df[df.index < cut]), ("recent 5mo (OOS)", df[df.index >= cut]))


def sig_of(frame, name):
    e, _ = pl[name] if name in pl else fs.sig(df, name)
    return pd.Series(e).reindex(frame.index).fillna(False).to_numpy(bool)


def session_bounds(frame):
    d = pd.factorize(frame["_day"])[0]
    starts = np.flatnonzero(np.r_[True, d[1:] != d[:-1]])
    return starts, np.r_[starts[1:], len(d)], d


def first_bar_masks(frame, mode):
    """Build long/short entry masks that all fire on the 09:45 bar.

    mode:
      sig_days_sig_dir  — only sessions the signal fired, its direction
      sig_days_long     — only those sessions, always long
      all_days_long     — every session, long
      all_days_short    — every session, short
    """
    starts, ends, _ = session_bounds(frame)
    eth = frame["eth"].to_numpy(float)
    ok = (eth >= WIN[0]) & (eth <= WIN[1]) & (frame["atr"].to_numpy(float) > 0)
    sl_, ss_ = sig_of(frame, LONG_SIG), sig_of(frame, SHORT_SIG)
    el = np.zeros(len(eth), bool)
    es = np.zeros(len(eth), bool)
    for s, e in zip(starts, ends):
        slot = np.flatnonzero(ok[s:e])
        if not len(slot):
            continue
        b = s + slot[0]                       # the 09:45 bar
        had_l = bool((sl_[s:e] & ok[s:e]).any())
        had_s = bool((ss_[s:e] & ok[s:e]).any())
        if mode == "sig_days_sig_dir":
            # if both fired, take whichever fired first that session
            if had_l and had_s:
                fl = np.flatnonzero(sl_[s:e] & ok[s:e])[0]
                fsh = np.flatnonzero(ss_[s:e] & ok[s:e])[0]
                (el if fl <= fsh else es)[b] = True
            elif had_l:
                el[b] = True
            elif had_s:
                es[b] = True
        elif mode == "sig_days_long":
            if had_l or had_s:
                el[b] = True
        elif mode == "all_days_long":
            el[b] = True
        elif mode == "all_days_short":
            es[b] = True
    return el, es


def points(frame, el, es, cost_pts=0.0):
    P = LF.prep(frame, el, es, WIN)
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
            r = sd * (px - entry) - cost_pts
            tot += r; n += 1; wins += r > 0; today += 1
            while j < len(idxs) and idxs[j] <= m:
                j += 1
    return dict(ppt=tot / max(n, 1), total=tot, n=n, win=100 * wins / max(n, 1))


MODES = [("signal days, signal direction", "sig_days_sig_dir"),
         ("signal days, always LONG", "sig_days_long"),
         ("EVERY day, always LONG", "all_days_long"),
         ("EVERY day, always SHORT", "all_days_short")]

print("=" * 104)
print("A. SELECTION — all entries on the 09:45 bar, same bracket. Does the signal matter?")
print("=" * 104)
for fname, frame in FRAMES:
    print(f"\n  ### {fname}")
    print(f"  {'rule':<34}{'pts/trade':>11}{'total pts':>12}{'trades':>9}{'win%':>8}")
    for label, mode in MODES:
        el, es = first_bar_masks(frame, mode)
        r = points(frame, el, es)
        print(f"  {label:<34}{r['ppt']:>+11.2f}{r['total']:>+12.0f}"
              f"{r['n']:>9}{r['win']:>8.1f}")

print("\n" + "=" * 104)
print("B. COSTS — fees plus slippage, on the holdout")
print("=" * 104)
print(f"  {'rule':<34}{'gross':>10}{'+fees':>10}{'+1 tick':>10}{'+2 ticks':>11}")
hold = FRAMES[0][1]
for label, mode in MODES[:3]:
    el, es = first_bar_masks(hold, mode)
    vals = [points(hold, el, es, c)["ppt"] for c in
            (0.0, FEE_PTS, FEE_PTS + 2 * TICK_PTS, FEE_PTS + 4 * TICK_PTS)]
    print(f"  {label:<34}" + "".join(f"{v:>+10.2f}" for v in vals[:3])
          + f"{vals[3]:>+11.2f}")

print("\n" + "=" * 104)
print("D. CONTROL — 09:45 bar vs a RANDOM bar, on the same days (fixed randomiser)")
print("=" * 104)
for label, mode in MODES[:3]:
    el, es = first_bar_masks(hold, mode)
    day_ids = pd.factorize(hold["_day"])[0]
    eth = hold["eth"].to_numpy(float)
    elig = (eth >= WIN[0]) & (eth <= WIN[1]) & (hold["atr"].to_numpy(float) > 0)
    fixed = points(hold, el, es)["ppt"]
    rnd = []
    for s in range(10):
        rng = np.random.default_rng(s)
        rnd.append(points(hold, randomise(el, day_ids, rng, elig),
                          randomise(es, day_ids, rng, elig))["ppt"])
    rnd = np.array(rnd)
    print(f"  {label:<34} 09:45 {fixed:>+8.2f}   random med {np.median(rnd):>+8.2f}"
          f"   seeds beating 09:45: {int((rnd >= fixed).sum())}/10")

print("\n" + "=" * 104)
print("E. BENCHMARK — raw drift, no bracket: hold from the 09:45 bar to the close")
print("=" * 104)
for fname, frame in FRAMES:
    starts, ends, _ = session_bounds(frame)
    eth = frame["eth"].to_numpy(float)
    cl = frame["close"].to_numpy(float)
    ok = (eth >= WIN[0]) & (eth <= WIN[1])
    moves = []
    for s, e in zip(starts, ends):
        slot = np.flatnonzero(ok[s:e])
        if len(slot):
            moves.append(cl[e - 1] - cl[s + slot[0]])
    m = np.array(moves)
    print(f"  {fname:<20} sessions={len(m):>5}  mean move {m.mean():>+8.2f} pts  "
          f"median {np.median(m):>+7.2f}  up-days {100*(m > 0).mean():.1f}%")

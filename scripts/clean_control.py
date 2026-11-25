"""A control that does not hand the random arm information the real arm lacks.

Two problems surfaced in sequence, and the second invalidates the first's verdict:

1. The "+39 pts/trade by entering at 09:45" replacement was LOOKAHEAD. It placed
   the entry on the 09:45 bar in the direction of a signal that, 84.4% of the time,
   had not fired yet (median 15 minutes later). Dead — not a candidate.

2. `randomise()` preserves the PER-SESSION fire count, so the random arm knows
   WHICH SESSIONS will produce signals and only has to guess the bar. The real
   strategy has no such knowledge. Knowing a session will produce a breakout is
   knowing it is a trending, volatile day — a real advantage. So "random beats
   real 59/60" was measured with the control arm holding a better hand, and it
   overstates the case against the signal.

THE CLEAN CONTROL: permute the per-session signal profile ACROSS sessions, then
place each session's entries at random eligible bars. Total trades, the
distribution of trades-per-session, and the long/short mix are all preserved
exactly; what is destroyed is WHICH sessions trade and WHICH bar — i.e. everything
the signal actually claims to know, and nothing else.

Read it as:
  real >> clean random  -> the signal has an edge, mostly in picking the session
  real ~= clean random  -> no edge; the earlier verdict stands for the right reason
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import funded_search as fs
import funded_1yr as f1
import lucid_fast as LF

WIN, SL, TP = (9.75, 11.0), 2.0, 3.0
LONG_SIG, SHORT_SIG = "sr_round100_break", "vol_lw_stretch_short"
SEEDS = range(20)

df = fs.load_enriched()
pl = f1.load_plugins(df)
end = df.index[-1]
cut = end - pd.DateOffset(months=5)


def build(frame):
    d = pd.factorize(frame["_day"])[0]
    starts = np.flatnonzero(np.r_[True, d[1:] != d[:-1]])
    ends = np.r_[starts[1:], len(d)]
    eth = frame["eth"].to_numpy(float)
    ok = (eth >= WIN[0]) & (eth <= WIN[1]) & (frame["atr"].to_numpy(float) > 0)

    def g(n):
        e, _ = pl[n] if n in pl else fs.sig(df, n)
        return pd.Series(e).reindex(frame.index).fillna(False).to_numpy(bool)
    return starts, ends, ok, g(LONG_SIG), g(SHORT_SIG)


def points(frame, el, es):
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
            r = sd * (px - entry)
            tot += r; n += 1; wins += r > 0; today += 1
            while j < len(idxs) and idxs[j] <= m:
                j += 1
    return tot / max(n, 1), n, 100 * wins / max(n, 1), tot


def shuffled(starts, ends, ok, sl_, ss_, rng, keep_sessions):
    """Permute each session's (n_long, n_short) profile across sessions.

    keep_sessions=True reproduces the OLD control (session identity preserved,
    only the bar randomised) so both can be read side by side.
    """
    prof = []
    for s, e in zip(starts, ends):
        prof.append((int((sl_[s:e] & ok[s:e]).sum()),
                     int((ss_[s:e] & ok[s:e]).sum())))
    order = np.arange(len(prof)) if keep_sessions else rng.permutation(len(prof))
    el = np.zeros(len(ok), bool)
    es = np.zeros(len(ok), bool)
    for pos, (s, e) in enumerate(zip(starts, ends)):
        nl, ns = prof[order[pos]]
        slot = np.flatnonzero(ok[s:e])
        need = nl + ns
        if not need or not len(slot):
            continue
        pick = rng.choice(slot, size=min(need, len(slot)), replace=False)
        pick = np.sort(pick)
        for idx, b in enumerate(pick):
            (el if idx < nl else es)[s + b] = True
    return el, es


print("=" * 106)
print("CLEAN CONTROL — does the signal know anything the shuffle does not?")
print(f"{WIN[0]}-{WIN[1]}, SL{SL}/TP{TP}, points per trade, no fees/sizing/account rules")
print("=" * 106)

for fname, frame in (("holdout 2021-2026", df[df.index < cut]),
                     ("recent 5mo (OOS)", df[df.index >= cut])):
    starts, ends, ok, sl_, ss_ = build(frame)
    real_ppt, real_n, real_w, real_tot = points(frame, sl_ & ok, ss_ & ok)
    print(f"\n  ### {fname}")
    print(f"    REAL signal              {real_ppt:>+8.2f} pts/trade   "
          f"{real_n:>5} trades   win {real_w:>5.1f}%   total {real_tot:>+9.0f}")
    for keep, label in ((True, "OLD ctl (same sessions)"), (False, "CLEAN ctl (shuffled)")):
        vals = []
        for s in SEEDS:
            rng = np.random.default_rng(s)
            el, es = shuffled(starts, ends, ok, sl_, ss_, rng, keep)
            vals.append(points(frame, el, es)[0])
        v = np.array(vals)
        beat = int((v >= real_ppt).sum())
        print(f"    {label:<24} {np.median(v):>+8.2f} pts/trade   "
              f"range {v.min():>+7.2f} to {v.max():>+7.2f}   "
              f"seeds beating real: {beat}/{len(v)}")

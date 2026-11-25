"""BEST-OF-GRID RANDOM CONTROL, redone under the corrected account rules.

The version noted in CONTINUE.md ran on the buggy `lucid_fast.evaluate` (the one
whose `days < 20` filter silently deleted every account that busted early) and was
killed. This is the redo. It is the single check standing between the current
recommendation and a fundable decision.

WHY BEST-OF-GRID AND NOT "IS THE WINNER BETTER THAN RANDOM"
-----------------------------------------------------------
Testing a chosen winner against random signals is circular: the winner was chosen
BECAUSE it topped a grid, so of course it beats an unselected random draw. The
honest question is whether the SEARCH PROCEDURE manufactures winners out of noise.
So the entire procedure — same pairings, same bracket grid, same metric, same
"take the maximum" — is applied to random signals, and the real maximum is
compared against the distribution of random maxima.

If the real winner sits inside the random max distribution, it is a search
artifact. If it sits well outside, the edge is real.

RANDOMISATION
-------------
Each random signal preserves its real counterpart's PER-SESSION fire count and
places those fires at uniformly random bars within the same session. That keeps
fire rate, session coverage and clustering-by-day intact, so the only thing
destroyed is WHICH bar — i.e. the timing edge, which is exactly the thing under
test. Randomising fire count as well would make the control too easy to beat.

Usage:  python bog_control.py --seed 0 --out bogc_0.csv
        (writes incrementally; one process per seed)
"""
from __future__ import annotations

import argparse
import itertools
import os

import numpy as np
import pandas as pd

import funded_search as fs
import funded_1yr as f1
import sim_trace as ST

REAL_L = ["sr_round100_break", "ema20_50_long", "mf_wkpiv_long", "so_k21_th30",
          "tt_turtle_s2_long", "wy_lps_long"]
REAL_S = ["vol_lw_stretch_short", "lw_oops_short", "pdh_fade_short",
          "lr_raschke_firstcross_short", "ww_volsys_short", "bb_break_short"]

WINS = ((9.75, 11.0), (9.75, 12.0), (9.75, 15.5))
BRACKETS = ((2.0, 3.0), (2.0, 1.5), (1.5, 2.0))
SIZES = ((440, 300), (250, 400))
STRIDE = 8


def randomise(mask, day_ids, rng, eligible):
    """Same number of fires per session INSIDE `eligible`, at random eligible bars.

    ⚠ BUG FOUND 2026-08-09 — the first version scattered fires across the WHOLE
    session and let `LF.prep` filter them to the window afterwards. Real signals
    are concentrated in the morning, so that halved the randomised in-window trade
    count (sr_round100_break 782 -> 432, vol_lw_stretch_short 225 -> 107). Trade
    count is not a neutral variable here: with the $1,000 MLL bounding the
    downside and floor-aware sizing shrinking positions near the floor, trading
    LESS is a large structural advantage. The control was therefore comparing
    "real signal, N trades" against "random signal, N/2 trades" and every random
    seed 'won' — an artifact of exposure, not evidence about timing.

    Randomising only among bars the window would have accepted holds the in-window
    count fixed, so the ONLY thing destroyed is which bar — which is the thing
    under test.
    """
    out = np.zeros(len(mask), bool)
    starts = np.flatnonzero(np.r_[True, day_ids[1:] != day_ids[:-1]])
    ends = np.r_[starts[1:], len(mask)]
    for s, e in zip(starts, ends):
        slot = np.flatnonzero(eligible[s:e])
        k = int((mask[s:e] & eligible[s:e]).sum())
        if k and len(slot):
            out[s + rng.choice(slot, size=min(k, len(slot)), replace=False)] = True
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    df = fs.load_enriched()
    pl = f1.load_plugins(df)
    end = df.index[-1]
    hold = df[df.index < end - pd.DateOffset(months=5)]
    day_ids = pd.factorize(hold["_day"])[0]

    def real(name):
        e, _ = pl[name] if name in pl else fs.sig(df, name)
        return pd.Series(e).reindex(hold.index).fillna(False).to_numpy(bool)

    import lucid_fast as LF

    real_l = {n: real(n) for n in REAL_L}
    real_s = {n: real(n) for n in REAL_S}
    eth = hold["eth"].to_numpy(float)
    atr_ok = (hold["atr"].to_numpy(float) > 0)
    tag = "REAL" if args.seed < 0 else f"RND{args.seed}"

    # Randomisation is per WINDOW, because eligibility depends on the window —
    # doing it once for all windows is what produced the invalid first run.
    # Built ONCE per window here rather than inside the pair loop, which would
    # redo 1,296 identical randomisations.
    def signals_for(win):
        if args.seed < 0:
            return real_l, real_s
        rng = np.random.default_rng(args.seed)
        elig = (eth >= win[0]) & (eth <= win[1]) & atr_ok
        return ({f"rnd_l{i}": randomise(v, day_ids, rng, elig)
                 for i, v in enumerate(real_l.values())},
                {f"rnd_s{i}": randomise(v, day_ids, rng, elig)
                 for i, v in enumerate(real_s.values())})

    BY_WIN = {win: signals_for(win) for win in WINS}

    # Fail loudly rather than silently producing another invalid run: the whole
    # point of the fix is that in-window fire counts match the real signals.
    for win in WINS:
        longs, shorts = BY_WIN[win]
        elig = (eth >= win[0]) & (eth <= win[1]) & atr_ok
        for got, want in ((longs, real_l), (shorts, real_s)):
            for (gn, gv), rv in zip(got.items(), want.values()):
                a, b = int(gv[elig].sum()), int(rv[elig].sum())
                if a != b:
                    raise SystemExit(
                        f"CONTROL INVALID: {gn} has {a} in-window fires vs the "
                        f"real signal's {b} at window {win}. Fix before running.")
    print(f"  in-window fire counts matched for all {len(WINS)} windows", flush=True)

    first = not os.path.exists(args.out)
    pair_names = list(itertools.product(range(len(REAL_L)), range(len(REAL_S))))
    for li, si in pair_names:
        rows = []
        for win in WINS:
            longs, shorts = BY_WIN[win]
            ln, lv = list(longs.items())[li]
            sn, sv = list(shorts.items())[si]
            P = LF.prep(hold, lv, sv, win)
            starts = [k for k in range(0, len(P["per"]), STRIDE)
                      if len(P["per"]) - k >= 20]
            for (sl, tp), (cap, bud) in itertools.product(BRACKETS, SIZES):
                res = [ST.trace(P, k, cap, bud, sl=sl, tp=tp) for k in starts]
                rows.append(dict(tag=tag, long=ln, short=sn,
                                 win=f"{win[0]}-{win[1]}", sl=sl, tp=tp,
                                 cap=cap, budget=bud,
                                 n_sig=int(lv.sum() + sv.sum()),
                                 **ST.summarise(res)))
        pd.DataFrame(rows).to_csv(args.out, mode="a", header=first, index=False)
        first = False
        print(f"  {tag} pair {li},{si}", flush=True)


if __name__ == "__main__":
    main()

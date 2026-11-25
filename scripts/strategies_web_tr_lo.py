"""BUYING THE LOW / SELLING THE HIGH — a mean-reversion family, both sides.

Area: lo (longs at lows) and hi (shorts at highs). The registry is dominated by
breakout and momentum logic; the only true fades in it are a handful of short
signals. This adds a systematic pass at the opposite idea: enter AGAINST the move
once it has exhausted, on both sides, so the pair can be tested as a two-sided
fade system rather than the breakout system currently in use.

WHAT "BUYING THE LOW" CAN AND CANNOT MEAN
-----------------------------------------
There is no causal rule that buys THE low — the low is only identifiable after the
fact, and any signal that appears to catch it exactly is reading the future. What is
causal is buying AFTER a low has been made and REJECTED: price extends, fails to
hold, and closes back. Every rule below fires on a bar that has already closed, at
a price a live trader could pay.

This distinction is the single most common lookahead bug in mean-reversion work, and
this project has already produced one (an "enter at 09:45 in the signal's direction"
rule that front-ran its own signal 84% of the time). `lookahead_audit.py` must pass
on every family here before any result is quoted.

THE STRUCTURAL WARNING, stated before any result is seen
--------------------------------------------------------
MNQ drifts upward across most of the sample. A long-biased rule with a favourable
reward:risk earns from that drift no matter when it opens, so a bottom-buying LONG
book will look profitable for reasons unrelated to its timing. Only the clean
control (`clean_control.py` — permute which session AND which bar) can separate the
two. Raw P&L on these families is expected to be positive and is NOT evidence.

CAUSALITY
---------
Session extremes use `cummin`/`cummax`, which include the current bar and no later
one. Prior-day levels come from `pdh`/`pdl`, already shifted. Rolling windows are
backward-looking. Swing points carry the 2-bar confirmation lag. Every trigger is a
CLOSE through a level, never a touch.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

RSI2_LONG, RSI2_SHORT = 10.0, 90.0     # Connors' extreme-RSI zone
SWEEP_LOOK = 20                        # bars defining the "prior low" to sweep
RECLAIM_BARS = 6                       # bars allowed to reclaim a broken level
CAPIT_RVOL = 1.5
CAPIT_RANGE_ATR = 1.2
STRETCH_K = 0.5                        # same gate the incumbent short uses
EXT_ATR = 1.5                          # "deep" below/above the session open


def _rsi(c, n=2):
    d = c.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


def _reclaim(level, c, side, max_bars=RECLAIM_BARS):
    """Fire on the first close back through `level` after breaking it.

    side=+1: price closed BELOW level, then closes back above (buy the failed
    breakdown). side=-1 is the mirror.
    """
    lv = level.to_numpy(float)
    cl = c.to_numpy(float)
    out = np.zeros(len(cl), bool)
    live, val, age = False, 0.0, 0
    for i in range(len(cl)):
        if live:
            age += 1
            back = cl[i] > val if side > 0 else cl[i] < val
            if back:
                out[i] = True
                live = False
            elif age >= max_bars:
                live = False
        if np.isfinite(lv[i]):
            broke = cl[i] < lv[i] if side > 0 else cl[i] > lv[i]
            if broke and not live:
                live, val, age = True, lv[i], 0
    return pd.Series(out, index=c.index)


def register(df: pd.DataFrame) -> dict:
    h, l, c, o, v = (df["high"], df["low"], df["close"], df["open"], df["volume"])
    atr, day, eth = df["atr"], df["_day"], df["eth"]
    rng = (h - l).replace(0, np.nan)
    rvol = (v / v.rolling(20).mean().shift(1)).fillna(1.0)
    upper_half = c > (h + l) / 2.0
    lower_half = c < (h + l) / 2.0

    run_lo = l.groupby(day).cummin()          # includes current bar only
    run_hi = h.groupby(day).cummax()
    sess_open = o.groupby(day).transform("first")
    prev_range = (df["pdh"] - df["pdl"]).abs()
    bod = df.groupby(day).cumcount()

    out: dict[str, tuple[pd.Series, int]] = {}

    # ── 1. New session low, rejected on the same bar ──
    new_low = (l <= run_lo) & (bod > 0)
    new_high = (h >= run_hi) & (bod > 0)
    out["lo_sesslow_reject_long"] = ((new_low & upper_half & (c > o)).fillna(False), +1)
    out["hi_sesshigh_reject_short"] = ((new_high & lower_half & (c < o)).fillna(False), -1)

    # ── 2. Failed breakdown / breakout of the trailing N-bar extreme ──
    prior_lo = l.rolling(SWEEP_LOOK).min().shift(1)
    prior_hi = h.rolling(SWEEP_LOOK).max().shift(1)
    out["lo_failed_breakdown_long"] = (_reclaim(prior_lo, c, +1), +1)
    out["hi_failed_breakout_short"] = (_reclaim(prior_hi, c, -1), -1)

    # ── 3. Connors RSI(2) at an extreme ──
    r2 = _rsi(c, 2)
    out["lo_rsi2_long"] = (((r2 < RSI2_LONG) & (c > o)).fillna(False), +1)
    out["hi_rsi2_short"] = (((r2 > RSI2_SHORT) & (c < o)).fillna(False), -1)

    # ── 4. Bollinger band tag and close back inside ──
    out["lo_bb_reclaim_long"] = (((l < df["bb_dn"]) & (c > df["bb_dn"])
                                  & upper_half).fillna(False), +1)
    out["hi_bb_reject_short"] = (((h > df["bb_up"]) & (c < df["bb_up"])
                                  & lower_half).fillna(False), -1)

    # ── 5. Fade the Larry Williams stretch gate instead of following it ──
    # The incumbent SHORT sells the first close below `open - 0.5 * prior range`.
    # This buys the reclaim of that same level — deliberately the opposite trade,
    # so the two can be compared directly on identical events.
    gate_dn = sess_open - STRETCH_K * prev_range
    gate_up = sess_open + STRETCH_K * prev_range
    out["lo_stretch_reclaim_long"] = (_reclaim(gate_dn, c, +1) & (bod > 0), +1)
    out["hi_stretch_reject_short"] = (_reclaim(gate_up, c, -1) & (bod > 0), -1)

    # ── 6. Prior-day low swept, then reclaimed ──
    out["lo_pdl_reclaim_long"] = (_reclaim(df["pdl"], c, +1), +1)
    out["hi_pdh_reject_short"] = (_reclaim(df["pdh"], c, -1), -1)

    # ── 7. Opening-range extreme swept, then reclaimed ──
    ready = df["or30_ready"].astype(bool)
    out["lo_orlow_reclaim_long"] = (_reclaim(df["or30_lo"].where(ready), c, +1), +1)
    out["hi_orhigh_reject_short"] = (_reclaim(df["or30_hi"].where(ready), c, -1), -1)

    # ── 8. Capitulation: heavy volume, wide bar, close rejecting the extreme ──
    wide = (rng / atr) >= CAPIT_RANGE_ATR
    out["lo_capitulation_long"] = (((c < o) & wide & (rvol >= CAPIT_RVOL)
                                    & (c > l + 0.6 * rng)).fillna(False), +1)
    out["hi_blowoff_short"] = (((c > o) & wide & (rvol >= CAPIT_RVOL)
                                & (c < h - 0.6 * rng)).fillna(False), -1)

    # ── 9. Three lower lows, then a close above the prior bar's high ──
    three_dn = (l < l.shift(1)) & (l.shift(1) < l.shift(2)) & (l.shift(2) < l.shift(3))
    three_up = (h > h.shift(1)) & (h.shift(1) > h.shift(2)) & (h.shift(2) > h.shift(3))
    out["lo_3bar_reversal_long"] = ((three_dn.shift(1).fillna(False)
                                     & (c > h.shift(1))).fillna(False), +1)
    out["hi_3bar_reversal_short"] = ((three_up.shift(1).fillna(False)
                                      & (c < l.shift(1))).fillna(False), -1)

    # ── 10. Stretched far from the session open, then closing back ──
    ext = (c - sess_open) / atr.replace(0, np.nan)
    out["lo_extension_long"] = (((ext <= -EXT_ATR) & (c > o) & upper_half
                                 & (bod > 3)).fillna(False), +1)
    out["hi_extension_short"] = (((ext >= EXT_ATR) & (c < o) & lower_half
                                  & (bod > 3)).fillna(False), -1)

    # ── 11. Deep below VWAP, then reclaiming it ──
    vw = df["vwap"]
    deep_lo = ((vw - c) / atr.replace(0, np.nan) >= 1.0)
    deep_hi = ((c - vw) / atr.replace(0, np.nan) >= 1.0)
    out["lo_vwap_reclaim_long"] = ((deep_lo.shift(1).fillna(False)
                                    & (c > vw) & (c.shift(1) <= vw.shift(1))), +1)
    out["hi_vwap_reject_short"] = ((deep_hi.shift(1).fillna(False)
                                    & (c < vw) & (c.shift(1) >= vw.shift(1))), -1)

    return {k: (s.reindex(df.index).fillna(False).astype(bool), side)
            for k, (s, side) in out.items()}

"""EXHAUSTION SHORTS at usable frequency — plus the multi-day washout long I owe.

Area: ex. Two things this session established point straight here:

  1. The SHORT side carries the edge. `vol_lw_stretch_short` scores +20.90 against
     the clean control while the incumbent long scores +4.74.
  2. The highest per-trade edges found anywhere were exhaustion shorts —
     `hi_rsi2_short` +22.56 and `hi_blowoff_short` +14.80 — but on 56 and 48 trades
     across 4.5 years. The concept works; the frequency does not.

So this builds the same idea at looser thresholds, in several independent forms, to
find out whether the edge survives being made frequent enough to matter. If it does
not, that is a clean answer: exhaustion shorts are real but too rare to trade.

Also included is the MULTI-DAY WASHOUT long. `extreme_low.py` tested "really low"
four ways and found the edge worsens monotonically with depth — but its 5-day-low
variant returned ZERO trades because the rolling window included recent bars, so
that concept was left untested rather than rejected. It is the one version of "low"
that means a multi-day washout rather than one bad morning, which is a genuinely
different hypothesis. Built correctly here.

CAUSALITY
---------
Multi-day extremes use a rolling window shifted a full session (78 bars) back, so
"the 5-day low" never includes today. Volume/range baselines exclude the current bar.
Every trigger is a close, never a touch.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

BARS_DAY = 78                 # 5-min RTH bars in one session


def _rsi(s, n):
    d = s.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


def register(df: pd.DataFrame) -> dict:
    h, l, c, o, v = df["high"], df["low"], df["close"], df["open"], df["volume"]
    atr, day = df["atr"], df["_day"]
    rng = (h - l).replace(0, np.nan)
    rvol = (v / v.rolling(20).mean().shift(1)).fillna(1.0)
    bod = df.groupby(day).cumcount()
    sess_open = o.groupby(day).transform("first")
    out: dict[str, tuple[pd.Series, int]] = {}

    # ── A. BLOW-OFF SHORTS at a range of strictnesses ──────────────────────────
    # `hi_blowoff_short` required range >= 1.2 ATR AND rvol >= 1.5 AND close in the
    # bottom 40% — three simultaneous conditions, hence 48 trades. Each is relaxed
    # separately so it is visible WHICH condition was doing the work.
    up_bar = c > o
    reject_hi = c < h - 0.5 * rng
    wide12, wide08, wide06 = (rng / atr >= 1.2), (rng / atr >= 0.8), (rng / atr >= 0.6)
    for tag, wide, rv in (("strict", wide12, 1.5), ("mid", wide08, 1.2),
                          ("loose", wide06, 1.0)):
        out[f"ex_blowoff_{tag}_short"] = (
            ((up_bar & wide & (rvol >= rv) & reject_hi)).fillna(False), -1)
    # volume dropped entirely — was RVOL the binding filter?
    out["ex_blowoff_novol_short"] = ((up_bar & wide08 & reject_hi).fillna(False), -1)

    # ── B. RSI EXTREME SHORTS with longer lookbacks ────────────────────────────
    # RSI(2) > 90 fires 56 times. A longer RSI reaches its extreme more often
    # because it is smoother, so the same idea should be tradable at RSI(5)/RSI(9).
    for n, th in ((2, 88.0), (3, 88.0), (5, 85.0), (9, 80.0), (14, 75.0)):
        r = _rsi(c, n)
        out[f"ex_rsi{n}_short"] = (((r > th) & (c < o)).fillna(False), -1)

    # ── C. CONSECUTIVE UP-CLOSES THEN A DOWN CLOSE ─────────────────────────────
    upc = (c > c.shift(1))
    for k in (3, 4, 5):
        streak = upc.shift(1).rolling(k).min().fillna(0).astype(bool)
        out[f"ex_streak{k}_short"] = ((streak & (c < o) & (bod > k)).fillna(False), -1)

    # ── D. STRETCHED ABOVE THE SESSION OPEN, THEN CLOSING DOWN ─────────────────
    ext = (c - sess_open) / atr.replace(0, np.nan)
    for th in (1.0, 1.5, 2.0):
        out[f"ex_stretch{th}_short"] = (
            ((ext >= th) & (c < o) & (bod > 3)).fillna(False), -1)

    # ── E. MULTI-DAY WASHOUT LONG — the concept left untested ──────────────────
    # `.shift(BARS_DAY)` puts the whole window in PRIOR sessions, so "the 5-day low"
    # cannot include today. The earlier attempt shifted by 1 bar, so today's own low
    # was inside the window and "close below the 5-day low" could never fire.
    for nd in (3, 5, 10):
        prior_lo = l.rolling(nd * BARS_DAY).min().shift(BARS_DAY)
        prior_hi = h.rolling(nd * BARS_DAY).max().shift(BARS_DAY)
        depth = (prior_lo - c) / atr.replace(0, np.nan)
        # below a multi-day low, then closing UP off it — a washout being rejected
        out[f"ex_washout{nd}d_long"] = (
            ((c < prior_lo) & (c > o) & (c > (h + l) / 2)).fillna(False), +1)
        # the deep version: not just below, but well below
        out[f"ex_washout{nd}d_deep_long"] = (
            ((depth >= 0.5) & (c > o)).fillna(False), +1)
        # mirror: pushing to a multi-day HIGH then closing down
        out[f"ex_blowout{nd}d_short"] = (
            ((c > prior_hi) & (c < o) & (c < (h + l) / 2)).fillna(False), -1)

    return {k: (s.reindex(df.index).fillna(False).astype(bool), side)
            for k, (s, side) in out.items()}

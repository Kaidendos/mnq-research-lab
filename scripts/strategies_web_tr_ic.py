"""ICT / Michael Huddleston — Silver Bullet, FVG, liquidity sweep + MSS.

Area: ic.  Included on reach, not on record: ICT's own results are not audited
and the material is taught, not traded publicly. What earns it a slot is that the
rules are unusually mechanical for discretionary-flavoured teaching, and one of
them names a fixed clock window (10:00-11:00 ET) that sits inside the 9:45-11:00
window this project independently found to hold the edge. If the concepts are
worth anything, that overlap should show up. If they are worth nothing, this
tests a very popular method and returns a clean negative.

RULES, as published
-------------------
https://www.ictkillzone.com/ict-silver-bullet
https://forexbee.co/ict-silver-bullet-trading-strategy/
  "The ICT Silver Bullet targets three specific one-hour windows: 3:00-4:00 AM
   EST, 10:00-11:00 AM EST (New York AM, highest probability), 2:00-3:00 PM EST."
  "Within each window, the setup requires a liquidity sweep followed by a
   displacement that creates a Fair Value Gap, entered at the 50% level on the
   retracement."
  "If there is no market structure shift, then there is strictly no opportunity
   for trading Silver Bullet. This rule is non-negotiable."

Translated to three testable objects:
  FVG            bullish 3-bar gap: low[i] > high[i-2], i.e. an untraded band.
  LIQUIDITY SWEEP price takes out a prior swing low, then closes back above it.
  MSS            after the sweep, close breaks the most recent confirmed swing high.

CAUSALITY
---------
Swing points are confirmed with a 2-bar lag (`.shift(2)`) — an unconfirmed swing
is the classic lookahead bug in this family, because a "swing high" is only a
swing high once two later bars have failed to exceed it. FVGs are read from bars
i-2..i, all closed. Entry is on a CLOSE back inside the gap, never on a touch.

READING: ICT teaches entry at the 50% level of the FVG via limit order. A limit
fill cannot be modelled honestly on 5-min OHLC, so entry here is the close of the
first bar that trades back into the gap. That is strictly WORSE than his stated
fill, which is the right direction for a test to err.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

SWING_N = 2          # bars either side that define a swing (ICT's "short-term high/low")
SB_START, SB_END = 10.0, 11.0    # published New York AM Silver Bullet window
FVG_MAX_AGE = 12     # READING: how long an unfilled FVG stays tradable (1 hour)
SWEEP_LOOKBACK = 24  # READING: how far back a "prior low" can be to count as liquidity


def _swings(h, l, n):
    """Confirmed swing highs/lows, lagged so they are only known after the fact."""
    hh = h.rolling(2 * n + 1, center=True).max()
    ll = l.rolling(2 * n + 1, center=True).min()
    is_hi = (h == hh)
    is_lo = (l == ll)
    # center=True peeks n bars forward; shift(n) moves confirmation to the bar
    # where it is actually knowable.
    return is_hi.shift(n).fillna(False), is_lo.shift(n).fillna(False)


def _last_level(flag, price, n):
    """Value of `price` at the most recent True in `flag`, as of each bar."""
    lv = price.shift(n).where(flag)
    return lv.ffill()


def register(df: pd.DataFrame) -> dict:
    h, l, c, o = df["high"], df["low"], df["close"], df["open"]
    eth = df["eth"]
    idx = df.index

    is_hi, is_lo = _swings(h, l, SWING_N)
    sw_hi = _last_level(is_hi, h, SWING_N)
    sw_lo = _last_level(is_lo, l, SWING_N)

    # ── Fair Value Gap: bullish when bar i-2's high is below bar i's low ──
    gap_dn_edge = h.shift(2)          # bullish FVG lower edge
    gap_up_edge = l                   # bullish FVG upper edge
    bull_fvg = gap_up_edge > gap_dn_edge
    bear_fvg = h < l.shift(2)
    bear_lo, bear_hi = h, l.shift(2)

    def fvg_entry(fvg, lo_edge, hi_edge, side):
        """Arm on the FVG bar; fire on the first later close back inside it."""
        f = fvg.to_numpy(bool)
        le, he = lo_edge.to_numpy(float), hi_edge.to_numpy(float)
        cl = c.to_numpy(float)
        out = np.zeros(len(cl), bool)
        live, a, b, age = False, 0.0, 0.0, 0
        for i in range(len(cl)):
            if live:
                age += 1
                inside = a <= cl[i] <= b
                if inside:
                    out[i] = True
                    live = False
                elif age >= FVG_MAX_AGE or (cl[i] < a if side > 0 else cl[i] > b):
                    live = False          # gap violated or stale
            if f[i] and np.isfinite(le[i]) and np.isfinite(he[i]) and he[i] > le[i]:
                live, a, b, age = True, le[i], he[i], 0
        return pd.Series(out, index=idx)

    long_fvg = fvg_entry(bull_fvg, gap_dn_edge, gap_up_edge, +1)
    short_fvg = fvg_entry(bear_fvg, bear_lo, bear_hi, -1)

    # ── liquidity sweep: wick under a prior swing low, close back above it ──
    prior_lo = l.rolling(SWEEP_LOOKBACK).min().shift(1)
    prior_hi = h.rolling(SWEEP_LOOKBACK).max().shift(1)
    swept_lo = (l < prior_lo) & (c > prior_lo)
    swept_hi = (h > prior_hi) & (c < prior_hi)

    # ── market structure shift: close through the last confirmed swing ──
    mss_up = (c > sw_hi) & (c.shift(1) <= sw_hi)
    mss_dn = (c < sw_lo) & (c.shift(1) >= sw_lo)

    # sweep must PRECEDE the shift, within a few bars
    recent_sweep_lo = swept_lo.rolling(8).max().shift(1).fillna(0).astype(bool)
    recent_sweep_hi = swept_hi.rolling(8).max().shift(1).fillna(0).astype(bool)

    sb_win = (eth >= SB_START) & (eth < SB_END)

    out = {
        # the full published sequence: sweep -> MSS -> (implicitly) displacement
        "ic_sweep_mss_long": (recent_sweep_lo & mss_up, +1),
        "ic_sweep_mss_short": (recent_sweep_hi & mss_dn, -1),
        # the same sequence confined to the 10-11 Silver Bullet hour
        "ic_silverbullet_long": (recent_sweep_lo & mss_up & sb_win, +1),
        "ic_silverbullet_short": (recent_sweep_hi & mss_dn & sb_win, -1),
        # FVG retrace on its own — is the gap doing any work without the sequence?
        "ic_fvg_long": (long_fvg, +1),
        "ic_fvg_short": (short_fvg, -1),
        # FVG retrace that follows a sweep (ICT's actual entry object)
        "ic_sweep_fvg_long": (long_fvg & recent_sweep_lo, +1),
        "ic_sweep_fvg_short": (short_fvg & recent_sweep_hi, -1),
        # sweep alone, no structure confirmation — the control for the above
        "ic_sweep_long": (swept_lo, +1),
        "ic_sweep_short": (swept_hi, -1),
    }

    # ── Judas swing: the first move of the session is the fake one ──
    # READING: operationalised as "session made its low in the opening 30 min,
    # then reclaimed the opening range high" — a reversal of the first push.
    day = df["_day"]
    or_hi, or_lo = df["or30_hi"], df["or30_lo"]
    ready = df["or30_ready"].astype(bool)
    run_lo = l.groupby(day).cummin()
    run_hi = h.groupby(day).cummax()
    low_was_early = (run_lo >= or_lo - 1e-9)
    high_was_early = (run_hi <= or_hi + 1e-9)
    out["ic_judas_long"] = (
        ready & low_was_early & (c > or_hi) & (c.shift(1) <= or_hi), +1)
    out["ic_judas_short"] = (
        ready & high_was_early & (c < or_lo) & (c.shift(1) >= or_lo), -1)
    return out

"""BRIAN SHANNON — Anchored VWAP.

Area: bs.  Shannon (Alphatrends, CMT) popularised the anchored VWAP and wrote the
book on it ("Maximum Trading Gains With Anchored VWAP", 2023); the CMT Association
publishes his lecture deck. He is included here for a structural reason rather
than a track-record one: AVWAP is the only tool in this whole registry that uses
VOLUME in its level construction, so it is genuinely orthogonal to everything
already tested, which is otherwise all price geometry and price-derived
oscillators.

RULES, as published
-------------------
https://cmtassociation.org/wp-content/uploads/2024/01/Shannon-Specific-Anchored-VWAP-Strategies-1.pdf
https://martinkronicle.com/using-anchored-vwap-as-a-trading-system-with-brian-shannon/
  "By anchoring the VWAP to a meaningful starting point, traders can identify the
   true trend based on the position of price relative to the anchored VWAP."
  "Common anchor point choices include swing lows or highs ... breakouts or
   breakdowns to evaluate the momentum post-event."
  "Trades can be executed when the price interacts with the anchored VWAP,
   aligning with volume spikes."

ANCHORS IMPLEMENTED (all are "meaningful starting points" in Shannon's sense,
and all are knowable in real time):
  session open       — the ordinary session VWAP, already in the feed
  prior session open — a 2-day AVWAP; the level today's price is measured against
  prior day's LOW    — support anchor, Shannon's most-cited long anchor
  prior day's HIGH   — resistance anchor
  session low so far — running anchor from the day's own low

CAUSALITY — the anchor is the whole risk here
---------------------------------------------
Anchoring to "the prior day's low" is legal because the prior day is closed.
Anchoring to "today's low" is legal ONLY as a running anchor — the anchor moves
forward whenever a new low prints, and the AVWAP is recomputed from that bar
onward, which is what a live trader does. It is NOT anchored to the day's final
low; that would be lookahead and is the reason `bs_avwap_daylow_long` is built
with a cumulative running reset rather than a groupby idxmin.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

VOL_SPIKE = 1.3          # READING: "aligning with volume spikes" -> RVOL > 1.3
MIN_BARS_BELOW = 3       # READING: bars spent below before a reclaim counts


def _avwap_from_flags(tp_v, vol, reset):
    """VWAP restarted at every True in `reset`. Pure cumsum, no forward reads."""
    grp = reset.cumsum()
    num = tp_v.groupby(grp).cumsum()
    den = vol.groupby(grp).cumsum()
    return num / den.replace(0, np.nan)


def register(df: pd.DataFrame) -> dict:
    h, l, c, v = df["high"], df["low"], df["close"], df["volume"]
    day = df["_day"]
    tp = (h + l + c) / 3.0
    tp_v = tp * v

    rvol = v / v.rolling(20).mean().shift(1)
    spike = (rvol > VOL_SPIKE).fillna(False)

    # ── anchor 1: session open (the ordinary VWAP, already computed) ──
    vwap = df["vwap"]

    # ── anchor 2: prior session open -> a rolling 2-day AVWAP ──
    new_day = day != day.shift(1)
    grp2 = (new_day.cumsum() // 2)
    avwap2 = (tp_v.groupby(grp2).cumsum() / v.groupby(grp2).cumsum().replace(0, np.nan))

    # ── anchor 3: the running session LOW (re-anchors on each new low) ──
    run_lo = l.groupby(day).cummin()
    new_low = (l <= run_lo) & (l < run_lo.shift(1).fillna(np.inf))
    reset_lo = new_day | new_low.fillna(False)
    avwap_lo = _avwap_from_flags(tp_v, v, reset_lo)

    # ── anchor 4: the running session HIGH ──
    run_hi = h.groupby(day).cummax()
    new_high = (h >= run_hi) & (h > run_hi.shift(1).fillna(-np.inf))
    reset_hi = new_day | new_high.fillna(False)
    avwap_hi = _avwap_from_flags(tp_v, v, reset_hi)

    def reclaim(level, side):
        """First close back through `level` after >= MIN_BARS_BELOW bars beyond it."""
        if side > 0:
            beyond = (c < level)
            cross = (c > level) & (c.shift(1) <= level.shift(1))
        else:
            beyond = (c > level)
            cross = (c < level) & (c.shift(1) >= level.shift(1))
        stayed = beyond.shift(1).rolling(MIN_BARS_BELOW).min().fillna(0).astype(bool)
        return (cross & stayed).fillna(False)

    return {
        # session VWAP reclaim / rejection — the baseline anchor
        "bs_avwap_open_long": (reclaim(vwap, +1), +1),
        "bs_avwap_open_short": (reclaim(vwap, -1), -1),
        # 2-day AVWAP: today measured against yesterday's participation
        "bs_avwap_2day_long": (reclaim(avwap2, +1), +1),
        "bs_avwap_2day_short": (reclaim(avwap2, -1), -1),
        # AVWAP anchored to the day's low — Shannon's support anchor
        "bs_avwap_daylow_long": (reclaim(avwap_lo, +1), +1),
        "bs_avwap_dayhigh_short": (reclaim(avwap_hi, -1), -1),
        # with the published volume-spike confirmation
        "bs_avwap_open_vol_long": (reclaim(vwap, +1) & spike, +1),
        "bs_avwap_open_vol_short": (reclaim(vwap, -1) & spike, -1),
        "bs_avwap_2day_vol_long": (reclaim(avwap2, +1) & spike, +1),
        "bs_avwap_2day_vol_short": (reclaim(avwap2, -1) & spike, -1),
        # trend-continuation: price holds above BOTH anchors and pushes on volume
        "bs_avwap_stack_long": ((c > vwap) & (c > avwap2) & spike
                                & (c > c.shift(1)), +1),
        "bs_avwap_stack_short": ((c < vwap) & (c < avwap2) & spike
                                 & (c < c.shift(1)), -1),
    }

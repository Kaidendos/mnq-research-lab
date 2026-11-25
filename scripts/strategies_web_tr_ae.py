"""ALEXANDER ELDER — Impulse System, Triple Screen, Elder-Ray, SafeZone.

Area: ae.  Elder's systems are published in "Trading for a Living" (1993) and
"Come Into My Trading Room" (2002) with named indicators and explicit
permission/veto logic. The Impulse System in particular is a censorship system,
not a signal system — it says what you may NOT do — which makes it unusually
clean to port: the veto is the rule.

RULES, as published
-------------------
https://chartschool.stockcharts.com/table-of-contents/chart-analysis/chart-types/elder-impulse-system
  "Green price bars show that the bulls are in control of both trend and momentum
   as both the 13-day EMA and MACD-Histogram are rising."
  "A red price bar indicates that the bears have taken control because the 13-day
   EMA and MACD-Histogram are falling."
https://www.quantifiedstrategies.com/alexander-elder-triple-screen-strategy/
  "Screen one should be 4-5x longer than trade timeframe."
  "Weekly EMA slope UP means look for long entries only; slope DOWN means look
   for short entries only; flat slope means avoid trading."

Elder-Ray: bull power = high - EMA13, bear power = low - EMA13. The published buy
condition is EMA13 rising AND bear power negative but RISING — a pullback inside
an uptrend that is running out of sellers.

TIMEFRAME PORT
--------------
Elder's ratio is what matters, not the calendar. Screen 1 here is the DAILY
series (already in the feed as gate_ema20 / gate_ema50, both shift(1)-ed), and
Screen 2/3 are the 5-min bars. Daily:5-min is a far wider ratio than his 5:1, so
`ae_triple_screen_*` also ships a variant whose Screen 1 is a 78-bar (one
session) EMA on the intraday series, which is close to his intended ratio.

CAUSALITY
---------
"Rising" is always `x > x.shift(1)` on closed bars. The daily gates were built in
`load_enriched` with `.shift(1)` and never see the live session.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

EMA_LEN = 13                 # Elder's number, used everywhere in his work
MACD_F, MACD_S, MACD_SIG = 12, 26, 9
SCREEN1_BARS = 78            # ~one RTH session of 5-min bars
FORCE_LEN = 2                # Elder's 2-period Force Index for entry timing


def register(df: pd.DataFrame) -> dict:
    h, l, c, v = df["high"], df["low"], df["close"], df["volume"]

    ema13 = c.ewm(span=EMA_LEN, adjust=False).mean()
    macd = (c.ewm(span=MACD_F, adjust=False).mean()
            - c.ewm(span=MACD_S, adjust=False).mean())
    hist = macd - macd.ewm(span=MACD_SIG, adjust=False).mean()

    ema_up = ema13 > ema13.shift(1)
    ema_dn = ema13 < ema13.shift(1)
    hist_up = hist > hist.shift(1)
    hist_dn = hist < hist.shift(1)

    # ── Impulse System: green / red / blue ──
    green = ema_up & hist_up
    red = ema_dn & hist_dn
    # Elder trades the CENSORSHIP: a red bar forbids buying. The tradable event
    # is the bar where the veto lifts — red ends, or green begins.
    green_start = green & ~green.shift(1).fillna(False).astype(bool)
    red_start = red & ~red.shift(1).fillna(False).astype(bool)
    red_lift = ~red & red.shift(1).fillna(False)      # bears lose control
    green_lift = ~green & green.shift(1).fillna(False)

    # ── Elder-Ray ──
    bull_power = h - ema13
    bear_power = l - ema13
    # published buy: uptrend, bear power below zero but rising
    ray_buy = ema_up & (bear_power < 0) & (bear_power > bear_power.shift(1))
    ray_sell = ema_dn & (bull_power > 0) & (bull_power < bull_power.shift(1))

    # ── Force Index (Elder's own) ──
    force = (c - c.shift(1)) * v
    force2 = force.ewm(span=FORCE_LEN, adjust=False).mean()
    # Screen 3 trigger: in an uptrend, buy when the 2-period Force Index turns
    # negative (a dip) and then turns back up.
    force_buy = (force2.shift(1) < 0) & (force2 > force2.shift(1))
    force_sell = (force2.shift(1) > 0) & (force2 < force2.shift(1))

    # ── Screen 1 candidates ──
    g_up = df["gate_ema50"].astype(bool)        # daily, already shift(1)-ed
    g_dn = df["gate_below50"].astype(bool)
    s1 = c.ewm(span=SCREEN1_BARS, adjust=False).mean()
    s1_up, s1_dn = s1 > s1.shift(1), s1 < s1.shift(1)

    # ── Screen 2: Elder's oscillator pullback (stochastic already in the feed) ──
    K = df["stochK"]
    dip = (K.shift(1) < 30) & (K > K.shift(1))
    rip = (K.shift(1) > 70) & (K < K.shift(1))

    return {
        # Impulse System proper
        "ae_impulse_long": (green_start, +1),
        "ae_impulse_short": (red_start, -1),
        # the veto lifting, which is what Elder actually acts on
        "ae_impulse_lift_long": (red_lift & (c > ema13), +1),
        "ae_impulse_lift_short": (green_lift & (c < ema13), -1),
        # Elder-Ray
        "ae_ray_long": (ray_buy, +1),
        "ae_ray_short": (ray_sell, -1),
        # Triple Screen — daily Screen 1
        "ae_triple_screen_long": (g_up & dip & (c > ema13), +1),
        "ae_triple_screen_short": (g_dn & rip & (c < ema13), -1),
        # Triple Screen — intraday Screen 1 at closer to Elder's 5:1 ratio
        "ae_triple_intraday_long": (s1_up & dip, +1),
        "ae_triple_intraday_short": (s1_dn & rip, -1),
        # Force Index entry inside an Impulse-permitted trend
        "ae_force_long": (~red & s1_up & force_buy, +1),
        "ae_force_short": (~green & s1_dn & force_sell, -1),
    }

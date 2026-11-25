"""BILL WILLIAMS — Profitunity / Chaos: Alligator, Fractals, Awesome Oscillator.

Area: bw.  Williams published a complete, fully specified mechanical system in
"Trading Chaos" (1995) and "New Trading Dimensions" (1998). The indicators ship
by name in MetaTrader and TradingView with his exact parameters, which is why the
rules below need no interpretation — the constants are his.

RULES, as published
-------------------
https://www.avatrade.com/education/technical-analysis-indicators-strategies/bill-williams-indicators
https://tradingstrategyguides.com/bill-williams-awesome-oscillator-strategy/
  Alligator: jaw = 13-period smoothed MA displaced 8 bars, teeth = 8-period
  displaced 5, lips = 5-period displaced 3, all on median price.
  "Do not take any AO signals until after a FRACTAL signal is formed outside the
   Alligator's mouth."
  "ONLY buy on an AO signal above the zero line (sell below the zero line)."
  "The saucer setup is formed by 3 consecutive bars on the AO histogram either
   above the zero line or below the zero line ... a buy signal is generated when
   the histogram which is above the zero line changes its direction from falling
   to rising."
  "The critical factor is where the fractal signal was HIT, as opposed to where
   the signal was FORMED."

CAUSALITY — the one real trap in this family
--------------------------------------------
A Williams fractal is a 5-bar pattern whose middle bar is the extreme. It CANNOT
be known until two bars after the middle bar prints. Every retail implementation
that plots it on the middle bar is drawing a line it did not have at the time.
Here the fractal level is published with a 2-bar lag and only then becomes
tradable, so `bw_fractal_break_long` fires no earlier than a live trader could.

The Alligator's "displacement" is the opposite case and is legal: displacing a
13-period average 8 bars FORWARD means each bar reads an average computed 8 bars
AGO — older data, not newer. That is `.shift(+8)`.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

JAW_N, JAW_D = 13, 8
TEETH_N, TEETH_D = 8, 5
LIPS_N, LIPS_D = 5, 3
AO_FAST, AO_SLOW = 5, 34
FRACTAL_MAX_AGE = 20      # READING: how long a fractal level stays tradable


def _smma(s, n):
    """Wilder / smoothed moving average — Williams' 'smoothed' MA."""
    return s.ewm(alpha=1.0 / n, adjust=False).mean()


def register(df: pd.DataFrame) -> dict:
    h, l, c = df["high"], df["low"], df["close"]
    idx = df.index
    med = (h + l) / 2.0

    # ── Alligator (displacement = .shift forward = reads OLDER values) ──
    jaw = _smma(med, JAW_N).shift(JAW_D)
    teeth = _smma(med, TEETH_N).shift(TEETH_D)
    lips = _smma(med, LIPS_N).shift(LIPS_D)
    mouth_hi = pd.concat([jaw, teeth, lips], axis=1).max(axis=1)
    mouth_lo = pd.concat([jaw, teeth, lips], axis=1).min(axis=1)
    awake_up = (lips > teeth) & (teeth > jaw)      # "the alligator is eating" up
    awake_dn = (lips < teeth) & (teeth < jaw)

    # ── Awesome Oscillator ──
    ao = med.rolling(AO_FAST).mean() - med.rolling(AO_SLOW).mean()
    ao1, ao2 = ao.shift(1), ao.shift(2)

    # saucer buy: AO above zero, two falling bars then a rising one
    saucer_buy = (ao > 0) & (ao2 > ao1) & (ao > ao1)
    saucer_sell = (ao < 0) & (ao2 < ao1) & (ao < ao1)
    zero_up = (ao > 0) & (ao.shift(1) <= 0)
    zero_dn = (ao < 0) & (ao.shift(1) >= 0)
    # twin peaks: second trough higher than the first, both below zero
    twin_buy = (ao < 0) & (ao > ao1) & (ao1 < ao2) & (ao1 > ao.rolling(20).min().shift(1))

    # ── Fractals, published with the mandatory 2-bar confirmation lag ──
    up_frac_raw = (h.shift(2) == h.rolling(5).max())     # middle of 5 is highest
    dn_frac_raw = (l.shift(2) == l.rolling(5).min())
    frac_hi_level = h.shift(2).where(up_frac_raw)
    frac_lo_level = l.shift(2).where(dn_frac_raw)

    # Williams: only fractals formed OUTSIDE the alligator's mouth count
    frac_hi_valid = frac_hi_level.where(frac_hi_level > mouth_hi)
    frac_lo_valid = frac_lo_level.where(frac_lo_level < mouth_lo)

    def break_of(level, side):
        """Fire on the first close beyond the most recent valid fractal level."""
        lv = level.to_numpy(float)
        cl = c.to_numpy(float)
        out = np.zeros(len(cl), bool)
        live, val, age = False, 0.0, 0
        for i in range(len(cl)):
            if live:
                age += 1
                if (cl[i] > val) if side > 0 else (cl[i] < val):
                    out[i] = True
                    live = False
                elif age >= FRACTAL_MAX_AGE:
                    live = False
            if np.isfinite(lv[i]):
                live, val, age = True, lv[i], 0
        return pd.Series(out, index=idx)

    frac_break_long = break_of(frac_hi_valid, +1)
    frac_break_short = break_of(frac_lo_valid, -1)

    # "signal is HIT outside the TEETH" — the published filter on the trigger bar
    above_teeth = c > teeth
    below_teeth = c < teeth

    return {
        "bw_fractal_break_long": (frac_break_long & above_teeth, +1),
        "bw_fractal_break_short": (frac_break_short & below_teeth, -1),
        # AO signals gated by a prior fractal break, as the system requires
        "bw_ao_saucer_long": (saucer_buy & above_teeth & awake_up, +1),
        "bw_ao_saucer_short": (saucer_sell & below_teeth & awake_dn, -1),
        "bw_ao_zero_long": (zero_up & above_teeth, +1),
        "bw_ao_zero_short": (zero_dn & below_teeth, -1),
        "bw_ao_twin_long": (twin_buy & above_teeth, +1),
        # the full stack: fractal break AND AO agreeing AND alligator awake
        "bw_full_long": (frac_break_long & (ao > 0) & awake_up, +1),
        "bw_full_short": (frac_break_short & (ao < 0) & awake_dn, -1),
        # alligator wake-up on its own — the control for the fractal filter
        "bw_alligator_long": (awake_up & ~awake_up.shift(1).fillna(False).astype(bool), +1),
        "bw_alligator_short": (awake_dn & ~awake_dn.shift(1).fillna(False).astype(bool), -1),
    }

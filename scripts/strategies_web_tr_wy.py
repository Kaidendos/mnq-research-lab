"""RICHARD WYCKOFF — spring, upthrust, sign of strength, last point of support.

Area: wy.  Wyckoff (1873-1934) ran a brokerage and published the method in "The
Richard D. Wyckoff Method of Trading and Investing in Stocks" (1931); it is the
oldest methodology in this registry and the only one whose logic is stated in
terms of SUPPLY AND DEMAND rather than indicator readings, which is why the
volume conditions below are not optional decoration — they are the rule.

RULES, as published
-------------------
https://tradingwyckoff.com/en/spring-shakeout/
https://alchemymarkets.com/education/guides/wyckoff-accumulation/
  "A spring is a price dip below a support level that quickly returns to the
   range, showing that supply is weak. An upthrust is a price rise above a
   resistance level that quickly returns to the range, showing that demand is
   weak."
  "Spring #2 (penetration 1-3%, moderate volume) requires waiting for a
   successful test showing reduced volume 40-60% and range narrowing, then trade
   on recovery after test with stop below Spring low."
  "Phase D shows strength through signs of strength (SOS) on expanding volume and
   last points of support (LPS) on quiet pullbacks."

PORT
----
"Trading range" = the high/low of the prior RANGE_BARS bars, excluding the
current one. A spring is a bar that trades below that low and CLOSES back inside.
The "successful test on reduced volume" is a later bar that revisits the area on
volume below the range average — implemented as a separate, stricter family so
the value of the test condition is measurable rather than assumed.

CAUSALITY
---------
Every range boundary is `.shift(1)`-ed off a backward rolling window, so the
range is the one that existed BEFORE the bar being judged. Volume comparisons use
a trailing mean that also excludes the current bar. Nothing reads the session's
eventual high or low.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

RANGE_BARS = 24          # READING: ~2 hours of 5-min bars forms the trading range
VOL_LOOK = 20
TEST_VOL_MAX = 0.60      # published: "reduced volume 40-60%"
SOS_VOL_MIN = 1.50       # published: SOS comes "on expanding volume"
TEST_WINDOW = 8          # READING: bars allowed between spring and its test


def register(df: pd.DataFrame) -> dict:
    h, l, c, v = df["high"], df["low"], df["close"], df["volume"]
    idx = df.index

    rng_hi = h.rolling(RANGE_BARS).max().shift(1)
    rng_lo = l.rolling(RANGE_BARS).min().shift(1)
    width = (rng_hi - rng_lo)
    vavg = v.rolling(VOL_LOOK).mean().shift(1)
    rvol = (v / vavg).fillna(1.0)

    # a range worth trading has to be a range, not a trend leg
    tight = width < width.rolling(RANGE_BARS).median().shift(1) * 1.5

    # ── SPRING: dips below range low, closes back inside ──
    spring = (l < rng_lo) & (c > rng_lo) & (c < rng_hi)
    upthrust = (h > rng_hi) & (c < rng_hi) & (c > rng_lo)

    # penetration depth, as a fraction of range width (Wyckoff's "1-3%")
    depth_dn = ((rng_lo - l) / width.replace(0, np.nan)).fillna(0)
    depth_up = ((h - rng_hi) / width.replace(0, np.nan)).fillna(0)
    shallow_dn = depth_dn <= 0.25
    shallow_up = depth_up <= 0.25

    # ── TEST: a later bar revisits the spring low on REDUCED volume ──
    def tested(trigger, level_series, side):
        t = trigger.to_numpy(bool)
        lv = level_series.to_numpy(float)
        L, H, C = l.to_numpy(float), h.to_numpy(float), c.to_numpy(float)
        R = rvol.to_numpy(float)
        out = np.zeros(len(C), bool)
        live, val, age, base_v = False, 0.0, 0, 1.0
        for i in range(len(C)):
            if live:
                age += 1
                near = (L[i] <= val * 1.0005) if side > 0 else (H[i] >= val * 0.9995)
                quiet = R[i] <= base_v * TEST_VOL_MAX
                if near and quiet and ((C[i] > val) if side > 0 else (C[i] < val)):
                    out[i] = True
                    live = False
                elif age >= TEST_WINDOW:
                    live = False
            if t[i]:
                live, val, age, base_v = True, lv[i], 0, max(R[i], 0.1)
        return pd.Series(out, index=idx)

    spring_tested = tested(spring & tight, l, +1)
    upthrust_tested = tested(upthrust & tight, h, -1)

    # ── SIGN OF STRENGTH: close above the range top on expanding volume ──
    sos = (c > rng_hi) & (c.shift(1) <= rng_hi) & (rvol >= SOS_VOL_MIN)
    sow = (c < rng_lo) & (c.shift(1) >= rng_lo) & (rvol >= SOS_VOL_MIN)

    # ── LAST POINT OF SUPPORT: quiet pullback holding above the broken top ──
    broke_up = (c > rng_hi).shift(1).rolling(TEST_WINDOW).max().fillna(0).astype(bool)
    broke_dn = (c < rng_lo).shift(1).rolling(TEST_WINDOW).max().fillna(0).astype(bool)
    lps = broke_up & (l <= rng_hi) & (c > rng_hi) & (rvol < 1.0)
    lpsy = broke_dn & (h >= rng_lo) & (c < rng_lo) & (rvol < 1.0)

    return {
        # the raw events
        "wy_spring_long": (spring & tight, +1),
        "wy_upthrust_short": (upthrust & tight, -1),
        # with the published shallow-penetration qualifier
        "wy_spring_shallow_long": (spring & tight & shallow_dn, +1),
        "wy_upthrust_shallow_short": (upthrust & tight & shallow_up, -1),
        # with the mandatory low-volume test — the strict, published version
        "wy_spring_tested_long": (spring_tested, +1),
        "wy_upthrust_tested_short": (upthrust_tested, -1),
        # phase D
        "wy_sos_long": (sos, +1),
        "wy_sow_short": (sow, -1),
        "wy_lps_long": (lps, +1),
        "wy_lpsy_short": (lpsy, -1),
    }

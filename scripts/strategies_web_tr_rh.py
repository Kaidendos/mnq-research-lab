"""ROB HOFFMAN — Inventory Retracement Bar, ported to MNQ 5-min RTH.

Area: rh.  Hoffman is the most-decorated live-trading-competition winner on
record (Trading Competition wins across multiple years and instruments), and the
IRB is his one fully published, fully mechanical pattern — it is implemented by
name in commercial platforms (WHSelfinvest / NanoTrader ship it as a stock tool),
which is what makes it reproducible rather than a marketing claim.

THE RULE, as published
----------------------
https://www.whselfinvest.com/en-lu/trading-platform/trader-tools/technical-analysis/13-rob-hoffman-irb-inventory-retracement-bar
  "To qualify as an IRB a candle must open and close at least 45 percent below
   its high."  (uptrend case)
  "In a downtrend, candlestick bars must open and close 45% or more off their
   low."
  "Once an IRB is identified in the proper trend direction, an entry signal only
   occurs when the market rises above the high of the IRB."

So the pattern is two conditions plus a trigger:
  1. TREND    — Hoffman uses a 20-period EMA for direction on the trading chart.
  2. IRB BAR  — open AND close both sit in the bottom 55% of the bar's own range
                (long case).  This is the "inventory retracement": institutions
                pausing, not reversing.
  3. TRIGGER  — price takes out the IRB's high.

CAUSALITY
---------
The IRB bar is fully closed before it can arm anything (`.shift(1)` into the
scan). The trigger uses CLOSE above the IRB high, not intrabar high, so the
signal is known at the close of the bar that emits it — the harness enters at
that same close. Using `high >` would fire on a level touched intrabar and would
be entering at a price the bar may already have left.

READING: the 45% threshold, the 20-EMA and "the IRB's high" are Hoffman's. The
arming window (how many bars an armed IRB stays valid) is not specified in the
source; 12 bars = 1 hour on this timeframe is my choice and is swept as a
separate family (`rh_irb_long_fast` uses 4).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

IRB_FRAC = 0.45          # published
EMA_LEN = 20             # Hoffman's trend EMA
ARM_BARS = 12            # READING: how long an armed IRB stays live
ARM_BARS_FAST = 4        # READING: tighter variant


def _irb_flags(o, h, l, c, frac):
    """open AND close at least `frac` of the range below the high / above the low."""
    rng = (h - l).replace(0, np.nan)
    down_from_high = ((h - o) / rng >= frac) & ((h - c) / rng >= frac)
    up_from_low = ((o - l) / rng >= frac) & ((c - l) / rng >= frac)
    return down_from_high.fillna(False), up_from_low.fillna(False)


def _trigger(arm_ok, level, close, arm_bars, direction):
    """Scan: when arm_ok fires, remember `level`; emit when close breaks it.

    One signal per arming — the level is consumed on trigger, and expires after
    `arm_bars` so a stale morning IRB cannot fire in the afternoon.
    """
    a = arm_ok.to_numpy(bool)
    lv = level.to_numpy(float)
    cl = close.to_numpy(float)
    out = np.zeros(len(cl), bool)
    live, live_lv, age = False, 0.0, 0
    for i in range(len(cl)):
        if live:
            age += 1
            hit = cl[i] > live_lv if direction > 0 else cl[i] < live_lv
            if hit:
                out[i] = True
                live = False
            elif age >= arm_bars:
                live = False
        # a fresh IRB re-arms (and overrides a stale one) on the same bar
        if a[i] and np.isfinite(lv[i]):
            live, live_lv, age = True, lv[i], 0
    return pd.Series(out, index=close.index)


def register(df: pd.DataFrame) -> dict:
    o, h, l, c = df["open"], df["high"], df["low"], df["close"]
    ema = c.ewm(span=EMA_LEN, adjust=False).mean()

    # trend: price above a RISING 20-EMA (long) / below a FALLING one (short).
    # Both parts are Hoffman's — he calls a flat EMA "no trade".
    up_trend = (c > ema) & (ema > ema.shift(1))
    dn_trend = (c < ema) & (ema < ema.shift(1))

    irb_dn, irb_up = _irb_flags(o, h, l, c, IRB_FRAC)

    # arm on the CLOSED bar -> shift(1) so the level is historical when scanned
    arm_long = (irb_dn & up_trend).shift(1).fillna(False)
    arm_short = (irb_up & dn_trend).shift(1).fillna(False)
    lvl_long, lvl_short = h.shift(1), l.shift(1)

    out = {}
    for tag, nbars in (("", ARM_BARS), ("_fast", ARM_BARS_FAST)):
        out[f"rh_irb_long{tag}"] = (
            _trigger(arm_long, lvl_long, c, nbars, +1), +1)
        out[f"rh_irb_short{tag}"] = (
            _trigger(arm_short, lvl_short, c, nbars, -1), -1)

    # Looser 33% variant. Hoffman's number is 45%; this is explicitly NOT his
    # rule, it is here to test whether the threshold is doing any work at all.
    irb_dn33, irb_up33 = _irb_flags(o, h, l, c, 0.33)
    out["rh_irb33_long"] = (
        _trigger((irb_dn33 & up_trend).shift(1).fillna(False), lvl_long, c,
                 ARM_BARS, +1), +1)
    out["rh_irb33_short"] = (
        _trigger((irb_up33 & dn_trend).shift(1).fillna(False), lvl_short, c,
                 ARM_BARS, -1), -1)

    # IRB with the harness's own daily trend gate instead of the intraday EMA —
    # separates "does the pattern work" from "does the 20-EMA pick the trend".
    g_up, g_dn = df["gate_ema50"].astype(bool), df["gate_below50"].astype(bool)
    out["rh_irb_gated_long"] = (
        _trigger((irb_dn & g_up).shift(1).fillna(False), lvl_long, c,
                 ARM_BARS, +1), +1)
    out["rh_irb_gated_short"] = (
        _trigger((irb_up & g_dn).shift(1).fillna(False), lvl_short, c,
                 ARM_BARS, -1), -1)
    return out

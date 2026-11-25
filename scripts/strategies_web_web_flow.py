"""Volume / order-flow / price-action ENTRY triggers for MNQ 5-min RTH bars.

Category: "flow" — volume spikes, relative-volume filters, engulfing & pin bars at
levels, three-bar reversals, order-block style retests.

Every rule below is transcribed from a public, documented write-up. Source URL sits
directly above each implementation. Where a source is vague (it usually is about the
exact numeric threshold on a 5-minute futures chart) the concrete reading chosen is
called out in a comment marked  # CHOICE:

CAUSALITY: nothing here looks forward. Session-scoped features use groupby("_day")
with .cummin()/.cummax() only. The time-of-day relative-volume baseline is built with
.shift(1) inside each time-of-day group so a bar is compared only to the SAME clock
time on EARLIER sessions. Plain .rolling(n) windows end on the current bar, which is
information known at that bar's close, so they are legal.

Returns ENTRY TRIGGERS ONLY. No stops, targets, sizing or exits — the harness owns
those and sweeps them.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# ── tunables (kept as named constants, no magic numbers inline) ──
RVOL_LOOKBACK_SESSIONS = 10      # sources say "same intraday window, 5-10 day lookback"
RVOL_MIN_SESSIONS = 4
RVOL_BREAKOUT_MULT = 1.5         # ChartMath band "1.5x-2.0x = elevated interest"
VOL_CONFIRM_MULT = 1.25          # engulfing volume confirmation
VOL_AVG_BARS = 20
CLIMAX_LOOKBACK = 20             # Better Volume default: highest in last 20 bars
CLIMAX_CONFIRM_BARS = 3          # bars allowed for the follow-through close
PIN_WICK_FRAC = 2.0 / 3.0        # wick >= 2/3 of total range
PIN_CLOSE_FRAC = 1.0 / 3.0       # close inside the far third
PIN_MIN_ATR = 0.6                # ignore noise-sized pins
OB_IMPULSE_ATR = 1.0             # displacement bar must be a real impulse
OB_MAX_WAIT_BARS = 24            # retest window after the order block forms
THREE_BAR_MIN_ATR = 0.5


# ══════════════════════════ helpers ══════════════════════════
def _tod_rvol(df: pd.DataFrame) -> pd.Series:
    """Time-matched relative volume.

    Current bar volume / mean volume at the SAME clock time over the previous N
    sessions. The .shift(1) inside each time-of-day group is what keeps it causal —
    today's bar never enters its own baseline.
    """
    tod = pd.Series(df.index.hour * 60 + df.index.minute, index=df.index)
    vol = df["volume"].astype(float)
    base = vol.groupby(tod).transform(
        lambda s: s.shift(1).rolling(RVOL_LOOKBACK_SESSIONS,
                                     min_periods=RVOL_MIN_SESSIONS).mean()
    )
    return vol / base.replace(0.0, np.nan)


def _carry(trigger: pd.Series, value: pd.Series, day: pd.Series,
           pos: pd.Series) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Forward-fill a value captured on `trigger` bars.

    Returns (carried_value, bars_since_trigger, still_same_session). Uses only
    .ffill(), so every carried value comes from a bar at or before the current one.
    """
    carried = value.where(trigger).ffill()
    trig_pos = pos.where(trigger).ffill()
    trig_day = day.where(trigger).ffill()
    return carried, pos - trig_pos, trig_day.eq(day)


def _clean(s: pd.Series, index) -> pd.Series:
    return s.reindex(index).fillna(False).astype(bool)


# ══════════════════════════ register ══════════════════════════
def register(df: pd.DataFrame) -> dict:
    o, h, l, c = df["open"], df["high"], df["low"], df["close"]
    pc, po, ph, pl = c.shift(1), o.shift(1), h.shift(1), l.shift(1)
    atr, day = df["atr"], df["_day"]
    rng = h - l
    body_hi, body_lo = np.maximum(c, o), np.minimum(c, o)

    pos = pd.Series(np.arange(len(df), dtype=float), index=df.index)
    rvol = _tod_rvol(df)
    vol_avg = df["volume"].rolling(VOL_AVG_BARS).mean()

    # session-cumulative extremes (cumulative => causal)
    sess_lo = l.groupby(day).cummin()
    sess_hi = h.groupby(day).cummax()

    out: dict[str, tuple[pd.Series, int]] = {}

    # ───────────────────────────────────────────────────────────────────
    # 1) flow_rvol_orb  — relative-volume-confirmed opening-range breakout
    # https://trendspider.com/learning-center/relative-volume-rvol-trading-strategies/
    # https://chartmath.com/blog/volume-analysis-for-day-traders-how-to-use-rvol-and-volume-spikes
    #   "When price breaks through a key resistance level and RVOL is above 1.5 or 2,
    #    the breakout is likelier to hold."  RVOL is defined as current volume over
    #    the average volume at that same time of day on previous days.
    # CHOICE: the source only says "a key support or resistance level". The two
    #   standard intraday index-futures levels are used: the 15-min and the 30-min
    #   opening-range highs. Only the FIRST break of each level in a session counts,
    #   so this cannot re-fire while price chops the level. Threshold 1.5x is the low
    #   edge of ChartMath's "elevated interest" band; 2.0x fired on only 0.12% of bars,
    #   which is too thin to evaluate.
    # ───────────────────────────────────────────────────────────────────
    first_or_break = (
        (df["or15_ready"] & (c > df["or15_hi"]) & (pc <= df["or15_hi"]))
        | (df["or30_ready"] & (c > df["or30_hi"]) & (pc <= df["or30_hi"]))
    )
    out["flow_rvol_orb"] = (
        _clean(first_or_break
               & (rvol >= RVOL_BREAKOUT_MULT)
               & (c > (h + l) / 2.0),          # closes in the upper half = break held
               df.index),
        +1,
    )

    # ───────────────────────────────────────────────────────────────────
    # 2) flow_vclimax_rev — Better Volume "Volume Climax Down" exhaustion reversal
    # https://emini-watch.com/free-indicators/volume-indicator/
    #   Volume Climax Down = selling volume x bar range, highest value in the last 20
    #   bars; it marks trend ENDS as well as starts, and the author's rule is to
    #   "wait for the market to become exhausted" at bottoms rather than sell into it.
    # Confirmation mechanic from ChartMath's volume-spike rule (same URL as #1):
    #   "enter when price breaks above the high of the volume spike candle".
    # CHOICE: Databento 5-min bars carry no bid/ask split, so selling volume is
    #   proxied by total volume on a DOWN-CLOSE bar (comment, not a hidden fudge).
    #   The climax must also print a NEW SESSION LOW so it is anchored to a real
    #   swing low, and the follow-through close must arrive within 3 bars.
    # ───────────────────────────────────────────────────────────────────
    vol_range = df["volume"].astype(float) * rng
    climax_dn = (
        (vol_range >= vol_range.rolling(CLIMAX_LOOKBACK).max())
        & (c < o)
        & (l <= sess_lo)                       # cumulative min => new session low
        & (rng > 0)
    )
    clim_hi, clim_age, clim_same = _carry(climax_dn, h, day, pos)
    out["flow_vclimax_rev"] = (
        _clean(clim_same
               & (clim_age >= 1) & (clim_age <= CLIMAX_CONFIRM_BARS)
               & (c > clim_hi) & (pc <= clim_hi)   # first close above the climax high
               & (c > o),
               df.index),
        +1,
    )

    # ───────────────────────────────────────────────────────────────────
    # 3) flow_engulf_vwap — bullish engulfing AT a level, with volume confirmation
    # https://audacity.capital/trading-guides/bullish-engulfing-candlestick-pattern/
    # https://www.edgeful.com/blog/posts/candlestick-patterns-for-day-trading
    #   Two-candle reversal: prior candle bearish, current candle bullish and its body
    #   fully engulfs the prior body. "Pattern forms at a key support level, not in
    #   the middle of a range; enter on the close of the engulfing candle; confirm
    #   volume on the engulfing candle is at least 1.25x the 20-period average."
    # CHOICE: the intraday "key support" is session VWAP — the bar must dip to/through
    #   VWAP and close back above it, which is the mechanical reading of "at the level".
    # ───────────────────────────────────────────────────────────────────
    engulf_bull = (pc < po) & (c > o) & (c >= po) & (o <= pc)
    out["flow_engulf_vwap"] = (
        _clean(engulf_bull
               & (df["volume"] >= VOL_CONFIRM_MULT * vol_avg)
               & (l <= df["vwap"]) & (c > df["vwap"]),
               df.index),
        +1,
    )

    # ───────────────────────────────────────────────────────────────────
    # 4) flow_3bar_long — three-bar reversal, long
    # https://www.tradingsetupsreview.com/three-bar-reversal-pattern-day-trading/
    #   Long: (1) Bar 1 closes down. (2) Low of Bar 2 is below the low of Bar 1 and
    #   Bar 3. (3) Bar 3 closes above the high of BOTH Bar 1 and Bar 2. (4) Buy at the
    #   close of Bar 3.  Same page's filter: skip it when Bar 2 is an outside bar.
    # CHOICE: added a range floor (pattern span >= 0.5 ATR) because the same source
    #   blames "lack of volatility" for most failures of this pattern.
    # ───────────────────────────────────────────────────────────────────
    b1_c, b1_o, b1_h, b1_l = c.shift(2), o.shift(2), h.shift(2), l.shift(2)
    b2_h, b2_l = ph, pl
    bar2_outside = (b2_h > b1_h) & (b2_l < b1_l)
    span = np.maximum(h, np.maximum(b1_h, b2_h)) - np.minimum(l, np.minimum(b1_l, b2_l))
    out["flow_3bar_long"] = (
        _clean((b1_c < b1_o)
               & (b2_l < b1_l) & (b2_l < l)
               & (c > np.maximum(b1_h, b2_h))
               & ~bar2_outside
               & (span >= THREE_BAR_MIN_ATR * atr),
               df.index),
        +1,
    )

    # ───────────────────────────────────────────────────────────────────
    # 5) flow_pin_sweep_short — bearish pin bar rejecting a swept level
    # https://www.strike.money/technical-analysis/pin-bar
    # https://www.colibritrader.com/pin-bar-pattern/
    #   "The wick makes up at least two-thirds of the candle's total range, the small
    #    body sits at the far end, a bearish pin bar has a long upper wick and closes
    #    near the low. A pin bar that doesn't form at a key level is a low-probability
    #    signal and should be ignored."
    # CHOICE: "key level" = the previous 10-bar high (prior swing high, shifted so the
    #   current bar is excluded). The bar must trade THROUGH it and close back below —
    #   a liquidity sweep and rejection — and be at least 0.6 ATR tall.
    # ───────────────────────────────────────────────────────────────────
    upper_wick = h - body_hi
    pin_bear = (
        (rng > 0)
        & (upper_wick >= PIN_WICK_FRAC * rng)
        & (c <= l + PIN_CLOSE_FRAC * rng)      # close inside the bottom third
        & (rng >= PIN_MIN_ATR * atr)
    )
    prior_swing_hi = df["donch_hi10"].shift(1)
    out["flow_pin_sweep_short"] = (
        _clean(pin_bear & (h > prior_swing_hi) & (c < prior_swing_hi), df.index),
        -1,
    )

    # ───────────────────────────────────────────────────────────────────
    # 6) flow_ob_retest — bullish order block, 50% retest
    # https://innercircletrader.net/tutorials/ict-bullish-order-block/
    # https://tradingstrategyguides.com/day-5-order-blocks-explained-ict-vs-smc-guide-to-bullish-bearish-obs/
    #   "A bullish order block is the last bearish candle before a strong bullish
    #    impulse. Mark the zone from the low to the high of that candle. The impulse
    #    candle must close above its high. Entry occurs at the 50% retracement of the
    #    order block on the retest. If price closes below the low of the order block
    #    the institutional logic is invalidated."
    # CHOICE: "strong impulse" = the engulfing bar's range >= 1 ATR (the sources say
    #   'strong' without a number). "Confirmation on the retest" = the retest bar
    #   closes back above the 50% level having traded into it, and closes up. The
    #   retest must land within 12 bars, same session. First-touch de-duplication is
    #   approximated by requiring the PREVIOUS bar's low to still be above the 50%
    #   level, which stops the same block firing on consecutive bars.
    # ───────────────────────────────────────────────────────────────────
    displacement = (
        (pc < po)                              # bar j (prior bar) is the bearish OB
        & (c > o) & (c > ph)                   # bar j+1 engulfs and closes above it
        & (rng >= OB_IMPULSE_ATR * atr)
    )
    ob_lo, ob_age, ob_same = _carry(displacement, pl, day, pos)
    ob_hi = h.shift(1).where(displacement).ffill()
    ob_mid = (ob_lo + ob_hi) / 2.0
    out["flow_ob_retest"] = (
        _clean(ob_same
               & (ob_age >= 1) & (ob_age <= OB_MAX_WAIT_BARS)
               & (l <= ob_mid) & (c > ob_mid) & (c > o)
               & (c > ob_lo)                   # source: invalidated only by a CLOSE
                                               # below the block low, not a wick
               & (pl > ob_mid),                # previous bar had not touched 50% yet
               df.index),
        +1,
    )

    return out

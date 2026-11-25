"""Scalping / fast-bank entry triggers for MNQ 5-min RTH bars.   prefix = "sc_"

Category: sc  (micro-pullback continuation, VWAP standard-deviation-band
reversion, VSA volume-climax fades, Bollinger/Stochastic band-touch fades).

WHY THESE, FOR THIS REGIME
--------------------------
Measured last 3 months vs the prior 4.5 years: net move flat (+1.8% vs +66.4%),
green days a coin flip (49.2%), median daily range nearly DOUBLE (451pt vs
229pt), median 5-min ATR nearly double (51.0 vs 25.9), body/range down to 44.3%
(more wick, less follow-through), ADX<20 days up.  Huge ranges with no net
progress is the textbook case for FADING extremes and banking quickly.  Four of
the six rules below are extreme-fades that trigger on a *rejection* bar (wick >
body), which is exactly the bar shape that has become more common.  The two
continuation rules are micro-pullbacks -- the shallowest possible continuation
entry (<=50% retrace, 1-3 bars), chosen because wide ATR makes any fixed
ATR-multiple stop twice as wide in dollars, so entry precision now matters more
than it did.

Every rule is a faithful port of a documented, mechanical published strategy.
The source URL sits directly above each implementation.  Where a source is
vague about a number, the concrete reading chosen is called out in a comment
beginning "READING:".  Nothing here is invented and attributed to a source.

ENTRY TRIGGERS ONLY.  No stops / targets / sizing / exits - the harness owns
those and sweeps them.

CAUSALITY NOTES
---------------
*  Every rolling window is backward-looking and includes at most the current
   bar (`.rolling(n)`, `.shift(1)`, `.cumsum()`).
*  The ONLY per-session aggregates used are `groupby(_day).cumsum()` and
   `groupby(_day).cumcount()`.  Both are running values known at the close of
   the current bar.  There is no `transform("max")`, no `transform("last")`,
   no `transform("sum")`, and no negative shift anywhere in this file.
*  The session VWAP standard deviation is built from within-day *cumulative*
   sums of v and v*tp^2, so at bar i it uses bars 0..i of that session only.
*  Rolling indicator windows (volume MA, spread MA, Donchian) may span the
   overnight gap, exactly as the harness's own df["atr"], df["bb_up"],
   df["donch_hi20"] do.  No future bar is ever touched.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# ───────────────────────── tunables ─────────────────────────
VWAP_SD_MULT = 2.0          # crosstrade: "price extends 2 x session std dev from VWAP"
VWAP_MIN_BARS = 6           # 30 min of session before the running sigma is trusted
VWAP_ADX_MAX = 25.0         # crosstrade: skip when ADX(14) 5-min > 25

MP_IMPULSE = 3              # length of the impulse leg before the pullback
MP_MIN_IMP_BARS = 2         # see READING in block 3 on the "3+ green candles" rule
MP_MAX_PULL = 3             # "1-3 red candles" pullback
MP_MAX_RETRACE = 0.50       # "Maximum retracement 50% of the prior move (default)"
MP_VOL_MULT = 1.0           # source's documented "aggressive" volume setting
MP_VOL_LEN = 20

VSA_LEN = 20                # lookback for the volume / spread averages and prior high
VSA_VOL_MULT = 1.5          # MT5 VSA indicator: climax = "volume 50% above the average"
VSA_CLOSE_THIRD = 1.0 / 3.0 # "close in the lower third of the range"

BB_STOCH_OS = 20.0          # stochastic oversold zone


# ───────────────────────── helpers ─────────────────────────
def _safe_div(a: pd.Series, b: pd.Series) -> pd.Series:
    """a / b with non-positive denominators mapped to NaN (never to +-inf)."""
    return a / b.where(b > 0)


def _all_true_window(flag: pd.Series, n: int) -> pd.Series:
    """True when the n bars ending at the current bar are all True."""
    return flag.rolling(n).sum() == n


def _session_vwap_sigma(df: pd.DataFrame, day: pd.Series) -> pd.Series:
    """Volume-weighted standard deviation of typical price about the session
    VWAP, computed from RUNNING within-day cumulative sums -> causal.

        sigma_i = sqrt( sum(v*tp^2)_0..i / sum(v)_0..i  -  vwap_i^2 )

    This is the same anchored-VWAP-band construction the sources describe; the
    harness's df["vwap"] is already the matching running mean.
    """
    tp = (df["high"] + df["low"] + df["close"]) / 3.0
    v = df["volume"]
    cum_v = v.groupby(day).cumsum()
    cum_vtp2 = (v * tp * tp).groupby(day).cumsum()
    var = _safe_div(cum_vtp2, cum_v) - df["vwap"] ** 2
    return np.sqrt(var.clip(lower=0.0))


# ───────────────────────── register ─────────────────────────
def register(df: pd.DataFrame) -> dict:
    o, h, l, c, v = df["open"], df["high"], df["low"], df["close"], df["volume"]
    day = df["_day"]
    eth = df["eth"]

    rng = h - l
    body = (c - o).abs()
    up_wick = h - pd.concat([o, c], axis=1).max(axis=1)
    dn_wick = pd.concat([o, c], axis=1).min(axis=1) - l
    close_pos = _safe_div(c - l, rng)          # 0 = close on the low, 1 = on the high

    bar_of_day = df.groupby(day).cumcount()    # 0 = 09:30 bar - causal
    vol_ma = v.rolling(MP_VOL_LEN).mean()

    out: dict[str, tuple[pd.Series, int]] = {}

    # ═══════════════════════════════════════════════════════════════════
    # 1 & 2.  VWAP 2-SIGMA REVERSION SCALP  (fade the band, target VWAP)
    # https://crosstrade.io/learn/trading-strategies/vwap-reversion
    # https://trendsandbreakouts.com/vwap-bands
    #
    #   "Price extends 2 x session standard deviations from VWAP."
    #   Long trigger : price touches or breaches the LOWER band.
    #   Short trigger: price touches or breaches the UPPER band.
    #   Rejection candle REQUIRED: "long lower wick for longs" / "long upper
    #   wick for shorts", with "body smaller than wick".
    #   Regime filter (mandatory): "ADX(14) on 5-minute > 25 (indicates strong
    #   trending regime)" -> stand aside.
    #   Time-of-day: best 10:00-11:30 ET and 13:30-14:30 ET; AVOID 09:30-10:00
    #   ("excess momentum").  Target is "VWAP itself".
    #
    #   REGIME NOTE: the 13:30-14:30 window is exactly where the measured
    #   forward 6-bar move has inverted hardest (14:00 hour: -0.2661 recent vs
    #   +0.1170 historical), so the documented short window is doing real work
    #   rather than being a decoration.
    #
    #   READING: "touches or breaches" -> the bar's HIGH reaches the upper band
    #   (LOW reaches the lower band); the close is not required to be outside.
    #   READING: the source enters "market order on the next bar open after the
    #   trigger bar closes"; the harness acts at the close of the signal bar,
    #   which is the nearest causal equivalent.
    #   READING: "volume spike on the rejection bar" is dropped as a hard gate -
    #   the source lists it under confirmation rather than in the trigger, and
    #   requiring it as well drops the firing rate under the 0.3% floor.  The
    #   two hard gates the source calls mandatory (ADX, session window) are kept.
    #   READING: the source's third filter, "opening-hour range > 2x 20-day
    #   average", is omitted: the causal version needs a 20-day history of
    #   completed opening ranges, and the ADX gate already removes the trend
    #   days it is aimed at.
    # ═══════════════════════════════════════════════════════════════════
    sigma = _session_vwap_sigma(df, day)
    vwap = df["vwap"]
    band_up = vwap + VWAP_SD_MULT * sigma
    band_dn = vwap - VWAP_SD_MULT * sigma

    sigma_ready = (bar_of_day >= VWAP_MIN_BARS) & (sigma > 0)
    calm = df["adx"] < VWAP_ADX_MAX

    # documented sessions: 10:00-11:30 and 13:30-14:30 ET (09:30-10:00 excluded)
    win = ((eth >= 10.0) & (eth <= 11.5)) | ((eth >= 13.5) & (eth <= 14.5))

    base = sigma_ready & calm & win

    out["sc_vwap_sd2_fade_short"] = (
        (base & (h >= band_up) & (up_wick > body)).fillna(False),
        -1,
    )
    out["sc_vwap_sd2_fade_long"] = (
        (base & (l <= band_dn) & (dn_wick > body)).fillna(False),
        +1,
    )

    # ═══════════════════════════════════════════════════════════════════
    # 3.  MICRO-PULLBACK CONTINUATION - LONG
    # https://www.tradingview.com/script/K0f6aI3t-Micro-Pullback-Entry-System/
    # https://www.warriortrading.com/pull-back-trading-strategy/
    #
    #   The TradingView "Micro Pullback Entry System" states the rules in code
    #   form; Warrior Trading is the originating description.
    #     * impulse   : "3+ green candles"
    #     * pullback  : "1-3 red candles", "shallow = buyers in control"
    #     * retrace   : capped at "50%" of the prior move (default setting)
    #     * entry     : "Entry triggers when green candle closes above pullback
    #                    high"  ("first green to break high")
    #     * volume    : "1.2x" multiplier on the entry candle (default)
    #     * EMA filter: 20-period EMA, price must be "Above EMA" (default ON)
    #     * stop      : "Set at pullback low"   (harness owns this - not used)
    #
    #   READING: green/red candle = close > open / close < open.
    #   READING: "pullback high" = the highest high of the 1-3 PULLBACK bars
    #   themselves, not the impulse top.  This is the literal reading of both
    #   sources: the script's stop is "set at pullback low" (the low of the red
    #   candles), so its mirror "pullback high" is the high of those same red
    #   candles, and Warrior states "the entry occurs when the first candle
    #   breaks its own high after the pullback".
    #   READING: "prior move" for the retracement test = the impulse leg's own
    #   high minus its own low; retracement = (impulse high - pullback low) /
    #   (impulse high - impulse low) <= 50%.
    #   READING: "3+ green candles" is a ONE-MINUTE-chart rule (Warrior's micro
    #   pullback is explicitly a 1-min pattern).  Three consecutive same-signed
    #   bodies is far rarer on 5-min MNQ bars: the literal reading fires on only
    #   0.13% of bars, under this harness's 0.3% floor, even at the script's
    #   most permissive documented preset.  The impulse leg is therefore read as
    #   Warrior describes it in prose - "a clear uptrend forming with higher
    #   highs" - and implemented as: over the 3 bars ending at the last impulse
    #   bar, at least 2 are green AND the close advanced across the leg.  This
    #   is the one place in this file where a source's literal number is
    #   loosened; it is called out rather than buried.
    #   READING: volume uses the script's documented "aggressive" setting of
    #   1.0x (default 1.2x, conservative 1.5x), measured against the 20-bar
    #   average.  Retracement (50%) and the EMA-20 filter (ON) stay at the
    #   script's DEFAULT settings.
    #   READING: the whole pattern (impulse + pullback + entry bar) must sit
    #   inside one RTH session - no leg may straddle the overnight gap.
    # ═══════════════════════════════════════════════════════════════════
    green, red = c > o, c < o
    imp_up = (green.rolling(MP_IMPULSE).sum() >= MP_MIN_IMP_BARS) & (c > c.shift(MP_IMPULSE))
    imp_dn = (red.rolling(MP_IMPULSE).sum() >= MP_MIN_IMP_BARS) & (c < c.shift(MP_IMPULSE))

    vol_ok = v >= MP_VOL_MULT * vol_ma

    long_any = pd.Series(False, index=df.index)
    short_any = pd.Series(False, index=df.index)

    for k in range(1, MP_MAX_PULL + 1):
        # bar layout for pullback length k, entry bar = i:
        #   impulse  i-k-MP_IMPULSE .. i-k-1   (all green)
        #   pullback i-k            .. i-1     (all red)
        #   entry    i
        # oldest bar touched is i-(k+MP_IMPULSE) -> keep the whole pattern in
        # one RTH session so no leg straddles the overnight gap.
        same_sess = day.shift(k + MP_IMPULSE) == day

        # levels measured over the PULLBACK bars only (i-k .. i-1)
        pb_high = h.rolling(k).max().shift(1)
        pb_low = l.rolling(k).min().shift(1)
        # the impulse leg's own high/low (bars i-k-MP_IMPULSE .. i-k-1)
        imp_high = h.rolling(MP_IMPULSE).max().shift(k + 1)
        imp_low = l.rolling(MP_IMPULSE).min().shift(k + 1)
        leg = imp_high - imp_low

        # ---- long: up leg, then k red bars, then a green bar closing above
        #      the pullback high, retracing no more than 50% of the leg
        long_any = long_any | (
            _all_true_window(red, k).shift(1).fillna(False)
            & imp_up.shift(k + 1).fillna(False)
            & same_sess
            & (_safe_div(imp_high - pb_low, leg) <= MP_MAX_RETRACE)
            & green
            & (c > pb_high)
        ).fillna(False)

        # ---- short mirror (see block 4)
        short_any = short_any | (
            _all_true_window(green, k).shift(1).fillna(False)
            & imp_dn.shift(k + 1).fillna(False)
            & same_sess
            & (_safe_div(pb_high - imp_low, leg) <= MP_MAX_RETRACE)
            & red
            & (c < pb_low)
        ).fillna(False)

    out["sc_micro_pull_long"] = (
        (long_any & vol_ok & (c > df["ema20"])).fillna(False),
        +1,
    )

    # ═══════════════════════════════════════════════════════════════════
    # 4.  MICRO-PULLBACK CONTINUATION - SHORT  (bear-flag breakdown)
    # https://highstrike.com/bear-flag-pattern/
    # https://bullishbears.com/bear-flag-patterns/
    #
    #   "Bear flag patterns consist of ... several smaller bearish candlesticks
    #   down, forming the flag pole, followed by several smaller bullish
    #   candlesticks pulling back up ... which forms the flag."
    #   "The cleanest entry is when price breaks and closes below the lower
    #   trendline of the flag."  Aggressive entry = "short on the close of the
    #   breakdown candle, ideally with a volume spike confirming participation";
    #   "a price break on low volume is the single biggest red flag".
    #
    #   READING: the geometry is the exact mirror of block 3 (the two sources
    #   describe the same pole/flag structure from opposite sides), so the same
    #   concrete numbers are reused: 3-bar pole, 1-3 bar flag, <=50% retrace,
    #   volume at or above the 20-bar average on the breakdown bar ("a price
    #   break on low volume is the single biggest red flag"), price below the
    #   20 EMA.
    #   READING: "lower trendline of the flag" -> the lowest low of the 1-3 flag
    #   bars; "breaks and closes below" -> the entry bar's CLOSE is under it,
    #   which is also the source's "aggressive entry ... on the close of the
    #   breakdown candle".
    # ═══════════════════════════════════════════════════════════════════
    out["sc_micro_pull_short"] = (
        (short_any & vol_ok & (c < df["ema20"])).fillna(False),
        -1,
    )

    # ═══════════════════════════════════════════════════════════════════
    # 5.  VSA UPTHRUST FADE  (volume-climax rejection of a new high)
    # https://tradersunion.com/technic-analysis/volume-spread-analysis/
    # https://github.com/Andre-Luis-Lopes-da-Silva/Volume-Spread-Analysis-VSA-indicator-for-Metatrader-5
    # https://www.quantum-algo.com/blog/guides/volume-spread-analysis-vsa-complete-guide/
    #
    #   Traders Union: "an upthrust is a bar that breaks above a prior high on
    #   volume, then closes at or below the prior high, with a wide spread up
    #   and close in the lower third, on high volume."
    #   Quantum-algo: Upthrust = "wide bar spikes up then closes low on high
    #   volume - a failed push where supply overwhelms demand."
    #   The MT5 VSA indicator supplies the missing threshold in code form: a
    #   climax bar is "volume 50% above the average" with "price closes in the
    #   lower third of the range".
    #
    #   READING: "a prior high" = the highest high of the previous 20 bars
    #   (the same 20-bar window used for the volume and spread averages).
    #   READING: "high volume" = the MT5 indicator's coded 1.5x average, since
    #   quantum-algo explicitly states the prose sources carry no thresholds.
    #   READING: "wide spread" = bar range above its own 20-bar mean range.
    #   READING: "closes at or below the prior high" is enforced literally, and
    #   is what separates an upthrust from a genuine breakout bar.
    # ═══════════════════════════════════════════════════════════════════
    prior_high = h.rolling(VSA_LEN).max().shift(1)
    spread_ma = rng.rolling(VSA_LEN).mean()

    out["sc_vsa_upthrust_short"] = (
        (
            (h > prior_high)                       # spikes above a prior high
            & (c <= prior_high)                    # but closes back at/below it
            & (close_pos <= VSA_CLOSE_THIRD)       # close in the lower third
            & (v > VSA_VOL_MULT * vol_ma)          # on high volume
            & (rng > spread_ma)                    # wide spread
        ).fillna(False),
        -1,
    )

    # ═══════════════════════════════════════════════════════════════════
    # 6.  BOLLINGER-BAND + STOCHASTIC BAND-TOUCH SCALP  (long side)
    # https://fbs.eu/en/analytics/tips/a-scalping-strategy-you-were-hungry-for-27189
    # https://forextester.com/blog/bollinger-bands-rsi-stochastic-scalping-strategy/
    #
    #   Timeframe M5.  "Bollinger Bands with the following settings: a period of
    #   20, 2 standard deviations" and a "Stochastic Oscillator".
    #   "Buy when price touches the lower Bollinger Band AND stochastic enters
    #   oversold territory."  Take profit is the middle SMA / upper band - i.e.
    #   a fast bank back to the mean, which is the point of the rule here.
    #   Both sources state the strategy is for "flat, sideways market
    #   consolidation periods rather than trending conditions".
    #
    #   REGIME NOTE: this is NOT the user's oversold-RECLAIM entry (which now
    #   shows -0.176 ATR / 44.8% win).  That rule waits for stochastic to cross
    #   back UP out of oversold, i.e. it buys the bounce as momentum.  This one
    #   fires ON the extreme itself with no reclaim, which is the fade the
    #   measured regime (flat net move, double range, more wick) argues for.
    #
    #   READING: "price touches the lower band" -> the bar's LOW reaches or
    #   pierces df["bb_dn"] (the harness's SMA20 -/+ 2*std20, exactly the
    #   source's setting).
    #   READING: the source's Stochastic is (14,5,3) / (14,3,3); the harness
    #   supplies raw %K(14).  Oversold zone = %K < 20, the standard level.
    #   READING: "trending conditions" are excluded with the same ADX(14) < 25
    #   gate crosstrade specifies in block 1, rather than a number these two
    #   sources do not give.
    #   READING: the short mirror ("sell when price touches the upper band AND
    #   stochastic enters the overbought zone") is not registered - block 5
    #   already fades upside extremes, and the upper-band mirror fires on 1.6%
    #   of bars if it is ever wanted.
    # ═══════════════════════════════════════════════════════════════════
    out["sc_bb_stoch_fade_long"] = (
        (
            (l <= df["bb_dn"])
            & (df["stochK"] < BB_STOCH_OS)
            & calm
            & (bar_of_day >= 1)
        ).fillna(False),
        +1,
    )

    # keep every series a clean bool Series on df.index
    return {
        k: (s.reindex(df.index).fillna(False).astype(bool), side)
        for k, (s, side) in out.items()
    }

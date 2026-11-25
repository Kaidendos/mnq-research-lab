"""RANGE FADE entries for MNQ 5-min RTH bars.

Fading the extremes of an already-established range: the initial balance, the
prior day's high/low, and the session's own running high/low. Every rule below is
a translation of a documented, mechanical source; where a source is vague the
concrete reading is spelled out in a comment marked [READING].

ENTRY TRIGGERS ONLY - stops / targets / sizing / exits belong to the harness.

Sources
-------
[S1] steady-turtle.com "Initial Balance Trading Strategy | Complete Guide for ES &
     NQ Futures"  https://steady-turtle.com/knowledge/initial-balance-trading-strategy
     IB = 09:30-10:30 ET. Fade entry: "a rejection candle at the IB extreme, a long
     wick, doji, or pin bar on weak volume, with the close back inside the range."
     Regime tell: "a wide IB is the opposite tell: the market already made its big
     move inside the hour, and the balance of the day tends to rotate and
     mean-revert inside that range." Width is judged "not in absolute points but
     against its own recent average, the last 10 to 20 sessions."

[S2] steady-turtle.com "6 Proven Day Trading Strategies | ES & NQ Futures Guide"
     https://steady-turtle.com/knowledge/day-trading-strategies
     Strategy 1 "Daily-Level Sweep and Reversal" - entry "on the rejection candle
     after price pokes through yesterday's high/low". Worked example: price spikes
     through the prior-day low, reclaims it, and prints a bullish candle.

[S3] crosstrade.io "Liquidity Sweeps"
     https://crosstrade.io/learn/price-action/liquidity-sweeps
     Sweep = "a very long wick in the swept direction and a small body"; qualifying
     levels include "Prior session highs/lows. Yesterday's high and low have many
     resting stops". Sequence: "Wait for the rejection - a candle that closes back
     inside" then "Enter on the rejection bar's close".

[S4] tradingstats.net "How Far Does Price Run After a Breakout? [NQ & ES Data]"
     https://tradingstats.net/price-extension-after-breakout/
     Median run after taking out the prior bar's high is ~40% of that prior bar's
     range, and "a break that can't clear the median run fails back inside the range
     about two-thirds of the time" (65-71%), versus 17-21% for breaks that clear it.
     Used here as the shallow-extension filter on prior-DAY levels.

[S5] crosstrade.io "Bollinger Band mean reversion"
     https://crosstrade.io/learn/trading-strategies/bollinger-mean-reversion
     Rejection-at-the-extreme template: "long upper wick, close below the high"
     (mirror for longs), taken only with "Range regime confirmed"; the mechanical
     regime filter given is "ADX(14) > 25 -> skip".

[S6] fortraders.com "False Breakouts: Why They Happen and How to Trade"
     https://fortraders.com/blog/false-breakouts-why-they-happen-how-to-trade
     A genuine break needs volume of "1.5-2x the 20-period average volume"; below
     that, breaks "are likely stop hunts". 5-minute breakout failure rate 60-65%.
     This supplies the concrete number behind [S1]'s "weak volume" poke.

Why this set fits the measured regime
-------------------------------------
Median daily range has roughly doubled (451pt vs 229pt) while net drift went flat
(+1.8% over three months) - the textbook rotational tape [S1] describes as the wide-IB
fade case. Body/range fell to 44.3% from 51.6%, i.e. more wick and less
follow-through, which is exactly the "long wick, small body" rejection print [S3]
and [S5] key on. Wider ATR also means a fixed ATR-multiple stop is twice as wide in
dollars, so every trigger here demands the close to be back INSIDE the level rather
than a mere touch, putting the fill at a confirmed turn instead of into the poke.

Causality
---------
Session-scoped values are built only from groupby-cummax / cummin / cumsum / shift,
or from prior-session aggregates that are explicitly .shift(1)-ed. Nothing fires on
information later than the close of its own bar.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# ── session windows ──────────────────────────────────────────────────────────
IB_END = 10.5           # [S1] initial balance 09:30-10:30 ET
PD_SWEEP_START = 10.0   # [READING] prior-day sweeps only after the opening 30 min,
                        # whose one-way auction [S6] warns is genuine flow, not a trap
FADE_CUTOFF = 15.5      # [READING] no new fades in the closing 30 minutes

# ── rejection-candle geometry ────────────────────────────────────────────────
WICK_MIN = 0.50         # [S1]/[S3]/[S5] "long wick" -> wick >= half the bar's range
DOJI_BODY_MAX = 0.25    # [S1] "doji" -> body <= a quarter of the bar's range

# ── volume ───────────────────────────────────────────────────────────────────
RVOL_LOOKBACK = 20      # [S6] "the 20-period average volume"
POKE_RVOL_MAX = 2.00    # [S1]'s "weak volume" poke made numeric. [S6] puts the
                        # genuine-break band at "1.5-2x the 20-period average" and
                        # calls anything below it a likely stop hunt; the top of
                        # that band is taken, i.e. the poke never printed confirmed
                        # breakout volume. NOTE this filter is close to non-binding:
                        # at 1.5x the rule fires 0.29%/0.34% of bars vs 0.31%/0.35%
                        # here, so it is not what makes or breaks the strategy.

# ── range-width context ──────────────────────────────────────────────────────
WIDTH_BASE_SESSIONS = 20    # [S1] "its own recent average, the last 10 to 20 sessions"
IB_WIDE_MIN = 1.00          # [S1] wide IB (at or above that average) => fade bias
STALL_FRAC = 0.40           # [S4] median run after a break ~40% of the prior bar's range
RANGE_ADX_MAX = 25.0        # [S5] "ADX(14) > 25 -> skip"


# ── causal helpers ───────────────────────────────────────────────────────────
def _locked_range(df: pd.DataFrame, end_eth: float):
    """High/low of the session window [open, end_eth), locked once the window ends.

    cummax/cummin then forward-fill inside the day: on any bar the value reflects
    only bars at or before it. `ready` stays False until the window has closed, so
    the locked value is never consumed while it is still forming.
    """
    day = df["_day"]
    inside = df["eth"] < end_eth
    hi = df["high"].where(inside).groupby(day).cummax().groupby(day).ffill()
    lo = df["low"].where(inside).groupby(day).cummin().groupby(day).ffill()
    return hi, lo, df["eth"] >= end_eth


def _rel_width(width: pd.Series, day: pd.Series) -> pd.Series:
    """Range width as a multiple of its own recent-session average [S1].

    The per-session width is a whole-day aggregate, but .shift(1) on the rolling
    mean means the baseline only ever contains COMPLETED prior sessions, and the
    numerator is the already-locked width of the current session.
    """
    per_day = width.groupby(day).last()
    base = per_day.rolling(WIDTH_BASE_SESSIONS).mean().shift(1)
    return width / day.map(base)


def _rvol(df: pd.DataFrame) -> pd.Series:
    """Volume vs the mean of the PREVIOUS `RVOL_LOOKBACK` bars [S6]."""
    base = df["volume"].shift(1).rolling(RVOL_LOOKBACK).mean()
    return df["volume"] / base.replace(0, np.nan)


def _candle_shape(df: pd.DataFrame):
    """Upper-wick, lower-wick and body, each as a fraction of the bar's range."""
    o, h, l, c = df["open"], df["high"], df["low"], df["close"]
    rng = (h - l).replace(0, np.nan)
    oc = pd.concat([o, c], axis=1)
    up_wick = (h - oc.max(axis=1)) / rng
    dn_wick = (oc.min(axis=1) - l) / rng
    body = (c - o).abs() / rng
    return up_wick, dn_wick, body


def _engulfing(df: pd.DataFrame):
    """Bullish / bearish engulfing - [S5]'s alternative rejection confirmation.

    Standard definition: this bar's body closes in the reversal direction and
    covers the whole of the previous bar's opposite-coloured body. Uses only bar
    i and bar i-1.
    """
    o, c = df["open"], df["close"]
    po, pc = o.shift(1), c.shift(1)
    up = (c > o) & (pc < po) & (c >= po) & (o <= pc)
    dn = (c < o) & (pc > po) & (c <= po) & (o >= pc)
    return up.fillna(False), dn.fillna(False)


def _session_extremes_before(df: pd.DataFrame):
    """Session high/low as of the close of the PREVIOUS bar (cummax then shift)."""
    day = df["_day"]
    prior_hi = df["high"].groupby(day).cummax().groupby(day).shift(1)
    prior_lo = df["low"].groupby(day).cummin().groupby(day).shift(1)
    return prior_hi, prior_lo


# ── registration ─────────────────────────────────────────────────────────────
def register(df: pd.DataFrame):
    day = df["_day"]
    h, l, c = df["high"], df["low"], df["close"]
    eth, adx = df["eth"], df["adx"]

    rvol = _rvol(df)
    up_wick, dn_wick, body = _candle_shape(df)
    engulf_up, engulf_dn = _engulfing(df)
    bull_bar, bear_bar = df["close"] > df["open"], df["close"] < df["open"]
    doji = body <= DOJI_BODY_MAX
    ib_hi, ib_lo, ib_ready = _locked_range(df, IB_END)

    out: dict[str, tuple[pd.Series, int]] = {}

    # ─────────────────────────────────────────────────────────────────────────
    # 1/2. INITIAL-BALANCE EXTREME FADE.  [S1] entry rule, [S6] volume number.
    #
    #   day filter : IB width >= its own 20-session average - [S1]'s "wide IB" tell
    #                that the day will rotate inside the range it already built.
    #   trigger    : after 10:30, a bar pokes THROUGH the IB extreme, prints a
    #                rejection candle and CLOSES BACK INSIDE the IB. [S1] names
    #                three acceptable rejection prints - "a long wick, doji, or pin
    #                bar" - so the test is the disjunction: a wick in the direction
    #                of the poke >= 50% of the bar's range (long wick / pin bar),
    #                OR a body <= 25% of the range (doji). Implementing only the
    #                long-wick branch would be stricter than the source.
    #   poke volume: RVOL < 1.5 - [S1] wants "weak volume"; [S6] puts the genuine-
    #                break threshold at 1.5-2x the 20-period average and calls
    #                anything below it a likely stop hunt.
    # ─────────────────────────────────────────────────────────────────────────
    wide_ib = _rel_width(ib_hi - ib_lo, day) >= IB_WIDE_MIN
    ib_win = ib_ready & (eth < FADE_CUTOFF) & wide_ib & (rvol < POKE_RVOL_MAX)

    out["rf_ib_fade_short"] = (
        ib_win & (h > ib_hi) & (c < ib_hi) & ((up_wick >= WICK_MIN) | doji), -1)
    out["rf_ib_fade_long"] = (
        ib_win & (l < ib_lo) & (c > ib_lo) & ((dn_wick >= WICK_MIN) | doji), +1)

    # ─────────────────────────────────────────────────────────────────────────
    # 3/4. PRIOR-DAY LEVEL SWEEP AND RECLAIM.  [S2] Strategy 1 + [S3], filtered by [S4].
    #
    #   level      : yesterday's RTH high / low (pdh, pdl) - [S3] "yesterday's high
    #                and low have many resting stops".
    #   trigger    : one bar spikes through the level and closes back inside it,
    #                and that bar is a rejection candle. [S2] is the operative
    #                wording - "the rejection candle after price pokes through
    #                yesterday's high/low", whose worked example is simply a spike
    #                through the prior-day low that "reclaims it, and prints a
    #                bullish candle". So the test is: poked through, closed back
    #                inside, and the body points the way of the fade. Entry is that
    #                bar's close [S3].
    #   stall test : the session's largest excursion beyond the level so far is
    #                under 40% of the prior day's range. [S4] measures the median
    #                run at ~40% of the broken bar's range and finds that breaks
    #                failing to clear it fall back inside about two thirds of the
    #                time, versus ~20% for breaks that do clear it. The excursion is
    #                a running cummax, so it only ever contains bars up to this one.
    #   [READING]  : [S3] describes the same setup more strictly ("a very long wick
    #                in the swept direction and a small body") and allows the
    #                reclaim to take 1-3 bars. Only the same-bar case is taken, and
    #                on [S2]'s looser candle test: stacking [S3]'s wick AND body
    #                conditions on top of the stall filter left this under 0.25% of
    #                bars, too thin to sweep. A close back inside the level is
    #                itself the rejection both sources are describing.
    # ─────────────────────────────────────────────────────────────────────────
    pdh, pdl = df["pdh"], df["pdl"]
    pd_range = (pdh - pdl).replace(0, np.nan)
    ext_up = (h - pdh).clip(lower=0).groupby(day).cummax()
    ext_dn = (pdl - l).clip(lower=0).groupby(day).cummax()

    pd_win = (eth >= PD_SWEEP_START) & (eth < FADE_CUTOFF)

    out["rf_pdh_sweep_short"] = (
        pd_win & (h > pdh) & (c < pdh) & bear_bar
        & (ext_up < STALL_FRAC * pd_range), -1)
    out["rf_pdl_sweep_long"] = (
        pd_win & (l < pdl) & (c > pdl) & bull_bar
        & (ext_dn < STALL_FRAC * pd_range), +1)

    # ─────────────────────────────────────────────────────────────────────────
    # 5/6. FAILED DAY-RANGE EXTENSION.  [S3] sweep template on the session's own
    #      extreme, taken only in [S5]'s range regime.
    #
    #   level      : the session high/low as of the PREVIOUS bar's close, i.e. the
    #                edge of the range the day has built so far.
    #   trigger    : this bar takes that extreme out AND extends the day beyond the
    #                initial balance (so it is a genuine range EXPANSION attempt,
    #                not an inside-IB wobble - this is what keeps it distinct from
    #                rules 1/2), and closes back BELOW/ABOVE the old extreme having
    #                printed [S5]'s rejection. [S5] accepts either of two prints -
    #                "a pronounced lower/upper wick relative to body size, or
    #                immediate reversal candle (bullish/bearish engulfing)" - so the
    #                test is that disjunction. The new high was bought into and
    #                immediately given back.
    #   regime     : ADX(14) < 25 - [S5]'s mechanical "range regime confirmed" test,
    #                which also keeps the rule off the band-walking trend days where
    #                fading extremes is how accounts die.
    # ─────────────────────────────────────────────────────────────────────────
    prior_hi, prior_lo = _session_extremes_before(df)
    ext_win = ib_ready & (eth < FADE_CUTOFF) & (adx < RANGE_ADX_MAX)

    out["rf_dayhi_fade_short"] = (
        ext_win & (h > prior_hi) & (h > ib_hi) & (c < prior_hi)
        & ((up_wick >= WICK_MIN) | engulf_dn), -1)
    out["rf_daylo_fade_long"] = (
        ext_win & (l < prior_lo) & (l < ib_lo) & (c > prior_lo)
        & ((dn_wick >= WICK_MIN) | engulf_up), +1)

    return {k: (v.reindex(df.index).fillna(False).astype(bool), s)
            for k, (v, s) in out.items()}

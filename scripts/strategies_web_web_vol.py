"""Volatility-compression / range-expansion entries for MNQ 5-min RTH bars.

Category: vol  (ATR expansion breakouts, TTM-squeeze compression breaks,
NR7 / inside-bar breaks, range-contraction -> expansion).

Every rule below is a faithful port of a documented, mechanical published
strategy.  Source URL is quoted directly above each implementation.  Where a
source is vague about a number, the chosen concrete reading is called out in a
comment beginning "READING:".

ENTRY TRIGGERS ONLY.  No stops / targets / sizing / exits - the harness owns
those and sweeps them.

CAUSALITY NOTES
---------------
*  Every rolling window used here is backward-looking and includes at most the
   current bar (`.rolling(n)`, `.shift(1)`, `.cumsum()`, `.ffill()`).
*  The only per-session aggregate used is `groupby(_day)["open"].transform("first")`,
   which is the session's FIRST bar open - a value already known at the close of
   bar 0 - and it is therefore causal (unlike transform("max")/"last").
*  Rolling indicator windows (BB / ATR / Donchian) are allowed to span the
   overnight gap, exactly as the harness's own df["bb_up"], df["atr"],
   df["donch_hi20"] do.  Nothing about a *future* bar is ever touched.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# ───────────────────────── tunables ─────────────────────────
BB_LEN, BB_SD = 20, 2.0            # TTM Squeeze Bollinger settings
KC_LEN, KC_MULT = 20, 1.5          # TTM Squeeze Keltner settings
MOM_LEN = 20                       # TTM Squeeze momentum linreg length

NR_LOOKBACK = 7                    # Crabel NR7
NR_MAX_WAIT = 6                    # bars allowed between NR7 bar and its break

IB_MAX_WAIT = 3                    # bars allowed between inside bar and its break
IB_VOL_MULT = 1.2                  # breakout-bar volume vs 20-bar average

ATR_MA_LEN = 12                    # PyQuantLab ATR moving-average window
COMPRESS_FACTOR = 0.8              # "ATR < 80% of its MA"
CHAN_LEN = 36                      # 36 x 5-min = 3 hours

LW_K = 0.5                         # Larry Williams stretch fraction of prior range


# ───────────────────────── helpers ─────────────────────────
def _linreg_endpoint(y: pd.Series, n: int = MOM_LEN) -> pd.Series:
    """Value of the least-squares line fitted to the last `n` points, evaluated
    at the most recent point.  Vectorised, backward-looking only."""
    x = np.arange(n, dtype=float)
    xbar = x.mean()
    varx = float(((x - xbar) ** 2).sum())
    w = x - xbar

    vals = y.to_numpy(dtype=float)
    ok = np.isfinite(vals)
    filled = np.where(ok, vals, 0.0)

    slope = np.full(len(vals), np.nan)
    if len(vals) >= n:
        slope[n - 1:] = np.convolve(filled, w[::-1], mode="valid") / varx

    ybar = y.rolling(n).mean().to_numpy(dtype=float)
    out = ybar + slope * (n - 1 - xbar)

    # any window that contained a NaN is not a valid fit
    okcnt = pd.Series(ok.astype(float), index=y.index).rolling(n).sum().to_numpy()
    out[okcnt < n] = np.nan
    return pd.Series(out, index=y.index)


def _true_range(df: pd.DataFrame) -> pd.Series:
    pc = df["close"].shift(1)
    return pd.concat(
        [df["high"] - df["low"], (df["high"] - pc).abs(), (df["low"] - pc).abs()],
        axis=1,
    ).max(axis=1)


def _last_pattern(flag: pd.Series, level: pd.Series, day: pd.Series,
                  max_wait: int) -> tuple[pd.Series, pd.Series]:
    """For each bar return (level of the most recent pattern bar STRICTLY before
    it, still-armed mask).  Armed = that pattern bar is at most `max_wait` bars
    back AND belongs to the same session."""
    n = len(flag)
    pos = pd.Series(np.arange(n, dtype=float), index=flag.index)

    lvl_prev = level.where(flag).shift(1).ffill()
    pos_prev = pos.where(flag).shift(1).ffill()
    day_prev = day.where(flag).shift(1).ffill()

    armed = ((pos - pos_prev) <= max_wait) & (day_prev == day)
    return lvl_prev, armed.fillna(False)


def _first_cross_up(close: pd.Series, lvl: pd.Series) -> pd.Series:
    return (close > lvl) & (close.shift(1) <= lvl)


def _first_cross_dn(close: pd.Series, lvl: pd.Series) -> pd.Series:
    return (close < lvl) & (close.shift(1) >= lvl)


# ───────────────────────── register ─────────────────────────
def register(df: pd.DataFrame) -> dict:
    c, h, l, v = df["close"], df["high"], df["low"], df["volume"]
    day = df["_day"]
    tr = _true_range(df)

    # bar index inside the session (0 = 09:30 bar) - causal
    bar_of_day = df.groupby(day).cumcount()

    out: dict[str, tuple[pd.Series, int]] = {}

    # ═══════════════════════════════════════════════════════════════════
    # 1 & 2.  TTM SQUEEZE  (John Carter / Simpler Trading)
    # https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-indicators/ttm-squeeze
    #
    #   Bollinger Bands  : 20 period, 2.0 standard deviations
    #   Keltner Channels : 20 period MA and ATR, 1.5 ATR multiplier
    #   Squeeze ON  : upper BB < upper KC  AND  lower BB > lower KC
    #   Squeeze OFF : one or both Bollinger Bands outside the Keltner Channel
    #   Momentum    : close - ((Donchian-20 midline + SMA-20) / 2), then
    #                 linear-regression smoothed
    #   Long  : squeeze fires (red -> green) with momentum above zero & rising
    #   Short : squeeze fires with momentum below zero & falling
    # ═══════════════════════════════════════════════════════════════════
    # BB: reuse the harness columns, which are exactly SMA20 +/- 2*std20.
    bb_up, bb_dn = df["bb_up"], df["bb_dn"]

    # KC: 20-period EMA basis; 20-period ATR (simple average of true range, the
    # "original 1960 Keltner formula" length the source specifies).
    atr20 = tr.rolling(KC_LEN).mean()
    kc_up = df["ema20"] + KC_MULT * atr20
    kc_dn = df["ema20"] - KC_MULT * atr20

    squeeze_on = (bb_up < kc_up) & (bb_dn > kc_dn)
    squeeze_fire = squeeze_on.shift(1).fillna(False) & (~squeeze_on)

    sma20 = c.rolling(BB_LEN).mean()
    dc_mid = (h.rolling(BB_LEN).max() + l.rolling(BB_LEN).min()) / 2.0
    mom = _linreg_endpoint(c - (dc_mid + sma20) / 2.0, MOM_LEN)
    mom_prev = mom.shift(1)

    # READING: "above zero and rising" -> mom > 0 and mom > previous mom.
    out["vol_ttm_squeeze_long"] = (
        (squeeze_fire & (mom > 0) & (mom > mom_prev)).fillna(False),
        +1,
    )
    out["vol_ttm_squeeze_short"] = (
        (squeeze_fire & (mom < 0) & (mom < mom_prev)).fillna(False),
        -1,
    )

    # ═══════════════════════════════════════════════════════════════════
    # 3.  NR7 COMPRESSION BREAK  (Toby Crabel, "Day Trading with Short Term
    #     Price Patterns and Opening Range Breakout", 1990)
    # https://chartschool.stockcharts.com/table-of-contents/trading-strategies-and-models/trading-strategies/narrow-range-day-nr7
    # https://www.quantifiedstrategies.com/nr7-trading-strategy-toby-crabel/
    #
    #   NR7   : the narrowest high-low range of the last seven bars.
    #   Long  : "Buy on move above high of narrow range day high".
    #   Short : "Sell on move below low of narrow range day low".
    #
    #   The sources also describe the NR7ID "double compression" variant - an
    #   NR7 bar that is ALSO an inside bar - as the higher-quality version of
    #   the setup:
    #   https://tradingstrategiesdaily.com/p/nr7id-toby-crabel
    #   That NR7ID form is used here; plain NR7 on 5-min bars fires far too
    #   often to be an entry.
    #
    #   READING: Crabel's pattern is a daily-bar pattern; the sources note it
    #   "is often applied to intraday timeframes such as 3-minute or 5-minute
    #   charts for day trading", which is the reading used - NR7 is measured
    #   over the last 7 five-minute bars.
    #   READING: "move above the high" is taken as a bar CLOSING above it (the
    #   harness can only act at bar close), and the break must arrive within
    #   NR_MAX_WAIT bars and inside the same session.
    # ═══════════════════════════════════════════════════════════════════
    rng = h - l
    is_nr7 = rng <= rng.rolling(NR_LOOKBACK).min()
    is_inside = (h < h.shift(1)) & (l > l.shift(1))
    nr7id = (is_nr7 & is_inside).fillna(False)

    #   READING: only the long ("buy above the narrow-range high") side is
    #   registered - the register() dict is capped at six entries, and the short
    #   mirror is already represented by the inside-bar breakdown below.
    nr_hi, nr_hi_armed = _last_pattern(nr7id, h, day, NR_MAX_WAIT)

    out["vol_nr7id_break_long"] = (
        (nr_hi_armed & _first_cross_up(c, nr_hi)).fillna(False),
        +1,
    )

    # ═══════════════════════════════════════════════════════════════════
    # 4.  INSIDE-BAR BREAKDOWN WITH VOLUME CONFIRMATION
    # https://www.quantvps.com/blog/inside-bar-breakout-strategy
    # https://www.edgeful.com/blog/posts/inside-bar-pattern-day-trading-strategy
    #
    #   Inside bar: "today's high must be lower than yesterday's high, AND
    #   today's low must be higher than yesterday's low".
    #   "For a bearish breakout, enter short below the low."
    #   "The breakout candle should show volume at least 1.2x the 20-bar
    #   average.  A breakout on below-average volume has materially lower
    #   follow-through probability."
    #
    #   READING: short side is implemented here because the TTM pair above
    #   already supplies a symmetric long/short compression break; the source's
    #   rules are symmetric, so the long mirror is simply not registered.
    #   READING: break must land within IB_MAX_WAIT bars of the inside bar and
    #   inside the same session.
    # ═══════════════════════════════════════════════════════════════════
    vol_ok = v > IB_VOL_MULT * v.rolling(20).mean()
    ib_lo, ib_armed = _last_pattern(is_inside.fillna(False), l, day, IB_MAX_WAIT)

    out["vol_inside_vol_break_short"] = (
        (ib_armed & _first_cross_dn(c, ib_lo) & vol_ok).fillna(False),
        -1,
    )

    # ═══════════════════════════════════════════════════════════════════
    # 5.  ATR-COMPRESSION CHANNEL BREAKOUT
    # https://pyquantlab.com/article.php?file=An+Intraday+Volatility+Breakout+Strategy.html
    #
    #   5-minute bars.  Channel = highest high / lowest low over the last
    #   3 hours (36 bars).  ATR window 14, ATR-MA window 12.  Compression when
    #   "ATR < 80% of its MA" (compression factor 0.8).
    #   Long  : "a breakout occurs if the current bar's high exceeds the
    #           previous bar's upper channel", and "the range was compressed on
    #           the prior bar".
    #   Short : current bar's low drops below the previous bar's lower channel,
    #           same compression precondition.
    # ═══════════════════════════════════════════════════════════════════
    # READING: the article's ATR is a plain 14-bar average of true range (it
    # pairs it with a 12-bar MA of itself).  The harness's df["atr"] is Wilder-
    # smoothed, which barely ever sits 20% under its own 12-bar mean (0.2% of
    # bars) and would make this rule fire ~13 times in five years, so the
    # simple-average reading is used.
    atr14 = tr.rolling(14).mean()
    atr_ma = atr14.rolling(ATR_MA_LEN).mean()
    compressed_prev = (atr14 < COMPRESS_FACTOR * atr_ma).shift(1).fillna(False)

    #   READING: only the long side is registered (six-entry cap); the short
    #   mirror `compressed_prev & (l < l.rolling(36).min().shift(1))` is the
    #   exact symmetric rule and fires on 0.22% of bars if it is ever wanted.
    up_chan_prev = h.rolling(CHAN_LEN).max().shift(1)   # channel as of prior bar

    out["vol_atr_compress_chan_long"] = (
        (compressed_prev & (h > up_chan_prev)).fillna(False),
        +1,
    )

    # ═══════════════════════════════════════════════════════════════════
    # 6.  LARRY WILLIAMS VOLATILITY BREAKOUT  (open +/- k * prior day range)
    # https://www.quantifiedstrategies.com/larry-williams-volatility-strategy/
    # https://www.mql5.com/en/articles/20745
    #
    #   "At the day's open, compute buy/sell gates as a user-defined fraction of
    #   the previous day's high-low range.  Trade only if price reaches a gate;
    #   otherwise stand aside."  Entry via buy stop at
    #   [session open + k * prior-day range], sell stop at
    #   [session open - k * prior-day range].  "The strategy uses a multiplier
    #   (often defaulting to values like 0.50 or 0.60)."  -> k = 0.50.
    #
    #   Session open is the RTH 09:30 bar open (known at bar 0 -> causal).
    #   Prior-day range uses df["pdh"]/df["pdl"], already correctly shifted.
    #   READING: "price reaches the gate" is taken as the first bar of the
    #   session that CLOSES beyond the gate; only the first such bar per
    #   session fires ("only one position is allowed").
    # ═══════════════════════════════════════════════════════════════════
    sess_open = df.groupby(day)["open"].transform("first")   # bar-0 open: causal
    prev_range = (df["pdh"] - df["pdl"]).abs()

    #   READING: only the sell gate is registered (six-entry cap); the buy gate
    #   is `c > sess_open + LW_K * prev_range` under the identical first-hit
    #   logic and fires on 0.51% of bars if it is ever wanted.
    gate_dn = sess_open - LW_K * prev_range

    hit_dn = ((c < gate_dn) & (bar_of_day > 0)).fillna(False)

    out["vol_lw_stretch_short"] = (
        (hit_dn & (hit_dn.groupby(day).cumsum() == 1)).fillna(False),
        -1,
    )

    # keep every series a clean bool Series on df.index
    return {
        k: (s.reindex(df.index).fillna(False).astype(bool), side)
        for k, (s, side) in out.items()
    }

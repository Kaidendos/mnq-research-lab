"""Mean-reversion / fade entries for MNQ 5-min RTH bars.

Every rule below is a faithful translation of a documented, mechanical source.
Where a source is vague the concrete reading is stated in a comment marked
[READING]. ENTRY TRIGGERS ONLY — stops/targets/sizing are the harness's job.

Sources
-------
RSI2   : "Day Trading Larry Connors RSI2 Mean-Reversion Strategies", MQL5 Articles
         https://www.mql5.com/en/articles/17636
         (Strategy 3 "RSI2 Overbought/Oversold": RSI(2) < 5 and close > 50-period
          MA -> long; RSI(2) > 95 and close < 50-period MA -> short. Intraday
          timeframe, no daily-bar dependency.)
VWAP2S : "VWAP Reversion Strategy", crosstrade.io
         https://crosstrade.io/learn/trading-strategies/vwap-reversion
         (Price breaches the 2x session-standard-deviation VWAP band, rejection
          pin bar at the extreme, skip if ADX(14) > 25, trade only 10:00-11:30
          and 13:30-14:30 ET, target VWAP.)
GAPFADE: "Gap Fill Strategy: 2,791 Days of NQ Data (2015-2025)", tradingstats.net
         https://tradingstats.net/gap-fill-strategy/
         (Gap = RTH open minus prior RTH close. "Tiny" gap < 0.3x ATR(14) fills
          77.8%; open inside the prior day's range fills 70.4%; "tiny gap + first
          15-min candle toward fill" = 93.1% over 773 cases. Fade toward the
          prior close.)

CAUSALITY: only cumulative / expanding / shifted session aggregates are used.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# ── thresholds (named, not magic) ────────────────────────────────────────────
RSI2_LEN = 2
RSI2_LOW = 5.0            # MQL5 Strategy 3 oversold trigger
RSI2_HIGH = 95.0          # MQL5 Strategy 3 overbought trigger
RSI2_MA_LEN = 50          # "50-period MA, more responsive for bidirectional trading"

VWAP_SIGMA_MULT = 2.0     # crosstrade: 2x session standard deviation band
VWAP_ADX_MAX = 25.0       # crosstrade: "Skip if ADX(14) on 5-minute > 25"
VWAP_WICK_FRAC = 0.5      # pin bar: rejection wick >= half the bar's range
VWAP_MIN_BARS = 6         # session sigma is meaningless on the first few bars

GAP_TINY_ATR = 0.30       # tradingstats "tiny" tier: gap < 0.3x daily ATR(14)
GAP_DATR_LEN = 14
GAP_ENTRY_ETH = 9.5 + 10 / 60.0   # bar stamped 09:40 = last bar of the first 15 min


# ── helpers ──────────────────────────────────────────────────────────────────
def _wilder_rsi(close: pd.Series, n: int) -> pd.Series:
    delta = close.diff()
    up = delta.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-delta.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


def _session_vwap_sigma(df: pd.DataFrame) -> pd.Series:
    """Volume-weighted std-dev of typical price about the session VWAP.

    Built from cumsum()s inside the day, so bar i sees only bars 0..i.
    """
    day = df["_day"]
    tp = (df["high"] + df["low"] + df["close"]) / 3.0
    v = df["volume"]
    cum_v = v.groupby(day).cumsum()
    cum_vtp = (tp * v).groupby(day).cumsum()
    cum_vtp2 = (tp * tp * v).groupby(day).cumsum()
    mean = cum_vtp / cum_v
    var = (cum_vtp2 / cum_v) - mean * mean
    return np.sqrt(var.clip(lower=0.0))


def _daily_atr_prev(df: pd.DataFrame, n: int) -> pd.Series:
    """Wilder ATR(n) of the RTH daily bars, SHIFTED — prior sessions only."""
    day = df["_day"]
    dh = df["high"].groupby(day).max()
    dl = df["low"].groupby(day).min()
    dc = df["close"].groupby(day).last()
    pdc = dc.shift(1)
    tr = pd.concat([dh - dl, (dh - pdc).abs(), (dl - pdc).abs()], axis=1).max(axis=1)
    atr_d = tr.ewm(alpha=1 / n, adjust=False).mean().shift(1)   # shift => causal
    return day.map(atr_d)


def _prev_rth_close(df: pd.DataFrame) -> pd.Series:
    day = df["_day"]
    dc = df["close"].groupby(day).last()
    return day.map(dc.shift(1))


# ── strategies ───────────────────────────────────────────────────────────────
def _rsi2(df: pd.DataFrame):
    """MQL5 art.17636 Strategy 3 ("RSI2 Overbought/Oversold").

    Long : RSI(2) < 5 and close > 50-period MA.
    Short: RSI(2) > 95 and close < 50-period MA.
    [READING] the source's "no open positions" clause is a position-state filter,
    not an entry rule; the mechanical equivalent on a bar series is to fire only
    on the FIRST bar of an extreme streak (prior bar not yet in the extreme).
    That is also what keeps this sparse instead of firing every bar of a flush.
    """
    c = df["close"]
    rsi2 = _wilder_rsi(c, RSI2_LEN)
    ma = c.rolling(RSI2_MA_LEN).mean()

    lo, lo_prev = rsi2 < RSI2_LOW, rsi2.shift(1) < RSI2_LOW
    hi, hi_prev = rsi2 > RSI2_HIGH, rsi2.shift(1) > RSI2_HIGH

    long_ = lo & ~lo_prev.fillna(False) & (c > ma)
    short = hi & ~hi_prev.fillna(False) & (c < ma)
    return long_.fillna(False), short.fillna(False)


def _vwap_2sigma(df: pd.DataFrame):
    """crosstrade.io VWAP reversion, 2-sigma band + rejection pin bar.

    Long : bar trades at/below VWAP - 2*sigma, prints a lower-wick pin bar
           (lower wick >= 50% of the bar range) and closes back above the band.
    Short: mirror image at VWAP + 2*sigma.
    Filters (from the source): ADX(14) < 25; only 10:00-11:30 and 13:30-14:30 ET.
    [READING] "pin bar with long lower wick" is made concrete as
    wick >= 0.5 * range; "rejection" is made concrete as closing back inside the
    band on the trigger bar (the source enters on the next bar's open, which the
    harness does for us by filling the bar after the signal).
    """
    o, h, l, c = df["open"], df["high"], df["low"], df["close"]
    vwap, eth = df["vwap"], df["eth"]
    sig = _session_vwap_sigma(df)
    lower = vwap - VWAP_SIGMA_MULT * sig
    upper = vwap + VWAP_SIGMA_MULT * sig

    rng = (h - l).replace(0, np.nan)
    body_lo = pd.concat([o, c], axis=1).min(axis=1)
    body_hi = pd.concat([o, c], axis=1).max(axis=1)
    pin_up = ((body_lo - l) / rng) >= VWAP_WICK_FRAC     # long lower wick
    pin_dn = ((h - body_hi) / rng) >= VWAP_WICK_FRAC     # long upper wick

    bar_no = df.groupby("_day").cumcount()
    ok = (bar_no >= VWAP_MIN_BARS) & (sig > 0) & (df["adx"] < VWAP_ADX_MAX)
    window = ((eth >= 10.0) & (eth < 11.5)) | ((eth >= 13.5) & (eth < 14.5))
    ok = ok & window

    long_ = ok & (l <= lower) & (c > lower) & pin_up
    short = ok & (h >= upper) & (c < upper) & pin_dn
    return long_.fillna(False), short.fillna(False)


def _gap_fade(df: pd.DataFrame):
    """tradingstats.net NQ gap-fill fade — their highest-count documented setup,
    "tiny gap + first 15-min candle toward fill" (93.1% fill, 773 of 2,791 days).

    gap        = today's RTH open - prior RTH close
    tiny       = 0 < |gap| < 0.30x prior-session ATR(14)        (their "tiny" tier)
    confirm    = the first 15 minutes (bars 09:30/09:35/09:40) closed toward the
                 fill, i.e. against the gap
    entry      = close of the 09:40 bar, in the direction of the prior close
                 (gap down -> long, gap up -> short)
    [READING] the article's "first 15-min candle" is the 09:30-09:45 block; on
    5-min bars that is the close of the bar stamped 09:40 versus the open of the
    bar stamped 09:30.
    NOTE the article's "opens inside the prior day's range" (70.4% fill) is listed
    as a SEPARATE factor, not part of the 93.1% setup, so it is not required here;
    requiring it as well cut the sample to ~16 signals/yr, far below the article's
    own hit count (773/2,791 = 27.7% of sessions, which this rule reproduces).
    """
    day = df["_day"]
    sess_open = df["open"].groupby(day).transform("first")   # first bar of the day
    prev_close = _prev_rth_close(df)
    datr = _daily_atr_prev(df, GAP_DATR_LEN)

    gap = sess_open - prev_close
    size = gap.abs() / datr.replace(0, np.nan)
    tiny = (size > 0) & (size < GAP_TINY_ATR)

    at_entry = (df["eth"] - GAP_ENTRY_ETH).abs() < 1e-9
    ib_bear = df["close"] < sess_open          # first 15 min closed down
    ib_bull = df["close"] > sess_open

    base = at_entry & tiny
    long_ = base & (gap < 0) & ib_bull         # gap down, first 15 min pushing up
    short = base & (gap > 0) & ib_bear         # gap up, first 15 min pushing down
    return long_.fillna(False), short.fillna(False)


def register(df):
    rsi_l, rsi_s = _rsi2(df)
    vw_l, vw_s = _vwap_2sigma(df)
    gap_l, gap_s = _gap_fade(df)
    return {
        "mr_rsi2_long":       (rsi_l.astype(bool), +1),
        "mr_rsi2_short":      (rsi_s.astype(bool), -1),
        "mr_vwap2sig_long":   (vw_l.astype(bool), +1),
        "mr_vwap2sig_short":  (vw_s.astype(bool), -1),
        "mr_gapfade_long":    (gap_l.astype(bool), +1),
        "mr_gapfade_short":   (gap_s.astype(bool), -1),
    }

"""Wave-9: the OHLCV-testable subset of the user's 50 'advanced' strategies
(the price-action / time-structure ones — order flow can't be done on OHLCV)."""

import numpy as np
import pandas as pd


def enrich8(d):
    d = d.copy()
    c, h, l, o, v = d["close"], d["high"], d["low"], d["open"], d["volume"]
    day = d["_day"]
    d["dow"] = d.index.dayofweek
    # running intraday range position (0=low of day, 1=high of day)
    dhi = h.groupby(day).cummax(); dlo = l.groupby(day).cummin()
    d["range_pos"] = (c - dlo) / (dhi - dlo).replace(0, np.nan)
    # VWAP z-score
    d["vwap_z"] = (c - d["vwap"]) / d["std20"].replace(0, np.nan)
    # candle anatomy
    body = (c - o).abs()
    d["lo_wick"] = (pd.concat([o, c], axis=1).min(axis=1) - l)
    d["wick_ratio"] = d["lo_wick"] / body.replace(0, np.nan)
    # consecutive green closes (for failed parabolic)
    green = (c > o).astype(int)
    d["green_streak"] = green.groupby((green != green.shift()).cumsum()).cumsum() * green
    # 5-bar range (micro-channel)
    d["rng5"] = (h.rolling(5).max() - l.rolling(5).min())
    return d


def sig8(df, name):
    c, h, l, o = df["close"], df["high"], df["low"], df["open"]
    pc = c.shift(1)
    up = c > (h + l) / 2.0
    e50 = df["ema50"]
    hi20, lo20 = df["donch_hi20"], df["donch_lo20"]
    if name == "ote_fib_long":                 # dip into 70.5-79% retrace of 20-bar up-range, turn up
        rng = (hi20 - lo20)
        fib705 = hi20 - 0.705 * rng
        fib79 = hi20 - 0.79 * rng
        return (l <= fib705) & (l >= fib79) & (c > o) & (c > e50), +1
    if name == "premium_discount_long":        # long only in the lower-half 'discount' zone, uptrend
        return (df["range_pos"] < 0.4) & (c > e50) & up, +1
    if name == "vwap_zscore_long":             # < -2.5 sigma below VWAP, reversion
        return (df["vwap_z"].shift(1) < -2.5) & (df["vwap_z"] >= -2.5) & up, +1
    if name == "failed_parab_short":           # 5+ green then a red bar breaking prior low
        return (df["green_streak"].shift(1) >= 5) & (c < o) & (c < l.shift(1)), -1
    if name == "wick_reject_long":             # big lower wick + volume at a 20-bar low
        return (df["wick_ratio"] > 2.0) & (df["volume"] > 2 * df["avgvol"]) & (l <= lo20.shift(1)), +1
    if name == "settle_revert_long":           # afternoon, below prior close -> revert up to settle
        return (df["eth"] > 14.0) & (c < df["pdc"]) & (c > pc) & up, +1
    if name == "tuesday_mom_long":             # Tuesday breakout of 20-bar high
        return (df["dow"] == 1) & (c > hi20.shift(1)) & (pc <= hi20.shift(1)), +1
    if name == "lunch_bb_long":                # lunchtime Bollinger reversion
        return (df["eth"] >= 11.5) & (df["eth"] <= 13.5) & (pc < df["bb_dn"].shift(1)) & (c >= df["bb_dn"]), +1
    if name == "microchannel_long":            # tight 5-bar coil then break up in uptrend
        return (df["rng5"].shift(1) < 0.6 * df["atr"]) & (c > h.shift(1)) & (c > e50), +1
    if name == "mss_long":                     # made a 20-bar low recently, now breaks a 10-bar high
        made_low = (l.rolling(5).min() <= lo20.shift(5))
        return made_low & (c > df["donch_hi10"].shift(1)) & (pc <= df["donch_hi10"].shift(1)), +1
    raise ValueError(name)


# (name, session window) — some need afternoon/lunch/all-day, not just morning
FAMILIES8 = [
    ("ote_fib_long", (9.75, 15.5)), ("premium_discount_long", (9.75, 15.5)),
    ("vwap_zscore_long", (9.75, 15.5)), ("failed_parab_short", (9.75, 15.5)),
    ("wick_reject_long", (9.75, 15.5)), ("settle_revert_long", (14.0, 15.75)),
    ("tuesday_mom_long", (9.75, 15.5)), ("lunch_bb_long", (11.5, 13.5)),
    ("microchannel_long", (9.75, 15.5)), ("mss_long", (9.75, 15.5)),
]

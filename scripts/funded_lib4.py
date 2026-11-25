"""Wave-5: fresh families aimed at fast, reliable payouts (high hit-rate
reversion + short-horizon momentum). New indicators: EMA200, IBS, VWAP sigma."""

import numpy as np
import pandas as pd


def enrich4(d):
    d = d.copy()
    c, h, l = d["close"], d["high"], d["low"]
    d["ema200"] = c.ewm(span=200, adjust=False).mean()
    d["ibs"] = ((c - l) / (h - l).replace(0, np.nan)).fillna(0.5)
    d["std20"] = c.rolling(20).std()
    return d


def sig4(df, name):
    c, h, l, o = df["close"], df["high"], df["low"], df["open"]
    pc = c.shift(1)
    up = c > (h + l) / 2.0
    e20, e50, e200 = df["ema20"], df["ema50"], df["ema200"]
    if name == "ibs_bounce_long":                 # low internal-bar-strength, uptrend, turning up
        return (df["ibs"].shift(1) < 0.15) & (c > pc) & (c > e50), +1
    if name == "vwap2sig_long":                   # 2-sigma below VWAP, uptrend reversion
        return (c < df["vwap"] - 2*df["std20"]) & up & (c > e50), +1
    if name == "gap_fill_long":                   # gap down then reclaim the open (fade the gap)
        return (df["day_open"] < df["pdc"]) & (c > df["day_open"]) & (pc <= df["day_open"]) & up, +1
    if name == "three_low_pull_long":             # 3 lower closes in uptrend, turning up (Connors)
        return (pc < c.shift(2)) & (c.shift(2) < c.shift(3)) & (c > pc) & (c > e50), +1
    if name == "rsi2_deep_long":                  # RSI2 < 5 extreme bounce above EMA200
        return (df["rsi2"].shift(1) < 5) & (df["rsi2"] >= 5) & (c > e200), +1
    if name == "pctb_rev_long":                   # %B reclaim from < 0.2 in uptrend
        return (df["pctb"].shift(1) < 0.2) & (df["pctb"] >= 0.2) & (c > e50), +1
    if name == "consec3_mom_long":                # 3 rising closes, above EMA20 (momentum burst)
        return (c > pc) & (pc > c.shift(2)) & (c.shift(2) > c.shift(3)) & (c > e20), +1
    raise ValueError(name)


FAMILIES4 = ["ibs_bounce_long", "vwap2sig_long", "gap_fill_long", "three_low_pull_long",
             "rsi2_deep_long", "pctb_rev_long", "consec3_mom_long"]

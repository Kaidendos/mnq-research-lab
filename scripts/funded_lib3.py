"""Wave-3: more new indicator columns + a fresh batch of signal families."""

import numpy as np
import pandas as pd


def enrich3(d):
    d = d.copy()
    c, h, l, o, v = d["close"], d["high"], d["low"], d["open"], d["volume"]
    mid = c.rolling(20).mean()
    d["pctb"] = (c - d["bb_dn"]) / (d["bb_up"] - d["bb_dn"]).replace(0, np.nan)
    d["rng"] = h - l
    d["avgrng"] = d["rng"].rolling(20).mean()
    d["avgvol"] = v.rolling(20).mean()
    d["donch_mid"] = (d["donch_hi20"] + d["donch_lo20"]) / 2.0
    hh14 = h.rolling(14).max(); ll14 = l.rolling(14).min()
    d["willr"] = -100 * (hh14 - c) / (hh14 - ll14).replace(0, np.nan)
    tp = (h + l + c) / 3.0
    d["cci"] = (tp - tp.rolling(20).mean()) / (0.015 * tp.rolling(20).std().replace(0, np.nan))
    # first-hour (9:30-10:30 ET) high/low
    eth = d["eth"]; day = d["_day"]
    infh = eth <= 10.5
    d["fh_hi"] = h.where(infh).groupby(day).cummax().groupby(day).transform("last")
    d["fh_lo"] = l.where(infh).groupby(day).cummin().groupby(day).transform("last")
    return d


def sig3(df, name):
    c, h, l, o = df["close"], df["high"], df["low"], df["open"]
    pc = c.shift(1)
    up = c > (h + l) / 2.0
    e9, e20, e50 = df["ema9"], df["ema20"], df["ema50"]
    if name == "ema_ribbon_long":
        aligned = (e9 > e20) & (e20 > e50)
        return aligned & ~(aligned.shift(1).fillna(False)), +1
    if name == "percentb_long":
        return (df["pctb"].shift(1) < 0.05) & (df["pctb"] >= 0.05) & up, +1
    if name == "atr_expand_long":
        return (df["rng"] > 1.5 * df["avgrng"]) & (c > o) & (c > e20), +1
    if name == "first_hour_break_long":
        return (df["eth"] > 10.5) & (c > df["fh_hi"]) & (pc <= df["fh_hi"]), +1
    if name == "outside_bar_long":
        return (h > h.shift(1)) & (l < l.shift(1)) & (c > o) & (c > pc), +1
    if name == "vwap_pullback_long":
        return (c > e50) & (l <= df["vwap"]) & (c > df["vwap"]) & up, +1
    if name == "willr_long":
        return (df["willr"].shift(1) < -80) & (df["willr"] >= -80), +1
    if name == "cci_long":
        return (df["cci"].shift(1) < -100) & (df["cci"] >= -100), +1
    if name == "strong_bar_long":
        return ((c - o) > 0.8 * df["atr"]) & (c > e20), +1
    if name == "hh_hl_long":
        return (h > h.shift(1)) & (l > l.shift(1)) & (c > e20) & up, +1
    if name == "donch_mid_long":
        return (c > df["donch_mid"]) & (pc <= df["donch_mid"].shift(1)) & (c > e50), +1
    if name == "rsi40_pull_long":
        return (c > e50) & (df["rsi"].shift(1) < 40) & (df["rsi"] >= 40), +1
    if name == "vol_break_long":
        return (df["volume"] > 1.8 * df["avgvol"]) & (c > h.shift(1)) & up, +1
    if name == "or_fade_short":
        return df["or15_ready"] & (pc > df["or15_hi"]) & (c < df["or15_hi"]), -1
    raise ValueError(name)


FAMILIES3 = ["ema_ribbon_long", "percentb_long", "atr_expand_long", "first_hour_break_long",
             "outside_bar_long", "vwap_pullback_long", "willr_long", "cci_long",
             "strong_bar_long", "hh_hl_long", "donch_mid_long", "rsi40_pull_long",
             "vol_break_long", "or_fade_short"]

"""Wave-2: new indicator columns + new signal families + a replay that supports
runner / trailing exits (to ride trend days toward the $440 cap)."""

import numpy as np
import pandas as pd

import funded_lib as fl

FEE, PV, MAXC = fl.FEE, fl.PV, fl.MAXC


def enrich2(d):
    d = d.copy()
    c, h, l, o = d["close"], d["high"], d["low"], d["open"]
    pc = c.shift(1)
    # 2-period RSI (Connors)
    delta = c.diff()
    up = delta.clip(lower=0).ewm(alpha=1/2, adjust=False).mean()
    dn = (-delta.clip(upper=0)).ewm(alpha=1/2, adjust=False).mean()
    d["rsi2"] = 100 - 100/(1 + up/dn.replace(0, np.nan))
    # Bollinger width + squeeze flag
    mid = c.rolling(20).mean()
    bbw = (d["bb_up"] - d["bb_dn"]) / mid
    d["squeeze"] = bbw < bbw.rolling(60).quantile(0.25)
    # Keltner channel
    d["kelt_up"] = d["ema20"] + 1.5 * d["atr"]
    d["kelt_dn"] = d["ema20"] - 1.5 * d["atr"]
    # range compression
    rng = h - l
    d["nr7"] = rng <= rng.rolling(7).min()
    d["inside"] = (h < h.shift(1)) & (l > l.shift(1))
    # 2 consecutive green closes
    d["green2"] = (c > o) & (pc > o.shift(1))
    # session open + prior-day close + pivots
    day = d["_day"]
    d["day_open"] = o.groupby(day).transform("first")
    dc = c.groupby(day).last()
    dmap = pd.Series(day.values, index=d.index)
    d["pdc"] = dmap.map(dc.shift(1))
    piv = (d["pdh"] + d["pdl"] + d["pdc"]) / 3.0
    d["piv_s1"] = 2*piv - d["pdh"]
    d["piv_r1"] = 2*piv - d["pdl"]
    return d


def sig2(df, name):
    c, h, l, o = df["close"], df["high"], df["low"], df["open"]
    pc = c.shift(1)
    up_bar = c > (h + l)/2.0
    if name == "rsi2_dip_long":                       # Connors: deep RSI2 dip in uptrend
        return (c > df["ema50"]) & (df["rsi2"] < 10), +1
    if name == "rsi2_x_long":
        return (df["rsi2"].shift(1) < 15) & (df["rsi2"] >= 15) & (c > df["ema50"]), +1
    if name == "squeeze_break_long":
        return df["squeeze"].shift(1) & (c > df["bb_up"]) & (pc <= df["bb_up"].shift(1)), +1
    if name == "keltner_break_long":
        return (c > df["kelt_up"]) & (pc <= df["kelt_up"].shift(1)), +1
    if name == "keltner_break_short":
        return (c < df["kelt_dn"]) & (pc >= df["kelt_dn"].shift(1)), -1
    if name == "nr7_break_long":
        return df["nr7"].shift(1) & (c > h.shift(1)), +1
    if name == "inside_break_long":
        return df["inside"].shift(1) & (c > h.shift(1)), +1
    if name == "gap_go_long":
        return (df["day_open"] > df["pdh"]) & (c > df["day_open"]) & up_bar, +1
    if name == "green2_mom_long":
        return df["green2"] & (c > pc) & (c > df["ema20"]), +1
    if name == "pivot_s1_bounce_long":
        return (l <= df["piv_s1"]) & (c > df["piv_s1"]) & up_bar, +1
    if name == "vwapband_revert_long":
        return (c < df["vwap"] - 1.5*df["atr"]) & up_bar, +1
    if name == "open_break_long":
        return (df["eth"] > 9.75) & (c > df["day_open"]) & (pc <= df["day_open"]) & (c > df["ema20"]), +1
    raise ValueError(name)


FAMILIES2 = ["rsi2_dip_long", "rsi2_x_long", "squeeze_break_long", "keltner_break_long",
             "keltner_break_short", "nr7_break_long", "inside_break_long", "gap_go_long",
             "green2_mom_long", "pivot_s1_bounce_long", "vwapband_revert_long", "open_break_long"]


def replay_runner(df, entry, side, sl, win, gate, mode="eod", trail=1.0,
                  cap=fl.CAP, budget=fl.LOSS_BUDGET, stop_green=True):
    """Runner exits: fixed sl-ATR stop, no fixed TP. mode='eod' rides to session
    close; mode='trail' uses an ATR trailing stop. A profit-cap exit banks the
    day at ~$cap if reached. Long only for this helper."""
    hi = df["high"].values; lo = df["low"].values; cl = df["close"].values
    atr = df["atr"].values; eth = df["eth"].values
    ent = (entry.fillna(False).to_numpy(dtype=bool) if hasattr(entry, "fillna")
           else np.asarray(entry, dtype=bool))
    gate_arr = df[gate].values if gate else np.ones(len(df), bool)
    dayid = df["_day"].values
    starts = np.flatnonzero(np.r_[True, dayid[1:] != dayid[:-1]])
    ends = np.r_[starts[1:], len(df)]
    ws, we = win
    out = {}; tot = 0; win_ct = 0
    for s, e in zip(starts, ends):
        if not gate_arr[s]:
            continue
        net = 0.0; ntr = 0; day_won = False; pos = None
        for i in range(s, e):
            last = i == e - 1
            if pos is not None:
                px = None
                # profit-cap price: bank remaining room to $cap
                room = cap - net
                cap_px = pos["entry"] + room / (pos["n"] * PV)
                if lo[i] <= pos["stop"]:
                    px = pos["stop"]
                elif hi[i] >= cap_px:
                    px = cap_px
                elif eth[i] >= 16.0 or last:
                    px = cl[i]
                elif mode == "trail":
                    pos["hi"] = max(pos["hi"], hi[i])
                    pos["stop"] = max(pos["stop"], pos["hi"] - atr[i]*trail)
                if px is not None:
                    pnl = (px - pos["entry"]) * PV * pos["n"] - FEE*pos["n"]
                    net += pnl; ntr += 1; tot += 1
                    if pnl > 0: win_ct += 1
                    if stop_green and net > 0: day_won = True
                    pos = None
            if (pos is None and not last and not day_won and ent[i]
                    and ws <= eth[i] <= we and atr[i] > 0 and not np.isnan(atr[i]) and ntr < 6):
                stop_usd = atr[i]*sl*PV
                n = min(MAXC, int((budget+net)/stop_usd))
                if n < 1:
                    continue
                pos = {"entry": cl[i], "stop": cl[i]-atr[i]*sl, "n": n, "hi": hi[i]}
        if ntr > 0:
            out[df.index[s].normalize()] = net
    return pd.Series(out).sort_index(), tot, win_ct

"""Funded strategy-hunt library: rich indicator enrichment + a signal library
(long & short families) + a funded day-replay harness.

Funded profile applied to every strategy so the comparison is fair:
  - $440/day profit cap, $300/day loss budget, stop-when-green, <=10 MNQ
  - SL/TP as ATR multiples, first-touch exit, EOD flat, fees $1.22 RT/ct
Scored elsewhere (funded_hunt.py) under $1k trailing DD / $1,100 buffer / 40%.
"""

import numpy as np
import pandas as pd

import improve_lab as il

FEE = 1.22
PV = 2.0
MAXC = 10
CAP = 440
LOSS_BUDGET = 300


# ───────────────────────── enrichment ─────────────────────────
def load_enriched() -> pd.DataFrame:
    """il.load() gives RTH 5-min bars with atr, stochK, svol (tz=ET). Add a
    full indicator set. Continuous indicators carry across sessions (as NT does
    on a continuous chart); VWAP / opening-range / prior-day reset per session."""
    d = il.load().copy()
    c, h, l = d["close"], d["high"], d["low"]

    # trend / momentum (continuous)
    for n in (9, 20, 50):
        d[f"ema{n}"] = c.ewm(span=n, adjust=False).mean()
    delta = c.diff()
    up = delta.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
    dn = (-delta.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean()
    d["rsi"] = 100 - 100 / (1 + up / dn.replace(0, np.nan))
    ema12 = c.ewm(span=12, adjust=False).mean()
    ema26 = c.ewm(span=26, adjust=False).mean()
    d["macd"] = ema12 - ema26
    d["macd_sig"] = d["macd"].ewm(span=9, adjust=False).mean()
    mid = c.rolling(20).mean()
    sd = c.rolling(20).std()
    d["bb_up"] = mid + 2 * sd
    d["bb_dn"] = mid - 2 * sd
    d["donch_hi20"] = h.rolling(20).max()
    d["donch_lo20"] = l.rolling(20).min()
    d["donch_hi10"] = h.rolling(10).max()
    d["donch_lo10"] = l.rolling(10).min()

    # session-reset features
    day = d.index.normalize()
    eth = d.index.hour + d.index.minute / 60.0
    d["eth"] = eth
    tp = (h + l + c) / 3.0
    d["vwap"] = ((tp * d["volume"]).groupby(day).cumsum()
                 / d["volume"].groupby(day).cumsum())
    # opening ranges (first 15 / 30 min => bars closing by 9:45 / 10:00)
    for orm, endeth in (("or15", 9.5 + 15/60), ("or30", 9.5 + 30/60)):
        inor = eth <= endeth
        hi = h.where(inor).groupby(day).cummax()
        lo = l.where(inor).groupby(day).cummin()
        d[f"{orm}_hi"] = hi.groupby(day).transform("last")
        d[f"{orm}_lo"] = lo.groupby(day).transform("last")
    d[f"or15_ready"] = eth > 9.5 + 15/60
    d[f"or30_ready"] = eth > 9.5 + 30/60

    # prior-day levels (no lookahead: shift daily agg by one session)
    dh = h.groupby(day).max(); dl = l.groupby(day).min(); dc = c.groupby(day).last()
    pdh = dh.shift(1); pdl = dl.shift(1)
    dmap = pd.Series(day, index=d.index)
    d["pdh"] = dmap.map(pdh); d["pdl"] = dmap.map(pdl)

    # daily EMA50 trend gate (yesterday's close > yesterday's EMA50), no lookahead
    ema50d = dc.ewm(span=50, adjust=False).mean()
    gate = (dc > ema50d).shift(1).fillna(False)
    d["gate_ema50"] = dmap.map(gate).astype(bool)
    d["_day"] = day
    return d


# ───────────────────────── signal library ─────────────────────────
# each returns (entry_bool_series, side)  side = +1 long, -1 short
def sig(df, name):
    c, h, l = df["close"], df["high"], df["low"]
    pc = c.shift(1)
    K = df["stochK"]; rsi = df["rsi"]
    up_bar = c > (h + l) / 2.0          # flow-positive
    dn_bar = c < (h + l) / 2.0
    if name == "stoch30_long":
        return (K.shift(1) <= 30) & (K > 30) & up_bar, +1
    if name == "stoch20_long":
        return (K.shift(1) <= 20) & (K > 20) & up_bar, +1
    if name == "stoch70_short":
        return (K.shift(1) >= 70) & (K < 70) & dn_bar, -1
    if name == "ema9_21_long":
        return (df["ema9"] > df["ema20"]) & (df["ema9"].shift(1) <= df["ema20"].shift(1)), +1
    if name == "ema9_21_short":
        return (df["ema9"] < df["ema20"]) & (df["ema9"].shift(1) >= df["ema20"].shift(1)), -1
    if name == "ema20_50_long":
        return (df["ema20"] > df["ema50"]) & (df["ema20"].shift(1) <= df["ema50"].shift(1)), +1
    if name == "rsi_x50_long":
        return (rsi.shift(1) <= 50) & (rsi > 50), +1
    if name == "rsi_bounce35_long":
        return (rsi.shift(1) < 35) & (rsi >= 35), +1
    if name == "rsi_fade70_short":
        return (rsi.shift(1) > 65) & (rsi <= 65), -1
    if name == "bb_reclaim_long":
        return (pc < df["bb_dn"].shift(1)) & (c >= df["bb_dn"]), +1
    if name == "bb_break_long":
        return (c > df["bb_up"]) & (pc <= df["bb_up"].shift(1)), +1
    if name == "bb_break_short":
        return (c < df["bb_dn"]) & (pc >= df["bb_dn"].shift(1)), -1
    if name == "donch20_long":
        return c > df["donch_hi20"].shift(1), +1
    if name == "donch20_short":
        return c < df["donch_lo20"].shift(1), -1
    if name == "donch10_long":
        return c > df["donch_hi10"].shift(1), +1
    if name == "orb15_long":
        return df["or15_ready"] & (c > df["or15_hi"]) & (pc <= df["or15_hi"]), +1
    if name == "orb15_short":
        return df["or15_ready"] & (c < df["or15_lo"]) & (pc >= df["or15_lo"]), -1
    if name == "orb30_long":
        return df["or30_ready"] & (c > df["or30_hi"]) & (pc <= df["or30_hi"]), +1
    if name == "vwap_reclaim_long":
        return (pc < df["vwap"].shift(1)) & (c >= df["vwap"]) & up_bar, +1
    if name == "vwap_lose_short":
        return (pc > df["vwap"].shift(1)) & (c <= df["vwap"]) & dn_bar, -1
    if name == "macd_x_long":
        return (df["macd"] > df["macd_sig"]) & (df["macd"].shift(1) <= df["macd_sig"].shift(1)) & (df["macd"] < 0), +1
    if name == "pdh_break_long":
        return (c > df["pdh"]) & (pc <= df["pdh"]), +1
    if name == "pdl_break_short":
        return (c < df["pdl"]) & (pc >= df["pdl"]), -1
    if name == "ema20_pullback_long":
        return (c > df["ema50"]) & (l <= df["ema20"]) & (c > df["ema20"]) & up_bar, +1
    raise ValueError("unknown signal " + name)


FAMILIES = [
    "stoch30_long", "stoch20_long", "stoch70_short", "ema9_21_long", "ema9_21_short",
    "ema20_50_long", "rsi_x50_long", "rsi_bounce35_long", "rsi_fade70_short",
    "bb_reclaim_long", "bb_break_long", "bb_break_short", "donch20_long",
    "donch20_short", "donch10_long", "orb15_long", "orb15_short", "orb30_long",
    "vwap_reclaim_long", "vwap_lose_short", "macd_x_long", "pdh_break_long",
    "pdl_break_short", "ema20_pullback_long",
]


# ───────────────────────── funded day-replay ─────────────────────────
def replay_sessions(df, entry, side, sl, tp, win, gate,
                    cap=CAP, budget=LOSS_BUDGET, stop_green=True):
    """entry = precomputed bool array. Loop each session, funded sizing + caps.
    win = (start_eth, end_eth) entry window. gate = bool 'trade this day'.
    Returns Series of day net $ (traded days only), + (ntrades, nwins) totals."""
    hi = df["high"].values; lo = df["low"].values; cl = df["close"].values
    atr = df["atr"].values; eth = df["eth"].values
    ent = (entry.fillna(False).to_numpy(dtype=bool) if hasattr(entry, "fillna")
           else np.asarray(entry, dtype=bool))
    gate_arr = df[gate].values if gate else np.ones(len(df), bool)
    dayid = df["_day"].values
    ws, we = win

    # session slice boundaries
    starts = np.flatnonzero(np.r_[True, dayid[1:] != dayid[:-1]])
    ends = np.r_[starts[1:], len(df)]

    out_days = {}; tot_tr = 0; tot_win = 0
    for s, e in zip(starts, ends):
        if not gate_arr[s]:
            continue
        net = 0.0; ntr = 0; day_won = False; pos = None
        for i in range(s, e):
            last = i == e - 1
            if pos is not None:
                exit_px = None
                if side > 0:
                    if lo[i] <= pos["sl"]: exit_px = pos["sl"]
                    elif hi[i] >= pos["tp"]: exit_px = pos["tp"]
                    elif eth[i] >= 16.0 or last: exit_px = cl[i]
                else:
                    if hi[i] >= pos["sl"]: exit_px = pos["sl"]
                    elif lo[i] <= pos["tp"]: exit_px = pos["tp"]
                    elif eth[i] >= 16.0 or last: exit_px = cl[i]
                if exit_px is not None:
                    pnl = side * (exit_px - pos["entry"]) * PV * pos["n"] - FEE * pos["n"]
                    net += pnl; ntr += 1; tot_tr += 1
                    if pnl > 0: tot_win += 1
                    if stop_green and net > 0: day_won = True
                    pos = None
            if (pos is None and not last and not day_won and ent[i]
                    and ws <= eth[i] <= we and atr[i] > 0 and not np.isnan(atr[i])
                    and ntr < 6):
                stop_usd = atr[i] * sl * PV
                tp_usd = atr[i] * tp * PV
                n = min(MAXC, int((budget + net) / stop_usd), int((cap - net) / tp_usd))
                if n < 1:
                    continue
                if side > 0:
                    pos = {"entry": cl[i], "sl": cl[i] - atr[i]*sl, "tp": cl[i] + atr[i]*tp, "n": n}
                else:
                    pos = {"entry": cl[i], "sl": cl[i] + atr[i]*sl, "tp": cl[i] - atr[i]*tp, "n": n}
        if ntr > 0:
            out_days[df.index[s].normalize()] = net
    s = pd.Series(out_days).sort_index()
    return s, tot_tr, tot_win

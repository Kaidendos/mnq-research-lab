"""KRISTJAN KULLAMÄGI (Qullamaggie) — continuation breakout, EP, parabolic short.

Area: qm.  Kullamägi publishes his brokerage statements and full trade history on
his own site, which makes him one of the very few traders in this registry with a
genuinely verifiable record. He trades EQUITIES on daily bars, so this is the
largest timeframe/instrument transposition in the project and is labelled as such
throughout — what is being tested is the SHAPE of his setups, not a claim that
his edge transfers to an index future.

RULES, as published
-------------------
https://qullamaggie.com/how-to-master-a-setup-episodic-pivots/
https://www.chartmill.com/documentation/stock-screener/technical-analysis-trading-strategies/467-Kristjan-Kullamagi-Continuation-Breakout-Screen
  "He looks for stocks that have made significant moves (30-100% within 12
   weeks), followed by an orderly pullback or consolidation lasting 2-8 weeks.
   The stock should 'surf' rising 10-day, 20-day, and 50-day moving averages,
   with the breakout occurring as the stock moves above the consolidation's high."
  "Episodic Pivots are gap-up breakouts driven by catalysts ... requiring a gap of
   10% or more with massive volume at the open."
  "A parabolic setup is a move that goes too far, too fast ... you wait for signs
   of exhaustion, such as a tall, climactic day or a failure to hold early
   strength, and the entry for a short is the first clean break lower with a tight
   stop above the day's high."

TRANSPOSITION, stated plainly
-----------------------------
  "30-100% in 12 weeks"  -> a move in the top decile of trailing 60-bar returns,
                            measured in ATR units because a 30% move in MNQ does
                            not happen intraday and a percentage threshold would
                            simply never fire.
  "2-8 week consolidation" -> 6-24 bars of contracting range.
  "surfing rising 10/20/50 MAs" -> kept literally, on 5-min bars.
  "gap up 10% + volume"  -> the session gap vs prior close in ATR units, plus RVOL.
The EP family is the weakest transposition of the three: index futures have no
earnings catalysts, so `qm_ep_long` is really "opening gap continuation" and
should be read that way.

CAUSALITY
---------
Consolidation width, prior-move size and all MAs are trailing windows ending at
the current bar. The overnight gap uses the PRIOR session's close via a shifted
daily aggregate, never the current session's eventual range.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

MOVE_LOOK = 60           # "12 weeks" of prior move, in bars
CONSOL_MIN, CONSOL_MAX = 6, 24
MOVE_ATR_MIN = 4.0       # READING: "significant move" in ATR units
CONSOL_ATR_MAX = 2.0     # READING: an "orderly" consolidation is a tight one
PARA_ATR = 3.0           # READING: "too far too fast" = this far above the 20-EMA
GAP_ATR = 0.75           # READING: an "EP-sized" opening gap for MNQ
RVOL_MIN = 1.5


def register(df: pd.DataFrame) -> dict:
    h, l, c, v = df["high"], df["low"], df["close"], df["volume"]
    atr = df["atr"]
    day = df["_day"]

    ma10 = c.rolling(10).mean()
    ma20 = c.rolling(20).mean()
    ma50 = c.rolling(50).mean()
    stacked_up = (ma10 > ma20) & (ma20 > ma50) & (ma10 > ma10.shift(1)) \
        & (ma20 > ma20.shift(1)) & (ma50 > ma50.shift(1))
    stacked_dn = (ma10 < ma20) & (ma20 < ma50) & (ma10 < ma10.shift(1)) \
        & (ma20 < ma20.shift(1)) & (ma50 < ma50.shift(1))

    rvol = (v / v.rolling(20).mean().shift(1)).fillna(1.0)

    # ── the prior move, in ATR units ──
    move_up = (c - c.shift(MOVE_LOOK)) / atr.replace(0, np.nan)
    big_up = move_up >= MOVE_ATR_MIN
    big_dn = move_up <= -MOVE_ATR_MIN

    out = {}
    for lo_n, hi_n, tag in ((CONSOL_MIN, CONSOL_MIN, "_tight"),
                            (CONSOL_MAX, CONSOL_MAX, "")):
        box_hi = h.rolling(hi_n).max().shift(1)
        box_lo = l.rolling(lo_n).min().shift(1)
        box_w = (box_hi - box_lo) / atr.replace(0, np.nan)
        orderly = box_w <= CONSOL_ATR_MAX
        brk_up = (c > box_hi) & (c.shift(1) <= box_hi)
        brk_dn = (c < box_lo) & (c.shift(1) >= box_lo)
        out[f"qm_breakout_long{tag}"] = (
            (big_up & orderly & stacked_up & brk_up).fillna(False), +1)
        out[f"qm_breakout_short{tag}"] = (
            (big_dn & orderly & stacked_dn & brk_dn).fillna(False), -1)

    # ── Episodic Pivot: opening gap + volume, entered on continuation ──
    dc = c.groupby(day).last()
    dmap = pd.Series(day, index=df.index)
    prev_close = dmap.map(dc.shift(1))
    sess_open = df["open"].groupby(day).transform("first")
    gap = (sess_open - prev_close) / atr.replace(0, np.nan)
    first_hour = df["eth"] <= 10.5
    or_hi, or_lo = df["or15_hi"], df["or15_lo"]
    ready = df["or15_ready"].astype(bool)
    out["qm_ep_long"] = (
        ((gap >= GAP_ATR) & ready & first_hour & (rvol >= RVOL_MIN)
         & (c > or_hi) & (c.shift(1) <= or_hi)).fillna(False), +1)
    out["qm_ep_short"] = (
        ((gap <= -GAP_ATR) & ready & first_hour & (rvol >= RVOL_MIN)
         & (c < or_lo) & (c.shift(1) >= or_lo)).fillna(False), -1)

    # ── parabolic short: overextended, then the first clean break lower ──
    ema20 = c.ewm(span=20, adjust=False).mean()
    stretch = (c - ema20) / atr.replace(0, np.nan)
    extended_up = (stretch >= PARA_ATR).shift(1).rolling(4).max().fillna(0).astype(bool)
    extended_dn = (stretch <= -PARA_ATR).shift(1).rolling(4).max().fillna(0).astype(bool)
    break_lower = (c < l.shift(1))
    break_higher = (c > h.shift(1))
    out["qm_parabolic_short"] = ((extended_up & break_lower).fillna(False), -1)
    out["qm_parabolic_long"] = ((extended_dn & break_higher).fillna(False), +1)
    return out

"""Opening-range-breakout family for MNQ 5-min RTH bars.

Every entry below is a translation of a documented, mechanical rule set.
Sources (one per strategy, listed again above each block):

  [S1] steady-turtle.com "Opening Range Breakout Strategy | ORB Guide for ES & NQ
       Futures" - https://steady-turtle.com/knowledge/opening-range-breakout-strategy
       Classic breakout: "Entry: on the close of the first bar that takes out the OR
       high or low with a body visibly larger than the last several inside-range
       bars", RVOL above 1.0x baseline, "If the range has not triggered a signal by
       10:15, move on". Fade: "Entry: on the close back inside the range after a
       failed break, ideally with below-average volume on the poke"; wide OR (above
       average) favours the fade, narrow OR favours the breakout.

  [S2] justintrading.com "15-Minute Opening Range Breakout: Futures Trading Guide"
       https://justintrading.com/15-minute-opening-range-breakout-futures/
       OR = 09:30-09:45 ET absolute high/low; entry requires "a five-minute candle to
       close decisively outside of these boundaries" on a "strong, high-volume
       candle", not a simple price touch.

  [S3] buildalpha.com "Opening Range Breakout Strategy: Complete Guide"
       https://www.buildalpha.com/opening-range-breakout/
       Setup 2 "Fade False Breakout": short when price reverses back below ORH after
       breaking above it. Setup 3 "Retest Entry" (described as highest probability):
       wait for the pullback to ORH after the initial breakout and enter there, the
       level having been confirmed as new support. Range width is normalised as
       OR / ATR. Max one or two trades per session.

  [S4] tradingstats.net "Initial Balance Breakout Statistics: ES & NQ Futures
       2015-2025" - https://tradingstats.net/initial-balance-breakout-statistics/
       IB = 09:30-10:30 ET. IB tiers vs 14-day ATR: narrow (<0.5x ATR) breaks 98.7%
       of the time with a 74.8% median extension vs 22.3% for extreme (>1.5x) IBs.
       65.2% of first breakouts land in the C-period (10:30-11:00), >80% by 11:30.
       Entry on C-period confirmation = a close outside the IB.

  [S5] steady-turtle.com "Initial Balance Trading Strategy | Complete Guide for ES &
       NQ Futures" - https://steady-turtle.com/knowledge/initial-balance-trading-strategy
       IB window 09:30-10:30; entry on "a close outside the IB range on a bar with a
       visibly larger body and volume than the last several inside-range bars";
       breakouts in the 30-60 minutes after the IB closes are the most reliable.

  [S6] tradealgo.com "Opening Range Breakout Strategy: How to Trade the First 30
       Minutes" - https://www.tradealgo.com/trading-guides/day-trading/opening-range-breakout-strategy-how-to-trade-the-first-30-minutes
       Directional bias filter: take longs only while price is above VWAP / prior
       close, shorts only below.

Where a source is vague the concrete reading is spelled out in a comment marked
"CONCRETE READING". Only ENTRY triggers are returned; the harness owns stops,
targets, sizing and exits.

Causality: every session-scoped quantity is built from cummax/cummin/cumsum or an
explicitly shifted prior-day aggregate. Nothing here can see past the close of the
bar it fires on.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# ── tunables kept as named constants (no magic numbers inline) ────────────────
OR15_END = 9.0 + 45 / 60.0          # 09:45 ET - end of the 15-min opening range
OR30_END = 10.0                     # 10:00 ET - end of the 30-min opening range
IB_END = 10.5                       # 10:30 ET - end of the 60-min initial balance

ORB_CUTOFF = 10.25                  # [S1] "not triggered by 10:15, move on"
FADE_CUTOFF = 14.0                  # CONCRETE READING: fades allowed through 14:00 ET
RETEST_CUTOFF = 14.0                # CONCRETE READING: retests allowed through 14:00 ET
IB_CUTOFF = 12.0                    # [S4] most first breaks by 11:30, [S5] skip 12:00-13:30 lunch

RVOL_LOOKBACK = 20                  # bars used for the relative-volume baseline
RVOL_MIN = 1.0                      # [S1] "confirm breaks with RVOL above 1.0x"
# [S1] wants a BELOW-average-volume poke for the fade, but that is qualified with
# "ideally". The literal RVOL < 1.0 reading survives on only ~0.1% of bars, which is
# too thin to backtest. CONCRETE READING: require the poke merely to be an ordinary,
# non-outsized break rather than a high-conviction one.
RVOL_POKE_MAX = 1.75

BODY_LOOKBACK = 6                   # "the last several inside-range bars"
BODY_MULT = 1.0                     # body must exceed that recent average

ATR_DAILY_LEN = 14                  # [S4] IB width is normalised by the 14-day ATR
IB_NARROW_MAX_ATR = 0.5             # [S4] narrow IB tier = width < 0.5x daily ATR
# Opening ranges are only ~0.3x a 14-day daily ATR, so [S4]'s ATR-based tiers do not
# transfer to them. [S5] gives the right reference for a short range: "recent 10-20
# session average". Tier boundaries below are [S4]'s, measured against that baseline.
WIDTH_BASE_SESSIONS = 20
OR_WIDTH_EXTREME = 1.5              # skip days whose OR is >1.5x its recent average


# ── causal helpers ───────────────────────────────────────────────────────────
def _locked_range(df: pd.DataFrame, end_eth: float):
    """High/low of the session window [open, end_eth), locked once the window ends.

    Built with groupby-cummax/cummin then forward-filled inside the day, so on any
    bar the value only reflects bars at or before it. `ready` is False until the
    window has actually closed, so the locked value is never consumed early.
    """
    day = df["_day"]
    inside = df["eth"] < end_eth
    hi = df["high"].where(inside).groupby(day).cummax().groupby(day).ffill()
    lo = df["low"].where(inside).groupby(day).cummin().groupby(day).ffill()
    ready = df["eth"] >= end_eth
    return hi, lo, ready


def _prior_count(cond: pd.Series, day: pd.Series) -> pd.Series:
    """How many times `cond` was true STRICTLY earlier in the same session."""
    c = cond.fillna(False).astype(int)
    return c.groupby(day).cumsum() - c


def _first_of_day(cond: pd.Series, day: pd.Series) -> pd.Series:
    """`cond`, thinned to its first occurrence per session ([S3] max 1-2 trades)."""
    cond = cond.fillna(False)
    return cond & (_prior_count(cond, day) == 0)


def _happened_earlier(cond: pd.Series, day: pd.Series) -> pd.Series:
    return _prior_count(cond, day) > 0


def _daily_atr(df: pd.DataFrame) -> pd.Series:
    """Wilder 14-day ATR from daily bars, SHIFTED one day, mapped back to bars.

    Uses whole-day aggregates but only ever of *completed prior* days (the .shift(1)),
    exactly the pattern the harness already uses for pdh/pdl.
    """
    day = df["_day"]
    dh = df["high"].groupby(day).max()
    dl = df["low"].groupby(day).min()
    dc = df["close"].groupby(day).last()
    pc = dc.shift(1)
    tr = pd.concat([dh - dl, (dh - pc).abs(), (dl - pc).abs()], axis=1).max(axis=1)
    atr_d = tr.ewm(alpha=1.0 / ATR_DAILY_LEN, adjust=False).mean().shift(1)
    return day.map(atr_d)


def _rel_width(width: pd.Series, day: pd.Series) -> pd.Series:
    """Range width as a multiple of its own recent-session average [S5].

    The per-session width is a whole-day aggregate, but .shift(1) on the rolling mean
    means the baseline only ever contains COMPLETED prior sessions.
    """
    per_day = width.groupby(day).last()
    base = per_day.rolling(WIDTH_BASE_SESSIONS).mean().shift(1)
    return width / day.map(base)


def _rvol(df: pd.DataFrame) -> pd.Series:
    """Relative volume vs the mean of the PREVIOUS `RVOL_LOOKBACK` bars."""
    base = df["volume"].shift(1).rolling(RVOL_LOOKBACK).mean()
    return df["volume"] / base.replace(0, np.nan)


def _big_body(df: pd.DataFrame) -> pd.Series:
    """"Body visibly larger than the last several inside-range bars" [S1]/[S5].

    CONCRETE READING: |close-open| greater than BODY_MULT x the mean body of the
    previous BODY_LOOKBACK bars.
    """
    body = (df["close"] - df["open"]).abs()
    base = body.shift(1).rolling(BODY_LOOKBACK).mean()
    return body > BODY_MULT * base


# ── registration ─────────────────────────────────────────────────────────────
def register(df: pd.DataFrame):
    day = df["_day"]
    c, l = df["close"], df["low"]
    eth, vwap = df["eth"], df["vwap"]

    datr = _daily_atr(df)
    rvol = _rvol(df)
    big_body = _big_body(df)

    or15_hi, or15_lo, or15_ok = _locked_range(df, OR15_END)
    or30_hi, or30_lo, or30_ok = _locked_range(df, OR30_END)
    ib_hi, ib_lo, ib_ok = _locked_range(df, IB_END)

    # width tiers [S3] "OR / ATR" normalisation, [S4] tier boundaries
    or15_not_extreme = _rel_width(or15_hi - or15_lo, day) <= OR_WIDTH_EXTREME
    ib_narrow = (ib_hi - ib_lo) < IB_NARROW_MAX_ATR * datr

    out = {}

    # ─────────────────────────────────────────────────────────────────────────
    # 1/2. Classic 15-minute ORB.  [S1] + [S2], bias filter from [S6]
    #      OR = 09:30-09:45. Enter on the CLOSE of the first 5-min bar that closes
    #      outside the range, with RVOL >= 1.0 and a body bigger than the recent
    #      average, no later than 10:15, and only on the VWAP-agreeing side.
    #      Extreme-wide ranges (>1.5x daily ATR) are skipped [S4].
    # ─────────────────────────────────────────────────────────────────────────
    base_orb = or15_ok & (eth < ORB_CUTOFF) & or15_not_extreme & (rvol >= RVOL_MIN) & big_body

    up_break = base_orb & (c > or15_hi) & (c > vwap)
    out["orb_or15_break_long"] = (_first_of_day(up_break, day), +1)

    dn_break = base_orb & (c < or15_lo) & (c < vwap)
    out["orb_or15_break_short"] = (_first_of_day(dn_break, day), -1)

    # ─────────────────────────────────────────────────────────────────────────
    # 3. 30-minute ORB with retest confirmation.  [S3] Setup 3
    #    OR = 09:30-10:00. First a bar must CLOSE above the OR high (breakout
    #    established). Later, price must trade back down to the level and hold it.
    #    CONCRETE READING of "wait for the pullback to ORH and enter there": the
    #    retest bar's LOW touches or undercuts the OR high while its CLOSE is still
    #    above it - i.e. the level was tested and defended on that bar. First such
    #    bar per session only, through 14:00.
    # ─────────────────────────────────────────────────────────────────────────
    broke_up30 = or30_ok & (c > or30_hi)
    retest_long = (
        or30_ok
        & (eth < RETEST_CUTOFF)
        & _happened_earlier(broke_up30, day)
        & (l <= or30_hi)
        & (c > or30_hi)
    )
    out["orb_or30_retest_long"] = (_first_of_day(retest_long, day), +1)

    # ─────────────────────────────────────────────────────────────────────────
    # 4/5. Failed 15-minute ORB, faded.  [S1] fade rules + [S3] Setup 2
    #      A bar closed outside the OR earlier in the session (the "poke") without
    #      outsized volume, and now a bar closes back INSIDE the range -> take the
    #      opposite side, i.e. against the trapped breakout traders.
    #      The poke's RVOL is read off the FIRST breakout bar of the session and
    #      carried forward, so it is always a value from an earlier bar.
    #      [S1] also prefers a wide OR for fades, but stacking that on top of the
    #      volume qualifier left under 0.2% of bars, so only the volume qualifier
    #      (which is part of the entry rule proper) is applied here.
    # ─────────────────────────────────────────────────────────────────────────
    poke_up = _first_of_day(or15_ok & (c > or15_hi), day)
    poke_up_rvol = rvol.where(poke_up).groupby(day).ffill()
    fail_short = (
        or15_ok
        & (eth < FADE_CUTOFF)
        & _happened_earlier(poke_up, day)
        & (poke_up_rvol < RVOL_POKE_MAX)
        & (c < or15_hi)          # close back inside the range
    )
    out["orb_fail_fade_short"] = (_first_of_day(fail_short, day), -1)

    poke_dn = _first_of_day(or15_ok & (c < or15_lo), day)
    poke_dn_rvol = rvol.where(poke_dn).groupby(day).ffill()
    fail_long = (
        or15_ok
        & (eth < FADE_CUTOFF)
        & _happened_earlier(poke_dn, day)
        & (poke_dn_rvol < RVOL_POKE_MAX)
        & (c > or15_lo)          # close back inside the range
    )
    out["orb_fail_fade_long"] = (_first_of_day(fail_long, day), +1)

    # ─────────────────────────────────────────────────────────────────────────
    # 6. Narrow-Initial-Balance breakout.  [S4] + [S5], bias filter from [S6]
    #    IB = 09:30-10:30. Only on days where the IB is in the "narrow" tier
    #    (< 0.5x the 14-day ATR), where [S4] measures a 98.7% break rate and a 74.8%
    #    median extension. Enter on the first bar after 10:30 that closes above the
    #    IB high with a bigger-than-recent body [S5] and while price is above VWAP
    #    [S6]. Cutoff 12:00: [S4] has >80% of first breaks in by 11:30 and [S5] says
    #    to avoid the 12:00-13:30 lunch window, so noon is the natural stop.
    # ─────────────────────────────────────────────────────────────────────────
    ib_break_long = (
        ib_ok
        & (eth < IB_CUTOFF)
        & ib_narrow
        & (c > ib_hi)
        & (c > vwap)
        & big_body
    )
    out["orb_ib_narrow_long"] = (_first_of_day(ib_break_long, day), +1)

    # harness expects clean boolean Series aligned to df.index
    return {k: (v.reindex(df.index).fillna(False).astype(bool), s) for k, (v, s) in out.items()}

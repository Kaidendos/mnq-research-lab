"""Time-of-day / session-structure entries for MNQ 5-min RTH bars.

Every rule below is a mechanical translation of a documented, sourced intraday
strategy for index futures.  Sources are cited per strategy.  Where a source is
vague, the interpretation chosen is flagged with "CONCRETE READING:".

ENTRIES ONLY.  No stops / targets / sizing / exits — the harness sweeps those.

CAUSALITY: every session-scoped feature is built from cumsum / cummax / cummin /
cumcount plus a within-day shift().  No whole-day aggregate is used anywhere.
The single transform("first") is the session OPEN, which is known at the first
bar of the session and is therefore not lookahead.

HARNESS NOTE: funded_search.WINS caps entry time at eth <= 15.5, so the
power-hour rule confirms in 15:00-15:30 ET.  That also dodges the chaotic
15:50-16:00 close the source warns about, so nothing is lost.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# ── named constants ───────────────────────────────────────────────────────
OR5_END = 9.5 + 5 / 60          # 09:35 ET — first 5-min bar complete
FIRST30_END = 10.0              # 10:00 ET — end of the first 30 minutes
IB_END = 10.5                   # 10:30 ET — Initial Balance close (A+B periods)
IB_BREAK_CUTOFF = 13.0
OR_FADE_CUTOFF = 11.0
LUNCH_START, LUNCH_END = 11.5, 14.5      # lunch chop + early-afternoon rotation
PH_START, PH_END = 15.0, 15.5            # power-hour confirmation window
MIDWEEK_START, MIDWEEK_END = 10.0, 11.5

DRIVE_MOVE_ATR = 0.75           # net move off the session open for an open drive
DRIVE_CLOSE_FRAC = 0.60         # close must sit in this top share of its range
OR_POKE_ATR = 0.10              # minimum overshoot for a "real" OR break
VWAP_SIGMA = 2.0                # session std-devs from VWAP for the fade
ADX_TREND = 25.0                # skip reversion above this ADX(14)
RVOL_MIN = 1.0                  # participation floor for breakouts
RVOL_SPIKE = 1.5                # "volume spike on the rejection bar"
WICK_FRAC = 0.33                # pin-bar wick share of the bar range
BODY_MIN_FRAC = 0.5             # rejects doji-thin pokes
RVOL_LOOKBACK = 12              # 12 x 5-min = the trailing hour
TUE_WED_THU = (1, 2, 3)         # pandas dayofweek codes


# ── causal helpers ────────────────────────────────────────────────────────
def _first_of_day(mask: pd.Series, day: pd.Series) -> pd.Series:
    """Keep only the FIRST bar of each session where mask is True.

    Causal: the cumsum covers the session up to and including the current bar.
    Implements the sources' "one and done" / first-signal-only convention.
    """
    m = mask.fillna(False).astype(bool)
    return m & (m.groupby(day).cumsum() == 1)


def _session_features(df: pd.DataFrame) -> dict:
    """Per-session state, built cumulatively so bar i sees only bars <= i."""
    day = df["_day"]
    o, h, l, c, v = df["open"], df["high"], df["low"], df["close"], df["volume"]

    f = {"day": day, "eth": df["eth"]}
    f["barn"] = df.groupby(day).cumcount()            # 0 = the 09:30 bar

    # session open — known at the first bar, so broadcasting it is not lookahead
    f["sopen"] = o.groupby(day).transform("first")

    # running session extremes (include the current bar, known at its close)
    f["shi"] = h.groupby(day).cummax()
    f["slo"] = l.groupby(day).cummin()

    # Relative volume against the TRAILING HOUR, not the session-to-date mean.
    # A session-to-date baseline is dominated by the huge 09:30-10:00 bars and
    # would make "RVOL >= 1" essentially unreachable after 11:00; the trailing
    # window is also the literal reading of "the last several inside-range bars".
    f["rvol"] = v / v.shift(1).rolling(RVOL_LOOKBACK).mean()

    # VWAP session standard-deviation bands (volume-weighted, cumulative)
    tp = (h + l + c) / 3.0
    cv = v.groupby(day).cumsum()
    m1 = (tp * v).groupby(day).cumsum() / cv
    m2 = (tp * tp * v).groupby(day).cumsum() / cv
    f["vwap"] = m1
    f["vsd"] = np.sqrt((m2 - m1 ** 2).clip(lower=0))

    # opening range = the first 5-min bar (09:30-09:35); frozen after bar 0
    in_or5 = f["barn"] == 0
    f["or5_hi"] = h.where(in_or5).groupby(day).cummax().groupby(day).ffill()
    f["or5_lo"] = l.where(in_or5).groupby(day).cummin().groupby(day).ffill()

    # Initial Balance = 09:30-10:30; the where() freezes it once the hour closes
    in_ib = df["eth"] <= IB_END
    f["ib_hi"] = h.where(in_ib).groupby(day).cummax().groupby(day).ffill()
    f["ib_lo"] = l.where(in_ib).groupby(day).cummin().groupby(day).ffill()

    # bar anatomy
    rng = (h - l).replace(0, np.nan)
    f["rng"] = rng
    f["up_wick"] = (h - np.maximum(o, c)) / rng
    f["body"] = (c - o).abs()
    f["body_prev5"] = f["body"].shift(1).rolling(5).mean()   # strictly past

    f["dow"] = pd.Series(df.index.dayofweek, index=df.index)
    return f


# ══════════════════════════════════════════════════════════════════════════
def register(df: pd.DataFrame) -> dict:
    o, h, l, c = df["open"], df["high"], df["low"], df["close"]
    atr, adx = df["atr"], df["adx"]
    f = _session_features(df)
    day, eth = f["day"], f["eth"]

    out = {}

    # ──────────────────────────────────────────────────────────────────
    # 1) tod_open_drive  (LONG)                                [OPENING DRIVE]
    # Market Profile "Open Drive" (Jim Dalton).  The pattern is defined as
    # price that "moves directionally and persistently for the first 30 minutes
    # from the cash market open" with maximum off-the-floor conviction, and its
    # signature test is that "the low made in the first 30 minutes is never
    # taken out throughout the day".
    #   https://atas.net/volume-analysis/strategies-and-trading-patterns/open-drive/
    #   https://ftmo.com/en/blog/market-profile-types-of-opens-and-the-anatomy-of-a-trading-day/
    #
    # CONCRETE READING: the incremental form of "the opening low is never taken
    # out" is: the running session low still equals the OPENING BAR's low.
    # Confirm on the first bar in 09:40-10:00 where that still holds, the net
    # move off the session open is >= 0.75 ATR (directional + persistent), and
    # the confirming bar is up and closes in the top 40% of its range.
    # ──────────────────────────────────────────────────────────────────
    drive = (
        (f["barn"] >= 2) & (eth < FIRST30_END)                  # 09:40 .. 09:55
        & (f["slo"] >= f["or5_lo"])                             # opening low intact
        & (c >= f["sopen"] + DRIVE_MOVE_ATR * atr)              # directional drive
        & (c > o)
        & ((c - l) >= DRIVE_CLOSE_FRAC * f["rng"])              # closing on its highs
    )
    out["tod_open_drive"] = (_first_of_day(drive, day), +1)

    # ──────────────────────────────────────────────────────────────────
    # 2) tod_or_fail_fade  (SHORT)                          [FIRST-30-MIN]
    # Steady Turtle strategy #6, "Opening Range Fade":
    #   "Time Window: 09:30-09:35 ET establishes Opening Range.
    #    Setup: break of OR high/low that fails to hold.
    #    Entry: on close back inside the range."
    #   https://steady-turtle.com/knowledge/day-trading-strategies
    # Same trap logic (opening-high liquidity raid then reversal back into the
    # prior range) is described here:
    #   https://www.tradingsim.com/blog/first-hour-trading
    #
    # CONCRETE READING: the source gives no overshoot size or cutoff, so require
    # the poke to clear the OR high by >= 0.10 ATR, demand a real upper
    # rejection wick (>= 1/3 of the bar range) plus a down close, and only look
    # inside the first 90 minutes (through 11:00 ET).
    # ──────────────────────────────────────────────────────────────────
    or_fail = (
        (eth > OR5_END) & (eth <= OR_FADE_CUTOFF)
        & (h > f["or5_hi"] + OR_POKE_ATR * atr)                 # genuine break above
        & (c < f["or5_hi"])                                     # closed back inside
        & (c < o)
        & (f["up_wick"] >= WICK_FRAC)
    )
    out["tod_or_fail_fade"] = (_first_of_day(or_fail, day), -1)

    # ──────────────────────────────────────────────────────────────────
    # 3) tod_ib_break  (LONG)                                [FIRST-HOUR / IB]
    # Initial Balance breakout / extension.  IB is "the high and low of the
    # first 60 minutes of RTH, 09:30 to 10:30 ET".  Entry is "a close outside
    # the IB range on a bar with a visibly larger body and volume than the last
    # several inside-range bars, not a thin, low-volume poke", and the volume
    # screen is mandatory: "if RVOL is under 1.0 at the break, skip it".
    #   https://steady-turtle.com/knowledge/initial-balance-trading-strategy
    #   https://steady-turtle.com/knowledge/day-trading-strategies  (strategy #3)
    #
    # CONCRETE READING: RVOL is measured against the trailing hour (see
    # _session_features) and carries the "not a thin, low-volume poke" screen;
    # the body test is kept only as a doji filter (body >= half the mean body of
    # the previous 5 bars).  The source calls 30-60 min after the IB "most
    # reliable" and says bias turns rotational after noon, so the window runs
    # 10:30-13:00 ET, first break only.
    # ──────────────────────────────────────────────────────────────────
    ib_break = (
        (eth > IB_END) & (eth <= IB_BREAK_CUTOFF)
        & (c > f["ib_hi"]) & (c.shift(1) <= f["ib_hi"])         # first close outside
        & (f["rvol"] >= RVOL_MIN)
        & (f["body"] > BODY_MIN_FRAC * f["body_prev5"])
    )
    out["tod_ib_break"] = (_first_of_day(ib_break, day), +1)

    # ──────────────────────────────────────────────────────────────────
    # 4) tod_lunch_vwap_fade  (SHORT)                            [LUNCH FADE]
    # Lunch-chop VWAP reversion.  11:30-13:30 ET is the window where "volume
    # drops meaningfully", price is "choppy sideways" and "trends reverse";
    # 13:30-14:30 is "early afternoon, often rotational".
    #   https://tradecovex.com/guides/best-times-day-trade-futures
    # The fade mechanics are CrossTrade's VWAP Reversion: "price extends
    # 2 x session standard deviations from VWAP", skip when "ADX(14) on
    # 5-minute > 25", and require a rejection candle at the extreme -- "pin bar
    # ... engulfing bar in the reversion direction, or volume spike on the
    # rejection bar".
    #   https://crosstrade.io/learn/trading-strategies/vwap-reversion
    #
    # CONCRETE READING: "extends 2 sigma" = the bar TAGS the +2 sigma band
    # intrabar and CLOSES back below it.  The source lists its three triggers as
    # alternatives, so they are OR'd: upper wick >= 1/3 of range (pin), or a
    # down close (engulfing-direction), or RVOL >= 1.5 (volume spike).
    # ──────────────────────────────────────────────────────────────────
    band_up = f["vwap"] + VWAP_SIGMA * f["vsd"]
    rejection = (f["up_wick"] >= WICK_FRAC) | (c < o) | (f["rvol"] >= RVOL_SPIKE)
    lunch_fade = (
        (eth >= LUNCH_START) & (eth <= LUNCH_END)
        & (f["vsd"] > 0)
        & (h >= band_up) & (c < band_up)                        # tag, then reject
        & rejection
        & (adx < ADX_TREND)                                     # not a trend day
    )
    out["tod_lunch_vwap_fade"] = (_first_of_day(lunch_fade, day), -1)

    # ──────────────────────────────────────────────────────────────────
    # 5) tod_power_hour_cont  (LONG)                             [POWER HOUR]
    # Power hour, 15:00-16:00 ET: "volume spikes as institutional traders close
    # positions before the cash close", the hour favours "trend continuation,
    # end-of-day momentum", and "the last 10 minutes (3:50-4:00) can be
    # chaotic".
    #   https://tradecovex.com/guides/best-times-day-trade-futures
    #   https://support.spotgamma.com/hc/en-us/articles/15214840723219-Power-Hour
    #
    # CONCRETE READING: "continuation" = a fresh 10-bar (50-minute) closing
    # break while the session is bid (close above session VWAP, EMA9 > EMA20),
    # on above-average volume ("volume spikes").  Confirmation stops at 15:30 --
    # both to avoid the chaotic final ten minutes and because the harness will
    # not open a trade after eth 15.5.
    # ──────────────────────────────────────────────────────────────────
    power = (
        (eth >= PH_START) & (eth <= PH_END)
        & (c > df["donch_hi10"].shift(1))                       # prior 10-bar high
        & (c > f["vwap"])
        & (df["ema9"] > df["ema20"])
        & (f["rvol"] >= RVOL_MIN)
    )
    out["tod_power_hour_cont"] = (_first_of_day(power, day), +1)

    # ──────────────────────────────────────────────────────────────────
    # 6) tod_midweek_pullback  (LONG)                        [DAY-OF-WEEK]
    # Day-of-week effect.  Tuesday/Wednesday/Thursday are the "full-size"
    # sessions -- Tuesday is "the first 'real' day ... clean trending moves,
    # high volume ... best risk-reward", Wednesday and Thursday continue it,
    # while Monday is a "slow start ... range-bound until midday" and Friday's
    # "afternoon fades".  The recommended sample is "Tuesday through Thursday".
    #   https://tradecovex.com/guides/best-times-day-trade-futures
    # The trigger is HolaPrime's "EMA Momentum Ride": 9- and 20-period EMAs,
    # "trade only when price is above both EMAs (uptrend)", best used
    # "9:30-11:00 AM ET, because volatility and liquidity are usually stronger".
    #   https://holaprime.com/blogs/trading-education/best-intraday-trading-strategies-e-mini-nasdaq-100/
    #
    # CONCRETE READING: take the first pullback that TOUCHES the EMA9 and closes
    # back above it, in a stacked EMA9 > EMA20 > EMA50 uptrend that is also
    # above session VWAP, between 10:00 and 11:30 ET -- skipping the noisy
    # opening 30 minutes that the source warns about, and running slightly past
    # 11:00 so the trailing edge of the morning window is covered.
    # ──────────────────────────────────────────────────────────────────
    midweek = (
        f["dow"].isin(TUE_WED_THU)
        & (eth >= MIDWEEK_START) & (eth <= MIDWEEK_END)
        & (df["ema9"] > df["ema20"]) & (df["ema20"] > df["ema50"])
        & (c > f["vwap"])
        & (l <= df["ema9"]) & (c > df["ema9"])                  # tagged and held
    )
    out["tod_midweek_pullback"] = (_first_of_day(midweek, day), +1)

    # hygiene: strict bool, index-aligned, no NaN leakage
    return {k: (s.reindex(df.index).fillna(False).astype(bool), side)
            for k, (s, side) in out.items()}

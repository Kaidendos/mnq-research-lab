"""TIME-STRUCTURED entries for MNQ 5-min RTH bars — regime-aware ("tm_" prefix).

Every rule below is a mechanical translation of a DOCUMENTED, sourced clock-based
intraday rule.  Sources are cited per strategy.  Where a source states a period
or a behaviour but not a numeric trigger, the interpretation used is flagged
"CONCRETE READING:".  Nothing here is invented and then attributed.

WHY THESE, AND WHY THESE LEGS
-----------------------------
Measured on MNQ, last ~3 months vs the prior 4.5 years, the intraday clock has
inverted while the tape has gone flat-and-wide (net +1.8% over 3 months, median
daily range 451pt vs 229pt, body/range 44.3% vs 51.6%):

    forward 6-bar move by ET hour     recent      history
        09:00                         -0.0133     +0.0677     open now NEGATIVE
        10:00                         +0.0825     +0.0473
        11:00                         +0.1253     +0.0786     late morning STRONG
        12:00                         +0.1402     +0.0764     lunch STRONG
        13:00                         +0.0892     +0.0921
        14:00                         -0.2661     +0.1170     2pm INVERTED, hard
        15:00                         +0.0880     +0.1069

Most of the sourced clock rules below are stated symmetrically (long on the
upside version, short on the downside version).  Since the interface takes one
side per name, each rule is registered on the ONE leg the measured regime
supports, and that choice is stated explicitly in each block.  No rule's
mechanics were altered to fit the regime — only which leg is taken and, in two
cases, which sub-window of the source's stated period is used.

ENTRIES ONLY.  Stops / targets / sizing / exits are swept by the harness.

CAUSALITY
---------
Every session-scoped level is built from cumsum / cummax / cummin / cumcount
plus a within-day ffill, so bar i sees only bars <= i.  The two cross-day
aggregates used (previous session's closing price, and the previous 14
sessions' average move-from-open at the same clock slot) are both .shift(1)-ed
by DAY before they are mapped back, so the current session never contributes.
There is no groupby("_day").transform("max"/"last") anywhere in this file.

HARNESS NOTE: funded_search.replay only opens a trade when
ws <= eth <= we with WINS spanning 9.75 .. 15.5, so no rule here confirms
before 09:45 or after 15:30.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# ── clock constants (ET, as float hours) ──────────────────────────────────
OR15_END = 9.5 + 15 / 60         # 09:45 — first 15 minutes complete
OPEN_START, OPEN_END = 9.75, 10.17   # 09:45-10:10  TradingSim "morning reversal" zone
MORNING_END = 11.5               # 11:30 — end of the pre-lunch session
LUNCH_START, LUNCH_END = 11.5, 13.5  # 11:30-13:30 ET, the documented lunch window
LUNCH_LONG_HOUR = 12.0           # 12:00 ET — QuantPedia lunch-effect long entry
MR_START, MR_END = 11.0, 13.0    # VWAP-reversion window (source 11:00-14:00)
PM_START, PM_END = 14.0, 15.5    # 14:00-15:30 — the inverted afternoon

# ── numeric thresholds ────────────────────────────────────────────────────
POKE_ATR = 0.05                  # minimum overshoot for a "real" (then failed) break
CLOSE_TAIL_FRAC = 0.40           # close must sit in this share of the bar range
VWAP_SIGMA = 2.0                 # "deviates 2+ standard deviations from VWAP"
RVOL_LOOKBACK = 12               # 12 x 5-min = the trailing hour
RVOL_MIN = 1.0                   # "volume surge" / "volume returns" floor
NOISE_LOOKBACK = 14              # "over the last 14 trading days"
NOISE_MINP = 8                   # min sessions before the noise band is usable
WICK_FRAC = 0.30                 # rejection-tail share of the bar range


# ── causal helpers ────────────────────────────────────────────────────────
def _first_of_day(mask: pd.Series, day: pd.Series) -> pd.Series:
    """Keep only the FIRST bar of each session where mask is True.

    Causal: the cumsum spans the session up to and including the current bar.
    """
    m = mask.fillna(False).astype(bool)
    return m & (m.groupby(day).cumsum() == 1)


def _window_hi(h: pd.Series, day: pd.Series, inside: pd.Series) -> pd.Series:
    """Running max of `h` over the bars of the session where `inside` is True,
    held flat afterwards.  NaN before the window opens.  Fully causal: cummax
    only ever looks left, ffill only propagates forward."""
    return h.where(inside).groupby(day).cummax().groupby(day).ffill()


def _window_lo(l: pd.Series, day: pd.Series, inside: pd.Series) -> pd.Series:
    return l.where(inside).groupby(day).cummin().groupby(day).ffill()


def _prev_day_close(c: pd.Series, day: pd.Series) -> pd.Series:
    """Previous session's final RTH close, broadcast to this session's bars.

    Causal: the per-day 'last' is .shift(1)-ed by day BEFORE the map, so the
    current (possibly partial) session's own last close is never consulted.
    """
    dc = c.groupby(day).last()
    return pd.Series(day.to_numpy(), index=c.index).map(dc.shift(1))


def _tod_avg_abs_move(df: pd.DataFrame, sopen: pd.Series) -> pd.Series:
    """Average |move from the session open| at THIS clock slot over the
    previous NOISE_LOOKBACK sessions.  This is sigma(t) in the Zarattini/Aziz
    "Noise Area".

    Causal: the per-(day, slot) table is .shift(1)-ed along the DAY axis before
    the rolling mean, so the value used on day D is built from days D-1 .. D-14
    only.  Truncating the current session cannot change it.
    """
    rel = (df["close"] / sopen - 1.0).abs()
    tbl = pd.DataFrame({"d": df["_day"].to_numpy(),
                        "t": np.round(df["eth"].to_numpy(), 4),
                        "r": rel.to_numpy()})
    piv = tbl.pivot_table(index="d", columns="t", values="r", aggfunc="last")
    sig = piv.shift(1).rolling(NOISE_LOOKBACK, min_periods=NOISE_MINP).mean()
    flat = sig.stack()                                   # MultiIndex (day, slot)
    key = pd.MultiIndex.from_arrays([tbl["d"].to_numpy(), tbl["t"].to_numpy()])
    return pd.Series(flat.reindex(key).to_numpy(), index=df.index)


def _features(df: pd.DataFrame) -> dict:
    day = df["_day"]
    o, h, l, c, v = (df["open"], df["high"], df["low"],
                     df["close"], df["volume"])
    eth = df["eth"]
    f = {"day": day, "eth": eth}

    f["barn"] = df.groupby(day).cumcount()
    f["sopen"] = o.groupby(day).transform("first")       # known at bar 0
    f["slo"] = l.groupby(day).cummin()                   # running session low

    # bar anatomy
    rng = (h - l).replace(0, np.nan)
    f["rng"] = rng
    f["dn_wick"] = (np.minimum(o, c) - l) / rng
    f["up_wick"] = (h - np.maximum(o, c)) / rng

    # relative volume against the TRAILING HOUR (a session-to-date baseline is
    # swamped by the 09:30-10:00 bars and is unreachable after 11:00)
    f["rvol"] = v / v.shift(1).rolling(RVOL_LOOKBACK).mean()

    # session VWAP + volume-weighted session standard deviation (cumulative)
    tp = (h + l + c) / 3.0
    cv = v.groupby(day).cumsum()
    m1 = (tp * v).groupby(day).cumsum() / cv
    m2 = (tp * tp * v).groupby(day).cumsum() / cv
    f["vwap"] = m1
    f["vsd"] = np.sqrt((m2 - m1 ** 2).clip(lower=0))

    # frozen clock ranges (all causal: cummax/cummin + forward fill)
    f["or15_lo"] = _window_lo(l, day, eth <= OR15_END)
    f["morn_lo"] = _window_lo(l, day, eth <= MORNING_END)
    in_lunch = (eth >= LUNCH_START) & (eth <= LUNCH_END)
    f["lunch_lo"] = _window_lo(l, day, in_lunch)
    f["lunch_hi"] = _window_hi(h, day, in_lunch)

    # running mean volume of the lunch window, held flat into the afternoon --
    # the baseline "afternoon volume returns" is measured against
    lv = v.where(in_lunch)
    f["lunch_vol"] = (lv.groupby(day).cumsum()
                      / lv.notna().groupby(day).cumsum()).groupby(day).ffill()
    return f


# ══════════════════════════════════════════════════════════════════════════
def register(df: pd.DataFrame) -> dict:
    o, h, l, c = df["open"], df["high"], df["low"], df["close"]
    atr = df["atr"]
    f = _features(df)
    day, eth = f["day"], f["eth"]
    minute = pd.Series(df.index.minute, index=df.index)

    out = {}

    # ──────────────────────────────────────────────────────────────────
    # 1) tm_open_newlow  (SHORT)                          [09:45-10:10 ET]
    # TradingSim's day-trading time zones.  The 09:50-10:10 zone is named
    # "Morning Reversal/Continuation" and its stated rule is:
    #   "Buy stocks that set new 30-minute highs and short stocks setting new
    #    30-minute lows."
    #   https://www.tradingsim.com/blog/day-trading-time-zones
    #
    # REGIME LEG: only the SHORT leg is registered.  The 09:00 ET hour's
    # forward 6-bar move has flipped to -0.0133 from +0.0677 historically, so
    # the documented rule's downside branch is the one with support now.
    #
    # CONCRETE READING: the data set is RTH-only, so "a new 30-minute low" at
    # 09:45-10:10 (when the session is 15-40 minutes old) is read as: the bar
    # sets a NEW SESSION LOW and closes below the 09:30-09:45 opening-range
    # low, closing in the bottom 40% of its own range (i.e. it is going out on
    # its lows, not a wick).  First occurrence per session only.
    # ──────────────────────────────────────────────────────────────────
    new_low = (
        (eth >= OPEN_START) & (eth <= OPEN_END)
        & (l <= f["slo"])                                  # new session low
        & (c < f["or15_lo"])                               # through the OR15 low
        & ((c - l) <= CLOSE_TAIL_FRAC * f["rng"])          # closing on its lows
    )
    out["tm_open_newlow"] = (_first_of_day(new_low, day), -1)

    # ──────────────────────────────────────────────────────────────────
    # 2) tm_lunch_effect_long  (LONG)                          [12:00 ET]
    # QuantPedia's "Lunch Effect in the U.S. Stock Market Indices" (SPY hourly,
    # May 2010 - May 2024, New York time).  The stated rule is verbatim:
    #   "From 11 am, (sell) short; Cover (buy back shorted [borrowed] shares at
    #    12 pm and go straight long (buy); Sell (liquidate) (whole) long
    #    position at 2 pm."
    # and the article notes the long-only 12:00 -> 14:00 leg "may offer
    # preferable risk-return tradeoffs".
    #   https://quantpedia.com/lunch-effect-in-the-u-s-stock-market-indices/
    #
    # REGIME LEG: the 12:00 leg is exactly the hour that has strengthened most
    # in the measured window (+0.1402 vs +0.0764).  The 11:00 short leg is NOT
    # registered — 11:00 has gone the other way (+0.1253 vs +0.0786), so
    # shorting it would be trading against the measurement.
    #
    # This is a pure clock entry; the source specifies no price condition, so
    # none is added.  It fires once per session, on the 12:00 ET bar.
    # ──────────────────────────────────────────────────────────────────
    lunch_long = (eth == LUNCH_LONG_HOUR)
    out["tm_lunch_effect_long"] = (_first_of_day(lunch_long, day), +1)

    # ──────────────────────────────────────────────────────────────────
    # 3) tm_lunch_falsebreak  (LONG)                      [11:30-13:30 ET]
    # The lunch window is defined as "11:30 AM to 1:30 PM ET", and the measured
    # property that defines it is a collapse in follow-through:
    #   "False breakout rate: 45% to 55% during lunch versus 25% to 30% in
    #    morning"; directional bars "62% during morning versus 38% at lunch".
    #   https://tosindicators.com/research/should-you-trade-during-the-lunch-time-hour
    # TradingSim's lunch zone says the same thing qualitatively:
    #   "False breakouts and choppy sideways moves characterize this time
    #    period."
    #   https://www.tradingsim.com/blog/day-trading-time-zones
    #
    # REGIME LEG: fading the FAILED DOWNSIDE break (i.e. long).  11:00-13:00 is
    # where forward returns are now strongest, and a flat tape with a doubled
    # range and a 44.3% body/range is the textbook false-break environment.
    #
    # CONCRETE READING: neither source gives an overshoot size, so require the
    # bar to trade at least 0.05 ATR BELOW the frozen 09:30-11:30 morning low
    # and then CLOSE back above it — the literal definition of a false
    # breakout.  A rejection tail OR an up close carries "the break did not
    # hold" (they are alternatives, not both, otherwise the rule fires on <0.3%
    # of bars).  First occurrence per session.
    # ──────────────────────────────────────────────────────────────────
    false_break = (
        (eth >= LUNCH_START) & (eth <= LUNCH_END)
        & (l < f["morn_lo"] - POKE_ATR * atr)              # genuine break below
        & (c > f["morn_lo"])                               # closed back inside
        & ((f["dn_wick"] >= WICK_FRAC) | (c > o))          # rejected the break
    )
    out["tm_lunch_falsebreak"] = (_first_of_day(false_break, day), +1)

    # ──────────────────────────────────────────────────────────────────
    # 4) tm_lunch_vwap_rev  (LONG)                        [11:00-13:00 ET]
    # FuturesHive's "VWAP Mean Reversion Strategy", stated with an explicit
    # clock window and explicit conditions:
    #   "Optimal Timing: works exceptionally well mid-day (11:00 AM - 2:00 PM
    #    ET) when volatility normalizes.
    #    Entry Conditions: price deviates 2+ standard deviations from VWAP;
    #    reversal candle pattern present; volume decreasing (indicating
    #    exhaustion); target: return to VWAP line itself."
    #   https://www.futureshive.com/blog/futures-trading-strategies-indicators-2025
    #
    # REGIME LEG + WINDOW: the LOWER-band (long) leg, and the source's window is
    # truncated at 13:00 rather than 14:00 because the 14:00 hour has inverted
    # to -0.2661; the retained 11:00-13:00 slice is the measured strong stretch.
    #
    # CONCRETE READING: "deviates 2+ SD" = the bar TAGS the -2 sigma session
    # VWAP band intrabar and CLOSES back above it; "reversal candle" = an up
    # close (c > o); "volume decreasing" = either this bar is lighter than the
    # one before it or it is below the trailing hour's average (the two natural
    # readings, OR'd — insisting on both drops the rule under a 0.3% fire
    # rate).  First occurrence per session.
    # ──────────────────────────────────────────────────────────────────
    band_dn = f["vwap"] - VWAP_SIGMA * f["vsd"]
    vol_falling = (df["volume"] < df["volume"].shift(1)) | (f["rvol"] < RVOL_MIN)
    vwap_rev = (
        (eth >= MR_START) & (eth <= MR_END)
        & (f["vsd"] > 0)
        & (l <= band_dn) & (c > band_dn)                   # tag, then reclaim
        & (c > o)                                          # reversal candle
        & vol_falling                                      # volume decreasing
    )
    out["tm_lunch_vwap_rev"] = (_first_of_day(vwap_rev, day), +1)

    # ──────────────────────────────────────────────────────────────────
    # 5) tm_pm_lunchbreak  (SHORT)                        [14:00-15:30 ET]
    # The lunch range as an afternoon setup framework.  The lunch window is
    # "11:30 AM to 1:30 PM ET"; the sizing schedule steps back up to "Normal
    # size" at 1:30-2:30 PM and "Full size" at 2:30-4:00 PM, and the stated
    # operational rule is:
    #   "Rather than fighting the low-volume lunch hour, experienced traders
    #    use the lunch hour range as a setup framework rather than trying to
    #    trade within it ... note which key levels price approaches but does
    #    not break. When afternoon volume returns after 2:00 PM, these levels
    #    often produce clean reactions."
    #   https://tosindicators.com/research/should-you-trade-during-the-lunch-time-hour
    # TradingSim's 2:15-3:00 PM zone is labelled "Back to Business ... trends
    # established ... volume pickup".
    #   https://www.tradingsim.com/blog/day-trading-time-zones
    #
    # REGIME LEG: the DOWNSIDE break only.  The 14:00 hour's forward 6-bar move
    # is -0.2661 vs +0.1170 historically — the single sharpest inversion in the
    # measurement — so only the short side of the lunch-range break is taken.
    #
    # CONCRETE READING: freeze the 11:30-13:30 lunch high/low; from 14:00 take
    # every FRESH 5-min CLOSE below the lunch low (previous bar still inside,
    # so this is the crossing bar itself).  The source describes repeated
    # "clean reactions" at these levels rather than a one-and-done, so this
    # rule is NOT capped at one fire per session.  "Afternoon volume returns"
    # is satisfied by either baseline: above the trailing hour's mean, or above
    # the lunch window's own mean bar volume.
    # ──────────────────────────────────────────────────────────────────
    vol_back = (f["rvol"] >= RVOL_MIN) | (df["volume"] > f["lunch_vol"])
    lunch_break = (
        (eth >= PM_START) & (eth <= PM_END)
        & f["lunch_lo"].notna()
        & (c < f["lunch_lo"]) & (c.shift(1) >= f["lunch_lo"])   # the break bar
        & vol_back                                              # volume returns
    )
    out["tm_pm_lunchbreak"] = (lunch_break, -1)

    # ──────────────────────────────────────────────────────────────────
    # 6) tm_pm_noise_short  (SHORT)                       [14:00-15:30 ET]
    # Zarattini, Aziz & Barbon, "Beat the Market: An Effective Intraday
    # Momentum Strategy for S&P500 ETF (SPY)" (SSRN 4824172).  CXO Advisory's
    # summary states the mechanics verbatim:
    #   "Each minute of each day, compute noise boundaries as daily opening SPY
    #    price times one plus and one minus the average daily return up to that
    #    minute over the last 14 trading days, adjusting the upper bound up by
    #    any gap-down the prior overnight and the lower bound down by any
    #    gap-up the prior overnight."
    #   "If at any clock hour or half-hour (HH:00 or HH:30), SPY price has
    #    moved above (below) the upper (lower) boundary, open a long (short)
    #    position."
    #   https://www.cxoadvisory.com/momentum-investing/complex-intraday-time-series-momentum-strategy-applied-to-spy/
    #   https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4824172
    #
    # REGIME LEG + WINDOW: the SHORT branch, evaluated only at the 14:00, 14:30,
    # 15:00 and 15:30 clock checks.  The rule itself is unchanged; the
    # restriction is that the afternoon is where the measured drift is now
    # strongly negative (-0.2661 at 14:00), and the harness will not open a
    # position after eth 15.5 anyway.
    #
    # CONCRETE READING: "the average daily return up to that minute" is the
    # average of |close/open_of_day - 1| at the SAME clock slot over the
    # previous 14 sessions; the prior overnight gap is measured against the
    # previous session's final RTH close (this data set is RTH-only).  Not
    # restricted to one fire per session — the source re-enters after a stop.
    # ──────────────────────────────────────────────────────────────────
    sigma_t = _tod_avg_abs_move(df, f["sopen"])
    gap = f["sopen"] - _prev_day_close(c, day)
    lower_bound = f["sopen"] * (1.0 - sigma_t) - gap.clip(lower=0.0)
    on_clock = (minute == 0) | (minute == 30)
    noise_short = (
        (eth >= PM_START) & (eth <= PM_END)
        & on_clock
        & sigma_t.notna()
        & (c < lower_bound)
    )
    out["tm_pm_noise_short"] = (noise_short, -1)

    # hygiene: strict bool, index-aligned, no NaN leakage
    return {k: (s.reindex(df.index).fillna(False).astype(bool), side)
            for k, (s, side) in out.items()}

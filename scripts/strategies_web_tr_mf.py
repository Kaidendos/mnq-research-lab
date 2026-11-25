"""Mark Fisher ACD methodology for MNQ 5-min RTH bars  (prefix "mf_").

TRADER
------
Mark B. Fisher - founder of MBF Clearing Corp, for years one of the largest
clearing firms on the NYMEX, and author of "The Logical Trader: Applying a
Method to the Madness" (John Wiley & Sons, 2002).  ACD is his published, named
methodology; it is taught commercially and ships as a built-in indicator
package in CQG.  What is actually verifiable: a book from a major publisher, a
real clearing firm, and a vendor-implemented indicator - NOT an audited P&L.
Nothing in this file depends on a performance claim.

SOURCES
-------
  [MF1] Mark B. Fisher, "The Logical Trader", Chapter 1 "Know Your ACDs",
        publisher's own free PDF excerpt (Wiley):
        https://catalogimages.wiley.com/images/db/pdf/E0471215511.01.pdf
        PRIMARY SOURCE.  Every A/B/C/D rule below is quoted from it verbatim.

  [MF2] CQG, "Mark Fisher Indicator" (the vendor's ACD implementation)
        https://news.cqg.com/workspaces/2016/11/mark-fisher-indicator
        "A user-set multiple of the Average True Range is added and subtracted
        from the open range to determine the A lines (red) and the C lines
        (blue)."  Also: "The three rolling pivot ranges are also displayed on
        the chart".  This is why A/C are sized off ATR here rather than off the
        book's per-contract tick table (which has no MNQ row - MNQ did not
        exist in 2002).

  [MF3] Fisher's pivot range, formula as reproduced by Frank Ochoa (PivotBoss),
        "A Quick Guide to the Pivot Range"
        https://pivotboss.com/2010/05/31/a-quick-guide-to-the-pivot-range/
        "Pivot = (High + Low + Close)/3", "BC = (High + Low)/2",
        "TC = (Pivot - BC) + Pivot", plus "I always refer to the highest level
        as TC, and the lowest level as BC, regardless of which formula led to
        the level's creation."

  [MF4] "The Central Pivot Range & Floor Trader Pivots" (Franklin O. Ochoa Jr.)
        https://time-price-research-astrofin.blogspot.com/2023/08/central-pivot-range-floor-trader-pivots.html
        ATTRIBUTION NOTE, read this before trusting the mf_pivot_* / mf_narpiv_*
        names: this page states outright that "The concept of the Central Pivot
        Range was developed by Frank Ochoa (2010) based on Mark Fisher's Pivot
        Range (2002)".  The pivot RANGE is Fisher's.  The two-day relationship
        taxonomy and the pivot-width rule below are OCHOA's extension of it.
        They are used here because they are mechanical and published; they are
        NOT presented as things Fisher wrote.
        Higher Value = "Current day's pivot range is completely higher than the
        prior day's pivot range.  The most bullish relationship of the seven
        two-day combinations" -> "buy a pull-back to the range ahead of a move
        to new highs".  Lower Value = "completely lower than the prior
        session's range... the most bearish two-day relationship" -> "sell any
        pull-back to the range ahead of a drop to new lows".
        Pivot width: "if the market experiences a very quiet trading day in the
        prior session, the pivots for the following day are likely to be
        unusually tight, or narrow, which typically leads to a Trend Day".

VERBATIM RULES FROM [MF1] THAT THIS FILE ENCODES
------------------------------------------------
  * Why the opening range at all.  "I constructed a trading model based on
    breakouts of the opening range on the premise that once this occurs, the
    market is likely to continue in that direction.  These breakouts are
    determined using a time and price filter that is applied to the opening
    range."
  * Opening range length.  "For stocks, the opening range time frame is
    generally the first 20 minutes of the day... In commodities, the length of
    time used for the opening range varies from 5 minutes to 30 minutes."
  * Point A.  "A points - up or down - are based upon a certain number of ticks
    above or below the opening range, if trading is sustained at these levels
    for a period of time equivalent to half the duration of the opening range
    that you have chosen."
  * One A per day.  "There is only one A per day.  That means, once an A up is
    established, there can be no A down for that trading day.  Or, if an A down
    is established, there can be no A up for that trading day."
  * Point B (a stop, not traded here).  "Once you have established an A - up or
    down - your stop for getting out of an unprofitable trade is B.  The B
    level, where you would be bias neutral, is delineated by the opening range."
  * The standing bias after an A.  "According to the ACD system, once an A is
    established, your bias has to reflect the market's relation to the opening
    range - long above it and short below it."  Repeated: "Once the A up or the
    A down is established, you retain a bullish bias above the opening range
    and a bearish one below."
  * Point C.  "Point Cs are calculated (just like As) based upon a certain
    number of ticks above or below the opening range."  "Point C is the
    crossover point at which your bias shifts from bullish to bearish, or vice
    versa."  "Point C is always in the opposite direction of Point A."
    Worked S&P example: opening range 1346.00-1351.50, A value 2.00 -> A up
    1353.50 (= OR high + A); C value 1.50 -> C down 1344.50 (= OR low - C).  So
    both A and C are measured from the OPENING-RANGE BOUNDARY, not the midpoint.
  * Point D (a stop, not traded here).  "If you have a C down, the stop - known
    as Point D - would be 1 tick above the top of the opening range."
  * Rubber band / failed A.  "A rubber band trade is made when the market
    approaches or just touches a target and snaps back.  In that instance, you
    would go short just below the A up or go long just above the A down.  Your
    stop on the trade would be the A up/down price point."  Guard from the same
    page: "this concept of the rubber band trading only works if you have a
    failed A or a failed A down.  Once an A has been established, you must
    retain a bullish bias above the opening range and a bearish one below."

CONCRETE READINGS (every place the source is not numeric, spelled out)
----------------------------------------------------------------------
  1. OR LENGTH.  [MF1] gives a range (5-30 min for commodities, 20 min for
     stocks) and says "The key is to define the time period for the opening
     range and then be consistent when you trade using that time period."  A
     30-minute OR (09:30-10:00) is used - the top of Fisher's commodity band -
     because it makes "half the opening range" exactly three 5-minute bars,
     the finest resolution this data supports.
  2. "TRADING IS SUSTAINED AT THESE LEVELS FOR HALF THE OPENING RANGE".  The
     intrabar clock is not observable on 5-minute bars.  Reading used: three
     CONSECUTIVE 5-minute bars each CLOSING at or beyond the level, i.e. the
     market was at or beyond the level at three successive 5-minute marks
     spanning 15 minutes.  Entry on the third bar's close.
  3. A AND C VALUES.  [MF1] refuses to publish the formula - "These variables
     are based on our own proprietary research, the process of which I won't
     share with you except to say that the ACD values are based on the
     volatility measurements of a particular stock, commodity, or financial
     derivative" - and its per-contract appendix table has no MNQ row.  [MF2]
     says the vendor uses "a user-set multiple of the Average True Range".  So
     A and C here are fractions of a 14-day Wilder ATR built from STRICTLY
     PRIOR sessions.  A_FRAC = 0.10 was set from the book's own worked
     examples, where the A value runs about 5-12% of that session's range
     (crude 7-8 ticks, natural gas 15 ticks, unleaded 25 ticks, S&P 2.00 pts,
     BRCM 76c).  Sanity check on this data: an A of one sign or the other
     prints on ~87% of sessions, consistent with Fisher's framing that there is
     one A on essentially every day.  Fisher does NOT state a universal C/A
     ratio - it is per-contract in his appendix and is not always > 1 (his S&P
     example has C 1.50 against A 2.00).
  4. "APPROACHES OR JUST TOUCHES A TARGET".  Book example: A up 20.78, the
     market printed 20.77 - one tick short of an 8-tick A value, i.e. within
     12.5% of it.  Reading used: the bar's extreme comes within 15% of the A
     value of the level (or through it) without the level being sustained.
  5. "SNAPS BACK".  Not quantified by Fisher.  Reading used: the bar closes in
     the far 40% of its own range, away from the level it poked.
  6. TIME CUTOFF.  Fisher puts no clock limit on any entry.  A 15:30 cutoff is
     applied to every signal purely so the harness has bars left to manage the
     trade in.

MEASURED AND DROPPED - Point C and failed-C
-------------------------------------------
Point C (mf_cdn_short / mf_cup_long) and the book's named "Good A Up, Failed C
Down" fade were both implemented faithfully and then removed, because they are
too rare on MNQ to be scored.  Measured on 99,030 RTH bars / 1,290 sessions:
after a confirmed A up, price TOUCHES the C-down level on only 5.3% of
sessions, and sustains it for half the opening range on 3.2%.  The finished
signals fired on 0.02-0.09% of bars (21-88 events in five years) under every
OR length (15 and 30 min) and C value (0.075-0.16 x ATR) tried.  That is not a
coding problem - Fisher himself notes C moves are far rarer than A moves - it
is simply below the harness's usable range, so the rules were dropped rather
than loosened into something Fisher did not write.

NOT IMPLEMENTED - and why
-------------------------
  * The ACD "number line" / macro A-up-A-down running score (Fisher's rolling
    30-day total of daily readings).  Chapter 1 does not define the scoring
    table and no located source states the exact per-day scoring rule.
    Inventing one and attributing it to Fisher would be a fabrication.
  * The appendix per-contract A/C tick table.  It exists but is not in the free
    chapter and has no MNQ entry regardless.
  * "Buy the dip" INSIDE the bias zone.  Fisher is explicit that this one is
    discretionary - "The decision to fade is based upon what you observe in the
    market" and "buy the bounce.  Never try to pick the top or the bottom."
    There is no mechanical bounce trigger in the text, so none is invented.
    What IS mechanical about that passage - the bias flipping on the opening
    range itself - is what mf_bias_* trades.

CAUSALITY
---------
Every session-scoped quantity is a cummax/cummin/cumsum/run-length inside the
current session, the current session's locked opening range (gated by
or_ready), or a whole-session / whole-week aggregate of STRICTLY PRIOR periods
reached through .shift(1) / .shift(2).  There is no groupby("_day").transform()
over the live session anywhere in this file, and the pre-computed or15_*/or30_*
columns are deliberately NOT used (they are built with transform("last")).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# ── opening range [MF1] + CONCRETE READING 1 ─────────────────────────────────
OR_END = 10.0            # 09:30-10:00 ET.  Bars are stamped at their START, so
                         # the OR is the bars with eth in [9.5, 10.0).
HALF_OR_BARS = 3         # "half the duration of the opening range" = 15 min

# ── A value [MF1] + [MF2] + CONCRETE READING 3 ───────────────────────────────
ATR_DAILY_LEN = 14       # Wilder daily ATR, built from prior sessions only
A_FRAC = 0.10            # A value = A_FRAC * prior daily ATR

# ── rubber band / failed A [MF1] + CONCRETE READINGS 4, 5 ────────────────────
NEAR_FRAC = 0.15         # "approaches or just touches": within 15% of A
SNAP_FRAC = 0.40         # "snaps back": close in the far 40% of the bar range

# ── pivot range [MF3] / relationships [MF4] ──────────────────────────────────
PIVOT_TOUCH_ATR = 0.05   # CONCRETE READING: "a pull-back to the range" counts
                         # when the bar reaches within 0.05 daily ATR of the
                         # range edge, not only on an exact tick touch.
NARROW_LOOKBACK = 60     # trailing window for "unusually tight" pivots [MF4]
NARROW_MIN_OBS = 20
NARROW_Q = 0.33          # bottom third of that window = "unusually tight"

# ── global entry cutoff (CONCRETE READING 6) ─────────────────────────────────
CUTOFF = 15.5


# ══════════════════════════════════════════════════════════════════════════════
# causal helpers
# ══════════════════════════════════════════════════════════════════════════════
def _prior_count(cond: pd.Series, day: pd.Series) -> pd.Series:
    """How many times `cond` was true STRICTLY earlier in the same session."""
    c = cond.fillna(False).astype(int)
    return c.groupby(day).cumsum() - c


def _first_of_day(cond: pd.Series, day: pd.Series) -> pd.Series:
    cond = cond.fillna(False)
    return cond & (_prior_count(cond, day) == 0)


def _earlier(cond: pd.Series, day: pd.Series) -> pd.Series:
    """True once `cond` has already fired STRICTLY earlier in this session."""
    return _prior_count(cond, day) > 0


def _at_or_before(cond: pd.Series, day: pd.Series) -> pd.Series:
    """True once `cond` has fired at or before this bar in this session."""
    return cond.fillna(False).astype(int).groupby(day).cumsum() > 0


def _run_length(flag: pd.Series, day: pd.Series) -> pd.Series:
    """Length of the current consecutive True run of `flag`, reset each session."""
    f = flag.fillna(False)
    block = (~f).astype(int).groupby(day).cumsum()   # new id at every False bar
    return f.astype(int).groupby([day, block]).cumsum()


def _locked_or(df: pd.DataFrame, end_eth: float):
    """High/low of [session open, end_eth), locked once that window has closed.

    cummax/cummin then ffill inside the day: on any bar the value reflects only
    bars at or before it.  `ready` gates consumption until the window is over.
    """
    day = df["_day"]
    inside = df["eth"] < end_eth
    hi = df["high"].where(inside).groupby(day).cummax().groupby(day).ffill()
    lo = df["low"].where(inside).groupby(day).cummin().groupby(day).ffill()
    return hi, lo, df["eth"] >= end_eth


def _daily_ohlc(df: pd.DataFrame):
    day = df["_day"]
    return (df["high"].groupby(day).max(),
            df["low"].groupby(day).min(),
            df["close"].groupby(day).last())


def _daily_atr_series(dh: pd.Series, dl: pd.Series, dc: pd.Series) -> pd.Series:
    """Wilder 14-day ATR from daily bars, SHIFTED one day (index = session date).

    [MF2]: the A and C offsets are "a user-set multiple of the Average True
    Range".  Shifted, so today's levels use only completed prior sessions.
    """
    pc = dc.shift(1)
    tr = pd.concat([dh - dl, (dh - pc).abs(), (dl - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1.0 / ATR_DAILY_LEN, adjust=False).mean().shift(1)


def _pivot_range(hi, lo, cl):
    """Fisher's pivot range [MF3].

        Pivot = (High + Low + Close) / 3
        BC    = (High + Low) / 2
        TC    = (Pivot - BC) + Pivot

    [MF3] then sorts them - "I always refer to the highest level as TC, and the
    lowest level as BC, regardless of which formula led to the level's
    creation."  Returns (top, bottom).
    """
    pp = (hi + lo + cl) / 3.0
    bc = (hi + lo) / 2.0
    tc = 2.0 * pp - bc
    return np.maximum(tc, bc), np.minimum(tc, bc)


def _weekly_prior_pivot(dh: pd.Series, dl: pd.Series, dc: pd.Series):
    """Pivot range of the PRIOR ISO week, as a per-session Series.

    [MF2] notes the vendor plots "three rolling pivot ranges"; this is the
    weekly one.  Built only from completed weeks, so it is known at the open of
    every session in the current week.
    """
    idx = pd.DatetimeIndex(dh.index)
    iso = idx.isocalendar()
    wk = pd.Index(np.asarray(iso["year"]) * 100 + np.asarray(iso["week"]))
    wh = pd.Series(dh.to_numpy(), index=wk).groupby(level=0).max()
    wl = pd.Series(dl.to_numpy(), index=wk).groupby(level=0).min()
    wc = pd.Series(dc.to_numpy(), index=wk).groupby(level=0).last()
    tc, bc = _pivot_range(wh.shift(1), wl.shift(1), wc.shift(1))
    return (pd.Series(np.asarray(tc.reindex(wk)), index=dh.index),
            pd.Series(np.asarray(bc.reindex(wk)), index=dh.index))


# ══════════════════════════════════════════════════════════════════════════════
def register(df: pd.DataFrame):
    day = df["_day"]
    h, l, c = df["high"], df["low"], df["close"]
    eth = df["eth"]
    bar_rng = (h - l).replace(0.0, np.nan)

    dh, dl, dc = _daily_ohlc(df)          # whole-session aggregates, prior days only
    datr_d = _daily_atr_series(dh, dl, dc)
    datr = day.map(datr_d)
    a_val = A_FRAC * datr

    or_hi, or_lo, or_ready = _locked_or(df, OR_END)

    # ── ACD price points [MF1].  A is measured from the opening-range BOUNDARY
    #    (verified against the book's S&P worked example: OR 1346.00-1351.50,
    #    A value 2.00 -> A up 1353.50).
    a_up = or_hi + a_val
    a_dn = or_lo - a_val

    live = or_ready & (eth < CUTOFF) & datr.notna()

    # ── "trading is sustained at these levels for a period of time equivalent
    #    to half the duration of the opening range" [MF1].
    #    CONCRETE READING 2: three consecutive 5-min closes at/beyond the level.
    sust_a_up = _run_length(or_ready & (c >= a_up), day) >= HALF_OR_BARS
    sust_a_dn = _run_length(or_ready & (c <= a_dn), day) >= HALF_OR_BARS

    # "There is only one A per day" [MF1] - whichever side confirms first kills
    # the other side's A for the rest of the session.
    first_a_up = _first_of_day(sust_a_up, day)
    first_a_dn = _first_of_day(sust_a_dn, day)
    a_up_made = _at_or_before(first_a_up, day)     # includes the bar it prints on
    a_dn_made = _at_or_before(first_a_dn, day)
    any_a_made = a_up_made | a_dn_made

    out = {}

    # ═════════════════════════════════════════════════════════════════════════
    # 1/2.  POINT A - the core ACD entry.  [MF1]
    #   "if the market traded up to 25.77 to 25.78 and stayed there for 2 1/2
    #    minutes (half the five-minute time frame for the opening range), you
    #    would establish a long position/bias above 25.77 to 25.78."
    #   Symmetric on the downside.  One A per day, so each side additionally
    #   requires that the OTHER side was not already established.
    # ═════════════════════════════════════════════════════════════════════════
    out["mf_aup_long"] = (live & first_a_up & ~_earlier(first_a_dn, day), +1)
    out["mf_adn_short"] = (live & first_a_dn & ~_earlier(first_a_up, day), -1)

    # ═════════════════════════════════════════════════════════════════════════
    # 3/4.  RUBBER BAND - the failed A.  [MF1]
    #   "A rubber band trade is made when the market approaches or just touches
    #    a target and snaps back.  In that instance, you would go short just
    #    below the A up or go long just above the A down."
    #   Guard from the same page: "this concept of the rubber band trading only
    #    works if you have a failed A or a failed A down" -> no A of either sign
    #    may have been established at or before this bar.
    #   CONCRETE READING 4: "approaches or just touches" = the bar's extreme
    #    comes within NEAR_FRAC of the A value of the level (Fisher's own
    #    example missed by 1 tick out of 8 = 12.5%).
    #   CONCRETE READING 5: "snaps back" = the bar closes in the far SNAP_FRAC
    #    of its own range.  Entry is "just below the A up", so the close must
    #    still be outside the opening range - Fisher's example enters at 20.76
    #    with an OR high of 20.70 and the A up at 20.78.
    # ═════════════════════════════════════════════════════════════════════════
    snapped_dn = (c - l) <= SNAP_FRAC * bar_rng
    snapped_up = (h - c) <= SNAP_FRAC * bar_rng

    rubber_short = (live & ~any_a_made
                    & (h >= a_up - NEAR_FRAC * a_val) & (c < a_up)
                    & snapped_dn & (c > or_hi))
    out["mf_rubber_short"] = (_first_of_day(rubber_short, day), -1)

    rubber_long = (live & ~any_a_made
                   & (l <= a_dn + NEAR_FRAC * a_val) & (c > a_dn)
                   & snapped_up & (c < or_lo))
    out["mf_rubber_long"] = (_first_of_day(rubber_long, day), +1)

    # ═════════════════════════════════════════════════════════════════════════
    # 5/6.  BIAS RESUMPTION ON THE OPENING RANGE.  [MF1]
    #   "According to the ACD system, once an A is established, your bias has to
    #    reflect the market's relation to the opening range - long above it and
    #    short below it."  The opening range itself is Point B, "where you would
    #    be bias neutral".
    #   So: an A up puts the session in a bullish regime, and the range is the
    #   line where that bias would go neutral.  CONCRETE READING of the entry:
    #   after the A up, the first bar that probes DOWN into the neutral zone
    #   (its low reaches the opening-range high) yet still CLOSES above it - the
    #   range rejected price and the bullish bias survived.  Mirrored after an
    #   A down.  Fisher's own dip-buy in this zone is discretionary ("The
    #   decision to fade is based upon what you observe in the market"), so the
    #   only thing traded here is the mechanical part: the range holding.
    #   Note what this deliberately does NOT do: Fisher forbids shorting below
    #   the OR after an A up ("you do nothing... your bias is neutral until you
    #   reach the downside target, which would be Point C"), so each side here
    #   only ever trades in the direction of the session's own A.
    # ═════════════════════════════════════════════════════════════════════════
    bias_long = live & _earlier(first_a_up, day) & (l <= or_hi) & (c > or_hi)
    out["mf_bias_long"] = (_first_of_day(bias_long, day), +1)

    bias_short = live & _earlier(first_a_dn, day) & (h >= or_lo) & (c < or_lo)
    out["mf_bias_short"] = (_first_of_day(bias_short, day), -1)

    # ═════════════════════════════════════════════════════════════════════════
    # 7/8.  PIVOT RANGE, TWO-DAY RELATIONSHIP.
    #   Range formula = Fisher [MF3].  Two-day taxonomy = Ochoa [MF4], built on
    #   Fisher's range - see the ATTRIBUTION NOTE at the top of this file.
    #   Higher Value: "Current day's pivot range is completely higher than the
    #     prior day's pivot range.  The most bullish relationship" -> "buy a
    #     pull-back to the range ahead of a move to new highs".
    #   Lower Value: "completely lower than the prior session's range... the
    #     most bearish two-day relationship" -> "sell any pull-back to the range
    #     ahead of a drop to new lows".
    #   CONCRETE READING of "a pull-back to the range": price closed above the
    #   range earlier in the session, then a bar reaches back down to within
    #   PIVOT_TOUCH_ATR of the range top and still closes above it - the range
    #   held as support.  Mirrored for the bearish case.  First per session.
    #   Today's range comes from the PRIOR session's H/L/C (shift 1); the
    #   comparison range from the session before that (shift 2).
    # ═════════════════════════════════════════════════════════════════════════
    tc_1, bc_1 = _pivot_range(dh.shift(1), dl.shift(1), dc.shift(1))   # today's
    tc_2, bc_2 = _pivot_range(dh.shift(2), dl.shift(2), dc.shift(2))   # yesterday's
    tc = day.map(tc_1)
    bc = day.map(bc_1)
    higher_value = day.map(bc_1 > tc_2).fillna(False).astype(bool)
    lower_value = day.map(tc_1 < bc_2).fillna(False).astype(bool)

    tol = PIVOT_TOUCH_ATR * datr
    pv_live = (eth < CUTOFF) & tc.notna() & bc.notna() & datr.notna()

    pv_long = (pv_live & higher_value & _earlier(c > tc, day)
               & (l <= tc + tol) & (c > tc))
    out["mf_pivot_hv_long"] = (_first_of_day(pv_long, day), +1)

    pv_short = (pv_live & lower_value & _earlier(c < bc, day)
                & (h >= bc - tol) & (c < bc))
    out["mf_pivot_lv_short"] = (_first_of_day(pv_short, day), -1)

    # ═════════════════════════════════════════════════════════════════════════
    # 9/10.  NARROW PIVOT RANGE -> TREND DAY -> OPENING-RANGE BREAKOUT.
    #   Filter = Ochoa [MF4]: "if the market experiences a very quiet trading
    #     day in the prior session, the pivots for the following day are likely
    #     to be unusually tight, or narrow, which typically leads to a Trend
    #     Day".
    #   Trade  = Fisher [MF1]: "I constructed a trading model based on breakouts
    #     of the opening range on the premise that once this occurs, the market
    #     is likely to continue in that direction."
    #   CONCRETE READING of "unusually tight": pivot width divided by the prior
    #   daily ATR, in the bottom third of its own trailing NARROW_LOOKBACK-day
    #   distribution.  Today's width is known at today's open (it is built from
    #   yesterday's bar), so the trailing window may include today.
    #   Trigger: on such a day, the first bar after the opening range to close
    #   beyond the opening-range boundary.  This is the raw OR breakout, WITHOUT
    #   Fisher's A price filter - that variant is mf_aup_long / mf_adn_short.
    # ═════════════════════════════════════════════════════════════════════════
    width_ratio = (tc_1 - bc_1) / datr_d
    thresh = width_ratio.rolling(NARROW_LOOKBACK,
                                 min_periods=NARROW_MIN_OBS).quantile(NARROW_Q)
    narrow = day.map(width_ratio <= thresh).fillna(False).astype(bool)

    out["mf_narpiv_long"] = (
        _first_of_day(live & narrow & (c > or_hi), day), +1)
    out["mf_narpiv_short"] = (
        _first_of_day(live & narrow & (c < or_lo), day), -1)

    # ═════════════════════════════════════════════════════════════════════════
    # 11/12.  DAILY vs WEEKLY PIVOT-RANGE ALIGNMENT.
    #   [MF2] confirms Fisher's package plots "three rolling pivot ranges"
    #   (daily / weekly / monthly).  The relationship rule applied across those
    #   two timeframes is Ochoa's Higher-Value / Lower-Value test [MF4] - the
    #   daily range sitting entirely above (below) the weekly range - so the
    #   attribution is the same split as 7/8: range = Fisher, relationship
    #   taxonomy = Ochoa.  Fisher does not write this cross-timeframe test in
    #   Chapter 1; it is labelled here so nobody mistakes it for his words.
    #   Trigger: on an aligned day, the first bar after the opening range to
    #   close beyond the opening-range boundary in the aligned direction.
    # ═════════════════════════════════════════════════════════════════════════
    wtc_d, wbc_d = _weekly_prior_pivot(dh, dl, dc)
    wtc = day.map(wtc_d)
    wbc = day.map(wbc_d)
    dw_bull = day.map(bc_1 > wtc_d).fillna(False).astype(bool)
    dw_bear = day.map(tc_1 < wbc_d).fillna(False).astype(bool)

    out["mf_wkpiv_long"] = (
        _first_of_day(live & dw_bull & wtc.notna() & (c > or_hi), day), +1)
    out["mf_wkpiv_short"] = (
        _first_of_day(live & dw_bear & wbc.notna() & (c < or_lo), day), -1)

    return {k: (v.reindex(df.index).fillna(False).astype(bool), s)
            for k, (v, s) in out.items()}

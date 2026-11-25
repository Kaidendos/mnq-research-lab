"""John Carter (Simpler Trading) and Toby Crabel entry triggers for MNQ 5-min RTH.

Every signal below is a translation of a rule that the named trader published, or
that is documented verbatim in a reference describing that trader's rule. Where a
source is vague and I had to pick a concrete number, the comment says
"CONCRETE READING" and names what was chosen and why. Nothing is attributed to a
trader that the sources do not actually say.

SOURCES
  [C1] John Carter's TTM Squeeze - StockCharts ChartSchool, "TTM Squeeze"
       https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-indicators/ttm-squeeze
       "introduced by John Carter of Trade the Markets (now Simpler Trading)".
       Bollinger Bands "20 periods and 2 standard deviations"; Keltner Channels
       "20 periods for the moving average and ATR, and 1.5 for the ATR multiplier".
       Squeeze ON when upper BB < upper KC and lower BB > lower KC ("red dots");
       squeeze OFF/fired = "green dots". Momentum oscillator = linear regression of
       Close - ((Donchian(20) midline + SMA(20)) / 2). Long: "Buy when green dots
       appear after red dots AND momentum histogram is above zero and rising".
       Short: "Enter short when the squeeze fires AND momentum histogram falls below
       zero and declining".

  [C2] John Carter's HOLP / LOHP - WH SelfInvest, "Trading strategy: HOLP (buy
       signals)" https://www.whselfinvest.com/en/trading_strategies_19_holp.php
       HOLP = High Of the Low Period. Identify "a close which is a 20-period low",
       take the high of the bar holding the lowest low of those 20 periods, and
       "Buy a long position after the first close above this high". LOHP is "a
       mirror strategy" giving short signals. Hard filter stated on the same page:
       "only apply HOLP (buy signals) when the market is up" and "only apply LOHP
       (short signals) when the market trend is down".
       Setup name and origin also confirmed at
       https://www.elitetrader.com/et/threads/anyone-ever-try-john-carters-mastering-the-trade-strategies.130898/
       ("HOLP stands for High Of the Low Period ... mark the low of the session high
       for a short entry, and vice versa"), describing Carter's Mastering the Trade.

  [C3] John Carter's Opening Gap play - Mastering the Trade ch. "The Opening Gap",
       summarised at https://www.simplertrading.com/newsetups and discussed at
       https://www.elitetrader.com/et/threads/gap-fades.130904/
       It is a fade: buy a gap down, short a gap up, at the cash open, targeting the
       gap fill. Carter states a MINIMUM gap size ("at least 10 on YM or 1 on ES")
       and screens OUT professional/breakaway gaps using pre-market cash volume
       (>70,000 = do not fade).

  [T1] Toby Crabel, "Day Trading with Short Term Price Patterns & Opening Range
       Breakout" (1990), as documented by StockCharts ChartSchool "Narrow Range Day
       NR7" https://chartschool.stockcharts.com/table-of-contents/trading-strategies-and-models/trading-strategies/narrow-range-day-nr7
       "An NR4 pattern would be the narrowest range in four days, while an NR7 would
       be the narrowest range in seven days"; range = high - low. Bull signal:
       "Buy on move above high of narrow range day high".

  [T2] Toby Crabel's ORB + stretch - QuantifiedStrategies "NR7 Trading Strategy -
       Toby Crabels Narrow Range 7 Pattern"
       https://www.quantifiedstrategies.com/nr7-trading-strategy-toby-crabel/
       and Oxford Strategies "NR7 Pattern | Trading Strategy (Setup & Exit)"
       https://oxfordstrat.com/trading-strategies/nr7/
       "A trade is taken at a predetermined amount above/below the open. The
       predetermined amount is called the stretch. Long trades place a buy stop at
       [Open + Stretch], and short trades place a sell stop at [Open - Stretch]."
       "The stretch is determined by looking at the previous 10 days and averaging
       the differences between the open for each day and the closest extreme to the
       open on each day" i.e. mean over 10 sessions of min(High-Open, Open-Low).
       Crabel "found the opening range breakout trade to be most effective after a
       Narrow Range 7 (NR7) day".

  [T3] Crabel's ORB source article: Toby Crabel, "Playing The Opening Range
       Breakout, Part 1", Technical Analysis of Stocks & Commodities V.6:9 (337-339)
       https://store.traders.com/-v06-c09-playing-pdf.html

NOT IMPLEMENTED, deliberately - see the report: Carter's "10 o'clock reversal"
and his pivot-based entries. The 09:50-10:10 reversal window is real published
folklore (T3Live "Reversal Times Explained", ShadowTrader "Reversal Periods") but
I could not find a source that states it as a mechanical Carter rule with an entry
condition, and Carter's pivot chapter describes pivots as "pausing points on
trending days and fading points on choppy days" - a discretionary regime read with
no stated trigger. Inventing a mechanical version and putting his name on it would
be dishonest, so neither is here.

OVERLAP WITH EXISTING PLUG-INS (declared, not accidental):
  * strategies_web/web_vol.py already has vol_ttm_squeeze_long/short. That version
    builds the Keltner Channel on an EMA-20 basis while the Bollinger Bands sit on
    an SMA-20 basis. Carter's indicator (and the thinkorswim TTM_Squeeze study the
    [C1] description is taken from) puts BOTH bands on the SAME 20-period simple
    moving average. jc_carter_squeeze_* is that same-basis version - a corrected
    variant of the same rule, not a new rule.
  * web_vol.py's vol_nr7id_break_long applies NR7 to 5-MINUTE bars. Crabel's NR7 is
    a DAILY-bar pattern used to select which day to trade, which is what
    jc_crabel_nr_orb_* does, and it is combined with the stretch ORB rather than a
    break of the pattern bar's high. Different construction, different timeframe.
  * web_mr.py's mr_gapfade_* waits until 09:45 and requires the first 15 minutes to
    already be pushing the fade direction, and only takes TINY gaps. Carter's play
    is at the market at the open with a minimum gap size, which is what
    jc_carter_gapfade_* does.

CAUSALITY: every session-scoped value is built from cumcount/cummax/ffill inside
the day, and every whole-day aggregate is .shift(1)-ed so it only ever contains
COMPLETED prior sessions. No groupby-transform of a current-day extreme anywhere.
Only ENTRY triggers are returned; the harness owns stops, targets and exits.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# ── TTM Squeeze [C1] ─────────────────────────────────────────────────────────
SQZ_LEN = 20            # BB period, KC period, ATR period, momentum period
BB_MULT = 2.0           # "20 periods and 2 standard deviations"
KC_MULT = 1.5           # "1.5 for the ATR multiplier"

# ── HOLP / LOHP [C2] ─────────────────────────────────────────────────────────
HOLP_LEN = 20           # "a close which is a 20-period low"

# ── Crabel ORB [T2] ──────────────────────────────────────────────────────────
STRETCH_DAYS = 10       # "looking at the previous 10 days"
NR_LEN_4 = 4            # NR4 = narrowest range in four days [T1]
                        # (NR7, the narrowest in seven, is a strict subset of NR4 -
                        #  see the compression-screen comment in register())
# Crabel places the buy/sell stop at the open and does NOT state a cancel time, so
# no cut-off is invented here: the resting stop stays live for the session and the
# signal is the first bar that touches it. The harness sweeps entry-time windows
# itself, so baking in a made-up deadline would only hide information from it.
# 15:30 just keeps entries off the closing bars.
ORB_CUTOFF = 15.5

# ── Opening gap fade [C3] ────────────────────────────────────────────────────
ADR_LEN = 14            # sessions in the average-daily-range yardstick
# CONCRETE READING. Carter's published gap filters are a fixed point minimum
# ("10 on YM or 1 on ES") and a PRE-MARKET CASH VOLUME screen for breakaway gaps.
# Neither transfers here: the point minimum is instrument-specific and the data set
# is RTH-only so pre-market volume does not exist. What survives of Carter's intent
# is "the gap must be big enough to be worth fading, and a huge gap is a breakaway
# gap you do not fade". These bounds, as a fraction of the 14-session average daily
# range, are MY choice, not Carter's numbers.
GAP_MIN_ADR = 0.20
GAP_MAX_ADR = 1.00


# ══════════════════════════ causal helpers ═══════════════════════════════════
def _bar_of_day(df: pd.DataFrame) -> pd.Series:
    """0-based index of the bar inside its own session (running count - causal)."""
    return df.groupby(df["_day"]).cumcount()


def _session_open(df: pd.DataFrame) -> pd.Series:
    """Today's 09:30 open, forward-filled. Known from the first bar onwards."""
    first = _bar_of_day(df) == 0
    return df["open"].where(first).groupby(df["_day"]).ffill()


def _daily(df: pd.DataFrame):
    """Per-session OHLC aggregates, indexed by session date (NOT yet shifted)."""
    day = df["_day"]
    return (
        df["open"].groupby(day).first(),
        df["high"].groupby(day).max(),
        df["low"].groupby(day).min(),
        df["close"].groupby(day).last(),
    )


def _map_prior(df: pd.DataFrame, per_day: pd.Series) -> pd.Series:
    """Map a per-session series onto bars using the PREVIOUS session's value."""
    return df["_day"].map(per_day.shift(1))


def _first_of_day(cond: pd.Series, day: pd.Series) -> pd.Series:
    """Thin `cond` down to its first occurrence in each session."""
    c = cond.fillna(False).astype(bool)
    prior = c.astype(int).groupby(day).cumsum() - c.astype(int)
    return c & (prior == 0)


def _rose_this_bar(flag: pd.Series, day: pd.Series) -> pd.Series:
    """flag is True now and was False (or absent) on the previous bar of the day.

    NOTE: groupby().shift() returns OBJECT dtype for a boolean Series, and `~` on an
    object Series inverts the Python bools to -2/-1 (both truthy). The explicit
    astype(bool) below is what keeps this from silently degenerating into `flag`.
    """
    f = flag.fillna(False).astype(bool)
    prev = f.groupby(day).shift(1).fillna(False).astype(bool)
    return f & ~prev


def _linreg_endpoint(y: pd.Series, n: int) -> pd.Series:
    """Value of the least-squares line fitted to the last `n` points, at the last
    point. Closed form (no rolling.apply) - x is 0..n-1 so var(x)=(n^2-1)/12.

    s1 = sum_{k=0}^{n-1} k * y[i-k]  (k is the lag, so k=0 is the current bar).
    """
    s0 = y.rolling(n).sum()
    s1 = sum(k * y.shift(k) for k in range(1, n))
    slope = 12.0 * ((n - 1) * s0 / 2.0 - s1) / (n * (n * n - 1))
    return s0 / n + slope * (n - 1) / 2.0


def _true_range(df: pd.DataFrame) -> pd.Series:
    pc = df["close"].shift(1)
    return pd.concat(
        [df["high"] - df["low"], (df["high"] - pc).abs(), (df["low"] - pc).abs()],
        axis=1,
    ).max(axis=1)


def _squeeze(df: pd.DataFrame):
    """[C1] squeeze-on flag and the momentum oscillator.

    CONCRETE READING of "Keltner Channels ... 20 periods for the moving average and
    ATR": the thinkorswim TTM_Squeeze implementation uses a SIMPLE 20-bar average of
    close for the midline and a SIMPLE 20-bar average of true range for the width,
    which is what is used here (not Wilder smoothing, and not the df["atr"] column
    which is Wilder-14).
    """
    c, n = df["close"], SQZ_LEN
    basis = c.rolling(n).mean()
    dev = BB_MULT * c.rolling(n).std(ddof=0)
    bb_up, bb_dn = basis + dev, basis - dev

    atr_s = _true_range(df).rolling(n).mean()
    kc_up, kc_dn = basis + KC_MULT * atr_s, basis - KC_MULT * atr_s

    squeeze_on = (bb_up < kc_up) & (bb_dn > kc_dn)

    # momentum: Close - ((Donchian(20) midline + SMA(20)) / 2), then linreg-smoothed
    donch_mid = (df["donch_hi20"] + df["donch_lo20"]) / 2.0
    delta = c - (donch_mid + basis) / 2.0
    mom = _linreg_endpoint(delta, n)
    return squeeze_on, mom


def _stretch(df: pd.DataFrame) -> pd.Series:
    """[T2] Crabel's stretch: mean over the previous 10 SESSIONS of the smaller of
    (High - Open) and (Open - Low). Shifted, so only completed sessions are used."""
    do, dh, dl, _ = _daily(df)
    noise = np.minimum(dh - do, do - dl)
    per_day = noise.shift(1).rolling(STRETCH_DAYS).mean()   # days d-10 .. d-1
    return df["_day"].map(per_day)


def _narrow_range_flag(rng: pd.Series, n: int) -> pd.Series:
    """[T1] NR{n}: this session's range is narrower than each of the previous n-1."""
    ok = pd.Series(True, index=rng.index)
    for k in range(1, n):
        ok &= rng < rng.shift(k)
    return ok


# ══════════════════════════ registration ═════════════════════════════════════
def register(df: pd.DataFrame):
    day = df["_day"]
    o, h, l, c = df["open"], df["high"], df["low"], df["close"]
    eth = df["eth"]

    out = {}

    # ─────────────────────────────────────────────────────────────────────────
    # 1/2. John Carter - THE SQUEEZE (TTM Squeeze).  [C1]
    #      Squeeze was ON last bar and is OFF this bar (the first green dot after
    #      red dots = "the squeeze fires"), and the momentum histogram agrees:
    #      above zero AND rising for the long, below zero AND falling for the short.
    # ─────────────────────────────────────────────────────────────────────────
    squeeze_on, mom = _squeeze(df)
    fired = squeeze_on.shift(1).fillna(False) & ~squeeze_on.fillna(False)
    mom_up = (mom > 0) & (mom > mom.shift(1))
    mom_dn = (mom < 0) & (mom < mom.shift(1))

    out["jc_carter_squeeze_long"] = (fired & mom_up, +1)
    out["jc_carter_squeeze_short"] = (fired & mom_dn, -1)

    # ─────────────────────────────────────────────────────────────────────────
    # 3. John Carter - HOLP, High Of the Low Period.  [C2]
    #    A close that is a 20-bar low sets the level = that bar's HIGH; buy the
    #    first close above it. Carter's own filter is applied: longs only "when the
    #    market is up", read as the harness's gate_ema50 (prior daily close above
    #    the daily EMA50 - the only market-trend gate available here).
    #    CONCRETE READING: the level is reset at each session open, so a HOLP set
    #    yesterday cannot trigger today. [C2] does not say this; it keeps the play
    #    intraday, which is what this harness trades.
    #    ([C2] says the level is the high of the bar with the lowest LOW of the 20;
    #    on a 20-bar-low CLOSE that is overwhelmingly the same bar, and using the
    #    signal bar's own high is the reading that stays strictly causal.)
    # ─────────────────────────────────────────────────────────────────────────
    low_close_20 = c <= c.rolling(HOLP_LEN).min()
    holp = h.where(low_close_20).groupby(day).ffill()
    first_above = _rose_this_bar((c > holp).fillna(False), day)
    out["jc_carter_holp_long"] = (first_above & df["gate_ema50"].astype(bool), +1)

    # ─────────────────────────────────────────────────────────────────────────
    # 4. John Carter - LOHP, Low Of the High Period.  [C2] "a mirror strategy".
    #    A close that is a 20-bar high sets the level = that bar's LOW; sell the
    #    first close below it, and only "when the market trend is down"
    #    (gate_below50).
    # ─────────────────────────────────────────────────────────────────────────
    high_close_20 = c >= c.rolling(HOLP_LEN).max()
    lohp = l.where(high_close_20).groupby(day).ffill()
    first_below = _rose_this_bar((c < lohp).fillna(False), day)
    out["jc_carter_lohp_short"] = (first_below & df["gate_below50"].astype(bool), -1)

    # ─────────────────────────────────────────────────────────────────────────
    # 5. John Carter - THE OPENING GAP, faded.  [C3]
    #    Short a gap up at the cash open, targeting the gap fill. Fires on the
    #    close of the 09:30 bar (the earliest causally admissible stand-in for
    #    Carter's "buy/sell at the market at 9:30"), only while the gap is still
    #    open at that close, and only for gaps inside the size band declared above
    #    - a band that is MY substitute for Carter's pre-market-volume screen, not
    #    a number he published.
    # ─────────────────────────────────────────────────────────────────────────
    _, dh, dl, dc = _daily(df)
    prior_close = _map_prior(df, dc)
    adr = df["_day"].map((dh - dl).shift(1).rolling(ADR_LEN).mean())
    sess_open = _session_open(df)

    gap = sess_open - prior_close
    gap_ok = (gap.abs() >= GAP_MIN_ADR * adr) & (gap.abs() <= GAP_MAX_ADR * adr)
    first_bar = _bar_of_day(df) == 0

    out["jc_carter_gapfade_short"] = (
        (first_bar & gap_ok & (gap > 0) & (c > prior_close)).fillna(False), -1
    )
    out["jc_carter_gapfade_long"] = (
        (first_bar & gap_ok & (gap < 0) & (c < prior_close)).fillna(False), +1
    )

    # ─────────────────────────────────────────────────────────────────────────
    # 6/7. Toby Crabel - OPENING RANGE BREAKOUT with the STRETCH.  [T2] [T3]
    #      Buy stop at [session open + stretch], sell stop at [session open -
    #      stretch], stretch = 10-session mean of min(High-Open, Open-Low).
    #      Crabel's order is a RESTING STOP, so the trigger is an intrabar touch
    #      (high >= level / low <= level), not a close beyond the level. This
    #      harness can only take the entry at a bar close, so the fill is recorded
    #      at the close of the bar the stop was hit on - later and generally worse
    #      than Crabel's real fill, which is the conservative direction. Both values
    #      are known at that bar's close, so this stays causal.
    # ─────────────────────────────────────────────────────────────────────────
    stretch = _stretch(df)
    up_trig = sess_open + stretch
    dn_trig = sess_open - stretch
    in_window = eth < ORB_CUTOFF

    orb_long = (in_window & (h >= up_trig)).fillna(False)
    orb_short = (in_window & (l <= dn_trig)).fillna(False)
    out["jc_crabel_orb_stretch_long"] = (_first_of_day(orb_long, day), +1)
    out["jc_crabel_orb_stretch_short"] = (_first_of_day(orb_short, day), -1)

    # ─────────────────────────────────────────────────────────────────────────
    # 8. Toby Crabel - the same ORB, but ONLY after a compression session.  [T1] [T2]
    #    "Crabel found the opening range breakout trade to be most effective after a
    #    Narrow Range 7 (NR7) day" [T2].
    #    CONCRETE READING: a strict NR7 screen leaves ~10% of sessions, which is too
    #    thin to backtest here, so the screen is widened to "the prior session was a
    #    compression session" = NR4 [T1] OR an inside day. Both are Crabel patterns
    #    from the same book and both express the same volatility-contraction idea,
    #    but the OR is mine - Crabel's stated best filter is NR7 alone.
    # ─────────────────────────────────────────────────────────────────────────
    rng_d = dh - dl
    nr4_d = _narrow_range_flag(rng_d, NR_LEN_4)
    inside_d = (dh < dh.shift(1)) & (dl > dl.shift(1))
    compressed = _map_prior(df, (nr4_d | inside_d)).fillna(False).astype(bool)

    out["jc_crabel_nr_orb_long"] = (_first_of_day(orb_long & compressed, day), +1)
    out["jc_crabel_nr_orb_short"] = (_first_of_day(orb_short & compressed, day), -1)

    return {
        k: (v.reindex(df.index).fillna(False).astype(bool), s)
        for k, (v, s) in out.items()
    }

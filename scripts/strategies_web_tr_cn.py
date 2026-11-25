"""Larry Connors / Connors Research mean-reversion entries for MNQ 5-min RTH bars.

Every rule below is a faithful translation of a rule Connors (with Cesar Alvarez)
PUBLISHED with explicit numbers, in a book or in a vendor/reference write-up that
quotes the book's parameter table. Where a source is vague, or where I had to make
a choice the source does not make, the choice is stated in a comment marked
[READING]. ENTRY TRIGGERS ONLY — stops / targets / sizing / exits are the
harness's job, so the published exit rules are recorded in the docstrings for
reference but are NOT implemented here.

WHO: Larry Connors — Connors Research / TradingMarkets. Track record that is
actually verifiable: published, backtested, explicitly-parameterised rule sets in
"Short Term Trading Strategies That Work" (Connors & Alvarez, 2008), "High
Probability ETF Trading" (Connors & Alvarez, 2009) and the Connors Research
Trading Strategy Series. The claim being relied on here is only that these ARE
his rules, verbatim and mechanical — not that his published hit rates replicate.

Sources
-------
RSI2    : StockCharts ChartSchool, "RSI(2)"
          https://chartschool.stockcharts.com/table-of-contents/trading-strategies-and-models/trading-strategies/rsi-2
          Long  : above the 200-period SMA and RSI(2) < 5.
          Short : below the 200-period SMA and RSI(2) > 95.
          ("He found that returns were higher when buying on an RSI dip below 5
           than on one below 10" / "higher when selling short on an RSI surge
           above 95 than on a surge above 90".)
          Published exit: cross of the 5-period SMA. Not implemented (harness).

DOUBLE7 : "Double 7's Strategy", The Chartist  https://www.thechartist.com.au/double-7-s-strategy/
          and roboforex https://blog.roboforex.com/blog/2023/02/24/larry-connors-double-7-trading-strategy/
          From "Short Term Trading Strategies That Work". Three rules verbatim:
          (1) above the 200-day MA, (2) close at a 7-day LOW -> buy,
          (3) exit when it closes at a 7-day high.

R3      : WH SelfInvest, "Larry Connors' R3 strategy"
          https://www.whselfinvest.com/en-lu/trading-platform/free-trading-strategies/tradingsystem/81-r3-larry-connors
          Ch.4 of "High Probability ETF Trading". Long: price > 200-day MA; RSI(2)
          falls three days in a row; on the first day of that drop RSI(2) is
          already < 60; today RSI(2) closes < 10. Exit RSI(2) > 70.

TPS     : "TPS Trading Strategy - Time, Price, Scale-In", tradingstrategyguides.com
          https://tradingstrategyguides.com/tps-trading-strategy/
          Ch.7 of "High Probability ETF Trading". First (10%) entry: ETF above the
          200-day MA and RSI(2) closes below 25 for the SECOND day in a row.
          Later scale-ins (20/30/40%) are sizing, and the exit is RSI(2) > 70 —
          both belong to the harness, so only the first entry is signalled.

CRSI    : StockCharts ChartSchool, "ConnorsRSI"
          https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-indicators/connorsrsi
          ConnorsRSI(3,2,100) = (RSI(3) + RSI(streak,2) + PercentRank(100)) / 3.
          "Connors recommends: oversold below 10, overbought above 90."

CUMRSI  : thinkorswim.net, "Cumulative RSI Trading Strategy (2 period)"
          https://thinkorswim.net/cumulative-rsi-trading-strategy/
          quoting the parameter table on p.67 of "Short Term Trading Strategies
          That Work": (200, 2, 2, 35, 65, no) = 200-period trend filter, RSI(2),
          SUM of the last 2 RSI(2) readings, buy < 35, exit > 65, no stop.

PCTB    : EdgeTools, "Larry Connors %b Strategy (Bollinger Band)", TradingView
          https://www.tradingview.com/script/yXkWPSlU/
          Ch.6 of "High Probability ETF Trading". (1) close above the 200-day MA,
          (2) %b below 0.2 for three consecutive days, (3) buy at the close.
          Exit when %b closes above 0.8.

TIMEFRAME TRANSLATION  [READING] — applies to ALL seven
-------------------------------------------------------
Connors states these rules on DAILY bars. This harness trades 5-minute RTH bars.
Rather than invent an intraday variant and attribute it to him, every period count
is carried over BAR-FOR-BAR: "200-day MA" becomes a 200-BAR SMA (~2.5 RTH
sessions of 5-min bars), "RSI(2)" becomes RSI over 2 bars, "7-day low" becomes a
7-bar low, "three consecutive days" becomes three consecutive bars. That is the
same translation the MQL5 study of Connors' RSI2 used, and it preserves the shape
of the rule (short-horizon extreme inside a longer-horizon trend) at intraday
scale. It is a translation, NOT something Connors published for 5-min bars.

SHORT SIDES  [READING]
----------------------
Only RSI2 and R3 are published by Connors with an explicit short side. Double 7's,
TPS, Cumulative RSI and %b are published LONG-ONLY (ETF long-bias books). Their
"_short" signals here are the exact mirror image (trend filter flipped, threshold
reflected about the indicator's midpoint) and are MY symmetric extension — Connors
did not publish them. Each is flagged in its docstring.

CAUSALITY: nothing but rolling / ewm / shift on the bar series. No session
aggregates, no groupby-transform, no forward-looking values whatsoever. A signal
on bar i uses only bars <= i.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# ── Connors' published constants (named, not magic) ──────────────────────────
TREND_LEN = 200          # "200-day moving average" -> 200-bar SMA  [READING]

RSI2_LEN = 2             # Connors' 2-period RSI, used by RSI2/R3/TPS/CUMRSI
RSI2_BUY = 5.0           # ChartSchool: dip below 5 beat a dip below 10
RSI2_SELL = 95.0         # ChartSchool: surge above 95 beat a surge above 90
RSI2_EXIT_MA = 5         # published exit: cross of the 5-period SMA

D7_LEN = 7               # "closes at a 7-day low"

R3_DROPS = 3             # "the 2-period RSI drops three days in a row"
R3_FIRST_MAX = 60.0      # "on the first day of the drop the RSI is already < 60"
R3_TRIGGER = 10.0        # "the 2-period RSI of the current day closes < 10"
R3_EXIT = 70.0           # published exit: RSI(2) > 70 long / < 30 short

TPS_LEVEL = 25.0         # "2-period RSI closes below 25"
TPS_DAYS = 2             # "...for two consecutive days" (the 10% entry)
TPS_EXIT = 70.0          # published exit: "we exit when RSI(2) crosses above 70"

CRSI_PRICE_LEN = 3       # ConnorsRSI(3,2,100)
CRSI_STREAK_LEN = 2
CRSI_RANK_LEN = 100
CRSI_BUY = 10.0          # "oversold below 10"
CRSI_SELL = 90.0         # "overbought above 90"

CUM_N = 2                # p.67 param table: sum of the last 2 RSI(2) values
CUM_BUY = 35.0           # p.67: buy below 35
CUM_EXIT = 65.0          # p.67: exit above 65
CUM_MAX = CUM_N * 100.0  # reflection axis for the mirrored short side

BB_LEN = 20              # %b is Bollinger's own default: 20-period, 2 sigma
BB_SD = 2.0
PCTB_BUY = 0.2           # "%b below 0.2"
PCTB_SELL = 0.8          # "exit when %b closes above 0.8"
PCTB_DAYS = 3            # "for three consecutive days"


# ── helpers ──────────────────────────────────────────────────────────────────
def _wilder_rsi(close: pd.Series, n: int) -> pd.Series:
    """Wilder-smoothed RSI, the definition Connors uses."""
    delta = close.diff()
    up = delta.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-delta.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


def _rsi_of_streak(close: pd.Series, n: int) -> pd.Series:
    """RSI(n) of the ConnorsRSI up/down STREAK series.

    ChartSchool: "the number of days in a row that the closing price has been
    higher (up) or lower (down) than the previous close"; +3 for three up closes,
    -2 for two down closes, reset to 0 when the price is unchanged.
    Vectorised: run-length of each constant-sign block, signed.
    """
    sgn = np.sign(close.diff()).fillna(0.0)
    blocks = (sgn != sgn.shift(1)).cumsum()
    run = sgn.groupby(blocks).cumcount() + 1
    streak = run * sgn                    # zero automatically where sgn == 0
    return _wilder_rsi(pd.Series(streak.to_numpy(), index=close.index), n)


def _percent_rank(series: pd.Series, n: int) -> pd.Series:
    """PercentRank(n): % of the previous n readings that are BELOW the current one.

    Window = the n prior values plus the current value, so bar i sees bars i-n..i.
    """
    v = series.to_numpy(dtype=float)
    out = np.full(v.shape, np.nan)
    if len(v) > n:
        filled = np.nan_to_num(v, nan=0.0)
        win = np.lib.stride_tricks.sliding_window_view(filled, n + 1)
        out[n:] = (win[:, :n] < win[:, n:n + 1]).mean(axis=1) * 100.0
    # the first n+1 bars never had a full window, and pct_change()'s leading NaN
    # poisons one more, so blank them out rather than emit a fake rank
    out[: n + 2] = np.nan
    return pd.Series(out, index=series.index)


def _connors_rsi(close: pd.Series) -> pd.Series:
    """ConnorsRSI(3,2,100) = (RSI(3) + RSI(streak,2) + PercentRank(100)) / 3."""
    return (
        _wilder_rsi(close, CRSI_PRICE_LEN)
        + _rsi_of_streak(close, CRSI_STREAK_LEN)
        + _percent_rank(close.pct_change(), CRSI_RANK_LEN)
    ) / 3.0


def _fresh(cond: pd.Series) -> pd.Series:
    """First bar of a condition run.

    [READING] Connors' rules are POSITION-ENTRY rules ("buy at the close when
    ..."); once filled you are in the trade and the setup cannot re-fire until it
    resets. On a pure bar series the mechanical equivalent is to trigger only on
    the first bar of a run — the prior bar was not yet in the setup. Without this
    a single flush would emit a dozen identical signals.
    """
    c = cond.fillna(False)
    return c & ~c.shift(1).fillna(False).astype(bool)


def _one_position(setup: pd.Series, exit_rule: pd.Series) -> pd.Series:
    """Fire only when a Connors trader following the published rules would be FLAT.

    [READING] Every one of these strategies is published as a matched pair — an
    entry rule AND an exit rule for a SINGLE position ("exit when the 2-period RSI
    closes above 70", "sell when it closes at a 7-day high", ...). A bare bar
    series carries no position state, so the setup is disarmed the moment it
    fires and only re-arms once THAT STRATEGY'S OWN published exit has printed.
    This is strictly more faithful than "first bar of a run": it emits exactly the
    trades the published rule set makes available, instead of re-signalling every
    bar of a long oversold stretch the trader is already positioned in.

    The harness supplies the real stop/target, so the exit rule is used ONLY as
    the re-arm gate here — it never closes a backtested trade.

    Causal by construction: a forward-only state machine, bar i sees bars <= i.
    """
    s = setup.fillna(False).to_numpy(dtype=bool)
    x = exit_rule.fillna(False).to_numpy(dtype=bool)
    out = np.zeros(len(s), dtype=bool)
    armed = True
    for i in range(len(s)):
        if armed:
            if s[i]:
                out[i] = True
                armed = False
        elif x[i]:
            armed = True
    return pd.Series(out, index=setup.index)


def _consecutive(cond: pd.Series, k: int) -> pd.Series:
    """True when `cond` has held for k bars in a row (the k-th bar included)."""
    return cond.fillna(False).rolling(k).sum() >= k


# ── strategies ───────────────────────────────────────────────────────────────
def _rsi2(df: pd.DataFrame):
    """Connors RSI-2, exactly as ChartSchool states it.

    Long : close > SMA(200) and RSI(2) < 5.
    Short: close < SMA(200) and RSI(2) > 95.
    Re-arm gate = Connors' published exit: "exiting long positions on a move above
    the 5-day SMA and short positions on a move below the 5-day SMA".
    """
    c = df["close"]
    rsi = _wilder_rsi(c, RSI2_LEN)
    sma = c.rolling(TREND_LEN).mean()
    ma5 = c.rolling(RSI2_EXIT_MA).mean()
    return (_one_position((c > sma) & (rsi < RSI2_BUY), c > ma5),
            _one_position((c < sma) & (rsi > RSI2_SELL), c < ma5))


def _double7(df: pd.DataFrame):
    """Connors & Alvarez "Double 7's".

    Long : close > SMA(200) and today's close is the lowest close of the last 7.
    Short: [READING] MY MIRROR, not published — close < SMA(200) and today's close
           is the highest close of the last 7. Connors publishes Double 7's as a
           long-only ETF strategy; the short is the exact reflection of rules 1-2.
    Re-arm gate = rule 3 verbatim, "sell the position if it closes at a 7-day
    high" (mirrored to a 7-bar low for the short side).
    """
    c = df["close"]
    sma = c.rolling(TREND_LEN).mean()
    lo7 = c.rolling(D7_LEN).min()
    hi7 = c.rolling(D7_LEN).max()
    at_lo, at_hi = c <= lo7, c >= hi7
    return (_one_position((c > sma) & at_lo, at_hi),
            _one_position((c < sma) & at_hi, at_lo))


def _r3(df: pd.DataFrame):
    """Connors & Alvarez R3 (High Probability ETF Trading, ch.4).

    Long : price > SMA(200); RSI(2) falls three bars in a row; the RSI(2) reading
           the first of those drops fell FROM is already < 60; RSI(2) now < 10.
    Short: price < SMA(200); RSI(2) rises three bars in a row; the reading the
           first rise started FROM is already > 40; RSI(2) now > 90.
           [READING] WH SelfInvest's short block is a copy-paste of the long block
           with two values left unmirrored ("first day ... > 60" and "closes > 10",
           which as written is true ~90% of the time and cannot be the rule). The
           short side is therefore the arithmetic reflection about 50 of the long
           side they DO state cleanly: 60 -> 40, 10 -> 90.
    Re-arm gate = the published exits, RSI(2) > 70 (long) / < 30 (short).
    """
    c = df["close"]
    rsi = _wilder_rsi(c, RSI2_LEN)
    sma = c.rolling(TREND_LEN).mean()

    dropping = rsi < rsi.shift(1)
    rising = rsi > rsi.shift(1)
    drop3 = dropping & dropping.shift(1) & dropping.shift(2)
    rise3 = rising & rising.shift(1) & rising.shift(2)
    # the value the 3-bar sequence started from = RSI three bars back
    start = rsi.shift(R3_DROPS)

    long_ = (c > sma) & drop3 & (start < R3_FIRST_MAX) & (rsi < R3_TRIGGER)
    short = (c < sma) & rise3 & (start > 100 - R3_FIRST_MAX) & (rsi > 100 - R3_TRIGGER)
    return (_one_position(long_, rsi > R3_EXIT),
            _one_position(short, rsi < 100 - R3_EXIT))


def _tps(df: pd.DataFrame):
    """Connors & Alvarez TPS — the initial 10% entry only.

    Long : above SMA(200) and RSI(2) closes below 25 for the second bar running.
    Short: [READING] MY MIRROR, not published — below SMA(200) and RSI(2) closes
           above 75 for the second bar running.
    The 20/30/40% scale-ins are position sizing and belong to the harness, so only
    the trigger that opens the trade is emitted.
    Re-arm gate = the published exit, "whether we established a 10% position or a
    100% position, we exit when the 2-period RSI crosses above the 70 level".
    """
    c = df["close"]
    rsi = _wilder_rsi(c, RSI2_LEN)
    sma = c.rolling(TREND_LEN).mean()
    long_ = (c > sma) & _consecutive(rsi < TPS_LEVEL, TPS_DAYS)
    short = (c < sma) & _consecutive(rsi > 100 - TPS_LEVEL, TPS_DAYS)
    return (_one_position(long_, rsi > TPS_EXIT),
            _one_position(short, rsi < 100 - TPS_EXIT))


def _crsi(df: pd.DataFrame):
    """Connors Research ConnorsRSI(3,2,100) extremes.

    Long : ConnorsRSI < 10 ("oversold below 10").
    Short: ConnorsRSI > 90 ("overbought above 90"). Both thresholds are Connors'
           own published recommendation and are symmetric in the source, so unlike
           the other mirrors here the short side IS documented.
    [READING] ChartSchool gives ConnorsRSI as an INDICATOR with recommended
    oversold/overbought levels rather than as a full strategy, so no trend filter
    is applied — adding one would be me inventing a rule. The trend-filtered
    version is covered by the other six.
    [READING] for the same reason there is no published exit to gate re-entry on,
    so this one falls back to _fresh() (first bar of the extreme) rather than the
    _one_position() gate the other six use.
    """
    crsi = _connors_rsi(df["close"])
    return _fresh(crsi < CRSI_BUY), _fresh(crsi > CRSI_SELL)


def _cumrsi(df: pd.DataFrame):
    """Connors & Alvarez Cumulative RSI, book parameters (200, 2, 2, 35, 65, no).

    Long : close > SMA(200) and SUM of the last 2 RSI(2) readings < 35.
    Short: [READING] MY MIRROR, not published — close < SMA(200) and the same
           2-bar sum > 165 (= 2*100 - 35, the reflection of the buy threshold).
    Re-arm gate = the published exit, 2-bar cumulative RSI > 65 (mirrored to < 135).
    """
    c = df["close"]
    rsi = _wilder_rsi(c, RSI2_LEN)
    cum = rsi.rolling(CUM_N).sum()
    sma = c.rolling(TREND_LEN).mean()
    return (_one_position((c > sma) & (cum < CUM_BUY), cum > CUM_EXIT),
            _one_position((c < sma) & (cum > CUM_MAX - CUM_BUY),
                          cum < CUM_MAX - CUM_EXIT))


def _pctb(df: pd.DataFrame):
    """Connors & Alvarez %b strategy (High Probability ETF Trading, ch.6).

    %b = (close - lower band) / (upper band - lower band), Bollinger(20, 2).
    Long : close > SMA(200) and %b < 0.2 for three consecutive bars.
    Short: [READING] MY MIRROR, not published — close < SMA(200) and %b > 0.8 for
           three consecutive bars.
    [READING] the EdgeTools write-up quotes the rules but not the band settings;
    20-period / 2-sigma is Bollinger's own default and the one Connors uses
    throughout the book. The harness's bb_up / bb_dn columns are exactly that, so
    they are used directly.
    Re-arm gate = the published exit, "%b closes above 0.8" (mirrored to < 0.2).
    """
    c, up, dn = df["close"], df["bb_up"], df["bb_dn"]
    width = (up - dn).replace(0, np.nan)
    pctb = (c - dn) / width
    sma = c.rolling(TREND_LEN).mean()
    long_ = (c > sma) & _consecutive(pctb < PCTB_BUY, PCTB_DAYS)
    short = (c < sma) & _consecutive(pctb > PCTB_SELL, PCTB_DAYS)
    return (_one_position(long_, pctb > PCTB_SELL),
            _one_position(short, pctb < PCTB_BUY))


# ── registry ─────────────────────────────────────────────────────────────────
_FAMILIES = (
    ("rsi2", _rsi2),
    ("double7", _double7),
    ("r3", _r3),
    ("tps", _tps),
    ("crsi", _crsi),
    ("cumrsi", _cumrsi),
    ("pctb", _pctb),
)


def register(df):
    """df = enriched MNQ 5-min RTH bars, tz America/New_York."""
    out = {}
    for short_name, fn in _FAMILIES:
        long_, short = fn(df)
        out[f"cn_connors_{short_name}_long"] = (long_.fillna(False).astype(bool), +1)
        out[f"cn_connors_{short_name}_short"] = (short.fillna(False).astype(bool), -1)
    return out

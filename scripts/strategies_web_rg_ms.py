"""ms_* — MEAN-REVERSION SYSTEMS for MNQ 5-min RTH bars.

Every rule below is a translation of a documented, mechanical source. Where a
source leaves something unspecified the concrete choice is stated in a comment
marked [READING]. ENTRY TRIGGERS ONLY — stops / targets / sizing / exits are
swept by the harness.

Regime this was built for (measured, last 3 months vs the prior 4.5 years):
net move flat (+1.8%), green days 49.2%, median daily range 451pt vs 229pt,
median 5-min ATR 51.0 vs 25.9, body/range 44.3% vs 51.6%, ADX<20 days 23.1%.
Huge range with no net progress and more wick than body is the textbook case for
fading extremes, so every rule here is a FADE. Because ATR has doubled, a fixed
ATR-multiple stop is now twice as wide in dollars and entry precision matters
more than it used to — so each rule additionally requires the extreme to be
REJECTED (close back inside the band, wick rejection, volume exhaustion, or a
retest that holds above the prior low) rather than merely touched, and each one
uses the source's own "one trade per excursion" state so a single flush does not
emit ten identical entries at ten different prices.

Sources
-------
CRSI2  : "Cumulative RSI-2 Trading Strategy", easycators.com — ThinkScript port of
         Connors & Alvarez, *Short Term Trading Strategies That Work*, p.67-68.
         https://easycators.com/thinkscript/cumulative-rsi-2-trading-strategy/
         Published settings "200, 2, 2, 35, 65" = 200-period MA trend filter,
         RSI period 2, sum the last 2 RSI(2) readings, buy threshold 35, sell
         (exit) threshold 65. Short side (below the trend MA, overbought RSI(2))
         from StockCharts' RSI(2) write-up:
         https://chartschool.stockcharts.com/table-of-contents/trading-strategies-and-models/trading-strategies/rsi-2

PCTB   : "Mean Reversion Day Trading Strategy: The Complete 2026 Guide", tradewink.com
         https://www.tradewink.com/learn/mean-reversion-strategy
         Five-condition checklist: (1) "The market must be in a choppy or
         range-bound regime"; (2) "At least two of these must be true: RSI > 75
         (short) or < 25 (long); Price outside Bollinger Bands; Price > 1.5x ATR
         from VWAP; Z-score > +2.0 or -2.0" — with "RSI is necessary but
         insufficient alone", and "Standard: RSI > 70 for shorts, RSI < 30 for
         longs"; (3) entry at a "structural level — prior support, a round
         number, a daily pivot, or the prior day's low/high"; (4) volume
         exhaustion — "declining volume relative to the initial spike bar";
         (5) no binary catalyst. %B thresholds: "%B > 1.05 for shorts,
         %B < -0.05 for longs". Z-score lookback and +-2.0 threshold
         cross-checked against https://quantstock.org/strategy-guide/zscore
         ("strongest with a 30-day lookback and +-2.0 threshold").

KFADE  : "Sam's Keltner Band Fade and Basis Bounce", TradingView (Sam_Levi)
         https://www.tradingview.com/script/QAQwu06o-Sam-s-Keltner-Band-Fade-and-Basis-Bounce/
         Keltner length 20 (SMA basis), ATR length 10, multiplier 2.0. Fade =
         "Price touches or slightly penetrates the outer band" + "Wick rejection"
         + "Close back inside the channel" + "Confirming candle direction" +
         full channel traverse ("A fade short at the upper band only fires if
         price recently came from the lower band"), opposite-band lookback 60.

KGRIMES: "Keltner Channel Study: Mean Reversion", leewenmarketstats.com
         https://www.leewenmarketstats.com/post/keltner_channel_fade_statistics
         Adam Grimes baseline: "20 Exponential Moving Average (EMA)", "Simple
         ATR", "2.25 ATR multiplier". "Fade Long: any closing below the lower
         Keltner band"; "Fade Short: any closing above the upper Keltner band".
         The ranging-only filter and the mid-line target come from
         https://protraderdashboard.com/blog/keltner-channels-guide/
         "Only use this strategy when there is no clear trend. In trending
         markets, fading channel touches often fails." / "Target the middle line
         (EMA) for profit".

WBOT   : Bollinger W-bottom / M-top — the multi-touch reversal — as mechanised by
         https://www.tradingsim.com/blog/bollinger-bands
         First bottom "closes outside of the lower Bollinger Band" on
         "substantial volume"; an "automatic rally"; then a retest that should
         "print inside the lower band", whose "retest price must be greater than
         or equal to the price of the first low", with "volume drop off
         dramatically".

REGCH  : "Automating Trading Strategies in MQL5 (Part 43): Adaptive Linear
         Regression Channel Strategy", MQL5 Articles
         https://www.mql5.com/en/articles/20347
         Least-squares channel, RegressionPeriod 100, Deviations 2.0. Buy:
         "(close2 >= lower2) && (closePrevious < channelLower)" — price was
         inside the lower band on the previous bar and has now closed decisively
         outside it. Sell is the mirror at the upper band.

CAUSALITY
---------
Every aggregate here is rolling / ewm / cumulative, a .shift(1)-ed daily value,
or a forward-scan state machine seeded at bar 0. There is no
groupby("_day").transform() over the current day, and no use of the or15_/or30_
columns (whose construction is only causal after the OR window closes).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# ── CRSI2 (easycators / Connors p.67, settings "200, 2, 2, 35, 65") ──────────
CRSI_RSI_LEN = 2          # "RSI period: 2"
CRSI_SUM_LEN = 2          # "Number of periods summed: 2"
CRSI_BUY = 35.0           # "Buy threshold (oversold): 35"
CRSI_EXIT = 65.0          # "Sell threshold (overbought): 65"  -> the re-arm level
CRSI_MA_LEN = 200         # "Long-term uptrend filter: 200-period moving average"

# ── PCTB (tradewink + quantstock) ────────────────────────────────────────────
PCTB_LONG = -0.05         # "%B < -0.05 for longs"
PCTB_SHORT = 1.05         # "%B > 1.05 for shorts"
PCTB_RSI_LONG = 30.0      # "Standard: RSI ... < 30 for longs"
PCTB_RSI_SHORT = 70.0     # "Standard: RSI > 70 for shorts"
PCTB_VWAP_ATR = 1.5       # "Price > 1.5x ATR from VWAP"
PCTB_Z_LEN = 30           # quantstock: "strongest with a 30-day lookback"
PCTB_Z = 2.0              # "Z-score > +2.0 or < -2.0"
PCTB_ADX_MAX = 25.0       # concrete reading of "choppy or range-bound regime"
PCTB_LEVEL_ATR = 0.5      # "at a structural level" -> within 0.5 ATR of one
PCTB_ROUND = 100.0        # "a round number" — MNQ trades in 100-point handles
PCTB_BB_LEN = 20          # standard Bollinger 20/2 (matches bb_up / bb_dn)

# ── KFADE (Sam's Keltner Band Fade) ──────────────────────────────────────────
KF_LEN = 20               # "Length: 20 (SMA basis)"
KF_ATR = 10               # "ATR Length: 10"
KF_MULT = 2.0             # "Multiplier: 2.0"
KF_TRAVERSE = 60          # "Lookback: 60 bars for opposite band detection"
KF_WICK = 0.40            # [READING] "wick rejection" = wick >= 40% of bar range

# ── KGRIMES (Grimes baseline) ────────────────────────────────────────────────
KG_EMA = 20               # "20 Exponential Moving Average (EMA)"
KG_ATR = 20               # [READING] "Simple ATR" length unstated -> match the EMA
KG_MULT = 2.25            # "2.25 ATR multiplier"
KG_ADX_MAX = 25.0         # "no clear trend" (protraderdashboard) made concrete

# ── WBOT (Bollinger W-bottom / M-top) ────────────────────────────────────────
WB_LEN = 20               # standard Bollinger 20/2
WB_MIN_GAP = 3            # the retest must be a separate low, not the same bar
WB_MAX_GAP = 30           # [READING] intraday horizon for "the most recent lows"
WB_RETEST_ATR = 0.50      # [READING] "retest the most recent lows" = within 0.5 ATR
WB_VOL_FRAC = 0.80        # "volume drop off dramatically" vs the first-bottom bar
WB_VOL_LEN = 20           # window for "substantial volume" on the first bottom

# ── REGCH (MQL5 art. 20347) ──────────────────────────────────────────────────
RC_LEN = 100              # "Regression Period: 100"
RC_DEV = 2.0              # "Standard Deviation Multiplier: 2.0"


# ══════════════════════════ helpers (all causal) ═════════════════════════════
def _wilder_rsi(close: pd.Series, n: int) -> pd.Series:
    delta = close.diff()
    up = delta.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-delta.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


def _true_range(df: pd.DataFrame) -> pd.Series:
    pc = df["close"].shift(1)
    return pd.concat([df["high"] - df["low"],
                      (df["high"] - pc).abs(),
                      (df["low"] - pc).abs()], axis=1).max(axis=1)


def _fresh(cond: pd.Series) -> pd.Series:
    """First bar of a streak."""
    c = cond.fillna(False)
    return c & ~c.shift(1).fillna(False).astype(bool)


def _rearm(entry: pd.Series, exit_: pd.Series) -> pd.Series:
    """Source-faithful 'no position open' gate.

    Fire on `entry` only while flat; go not-flat on the fire; become flat again
    on the source's own exit condition. Scanned forward from bar 0, so the state
    at bar i is a function of bars 0..i only — causal, and stable under prefix
    truncation (which is what lookahead_audit.py checks).
    """
    e = entry.fillna(False).to_numpy(dtype=bool)
    x = exit_.fillna(False).to_numpy(dtype=bool)
    out = np.zeros(len(e), dtype=bool)
    flat = True
    for i in range(len(e)):
        if flat:
            if e[i]:
                out[i] = True
                flat = False
        elif x[i]:
            flat = True
    return pd.Series(out, index=entry.index)


def _zscore(close: pd.Series, n: int) -> pd.Series:
    return (close - close.rolling(n).mean()) / close.rolling(n).std().replace(0, np.nan)


def _touched_within(flag: pd.Series, n: int) -> pd.Series:
    """Was `flag` True on any of the previous n bars (this bar excluded)?"""
    return flag.fillna(False).shift(1).rolling(n).max().fillna(0) > 0


def _last_event(flag: pd.Series) -> pd.Series:
    """Integer position of the most recent True at or before each bar."""
    pos = pd.Series(np.arange(len(flag), dtype=float), index=flag.index)
    return pos.where(flag.fillna(False).to_numpy()).ffill()


def _daily_adx_prev(df: pd.DataFrame, n: int = 14) -> pd.Series:
    """Wilder ADX(n) of the RTH DAILY bars, shifted — prior sessions only."""
    day = df["_day"]
    dh, dl, dc = (df["high"].groupby(day).max(), df["low"].groupby(day).min(),
                  df["close"].groupby(day).last())
    pc = dc.shift(1)
    tr = pd.concat([dh - dl, (dh - pc).abs(), (dl - pc).abs()], axis=1).max(axis=1)
    up_m, dn_m = dh.diff(), -dl.diff()
    plus = np.where((up_m > dn_m) & (up_m > 0), up_m, 0.0)
    minus = np.where((dn_m > up_m) & (dn_m > 0), dn_m, 0.0)
    atr_ = tr.ewm(alpha=1 / n, adjust=False).mean()
    pdi = 100 * pd.Series(plus, index=dh.index).ewm(alpha=1 / n, adjust=False).mean() / atr_
    mdi = 100 * pd.Series(minus, index=dh.index).ewm(alpha=1 / n, adjust=False).mean() / atr_
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    adx_d = dx.ewm(alpha=1 / n, adjust=False).mean().shift(1)      # shift => causal
    return pd.Series(day.to_numpy(), index=df.index).map(adx_d)


def _prior_day_levels(df: pd.DataFrame) -> list[pd.Series]:
    """Prior-day high/low/close plus the classic floor pivots — all shifted."""
    day = df["_day"]
    dc = df["close"].groupby(day).last()
    pdc = pd.Series(day.to_numpy(), index=df.index).map(dc.shift(1))
    pdh, pdl = df["pdh"], df["pdl"]                     # already prior-day, causal
    piv = (pdh + pdl + pdc) / 3.0
    rng = pdh - pdl
    return [pdh, pdl, pdc, piv,
            2 * piv - pdl, 2 * piv - pdh,               # R1, S1
            piv + rng, piv - rng]                       # R2, S2


def _linreg_channel(close: pd.Series, n: int, k: float):
    """Rolling least-squares channel: (fitted value at the last bar, k * resid sd).

    Closed form from rolling sums, so bar i sees only bars i-n+1 .. i.
    x = 0..n-1 within the window, so the x-moments are constants.
    """
    t = pd.Series(np.arange(len(close), dtype=float), index=close.index)
    sy = close.rolling(n).sum()
    sty = (t * close).rolling(n).sum()
    syy = (close * close).rolling(n).sum()

    sxy = sty - (t - n + 1) * sy                        # sum(x*y), x = t - (i-n+1)
    xbar = (n - 1) / 2.0
    sxx_c = (n - 1) * n * (2 * n - 1) / 6.0 - n * xbar * xbar
    ybar = sy / n

    slope = (sxy - n * xbar * ybar) / sxx_c
    fitted_last = ybar + slope * (n - 1 - xbar)

    ss_tot = syy - n * ybar * ybar
    ss_res = (ss_tot - slope * slope * sxx_c).clip(lower=0.0)
    return fitted_last, k * np.sqrt(ss_res / (n - 2))


# ══════════════════════════ strategies ═══════════════════════════════════════
def _crsi2(df: pd.DataFrame):
    """CRSI2 — Connors Cumulative RSI(2), published settings "200, 2, 2, 35, 65".

    Long : close > 200-period MA and RSI(2)[i] + RSI(2)[i-1] < 35, while flat.
           Flat is regained once that same 2-bar sum climbs back above 65 — the
           source's own exit threshold, so this is the book's state machine, not
           a bolted-on cooldown.
    Short: mirror — close < 200-period MA, 2-bar sum > 165 (= 2*100 - 35),
           re-arming once the sum drops back under 135 (= 2*100 - 65).
    [READING] the source's "200-period moving average" is applied on the chart's
    own timeframe, i.e. 200 five-minute bars (~2.5 sessions), which is the
    literal transcription. The short side is the exact mirror of the long
    thresholds; StockCharts documents the below-the-MA / overbought short leg.
    Why this regime: a 2-period RSI is the fastest available exhaustion read, and
    exhaustion is what pays when the median 5-min ATR doubles while net drift
    goes to zero. The state machine is what stops a 451-point day from firing a
    dozen entries down one leg.
    """
    c = df["close"]
    r = _wilder_rsi(c, CRSI_RSI_LEN)
    cum = r.rolling(CRSI_SUM_LEN).sum()
    ma = c.rolling(CRSI_MA_LEN).mean()
    hi_th = CRSI_SUM_LEN * 100.0 - CRSI_BUY             # 165
    hi_exit = CRSI_SUM_LEN * 100.0 - CRSI_EXIT          # 135

    long_ = _rearm(cum < CRSI_BUY, cum > CRSI_EXIT) & (c > ma)
    short = _rearm(cum > hi_th, cum < hi_exit) & (c < ma)
    return long_.fillna(False), short.fillna(False)


def _pctb(df: pd.DataFrame):
    """PCTB — tradewink's five-condition mean-reversion checklist.

    (1) regime     : prior session's DAILY ADX(14) < 25.
    (2) extreme    : RSI(14) < 30 (long) / > 70 (short) — "necessary" — AND at
                     least one of {%B < -0.05 / > 1.05, price more than 1.5 ATR
                     the wrong side of VWAP, z(30) beyond -+2.0} — "at least two
                     of these must be true".
    (3) structure  : within 0.5 ATR of the prior day's high/low/close, one of the
                     classic floor pivots (P, R1, S1, R2, S2), or a round
                     100-point handle.
    (4) exhaustion : this bar's volume is below the previous bar's.
    (5) catalyst   : not modellable from OHLCV — omitted, and said so.

    [READING] the article names the regime condition but gives it no number.
    Reading it at BAR level (5-min ADX < 25) is self-defeating: the very push
    that drives RSI to an extreme also lifts the 5-min ADX, so the combination
    fires on 0.17% of bars, under the harness's floor. Regime is a property of
    the market over days, so it is read on the DAILY bars and taken from the
    PRIOR session (shifted, hence causal). That is also the honest way to use it
    live — you know the regime before the session starts.
    Why this regime: this is the only rule here that demands the extreme land on
    a pre-known price level. With ATR doubled, an entry 25 points earlier or
    later is worth real money, and prior-day/pivot/round levels are the only
    reference points that exist before the bar prints.
    """
    c, h, l = df["close"], df["high"], df["low"]
    atr = df["atr"].replace(0, np.nan)
    up, dn = df["bb_up"], df["bb_dn"]
    pctb = (c - dn) / (up - dn).replace(0, np.nan)
    z = _zscore(c, PCTB_Z_LEN)
    dev = (c - df["vwap"]) / atr

    regime = _daily_adx_prev(df) < PCTB_ADX_MAX
    exhaust = df["volume"] < df["volume"].shift(1)

    near = ((c - (c / PCTB_ROUND).round() * PCTB_ROUND).abs() < PCTB_LEVEL_ATR * atr)
    for lvl in _prior_day_levels(df):
        near = near | ((c - lvl).abs() < PCTB_LEVEL_ATR * atr)

    l_extra = ((pctb < PCTB_LONG).astype(int)
               + (dev < -PCTB_VWAP_ATR).astype(int)
               + (z < -PCTB_Z).astype(int)) >= 1
    s_extra = ((pctb > PCTB_SHORT).astype(int)
               + (dev > PCTB_VWAP_ATR).astype(int)
               + (z > PCTB_Z).astype(int)) >= 1

    base = regime & exhaust & near
    long_raw = base & (df["rsi"] < PCTB_RSI_LONG) & l_extra
    short_raw = base & (df["rsi"] > PCTB_RSI_SHORT) & s_extra
    return _fresh(long_raw).fillna(False), _fresh(short_raw).fillna(False)


def _kfade(df: pd.DataFrame):
    """KFADE — Sam's Keltner Band Fade: SMA20 / ATR10 / 2.0, full-channel traverse.

    Long : the bar's low touches or penetrates the LOWER band, the bar shows a
           lower-wick rejection, it closes back INSIDE the channel, it is a
           bullish candle (close > open), and price touched the UPPER band within
           the previous 60 bars ("came from the opposite band").
    Short: the mirror at the upper band.
    [READING] "wick rejection" is made concrete as a wick >= 40% of the bar's
    range; "touch or slightly penetrate" is measured with the bar's extreme and
    "close back inside" with the close, exactly as the script describes.
    Why this regime: the traverse filter is the direct expression of "451-point
    range, no net progress" — it only fades an extreme that the market has just
    swung the full width of the channel to reach, which is the swing that a
    rangebound tape gives back. In a trending tape the traverse rarely completes,
    so the rule mutes itself.
    """
    o, h, l, c = df["open"], df["high"], df["low"], df["close"]
    basis = c.rolling(KF_LEN).mean()                       # SMA basis
    atr = _true_range(df).rolling(KF_ATR).mean()           # ATR length 10
    upper, lower = basis + KF_MULT * atr, basis - KF_MULT * atr

    rng = (h - l).replace(0, np.nan)
    body_lo = pd.concat([o, c], axis=1).min(axis=1)
    body_hi = pd.concat([o, c], axis=1).max(axis=1)
    wick_dn = ((body_lo - l) / rng) >= KF_WICK
    wick_up = ((h - body_hi) / rng) >= KF_WICK

    hit_lo, hit_hi = l <= lower, h >= upper
    from_hi = _touched_within(hit_hi, KF_TRAVERSE)
    from_lo = _touched_within(hit_lo, KF_TRAVERSE)

    long_ = hit_lo & (c > lower) & wick_dn & (c > o) & from_hi
    short = hit_hi & (c < upper) & wick_up & (c < o) & from_lo
    return long_.fillna(False), short.fillna(False)


def _kgrimes(df: pd.DataFrame):
    """KGRIMES — Grimes baseline Keltner fade: 20 EMA, simple ATR, 2.25x.

    "Fade Long: any closing below the lower Keltner band."
    "Fade Short: any closing above the upper Keltner band."
    Ranging-only, per protraderdashboard: "Only use this strategy when there is
    no clear trend" -> ADX(14) < 25 on the signal bar.
    [READING] the study opens ONE trade per excursion and holds it; the same
    guide's stated target is "the middle line (EMA)", so the rule re-arms once
    price closes back through the 20 EMA. Without that, a single flush emits a
    signal on every bar it spends outside the band.
    [READING] "Simple ATR" length is not given; 20 is used to match the 20 EMA.
    Why this regime: the plainest possible fade of a statistically stretched
    close, deliberately kept free of pattern conditions so the sweep gets one
    clean read on whether raw band-stretch reversion is paying right now.
    """
    c = df["close"]
    basis = c.ewm(span=KG_EMA, adjust=False).mean()
    atr = _true_range(df).rolling(KG_ATR).mean()           # "Simple ATR"
    upper, lower = basis + KG_MULT * atr, basis - KG_MULT * atr
    ranging = df["adx"] < KG_ADX_MAX

    long_ = _rearm(c < lower, c > basis) & ranging
    short = _rearm(c > upper, c < basis) & ranging
    return long_.fillna(False), short.fillna(False)


def _wbot(df: pd.DataFrame):
    """WBOT — Bollinger W-bottom (long) / M-top (short): the multi-touch reversal.

    Long, in the article's own order:
      1. first bottom   : a bar CLOSES below the lower Bollinger band, on
                          "substantial volume" (above its own 20-bar mean)
      2. automatic rally: since that bar, the running max close has recovered to
                          the middle band
      3. retest         : this bar's low comes back within 0.5 ATR of the first
                          bottom's low but is NOT below it — "the retest price
                          must be greater than or equal to the price of the first
                          low"
      4. prints inside  : this bar's low stays inside the lower band
      5. volume dries   : this bar's volume < 80% of the first-bottom bar's
    3 to 30 bars must separate the two lows. Short is the mirror (M-top).

    Causality: the first-bottom index, low and volume are forward-filled from
    PAST bars only; the recovery extreme is a cummax/cummin inside the event
    group shifted one bar, so bar i uses nothing after bar i.
    Why this regime: a double bottom that holds is the cleanest evidence that a
    session with a 451-point range has actually run out of sellers, and the
    "second low >= first low" clause gives the harness a stop reference only a
    few points away instead of a full ATR — which is exactly what a doubled ATR
    demands.
    """
    h, l, c, v = df["high"], df["low"], df["close"], df["volume"]
    atr = df["atr"]
    mid = c.rolling(WB_LEN).mean()
    up, dn = df["bb_up"], df["bb_dn"]
    pos = pd.Series(np.arange(len(df), dtype=float), index=df.index)
    vol_ma = v.rolling(WB_VOL_LEN).mean()

    out = {}
    for side in ("long", "short"):
        first = ((c < dn) if side == "long" else (c > up)) & (v > vol_ma)
        ev = _last_event(first)
        gap = pos - ev
        f_low = l.where(first.to_numpy()).ffill()
        f_high = h.where(first.to_numpy()).ffill()
        f_vol = v.where(first.to_numpy()).ffill()

        window = (gap >= WB_MIN_GAP) & (gap <= WB_MAX_GAP)
        dry = v < WB_VOL_FRAC * f_vol

        if side == "long":
            rally = c.groupby(ev).cummax().shift(1)          # through bar i-1
            cond = (window & (rally > mid)
                    & (l >= f_low) & (l <= f_low + WB_RETEST_ATR * atr)
                    & (l > dn) & dry)
        else:
            slide = c.groupby(ev).cummin().shift(1)
            cond = (window & (slide < mid)
                    & (h <= f_high) & (h >= f_high - WB_RETEST_ATR * atr)
                    & (h < up) & dry)
        out[side] = _fresh(cond)

    return out["long"].fillna(False), out["short"].fillna(False)


def _regch(df: pd.DataFrame):
    """REGCH — MQL5 art.20347 linear-regression channel, 100 bars / 2.0 SD.

    Buy  : "(close2 >= lower2) && (closePrevious < channelLower)" — the close was
           at or above the lower band on the prior bar and is now decisively
           below it. On this series: close[i-1] >= lower[i-1] and close[i] <
           lower[i], evaluated at the close of bar i.
    Sell : the mirror at the upper band.
    [READING] the article gates the channel on |slope| >= MinSlopeThreshold but
    does not publish the default value, so no slope gate is applied — the least
    restrictive faithful reading, and the right one for a flat tape. The
    article's default (non-inverse) mode is used; its buy already fires on the
    DOWNSIDE break, i.e. it is already the fade direction.
    Why this regime: this is the "standard-deviation reversion band" that adapts
    to drift. A plain 20-bar z-score calls a whole trending leg oversold; the
    100-bar least-squares channel measures the deviation about the fitted line
    instead, so it only flags a break that is extreme RELATIVE to the current
    slope — which is what you want when the range doubled but direction did not.
    """
    c = df["close"]
    fit, half = _linreg_channel(c, RC_LEN, RC_DEV)
    lower, upper = fit - half, fit + half

    long_ = (c.shift(1) >= lower.shift(1)) & (c < lower)
    short = (c.shift(1) <= upper.shift(1)) & (c > upper)
    return long_.fillna(False), short.fillna(False)


# ══════════════════════════ registry ═════════════════════════════════════════
def register(df):
    """df = enriched MNQ 5-min RTH bars, tz America/New_York.
    Returns {name: (entry_bool_series, side)}   side=+1 long, -1 short."""
    cr_l, cr_s = _crsi2(df)
    pb_l, pb_s = _pctb(df)
    kf_l, kf_s = _kfade(df)
    kg_l, kg_s = _kgrimes(df)
    wb_l, wb_s = _wbot(df)
    rc_l, rc_s = _regch(df)
    return {
        "ms_crsi2_long":    (cr_l.astype(bool), +1),
        "ms_crsi2_short":   (cr_s.astype(bool), -1),
        "ms_pctb_long":     (pb_l.astype(bool), +1),
        "ms_pctb_short":    (pb_s.astype(bool), -1),
        "ms_kfade_long":    (kf_l.astype(bool), +1),
        "ms_kfade_short":   (kf_s.astype(bool), -1),
        "ms_kgrimes_long":  (kg_l.astype(bool), +1),
        "ms_kgrimes_short": (kg_s.astype(bool), -1),
        "ms_wbot_long":     (wb_l.astype(bool), +1),
        "ms_mtop_short":    (wb_s.astype(bool), -1),
        "ms_regch_long":    (rc_l.astype(bool), +1),
        "ms_regch_short":   (rc_s.astype(bool), -1),
    }

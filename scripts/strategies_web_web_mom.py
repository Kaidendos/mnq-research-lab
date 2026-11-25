"""Momentum / trend-continuation ENTRY signals for MNQ 5-min RTH bars.

Category: pullback-to-moving-average in trend, higher-timeframe alignment,
ADX-gated continuation, breakout of consolidation.

Every rule below is a translation of a published, mechanically-specified
strategy.  Where a source is vague (or is written for daily bars) the concrete
reading chosen for 5-min MNQ is called out in a comment marked ADAPTED.

Sources
  [1] Raschke / Connors "Holy Grail"  -- 14-period ADX above 30 and rising,
      price retraces to the 20-period MA, enter at the high of the bar that
      touches the MA.
      https://www.tradingsetupsreview.com/the-holy-grail-trading-setup/
      https://tradersmastermind.com/linda-raschke-trading-strategy/
  [2] TradingSim "20 Moving Average Pullback" -- 20 MA sloping in trade
      direction (20 MA above its value 5 bars ago), prior higher high, lighter
      volume on the pullback than on the impulse, reversal candle closing at or
      above the rising 20 MA; enter on the close of the trigger candle.
      https://www.tradingsim.com/blog/20-moving-average-pullback
  [3] ADX / DI mechanical continuation rules -- ADX above 25 AND rising (two
      consecutive rising bars minimum), +DI crossing -DI, spread between +DI
      and -DI at least 5 points, enter on the close of the crossover candle or
      after a one-bar pullback toward the leading DI line.
      https://fxnx.com/en/blog/adx-indicator-strategy-the-gatekeeper-to-profitable-trends
      https://www.avatrade.com/education/technical-analysis-indicators-strategies/adx-indicator-trading-strategies
  [4] Bollinger BandWidth squeeze breakout -- BandWidth = (upper-lower)/middle,
      squeeze = BandWidth at its lowest level of the last N periods, then trade
      in the direction of the break out of the band.
      https://www.technical-analysis-pro.com/strategies-bollinger-bands-squeeze-strategy/
      https://www.thinkcapital.com/bollinger-bands-squeeze-strategy/
  [5] Elder Triple Screen -- screen 1 = higher-timeframe trend, screen 2 =
      oscillator oversold against that trend on the intermediate timeframe,
      screen 3 = buy-stop a few ticks above the high of the last closed bar.
      https://www.mql5.com/en/blogs/post/731016
      https://www.dailyforex.com/forex-articles/2020/09/elder-triple-screen-system/151378

CAUSALITY: every quantity here is either the current bar's own close-of-bar
value or a strictly backward-looking rolling / shifted aggregate.  Nothing uses
a whole-session max/min/last.  The one session-scoped helper, _sess_rollmax,
is a backward window that RESETS each session (rule 2).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# ── tunables (named, no magic numbers) ────────────────────────────────
ADX_HG = 30.0          # [1] Holy Grail trend-strength floor
ADX_HG_LOOKBACK = 10   # bars the "ADX>30 and rising" setup stays valid
HG_STOP_BARS = 3       # [1] bars the resting buy/sell stop stays working
ADX_DI = 25.0          # [3] "trending zone" threshold the ADX must enter
DI_SPREAD = 5.0        # [3] minimum +DI/-DI gap
SLOPE_BARS = 5         # [2] "20 MA above its value five bars ago"
HH_LOOKBACK = 20       # [2] window defining "made a higher high"
HH_RECENT = 10         # [2] how recently that higher high must have happened
VOL_MA = 10            # [2] pullback-volume reference average
SQUEEZE_WIN = 78       # [4] ADAPTED: 120 daily bars ~ 6 months; on 5-min RTH
                       #     one session is 78 bars, so "lowest BandWidth of
                       #     the last full session" is the intraday analogue.
SQUEEZE_RECENT = 12    # [4] breakout must come within an hour of the squeeze
STOCH_OS = 30.0        # [5] screen-2 oversold threshold
STOCH_OB = 70.0        # [5] screen-2 overbought threshold
OSC_RECENT = 3         # [5] oscillator must have been oversold this recently
HTF_SLOPE_BARS = 6     # [5] ADAPTED: 6 bars = 30 min of slope on ema50
MIN_BAR = 6            # skip the first 30 min so every shift(1..5) and every
                       # session-reset window stays inside the same session


# ── helpers ───────────────────────────────────────────────────────────
def _dmi(h: pd.Series, l: pd.Series, c: pd.Series, n: int = 14):
    """Wilder +DI / -DI, identical smoothing to funded_search._adx."""
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    up_m, dn_m = h.diff(), -l.diff()
    plus = np.where((up_m > dn_m) & (up_m > 0), up_m, 0.0)
    minus = np.where((dn_m > up_m) & (dn_m > 0), dn_m, 0.0)
    atr_ = tr.ewm(alpha=1 / n, adjust=False).mean()
    pdi = 100 * pd.Series(plus, index=h.index).ewm(alpha=1 / n, adjust=False).mean() / atr_
    mdi = 100 * pd.Series(minus, index=h.index).ewm(alpha=1 / n, adjust=False).mean() / atr_
    return pdi, mdi


def _sess_rollmax(cond: pd.Series, day, bar_idx: pd.Series, n: int) -> pd.Series:
    """'cond was true at least once in the last n bars', RESET EACH SESSION.

    Strictly causal: the window ends on the current bar.  Before n bars have
    elapsed in the session it degrades to an expanding max from the session
    open (groupby.cummax), never borrowing from the previous session.
    """
    x = cond.astype(float).fillna(0.0)
    full = x.rolling(n, min_periods=1).max()      # exact once n bars into session
    early = x.groupby(day).cummax()               # session-start expanding max
    return pd.Series(np.where(bar_idx >= n - 1, full, early), index=cond.index) > 0


def _resting_stop(setup: pd.Series, level: pd.Series, px: pd.Series,
                  maxk: int, long: bool) -> pd.Series:
    """Fire on the first bar within `maxk` bars of a `setup` bar on which price
    reaches that setup bar's `level` -- i.e. a resting buy/sell stop that stays
    working for maxk bars and is only filled once.

    Causal: only setup.shift(k), level.shift(k) and px.shift(j<k) are read, all
    strictly in the past, plus the current bar's own high/low.
    """
    out = pd.Series(False, index=setup.index)
    for k in range(1, maxk + 1):
        lv = level.shift(k)
        cond = setup.shift(k).fillna(False) & ((px > lv) if long else (px < lv))
        for j in range(1, k):                     # not already filled in between
            pj = px.shift(j)
            cond &= (pj <= lv) if long else (pj >= lv)
        out |= cond.fillna(False)
    return out


def register(df: pd.DataFrame) -> dict:
    o, h, l, c = df["open"], df["high"], df["low"], df["close"]
    vol = df["volume"]
    ema20, ema50 = df["ema20"], df["ema50"]
    adx, K = df["adx"], df["stochK"]
    day = df["_day"]

    bar_idx = df.groupby("_day").cumcount()
    okbar = bar_idx >= MIN_BAR

    up_bar = c > (h + l) / 2.0

    # ── [1] Holy Grail: ADX>30 & rising, first retrace to the 20 MA ──
    # The source's "ADX initially above 30 and rising" describes the SETUP, and
    # notes ADX naturally falls during the retrace.  ADAPTED: the setup stays
    # armed for ADX_HG_LOOKBACK bars after it last printed.
    adx_hot = _sess_rollmax((adx > ADX_HG) & (adx > adx.shift(1)),
                            day, bar_idx, ADX_HG_LOOKBACK)

    # "wait for the FIRST pullback, not the second or third" -> ADAPTED as: the
    # tagging bar is the first bar to reach the MA after price was clear of it.
    up_ctx = (ema20 > ema20.shift(SLOPE_BARS)) & (c > ema50)
    tag_l = (l <= ema20) & (l.shift(1) > ema20.shift(1))
    setup_l = tag_l & adx_hot & up_ctx
    # "place buy order AT the high of the bar that touches the MA" is a resting
    # stop, so it can fill on any of the next few bars, not only the very next
    # one.  The harness fills at the bar CLOSE rather than at the stop price, so
    # the extra (c > ema20) guard drops bars that poked the level and collapsed
    # back under the MA -- those are exactly the fills that would flatter us.
    hg_long = (okbar & _resting_stop(setup_l, h, h, HG_STOP_BARS, long=True)
               & (c > ema20))

    dn_ctx = (ema20 < ema20.shift(SLOPE_BARS)) & (c < ema50)
    tag_s = (h >= ema20) & (h.shift(1) < ema20.shift(1))
    setup_s = tag_s & adx_hot & dn_ctx
    hg_short = (okbar & _resting_stop(setup_s, l, l, HG_STOP_BARS, long=False)
                & (c < ema20))

    # ── [2] TradingSim 20 MA pullback, all four conditions ──
    slope_up = ema20 > ema20.shift(SLOPE_BARS)                    # 1 slope filter
    is_hh = h >= h.rolling(HH_LOOKBACK).max()                     # 20-bar high
    made_hh = _sess_rollmax(is_hh, day, bar_idx, HH_RECENT)       # 2 prior structure
    light_vol = vol < vol.rolling(VOL_MA).mean()                  # 3 lighter pullback vol
    trigger = (l <= ema20) & (c > ema20) & (c > o) & up_bar       # 4 reversal candle at MA
    ma20_pullback = okbar & slope_up & made_hh & light_vol & trigger

    # ── [3] ADX-gated DI continuation ──
    # The source states two things: "enter long when +DI > -DI and ADX > 25",
    # and "ADX must be in the trending zone and moving upward".  ADAPTED: taken
    # literally on a +DI/-DI CROSSOVER bar these are near mutually exclusive --
    # DX collapses toward zero as the DI lines converge, so ADX is falling into
    # every crossover (measured: 8 qualifying bars in 5 years).  The trigger
    # used here is therefore the moment the trend-strength GATE opens -- ADX
    # crossing up through 25 -- with direction already established by
    # +DI leading -DI by the source's 5-point minimum.
    pdi, mdi = _dmi(h, l, c)
    adx_gate_opens = (adx > ADX_DI) & (adx.shift(1) <= ADX_DI)
    adx_di_gate = (okbar & adx_gate_opens & (pdi > mdi)
                   & ((pdi - mdi) >= DI_SPREAD) & up_bar)

    # ── [4] Bollinger BandWidth squeeze -> break of the upper band ──
    mid = (df["bb_up"] + df["bb_dn"]) / 2.0
    bw = 100.0 * (df["bb_up"] - df["bb_dn"]) / mid.replace(0, np.nan)
    squeeze = bw <= bw.rolling(SQUEEZE_WIN).min()                 # lowest of last N
    sq_recent = _sess_rollmax(squeeze, day, bar_idx, SQUEEZE_RECENT)
    band_break = (c > df["bb_up"]) & (c.shift(1) <= df["bb_up"].shift(1))
    squeeze_break = okbar & sq_recent & band_break & (c > ema50)

    # ── [5] Elder Triple Screen (long) ──
    # screen 1 = higher timeframe: daily close above its daily EMA20 (gate_ema20
    # is already shifted one session, so it is known at the open) AND the 4-hour
    # proxy ema50 rising over the last 30 minutes.
    screen1 = df["gate_ema20"].astype(bool) & (ema50 > ema50.shift(HTF_SLOPE_BARS))
    # screen 2 = oscillator oversold against that uptrend, within OSC_RECENT bars
    screen2 = _sess_rollmax(K < STOCH_OS, day, bar_idx, OSC_RECENT)
    # screen 3 = buy stop above the high of the last closed bar
    screen3 = c > h.shift(1)
    triple_screen = okbar & screen1 & screen2 & screen3 & (c > ema20)

    def _b(s):
        return s.reindex(df.index).fillna(False).astype(bool)

    return {
        "mom_holygrail_long":  (_b(hg_long), +1),
        "mom_holygrail_short": (_b(hg_short), -1),
        "mom_ma20_pullback":   (_b(ma20_pullback), +1),
        "mom_adx_di_gate":     (_b(adx_di_gate), +1),
        "mom_squeeze_break":   (_b(squeeze_break), +1),
        "mom_triple_screen":   (_b(triple_screen), +1),
    }

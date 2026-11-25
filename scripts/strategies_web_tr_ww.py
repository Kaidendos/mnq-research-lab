"""J. WELLES WILDER — Parabolic SAR, Directional Movement, Volatility System.

Area: ww.  "New Concepts in Technical Trading Systems" (1978) is the source of
RSI, ATR, ADX/DMI and Parabolic SAR — this project's own ATR sizing is Wilder's.
The book is unusual in that it specifies complete SYSTEMS with exact constants,
not just indicators, so almost nothing here needs interpretation.

RULES, as published
-------------------
https://www.macroption.com/new-concepts-in-technical-trading-systems/
https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-indicators/average-directional-index-adx
  Parabolic SAR: acceleration factor starts at 0.02, increases by 0.02 on each
  new extreme, capped at 0.20. The system is stop-and-reverse: the SAR flip IS
  the entry.
  "When +DI is above -DI, the trend is up; when +DI is below -DI, the trend is
   down. The ADX ... measures the strength of the trend regardless of direction."
  "While describing the PSAR system, he added an alternate way to trade the
   system which is to use the DMI to determine when to trade. For example, if the
   +DI is dominant, then only trade to the up side based on PSAR signals."
  Volatility System: a stop-and-reverse trailing stop set at a multiple (Wilder
  used 3.0) of the Average True Range from the extreme close.

CAUSALITY
---------
The SAR is a forward-recursive calculation — each bar's SAR is computed from the
PREVIOUS bar's SAR, EP and AF — so it is causal by construction, but only if the
loop never reads bar i's high/low when setting bar i's SAR. That is the classic
implementation bug and it is avoided here: `sar[i]` is finalised from state as of
i-1, and bar i's extremes only update the state used for i+1.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

AF_STEP, AF_MAX = 0.02, 0.20      # Wilder's constants
ADX_TREND = 25.0                  # Wilder: ADX above 25 = trending
VOL_MULT, VOL_LEN = 3.0, 7        # Wilder's Volatility System


def _psar(high, low, step=AF_STEP, cap=AF_MAX):
    h, l = high.to_numpy(float), low.to_numpy(float)
    n = len(h)
    sar = np.full(n, np.nan)
    is_long = np.zeros(n, bool)
    if n < 2:
        return pd.Series(sar, index=high.index), pd.Series(is_long, index=high.index)

    long_ = True
    af = step
    ep = h[0]
    cur = l[0]
    for i in range(1, n):
        # SAR for bar i is fixed BEFORE looking at bar i's range
        cur = cur + af * (ep - cur)
        if long_:
            cur = min(cur, l[i - 1], l[max(i - 2, 0)])
        else:
            cur = max(cur, h[i - 1], h[max(i - 2, 0)])
        sar[i] = cur
        is_long[i] = long_
        # now bar i prints and may flip / extend
        if long_:
            if l[i] < cur:
                long_, cur, ep, af = False, ep, l[i], step
            elif h[i] > ep:
                ep, af = h[i], min(af + step, cap)
        else:
            if h[i] > cur:
                long_, cur, ep, af = True, ep, h[i], step
            elif l[i] < ep:
                ep, af = l[i], min(af + step, cap)
    return pd.Series(sar, index=high.index), pd.Series(is_long, index=high.index)


def _dmi(h, l, c, n=14):
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    up_m, dn_m = h.diff(), -l.diff()
    plus = np.where((up_m > dn_m) & (up_m > 0), up_m, 0.0)
    minus = np.where((dn_m > up_m) & (dn_m > 0), dn_m, 0.0)
    atr = tr.ewm(alpha=1 / n, adjust=False).mean()
    pdi = 100 * pd.Series(plus, index=h.index).ewm(alpha=1/n, adjust=False).mean() / atr
    mdi = 100 * pd.Series(minus, index=h.index).ewm(alpha=1/n, adjust=False).mean() / atr
    return pdi, mdi


def register(df: pd.DataFrame) -> dict:
    h, l, c = df["high"], df["low"], df["close"]
    adx = df["adx"]

    sar, sar_long = _psar(h, l)
    flip_up = sar_long & ~sar_long.shift(1).fillna(False).astype(bool)
    flip_dn = ~sar_long & sar_long.shift(1).fillna(True)

    pdi, mdi = _dmi(h, l, c, 14)
    di_up = (pdi > mdi) & (pdi.shift(1) <= mdi.shift(1))
    di_dn = (pdi < mdi) & (pdi.shift(1) >= mdi.shift(1))
    dom_up, dom_dn = pdi > mdi, pdi < mdi
    trending = adx > ADX_TREND

    # ── Volatility System: stop-and-reverse at 3 x ATR(7) from the extreme close ──
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    arc = tr.ewm(alpha=1 / VOL_LEN, adjust=False).mean() * VOL_MULT
    hi_close = c.rolling(VOL_LEN).max().shift(1)
    lo_close = c.rolling(VOL_LEN).min().shift(1)
    vol_long = (c > lo_close + arc) & (c.shift(1) <= lo_close.shift(1) + arc.shift(1))
    vol_short = (c < hi_close - arc) & (c.shift(1) >= hi_close.shift(1) - arc.shift(1))

    return {
        # Parabolic SAR stop-and-reverse, as published
        "ww_psar_long": (flip_up, +1),
        "ww_psar_short": (flip_dn, -1),
        # Wilder's own stated filter: only take SAR signals in the DMI's direction
        "ww_psar_dmi_long": (flip_up & dom_up, +1),
        "ww_psar_dmi_short": (flip_dn & dom_dn, -1),
        # DMI crossover alone
        "ww_dmi_cross_long": (di_up, +1),
        "ww_dmi_cross_short": (di_dn, -1),
        # DMI crossover with the ADX>25 trend filter
        "ww_dmi_adx_long": (di_up & trending, +1),
        "ww_dmi_adx_short": (di_dn & trending, -1),
        # Volatility System
        "ww_volsys_long": (vol_long.fillna(False), +1),
        "ww_volsys_short": (vol_short.fillna(False), -1),
    }

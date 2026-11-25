"""Wave-6: ADX (trend-strength) column for filtering breakouts."""

import numpy as np
import pandas as pd


def enrich5(d):
    d = d.copy()
    h, l = d["high"], d["low"]
    up = h.diff()
    dn = -l.diff()
    plus_dm = np.where((up > dn) & (up > 0), up, 0.0)
    minus_dm = np.where((dn > up) & (dn > 0), dn, 0.0)
    atr = d["atr"].replace(0, np.nan)
    plus_di = 100 * pd.Series(plus_dm, index=d.index).ewm(alpha=1/14, adjust=False).mean() / atr
    minus_di = 100 * pd.Series(minus_dm, index=d.index).ewm(alpha=1/14, adjust=False).mean() / atr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    d["adx"] = dx.ewm(alpha=1/14, adjust=False).mean()
    return d

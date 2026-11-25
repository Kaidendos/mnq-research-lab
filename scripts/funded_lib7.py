"""Wave-8: many more NinjaTrader indicators (new MA types + oscillators)."""

import numpy as np
import pandas as pd


def _wma(s, n):
    w = np.arange(1, n + 1)
    return s.rolling(n).apply(lambda x: np.dot(x, w) / w.sum(), raw=True)


def enrich7(d):
    d = d.copy()
    c, h, l, o, v = d["close"], d["high"], d["low"], d["open"], d["volume"]
    pc = c.shift(1)

    # ---- new MA types, fast (20) + slow (50) for crosses ----
    def ema(n): return c.ewm(span=n, adjust=False).mean()
    for n in (20, 50):
        d[f"dema{n}"] = 2*ema(n) - ema(n).ewm(span=n, adjust=False).mean()
        e1 = ema(n); e2 = e1.ewm(span=n, adjust=False).mean(); e3 = e2.ewm(span=n, adjust=False).mean()
        d[f"tema{n}"] = 3*e1 - 3*e2 + e3
        lag = (n - 1) // 2
        d[f"zlema{n}"] = (c + (c - c.shift(lag))).ewm(span=n, adjust=False).mean()
        d[f"vwma{n}"] = (c*v).rolling(n).sum() / v.rolling(n).sum()
        d[f"hma{n}"] = _wma(2*_wma(c, n//2) - _wma(c, n), int(np.sqrt(n)))
        d[f"wma{n}"] = _wma(c, n)

    # ---- oscillators ----
    # Aroon oscillator (25)
    d["aroon_osc"] = (h.rolling(25).apply(lambda x: x.argmax(), raw=True)
                      - l.rolling(25).apply(lambda x: x.argmin(), raw=True)) * (100/25)
    # TRIX(15)
    e1 = ema(15); e2 = e1.ewm(span=15, adjust=False).mean(); e3 = e2.ewm(span=15, adjust=False).mean()
    d["trix"] = e3.pct_change() * 100
    # StochRSI(14)
    r = d["rsi"]
    d["stochrsi"] = (r - r.rolling(14).min()) / (r.rolling(14).max() - r.rolling(14).min()).replace(0, np.nan)
    # Ultimate Oscillator
    bp = c - pd.concat([l, pc], axis=1).min(axis=1)
    tr = pd.concat([h, pc], axis=1).max(axis=1) - pd.concat([l, pc], axis=1).min(axis=1)
    a7 = bp.rolling(7).sum()/tr.rolling(7).sum()
    a14 = bp.rolling(14).sum()/tr.rolling(14).sum()
    a28 = bp.rolling(28).sum()/tr.rolling(28).sum()
    d["uo"] = 100*(4*a7 + 2*a14 + a28)/7
    # RVI(10)
    num = ((c-o) + 2*(c.shift(1)-o.shift(1)) + 2*(c.shift(2)-o.shift(2)) + (c.shift(3)-o.shift(3)))/6
    den = ((h-l) + 2*(h.shift(1)-l.shift(1)) + 2*(h.shift(2)-l.shift(2)) + (h.shift(3)-l.shift(3)))/6
    rvi = num.rolling(10).mean()/den.rolling(10).mean()
    d["rvi"] = rvi; d["rvi_sig"] = rvi.rolling(4).mean()
    # TSI(25,13)
    m = c.diff()
    ds = m.ewm(span=25, adjust=False).mean().ewm(span=13, adjust=False).mean()
    da = m.abs().ewm(span=25, adjust=False).mean().ewm(span=13, adjust=False).mean()
    d["tsi"] = 100*ds/da.replace(0, np.nan)
    # PPO
    d["ppo"] = (ema(12) - ema(26))/ema(26) * 100
    # Momentum(14)
    d["mom"] = c - c.shift(14)
    # OBV vs EMA
    obv = (np.sign(c.diff()).fillna(0) * v).cumsum()
    d["obv_osc"] = obv - obv.ewm(span=20, adjust=False).mean()
    # Chaikin Money Flow(20)
    mfv = ((2*c - l - h)/(h - l).replace(0, np.nan)) * v
    d["cmf"] = mfv.rolling(20).sum()/v.rolling(20).sum()
    # Disparity(14)
    d["disp"] = 100*(c/c.rolling(14).mean() - 1)
    # Ease of Movement(14)
    dm = ((h+l)/2).diff()
    br = (v/1e6)/(h-l).replace(0, np.nan)
    d["eom"] = (dm/br).rolling(14).mean()
    return d


def sig7(df, name):
    c = df["close"]; pc = c.shift(1)
    # MA-type crosses (fast20 over slow50)
    for t in ("dema", "tema", "zlema", "vwma", "hma", "wma"):
        if name == f"{t}_cross_long":
            f, s = df[f"{t}20"], df[f"{t}50"]
            return (f > s) & (f.shift(1) <= s.shift(1)), +1
    if name == "aroon_osc_long":
        return (df["aroon_osc"] > 0) & (df["aroon_osc"].shift(1) <= 0), +1
    if name == "trix_long":
        return (df["trix"] > 0) & (df["trix"].shift(1) <= 0), +1
    if name == "stochrsi_long":
        return (df["stochrsi"].shift(1) < 0.2) & (df["stochrsi"] >= 0.2), +1
    if name == "uo_long":
        return (df["uo"].shift(1) < 35) & (df["uo"] >= 35), +1
    if name == "rvi_long":
        return (df["rvi"] > df["rvi_sig"]) & (df["rvi"].shift(1) <= df["rvi_sig"].shift(1)), +1
    if name == "tsi_long":
        return (df["tsi"] > 0) & (df["tsi"].shift(1) <= 0), +1
    if name == "ppo_long":
        return (df["ppo"] > 0) & (df["ppo"].shift(1) <= 0), +1
    if name == "mom_long":
        return (df["mom"] > 0) & (df["mom"].shift(1) <= 0) & (c > df["ema50"]), +1
    if name == "obv_long":
        return (df["obv_osc"] > 0) & (df["obv_osc"].shift(1) <= 0) & (c > df["ema50"]), +1
    if name == "cmf_long":
        return (df["cmf"] > 0) & (df["cmf"].shift(1) <= 0), +1
    if name == "disp_long":
        return (df["disp"] > 0) & (df["disp"].shift(1) <= 0) & (c > df["ema50"]), +1
    if name == "eom_long":
        return (df["eom"] > 0) & (df["eom"].shift(1) <= 0), +1
    raise ValueError(name)


FAMILIES7 = ([f"{t}_cross_long" for t in ("dema", "tema", "zlema", "vwma", "hma", "wma")]
             + ["aroon_osc_long", "trix_long", "stochrsi_long", "uo_long", "rvi_long",
                "tsi_long", "ppo_long", "mom_long", "obv_long", "cmf_long", "disp_long", "eom_long"])

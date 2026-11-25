"""Wave-7: 12 genuinely new indicator families (none used before)."""

import numpy as np
import pandas as pd


def enrich6(d):
    d = d.copy()
    h, l, c, o, v = d["high"], d["low"], d["close"], d["open"], d["volume"]
    atr = d["atr"]
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    hv, lv, cv, ov = h.values, l.values, c.values, o.values

    # --- SuperTrend(10,3) ---
    hl2 = (h + l) / 2.0
    bub = (hl2 + 3 * atr).values
    blb = (hl2 - 3 * atr).values
    n = len(d)
    fub = bub.copy(); flb = blb.copy(); stdir = np.ones(n)
    for i in range(1, n):
        fub[i] = bub[i] if (bub[i] < fub[i-1] or cv[i-1] > fub[i-1]) else fub[i-1]
        flb[i] = blb[i] if (blb[i] > flb[i-1] or cv[i-1] < flb[i-1]) else flb[i-1]
        if cv[i] > fub[i-1]:
            stdir[i] = 1
        elif cv[i] < flb[i-1]:
            stdir[i] = -1
        else:
            stdir[i] = stdir[i-1]
    d["st_dir"] = stdir

    # --- Parabolic SAR (0.02, 0.2) ---
    psar = np.zeros(n); bull = True; af = 0.02; ep = lv[0]; sar = lv[0]
    for i in range(1, n):
        sar = sar + af * (ep - sar)
        if bull:
            if lv[i] < sar:
                bull = False; sar = ep; ep = lv[i]; af = 0.02
            else:
                if hv[i] > ep:
                    ep = hv[i]; af = min(af + 0.02, 0.2)
        else:
            if hv[i] > sar:
                bull = True; sar = ep; ep = hv[i]; af = 0.02
            else:
                if lv[i] < ep:
                    ep = lv[i]; af = min(af + 0.02, 0.2)
        psar[i] = 1 if bull else -1
    d["psar_dir"] = psar

    # --- Heikin-Ashi trend ---
    ha_c = (o + h + l + c) / 4.0
    ha_o = np.zeros(n); ha_o[0] = (ov[0] + cv[0]) / 2.0
    hac = ha_c.values
    for i in range(1, n):
        ha_o[i] = (ha_o[i-1] + hac[i-1]) / 2.0
    d["ha_green"] = (ha_c.values > ha_o)

    # --- Awesome Oscillator ---
    med = (h + l) / 2.0
    d["ao"] = med.rolling(5).mean() - med.rolling(34).mean()
    # --- Vortex(14) ---
    d["vi_p"] = (h - l.shift(1)).abs().rolling(14).sum() / tr.rolling(14).sum()
    d["vi_m"] = (l - h.shift(1)).abs().rolling(14).sum() / tr.rolling(14).sum()
    # --- MFI(14) ---
    tp = (h + l + c) / 3.0
    rmf = tp * v
    pos = rmf.where(tp > tp.shift(1), 0.0).rolling(14).sum()
    neg = rmf.where(tp < tp.shift(1), 0.0).rolling(14).sum()
    d["mfi"] = 100 - 100 / (1 + pos / neg.replace(0, np.nan))
    # --- CMO(14) ---
    mom = c.diff()
    su = mom.clip(lower=0).rolling(14).sum(); sd = (-mom.clip(upper=0)).rolling(14).sum()
    d["cmo"] = 100 * (su - sd) / (su + sd).replace(0, np.nan)
    # --- Elder Force Index(13) ---
    d["efi"] = (c.diff() * v).ewm(span=13, adjust=False).mean()
    # --- ROC(10) ---
    d["roc"] = 100 * (c - c.shift(10)) / c.shift(10)
    # --- swing high (5-bar fractal) ---
    d["swing_hi"] = h.rolling(11, center=True).max()
    # --- Fisher Transform(9) ---
    mn = med.rolling(9).min(); mx = med.rolling(9).max()
    raw = (2 * ((med - mn) / (mx - mn).replace(0, np.nan) - 0.5)).fillna(0).values
    val = np.zeros(n); fish = np.zeros(n)
    for i in range(1, n):
        val[i] = 0.33 * raw[i] + 0.67 * val[i-1]
        vv = min(max(val[i], -0.999), 0.999)
        fish[i] = 0.5 * np.log((1 + vv) / (1 - vv)) + 0.5 * fish[i-1]
    d["fisher"] = fish
    return d


def sig6(df, name):
    c, h, l = df["close"], df["high"], df["low"]
    pc = c.shift(1)
    if name == "supertrend_long":
        return (df["st_dir"] == 1) & (df["st_dir"].shift(1) == -1), +1
    if name == "psar_flip_long":
        return (df["psar_dir"] == 1) & (df["psar_dir"].shift(1) == -1), +1
    if name == "heikin_ashi_long":
        return df["ha_green"] & ~df["ha_green"].shift(1).fillna(False), +1
    if name == "ao_cross_long":
        return (df["ao"] > 0) & (df["ao"].shift(1) <= 0), +1
    if name == "vortex_long":
        return (df["vi_p"] > df["vi_m"]) & (df["vi_p"].shift(1) <= df["vi_m"].shift(1)), +1
    if name == "mfi_reclaim_long":
        return (df["mfi"].shift(1) < 20) & (df["mfi"] >= 20), +1
    if name == "cmo_cross_long":
        return (df["cmo"].shift(1) < -50) & (df["cmo"] >= -50), +1
    if name == "efi_zero_long":
        return (df["efi"] > 0) & (df["efi"].shift(1) <= 0), +1
    if name == "roc_zero_long":
        return (df["roc"] > 0) & (df["roc"].shift(1) <= 0) & (c > df["ema50"]), +1
    if name == "swing_break_long":
        return (c > df["swing_hi"].shift(6)) & (pc <= df["swing_hi"].shift(6)), +1
    if name == "fisher_turn_long":
        return (df["fisher"] > df["fisher"].shift(1)) & (df["fisher"].shift(1) <= df["fisher"].shift(2)) & (df["fisher"].shift(1) < 0), +1
    if name == "three_down_fade_long":
        return (c.shift(1) < c.shift(2)) & (c.shift(2) < c.shift(3)) & (c.shift(3) < c.shift(4)) & (c > c.shift(1)), +1
    raise ValueError(name)


FAMILIES6 = ["supertrend_long", "psar_flip_long", "heikin_ashi_long", "ao_cross_long",
             "vortex_long", "mfi_reclaim_long", "cmo_cross_long", "efi_zero_long",
             "roc_zero_long", "swing_break_long", "fisher_turn_long", "three_down_fade_long"]

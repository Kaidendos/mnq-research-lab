"""What has MNQ actually been doing lately, and is it unusual?

Characterises the last 3 months against the prior 5 years on the dimensions that
decide whether a long-only oversold-reclaim strategy can work:
trend, volatility, trend-vs-chop, intraday follow-through, and time-of-day.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import funded_search as fs

df = fs.load_enriched()
end = df.index[-1]
w3 = end - pd.Timedelta(days=90)
w6 = end - pd.Timedelta(days=180)

recent = df[df.index >= w3]
prior6 = df[(df.index >= w6) & (df.index < w3)]
hist = df[df.index < w6]

def daily(d):
    g = d.groupby("_day")
    return pd.DataFrame({
        "open": g["open"].first(), "high": g["high"].max(),
        "low": g["low"].min(), "close": g["close"].last(),
        "atr": g["atr"].mean(), "adx": g["adx"].mean(),
        "vol": g["volume"].sum(),
    })

def describe(d, label):
    dd = daily(d)
    if len(dd) < 5:
        return
    rng = dd["high"] - dd["low"]
    body = (dd["close"] - dd["open"])
    up = (dd["close"] > dd["open"]).mean()
    net = dd["close"].iloc[-1] - dd["open"].iloc[0]
    # intraday follow-through: does the close finish near the extreme it made?
    pos = ((dd["close"] - dd["low"]) / rng.replace(0, np.nan))
    print(f"\n{label}   ({len(dd)} sessions, {d.index[0]:%Y-%m-%d} -> {d.index[-1]:%Y-%m-%d})")
    print(f"  net move            {net:>+10,.0f} pts   ({100*net/dd['open'].iloc[0]:>+6.1f}%)")
    print(f"  green days          {100*up:>10.1f}%")
    print(f"  median daily range  {rng.median():>10.0f} pts")
    print(f"  median 5m ATR       {dd['atr'].median():>10.1f} pts")
    print(f"  median ADX          {dd['adx'].median():>10.1f}      (>25 trending, <20 chop)")
    print(f"  days ADX<20 (chop)  {100*(dd['adx']<20).mean():>10.1f}%")
    print(f"  close-in-range      {100*pos.median():>10.1f}%      (50 = closes mid, >50 closes strong)")
    print(f"  median |body|/range {100*(body.abs()/rng.replace(0,np.nan)).median():>10.1f}%   "
          f"(high = trend days, low = chop)")

print("=" * 78)
print("MNQ REGIME — last 3 months vs the rest of the sample")
print("=" * 78)
describe(recent, "LAST 3 MONTHS")
describe(prior6, "THE 3 MONTHS BEFORE THAT")
describe(hist, "PRIOR ~4.5 YEARS")

# ── does the strategy's own signal behave differently now? ──
print("\n" + "=" * 78)
print("WHAT HAPPENS AFTER THE STRATEGY'S ENTRY SIGNAL FIRES")
print("=" * 78)
for nm in ("stoch30_long",):
    e, side = fs.sig(df, nm)
    e = e.reindex(df.index).fillna(False)
    fwd = {}
    for k in (3, 6, 12):
        fwd[k] = (df["close"].shift(-k) - df["close"]) / df["atr"]
    print(f"\n{nm}: forward move in ATR units after a signal")
    print(f"  {'window':<22}{'n':>7}{'+3 bars':>11}{'+6 bars':>11}{'+12 bars':>11}{'win@+6':>9}")
    for lbl, mask in (("last 3 months", df.index >= w3),
                      ("3-6 months ago", (df.index >= w6) & (df.index < w3)),
                      ("prior 4.5 years", df.index < w6)):
        m = e & mask
        n = int(m.sum())
        if n < 20:
            continue
        vals = [fwd[k][m].median() for k in (3, 6, 12)]
        win = (fwd[6][m] > 0).mean()
        print(f"  {lbl:<22}{n:>7}{vals[0]:>11.3f}{vals[1]:>11.3f}{vals[2]:>11.3f}{100*win:>8.1f}%")

# ── long vs short edge recently ──
print("\n" + "=" * 78)
print("IS THERE A DIRECTIONAL TILT RIGHT NOW?  (median forward 6-bar move, all bars)")
print("=" * 78)
f6 = (df["close"].shift(-6) - df["close"]) / df["atr"]
for lbl, mask in (("last 3 months", df.index >= w3),
                  ("3-6 months ago", (df.index >= w6) & (df.index < w3)),
                  ("prior 4.5 years", df.index < w6)):
    s = f6[mask]
    print(f"  {lbl:<22} median {s.median():>+7.4f} ATR   mean {s.mean():>+7.4f}   "
          f"P(up) {100*(s>0).mean():>5.1f}%")

# ── time of day, last 3 months ──
print("\n" + "=" * 78)
print("TIME OF DAY — median 6-bar forward move by hour (last 3 months vs history)")
print("=" * 78)
print(f"  {'hour ET':<10}{'recent':>12}{'history':>12}{'recent n':>11}")
for hr in range(9, 16):
    mr = (df.index >= w3) & (df.index.hour == hr)
    mh = (df.index < w6) & (df.index.hour == hr)
    if mr.sum() < 20:
        continue
    print(f"  {hr:02d}:00{'':<5}{f6[mr].median():>+12.4f}{f6[mh].median():>+12.4f}{int(mr.sum()):>11}")

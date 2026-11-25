"""Stage 2 of the fold-in: combine the second signals that survived stage 1.

Stage 1 (`foldin_2l2s.py`) added ONE signal at a time to the confirmed base and
found the winners are NOT the ones `speed_test.py` assumed:

    +L ema20_50_long   paid 73.6 -> 84.4,  bust 1.7 -> 0.0,  med $1,503 -> $2,270
    +S lw_oops_short   paid 73.6 -> 75.7,  bust 1.7 -> 0.3,  med $1,503 -> $2,174
    +S pdh_fade_short  paid 73.6 -> 74.0,  bust 1.7 -> 4.5,  med $1,503 -> $1,759

`speed_test.py` used mf_wkpiv_long and lr_raschke_firstcross_short, both of which
are mid-pack here. Its "2L+2S is a free improvement" claim was directionally right
and specifically wrong.

Two things this stage has to establish, because stage 1 cannot:
  1. Do the winners COMBINE, or do they overlap? Adding both could be additive,
     redundant, or actively worse (more signals firing in the same conditions is
     exactly how the 3L+3S speed configs busted at 13.5%).
  2. Is any of this selection-window luck? Stage 1 reported holdout only. Here
     BOTH windows are reported side by side, so a config that only works in one
     is visible immediately.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import funded_search as fs
import funded_1yr as f1
import lucid_fast as LF

BASE_L, BASE_S = "sr_round100_break", "vol_lw_stretch_short"
WIN, SL, TP, RF, MC = (9.75, 11.0), 2.0, 3.0, 1.0, 10

COMBOS = [
    ("BASE 1L+1S",                    [], []),
    ("+L ema20_50",                   ["ema20_50_long"], []),
    ("+S lw_oops",                    [], ["lw_oops_short"]),
    ("+S pdh_fade",                   [], ["pdh_fade_short"]),
    ("2L2S ema+oops",                 ["ema20_50_long"], ["lw_oops_short"]),
    ("2L2S ema+pdh",                  ["ema20_50_long"], ["pdh_fade_short"]),
    ("2L2S ema+turtle_s",             ["ema20_50_long"], ["tt_turtle_s2_short"]),
    ("2L3S ema+oops+pdh",             ["ema20_50_long"], ["lw_oops_short", "pdh_fade_short"]),
    ("3L2S ema+fisher+oops",          ["ema20_50_long", "mf_wkpiv_long"], ["lw_oops_short"]),
    ("3L2S ema+turtle_l+oops",        ["ema20_50_long", "tt_turtle_s2_long"], ["lw_oops_short"]),
    ("SPEEDTEST 2L2S (old guess)",    ["mf_wkpiv_long"], ["lr_raschke_firstcross_short"]),
]

df = fs.load_enriched()
pl = f1.load_plugins(df)
end = df.index[-1]
cut = end - pd.DateOffset(months=5)
SEL, HOLD = df[df.index >= cut], df[df.index < cut]

NAMES = sorted({BASE_L, BASE_S} | {x for _, a, b in COMBOS for x in a + b})


def grab(frame, n):
    e, _ = pl[n] if n in pl else fs.sig(df, n)
    return pd.Series(e).reindex(frame.index).fillna(False).to_numpy(bool)


CACHE = {w: {n: grab(f, n) for n in NAMES} for w, f in (("sel", SEL), ("hold", HOLD))}


def combine(win, names):
    out = np.zeros(len(CACHE[win][BASE_L]), bool)
    for n in names:
        out |= CACHE[win][n]
    return out


def trace(P, start, cap, bud, maxdays=365):
    hi, lo, cl, atr, eth, per = P["hi"], P["lo"], P["cl"], P["atr"], P["eth"], P["per"]
    dates = P["dates"]
    bal, floor, locked = LF.START, LF.START - LF.MLL, False
    cyc_d, cyc_p, cyc_b = 0, 0.0, 0.0
    wd, npay, fd = 0.0, 0, None
    t0 = dates[start]
    for k in range(start, len(per)):
        d = (dates[k] - t0).days
        if d > maxdays:
            break
        s, e, idxs, sides = per[k]
        room = bal - floor
        if room <= 0:
            return dict(fate="BUST", wd=wd, pays=npay, first=fd, final=bal)
        budget = min(bud, room * RF)
        net, ntr, j = 0.0, 0, 0
        while j < len(idxs) and ntr < 6:
            i, sd = idxs[j], int(sides[j])
            a = atr[i]
            n = min(MC, int((budget + net) / (a * SL * LF.PV)),
                    int((cap - net) / (a * TP * LF.PV)))
            if n < 1:
                j += 1; continue
            entry = cl[i]
            slp, tpp = entry - sd * a * SL, entry + sd * a * TP
            px, m = None, i + 1
            while m < e:
                if sd > 0:
                    if lo[m] <= slp: px = slp; break
                    if hi[m] >= tpp: px = tpp; break
                else:
                    if hi[m] >= slp: px = slp; break
                    if lo[m] <= tpp: px = tpp; break
                if eth[m] >= 16.0 or m == e - 1:
                    px = cl[m]; break
                m += 1
            if px is None:
                px, m = cl[e - 1], e - 1
            net += sd * (px - entry) * LF.PV * n - LF.FEE * n
            ntr += 1
            while j < len(idxs) and idxs[j] <= m:
                j += 1
        if ntr == 0:
            continue
        bal += net
        cyc_d += 1; cyc_p += net; cyc_b = max(cyc_b, net)
        if bal <= floor:
            return dict(fate="BUST", wd=wd, pays=npay, first=fd, final=bal)
        if not locked:
            floor = max(floor, bal - LF.MLL)
            if bal >= LF.BUFFER:
                floor, locked = LF.LOCK_FLOOR, True
        if bal > LF.BUFFER and cyc_d >= LF.MIN_DAYS and cyc_p > 0 \
                and cyc_b <= LF.CONSISTENCY * cyc_p:
            amt = min(bal - LF.BUFFER, LF.CAP_FIRST if npay == 0 else LF.CAP_AFTER)
            if amt >= 250:
                bal -= amt; wd += amt; npay += 1
                if fd is None:
                    fd = d
                cyc_d, cyc_p, cyc_b = 0, 0.0, 0.0
    return dict(fate="PAID" if npay else "STALLED", wd=wd, pays=npay, first=fd, final=bal)


def score(win, frame, longs, shorts, cap, bud, horizon):
    P = LF.prep(frame, combine(win, [BASE_L] + longs),
                combine(win, [BASE_S] + shorts), WIN)
    res = [trace(P, k, cap, bud, horizon) for k in range(0, len(P["per"]), 4)
           if len(P["per"]) - k >= 20]
    r = pd.DataFrame(res)
    f = r["first"].dropna()
    return dict(paid=round(100 * (r.fate == "PAID").mean(), 1),
                bust=round(100 * (r.fate == "BUST").mean(), 1),
                mean=round(r.wd.mean()), med=round(r.wd.median()),
                days=int(f.median()) if len(f) else -1)


rows = []
for cap, bud in ((250, 400), (440, 300)):
    for label, longs, shorts in COMBOS:
        h = score("hold", HOLD, longs, shorts, cap, bud, 365)
        s = score("sel", SEL, longs, shorts, cap, bud, 150)
        rows.append(dict(config=label, cap=cap,
                         **{f"hold_{k}": v for k, v in h.items()},
                         **{f"sel_{k}": v for k, v in s.items()}))
        print(f"  {label} cap{cap}", flush=True)

out = pd.DataFrame(rows)
out.to_csv("foldin_combo.csv", index=False)
pd.set_option("display.width", 210)
print("\n" + "=" * 150)
print("COMBINED SECOND SIGNALS — holdout (4.5yr, 1-yr horizon) vs selection (last 5mo, 150d)")
print("=" * 150)
for cap, grp in out.groupby("cap", sort=False):
    print(f"\n  ### cap ${cap}")
    print(grp[["config", "hold_paid", "hold_bust", "hold_mean", "hold_med",
               "hold_days", "sel_paid", "sel_bust", "sel_mean", "sel_med"]]
          .to_string(index=False))

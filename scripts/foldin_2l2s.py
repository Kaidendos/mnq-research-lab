"""FOLD IN THE FREE IMPROVEMENT — which second long and second short to add.

`speed_test.py` found that 2 longs + 2 shorts on the narrow 9:45-11:00 window beat
1L+1S on every axis. It used LONGS[:2] and SHORTS[:2] from a list ordered by
STANDALONE rank. `harvest_tp.py` has since shown standalone rank is a poor guide:
mf_wkpiv_long is the best standalone long in the registry but places 6th of 10 when
paired, losing 91% of 1,080 matched head-to-heads against sr_round100_break.

So the second signal has to be chosen by testing, not inherited. This adds each
candidate ONE AT A TIME to the confirmed base pairing (a paired test — everything
else held fixed) and only then tries the best of each together.

Signals are OR'd: a bar is a long entry if ANY long fires there. Same replay,
same sizing, same account rules as every other run — only the entry set changes.

Holdout only. Both cap configs. 1-year horizon, stride 4.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import funded_search as fs
import funded_1yr as f1
import lucid_fast as LF

BASE_L, BASE_S = "sr_round100_break", "vol_lw_stretch_short"
WIN, SL, TP, RF, MC = (9.75, 11.0), 2.0, 3.0, 1.0, 10

# candidates ranked by PAIRED performance (harvest_tp per-family table), not standalone
ADD_LONGS = ["so_k21_th30", "lr_raschke_anti_long", "ema20_50_long",
             "tt_turtle_s2_long", "mf_wkpiv_long"]
ADD_SHORTS = ["lr_raschke_firstcross_short", "bb_break_short", "pdh_fade_short",
              "lw_oops_short", "tt_turtle_s2_short"]

df = fs.load_enriched()
pl = f1.load_plugins(df)
end = df.index[-1]
hold = df[df.index < end - pd.DateOffset(months=5)]
N = len(hold)


def g(n):
    e, _ = pl[n] if n in pl else fs.sig(df, n)
    return pd.Series(e).reindex(hold.index).fillna(False).to_numpy(bool)


CACHE = {n: g(n) for n in [BASE_L, BASE_S] + ADD_LONGS + ADD_SHORTS}


def combine(names):
    out = np.zeros(N, bool)
    for n in names:
        out |= CACHE[n]
    return out


def trace(P, start, cap, bud, maxdays=365):
    hi, lo, cl, atr, eth, per = P["hi"], P["lo"], P["cl"], P["atr"], P["eth"], P["per"]
    dates = P["dates"]
    bal, floor, locked = LF.START, LF.START - LF.MLL, False
    cyc_d, cyc_p, cyc_b = 0, 0.0, 0.0
    wd, npay, fd, ntr_tot = 0.0, 0, None, 0
    t0 = dates[start]
    for k in range(start, len(per)):
        d = (dates[k] - t0).days
        if d > maxdays:
            break
        s, e, idxs, sides = per[k]
        room = bal - floor
        if room <= 0:
            return dict(fate="BUST", wd=wd, pays=npay, first=fd, final=bal, trades=ntr_tot)
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
        ntr_tot += ntr
        bal += net
        cyc_d += 1; cyc_p += net; cyc_b = max(cyc_b, net)
        if bal <= floor:
            return dict(fate="BUST", wd=wd, pays=npay, first=fd, final=bal, trades=ntr_tot)
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
    return dict(fate="PAID" if npay else "STALLED", wd=wd, pays=npay, first=fd,
                final=bal, trades=ntr_tot)


def score(label, longs, shorts, cap, bud):
    P = LF.prep(hold, combine(longs), combine(shorts), WIN)
    res = [trace(P, k, cap, bud) for k in range(0, len(P["per"]), 4)
           if len(P["per"]) - k >= 30]
    r = pd.DataFrame(res)
    f = r["first"].dropna()
    return dict(config=label, cap=cap, budget=bud, n=len(r),
                paid=round(100 * (r.fate == "PAID").mean(), 1),
                stalled=round(100 * (r.fate == "STALLED").mean(), 1),
                bust=round(100 * (r.fate == "BUST").mean(), 1),
                med_days=int(f.median()) if len(f) else -1,
                p25_days=int(f.quantile(.25)) if len(f) else -1,
                mean_wd=round(r.wd.mean()), med_wd=round(r.wd.median()),
                avg_pays=round(r.pays.mean(), 2),
                trades=round(r.trades.mean()))


rows = []
for cap, bud in ((250, 400), (440, 300)):
    rows.append(score("BASE 1L+1S", [BASE_L], [BASE_S], cap, bud))
    print(f"  base cap{cap} done", flush=True)
    for a in ADD_LONGS:
        rows.append(score(f"+L {a}", [BASE_L, a], [BASE_S], cap, bud))
        print(f"  +L {a} cap{cap}", flush=True)
    for a in ADD_SHORTS:
        rows.append(score(f"+S {a}", [BASE_L], [BASE_S, a], cap, bud))
        print(f"  +S {a} cap{cap}", flush=True)

out = pd.DataFrame(rows)
out.to_csv("foldin_2l2s.csv", index=False)
pd.set_option("display.width", 200)
print("\n" + "=" * 130)
print("PAIRED TEST — add ONE signal to the confirmed base, hold everything else fixed")
print("holdout, 9:45-11:00, SL2.0/TP3.0, rf 1.0, 1-yr horizon")
print("=" * 130)
for (cap, bud), grp in out.groupby(["cap", "budget"], sort=False):
    print(f"\n  ### cap ${cap} / budget ${bud}")
    print(grp[["config", "paid", "stalled", "bust", "p25_days", "med_days",
               "mean_wd", "med_wd", "avg_pays", "trades"]].to_string(index=False))

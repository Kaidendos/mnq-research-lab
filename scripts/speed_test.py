"""How fast can a payout be made without wrecking the outcome?

Speed levers, in order of how much they should matter:
  1. MORE SIGNALS   — run several longs and shorts together. More trades per day
                      means the buffer is reached sooner. Never tested; every run
                      so far used exactly one long and one short.
  2. WIDER WINDOW   — 9:45-15:30 has far more opportunities than 9:45-11:00.
  3. MORE TRADES/DAY — the cap has been 6 throughout.
  4. HIGHER CAP     — known to be faster and worse; included for reference.

Measured on days-to-first-payout AND on whether the account survives to get there.
"""
from __future__ import annotations

import itertools

import numpy as np
import pandas as pd

import funded_search as fs
import funded_1yr as f1
import lucid_fast as LF

df = fs.load_enriched()
pl = f1.load_plugins(df)
g = lambda n: pd.Series((pl[n] if n in pl else fs.sig(df, n))[0]).reindex(df.index).fillna(False).to_numpy(bool)
end = df.index[-1]
hold = df[df.index < end - pd.DateOffset(months=5)]
N = len(hold)

# signal pools, best-first from rank_sides
LONGS = ["sr_round100_break", "mf_wkpiv_long", "tt_turtle_s2_long",
         "so_k21_th30", "ema20_50_long"]
SHORTS = ["vol_lw_stretch_short", "lr_raschke_firstcross_short",
          "bb_break_short", "pdh_fade_short", "mr_rsi2_short"]
LSIG = {n: g(n)[:N] for n in LONGS}
SSIG = {n: g(n)[:N] for n in SHORTS}


def combine(names, pool):
    out = np.zeros(N, bool)
    for n in names:
        out |= pool[n]
    return out


def run(el, es, win, cap, bud, mc, max_tr, maxdays=365, stride=4):
    P = LF.prep(hold, el, es, win)
    hi, lo, cl, atr, eth, per = P["hi"], P["lo"], P["cl"], P["atr"], P["eth"], P["per"]
    dates = P["dates"]
    firsts, paid, stalled, bust, wds, n = [], 0, 0, 0, [], 0
    for start in range(0, len(per), stride):
        if len(per) - start < 30:
            continue
        bal, floor, locked = LF.START, LF.START - LF.MLL, False
        cyc_d, cyc_p, cyc_b = 0, 0.0, 0.0
        wd, np_, fd = 0.0, 0, None
        t0, dead = dates[start], False
        for k in range(start, len(per)):
            d = (dates[k] - t0).days
            if d > maxdays:
                break
            s, e, idxs, sides = per[k]
            room = bal - floor
            if room <= 0:
                bust += 1; dead = True; break
            budget = min(bud, room * 1.0)
            net, ntr, j = 0.0, 0, 0
            while j < len(idxs) and ntr < max_tr:
                i, sd = idxs[j], int(sides[j])
                a = atr[i]
                cts = min(mc, int((budget + net) / (a * 2.0 * LF.PV)),
                          int((cap - net) / (a * 3.0 * LF.PV)))
                if cts < 1:
                    j += 1; continue
                entry = cl[i]
                slp, tpp = entry - sd * a * 2.0, entry + sd * a * 3.0
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
                net += sd * (px - entry) * LF.PV * cts - LF.FEE * cts
                ntr += 1
                while j < len(idxs) and idxs[j] <= m:
                    j += 1
            if ntr == 0:
                continue
            bal += net
            cyc_d += 1; cyc_p += net; cyc_b = max(cyc_b, net)
            if bal <= floor:
                bust += 1; dead = True; break
            if not locked:
                floor = max(floor, bal - LF.MLL)
                if bal >= LF.BUFFER:
                    floor, locked = LF.LOCK_FLOOR, True
            if bal > LF.BUFFER and cyc_d >= LF.MIN_DAYS and cyc_p > 0 \
                    and cyc_b <= LF.CONSISTENCY * cyc_p:
                amt = min(bal - LF.BUFFER, LF.CAP_FIRST if np_ == 0 else LF.CAP_AFTER)
                if amt >= 250:
                    bal -= amt; wd += amt; np_ += 1
                    if fd is None:
                        fd = d
                    cyc_d, cyc_p, cyc_b = 0, 0.0, 0.0
        n += 1
        wds.append(wd)
        if np_:
            paid += 1; firsts.append(fd)
        elif not dead:
            stalled += 1
    if not n:
        return None
    f = np.array(firsts) if firsts else np.array([9999])
    w = np.array(wds)
    return dict(n=n, paid=round(100*paid/n, 1), stalled=round(100*stalled/n, 1),
                bust=round(100*bust/n, 1), med_days=int(np.median(f)),
                p25_days=int(np.percentile(f, 25)),
                by60=round(100*(f <= 60).sum()/n, 1),
                by90=round(100*(f <= 90).sum()/n, 1),
                mean_wd=round(w.mean()), med_wd=round(np.median(w)))


rows = []
CASES = [
    ("1L+1S  9:45-11:00 (current)", 1, 1, (9.75, 11.0), 250, 400, 6),
    ("1L+1S  9:45-15:30 wide",      1, 1, (9.75, 15.5), 250, 400, 6),
    ("2L+2S  9:45-11:00",           2, 2, (9.75, 11.0), 250, 400, 6),
    ("2L+2S  9:45-15:30",           2, 2, (9.75, 15.5), 250, 400, 6),
    ("3L+3S  9:45-15:30",           3, 3, (9.75, 15.5), 250, 400, 6),
    ("5L+5S  9:45-15:30",           5, 5, (9.75, 15.5), 250, 400, 6),
    ("3L+3S wide, 12 trades/day",   3, 3, (9.75, 15.5), 250, 400, 12),
    ("3L+3S wide, cap 440",         3, 3, (9.75, 15.5), 440, 400, 6),
    ("3L+3S wide, cap 440 bud 500", 3, 3, (9.75, 15.5), 440, 500, 6),
    ("5L+5S wide, cap 440, 12/day", 5, 5, (9.75, 15.5), 440, 400, 12),
]
for lbl, nl, ns, win, cap, bud, mt in CASES:
    el = combine(LONGS[:nl], LSIG)
    es = combine(SHORTS[:ns], SSIG)
    r = run(el, es, win, cap, bud, 10, mt)
    if r:
        rows.append(dict(config=lbl, **r))
        print(f"  done {lbl}", flush=True)

out = pd.DataFrame(rows)
out.to_csv("speed_test.csv", index=False)
pd.set_option("display.width", 200)
print("\n" + "=" * 140)
print("SPEED TEST — can a payout come sooner without wrecking the outcome?")
print("=" * 140)
print(out[["config", "paid", "stalled", "bust", "p25_days", "med_days",
           "by60", "by90", "mean_wd", "med_wd"]].to_string(index=False))
print("\n  by60 / by90 = % of ALL accounts with a first payout by day 60 / 90")

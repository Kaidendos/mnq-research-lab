"""Sweep the SIGNALS' OWN CONSTANTS — never once tested in this project.

Both entry rules carry hard-coded numbers that were taken from their source and
never questioned:

    sr_round100_break   ROUND_STEP 100 pts · BREAK_BUF_ATR 0.15 · RVOL > 1.0
                        (RVOL baseline = trailing 20 bars)
    vol_lw_stretch_short LW_K 0.50 of the prior-day range

Every sweep so far varied brackets, windows, caps, budgets, pairings and exit
logic — never these. That matters because the single real improvement ever found in
this project was exactly this shape: `%K 14 -> 21` won 96.2% of 840 matched configs
and 6 of 6 years. Parameter sweeps of an existing rule are also the cheapest kind of
finding to trust, because a PAIRED toggle (change one number, hold everything else)
is immune to the multiple-comparisons problem that killed seven candidates today.

Measured as EDGE OVER THE CLEAN CONTROL x TRADES (total edge), which is the metric
established today as the one the account actually experiences — not net points, and
not edge per trade.

Step 0 validates the re-implementation against the registry plug-in before any
sweeping: if the default parameters do not reproduce the plug-in's fire count
exactly, the sweep is measuring a different signal and nothing it says is usable.
"""
from __future__ import annotations

import itertools

import numpy as np
import pandas as pd

import funded_search as fs
import funded_1yr as f1
import lucid_fast as LF

WIN = (9.75, 11.0)
SL, TP = 2.0, 3.0
SEEDS = 8

df = fs.load_enriched()
pl = f1.load_plugins(df)
end = df.index[-1]
hold = df[df.index < end - pd.DateOffset(months=5)]

H = hold
c, o, h, l, v = H["close"], H["open"], H["high"], H["low"], H["volume"]
day = H["_day"]
atr = H["atr"]
pc = c.shift(1)
bull = c > o
# web_sr.py: `same_day = g == g.shift(1)` — NOT a pdh/pdl validity check. It drops
# the first bar of each session, where `pc = c.shift(1)` would be the PRIOR day's
# close and the round-number "cross" would be a cross of the overnight gap rather
# than an intraday break. Getting this wrong over-fired by 240 bars.
valid_prior = (day == day.shift(1))


def make_long(step=100.0, buf=0.15, rvol_th=1.0, vol_look=20):
    lvl = np.floor(c / step)
    cross_up = lvl > np.floor(pc / step)
    rvol = v / v.rolling(vol_look).mean()
    return (valid_prior & cross_up & (c >= lvl * step + buf * atr)
            & bull & (rvol > rvol_th)).fillna(False).to_numpy(bool)


def make_short(k=0.5):
    sess_open = o.groupby(day).transform("first")
    prev_range = (H["pdh"] - H["pdl"]).abs()
    bar_of_day = H.groupby(day).cumcount()
    gate = sess_open - k * prev_range
    hit = ((c < gate) & (bar_of_day > 0)).fillna(False)
    return (hit & (hit.groupby(day).cumsum() == 1)).to_numpy(bool)


# ── step 0: does the re-implementation match the registry plug-in? ──
def plugin(name):
    e, _ = pl[name] if name in pl else fs.sig(df, name)
    return pd.Series(e).reindex(H.index).fillna(False).to_numpy(bool)


ref_l, ref_s = plugin("sr_round100_break"), plugin("vol_lw_stretch_short")
my_l, my_s = make_long(), make_short()
print("VALIDATION of the re-implementation against the registry plug-ins")
for nm, a, b in (("sr_round100_break", ref_l, my_l),
                 ("vol_lw_stretch_short", ref_s, my_s)):
    agree = int((a == b).sum())
    print(f"  {nm:<24} plugin {int(a.sum()):>5} fires | mine {int(b.sum()):>5} | "
          f"identical bars {agree}/{len(a)} "
          f"({'EXACT MATCH' if agree == len(a) else 'MISMATCH — sweep is unusable'})")
if not (ref_l == my_l).all() or not (ref_s == my_s).all():
    print("\n  Differences found. Reporting them, then continuing with MY version so")
    print("  the sweep is at least internally consistent — but treat absolute levels")
    print("  as not comparable to earlier runs.")
print()

eth = H["eth"].to_numpy(float)
atr_ok = atr.to_numpy(float) > 0
elig = (eth >= WIN[0]) & (eth <= WIN[1]) & atr_ok
d_ids = pd.factorize(day)[0]
starts = np.flatnonzero(np.r_[True, d_ids[1:] != d_ids[:-1]])
ends = np.r_[starts[1:], len(d_ids)]


def points(el, es):
    P = LF.prep(H, el, es, WIN)
    hi_, lo_, cl_, atr_, ethv = P["hi"], P["lo"], P["cl"], P["atr"], P["eth"]
    tot, n = 0.0, 0
    for s, e, idxs, sides in P["per"]:
        j, today = 0, 0
        while j < len(idxs) and today < 6:
            i, sd = idxs[j], int(sides[j])
            a, entry = atr_[i], cl_[i]
            stop_px, targ_px = entry - sd * a * SL, entry + sd * a * TP
            px, m = None, i + 1
            while m < e:
                if sd > 0:
                    if lo_[m] <= stop_px: px = stop_px; break
                    if hi_[m] >= targ_px: px = targ_px; break
                else:
                    if hi_[m] >= stop_px: px = stop_px; break
                    if lo_[m] <= targ_px: px = targ_px; break
                if ethv[m] >= 16.0 or m == e - 1:
                    px = cl_[m]; break
                m += 1
            if px is None:
                px, m = cl_[e - 1], e - 1
            tot += sd * (px - entry); n += 1; today += 1
            while j < len(idxs) and idxs[j] <= m:
                j += 1
    return tot, n


def shuffle(mask, rng):
    prof = [int((mask[s:e] & elig[s:e]).sum()) for s, e in zip(starts, ends)]
    order = rng.permutation(len(prof))
    out = np.zeros(len(mask), bool)
    for pos, (s, e) in enumerate(zip(starts, ends)):
        k = prof[order[pos]]
        if not k:
            continue
        slot = np.flatnonzero(elig[s:e])
        if len(slot):
            out[s + rng.choice(slot, size=min(k, len(slot)), replace=False)] = True
    return out


def score(mask, side):
    zero = np.zeros(len(mask), bool)
    el, es = (mask, zero) if side > 0 else (zero, mask)
    tot, n = points(el, es)
    if n < 30:
        return None
    ctl = []
    for s in range(SEEDS):
        rng = np.random.default_rng(s)
        sh = shuffle(mask, rng)
        sel, ses = (sh, zero) if side > 0 else (zero, sh)
        t2, n2 = points(sel, ses)
        if n2:
            ctl.append(t2 / n2)
    if not ctl:
        return None
    edge = tot / n - float(np.median(ctl))
    return dict(trades=n, ppt=round(tot / n, 2), edge=round(edge, 2),
                total_edge=round(edge * n), beaten=int((np.array(ctl) >= tot / n).sum()))


print("=" * 104)
print("LONG — sr_round100_break, one parameter at a time (others at their defaults)")
print("=" * 104)
rows = []
for name, vals, kw in (("ROUND_STEP", (25.0, 50.0, 100.0, 200.0, 250.0), "step"),
                       ("BREAK_BUF_ATR", (0.0, 0.05, 0.10, 0.15, 0.25, 0.40), "buf"),
                       ("RVOL_THRESH", (0.0, 0.8, 1.0, 1.2, 1.5, 2.0), "rvol_th"),
                       ("VOL_LOOKBACK", (10, 20, 40, 78), "vol_look")):
    print(f"\n  {name}   (default in **bold** conceptually: "
          f"{'100' if kw=='step' else '0.15' if kw=='buf' else '1.0' if kw=='rvol_th' else '20'})")
    print(f"    {'value':>8}{'trades':>8}{'ppt':>8}{'edge':>8}{'TOTAL':>9}{'beaten':>8}")
    for val in vals:
        r = score(make_long(**{kw: val}), +1)
        if r:
            rows.append(dict(param=name, value=val, **r))
            print(f"    {val:>8}{r['trades']:>8}{r['ppt']:>8.2f}{r['edge']:>8.2f}"
                  f"{r['total_edge']:>9}{r['beaten']:>8}")

print("\n" + "=" * 104)
print("SHORT — vol_lw_stretch_short, the stretch fraction LW_K (default 0.50)")
print("=" * 104)
print(f"    {'LW_K':>8}{'trades':>8}{'ppt':>8}{'edge':>8}{'TOTAL':>9}{'beaten':>8}")
for k in (0.25, 0.35, 0.45, 0.50, 0.60, 0.75, 0.90):
    r = score(make_short(k=k), -1)
    if r:
        rows.append(dict(param="LW_K", value=k, **r))
        print(f"    {k:>8}{r['trades']:>8}{r['ppt']:>8.2f}{r['edge']:>8.2f}"
              f"{r['total_edge']:>9}{r['beaten']:>8}")

pd.DataFrame(rows).to_csv("param_sweep.csv", index=False)
print("\n  -> param_sweep.csv")
print("\n  Read TOTAL edge, not ppt. A tighter filter always raises edge per trade")
print("  by trading less; only total edge says whether the account gains.")

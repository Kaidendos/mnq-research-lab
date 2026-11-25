"""End-to-end verification of the FINAL recommended config.

One change was accepted this session — `VOL_LOOKBACK` 20 → 40 — on the strength of
a smooth 2-D surface (19/19 alternatives beat the default) and 36/54 per-year cells.
Before it goes into a live spec it has to clear the same battery the incumbent did,
because a parameter accepted on aggregate statistics can still fail on the specific
questions the user actually asked.

Everything is reported side by side against the current incumbent:

  1. CLEAN CONTROL   the change must not come from trading a worse-timed bar set.
                     This is the test that overturned the whole recommendation
                     earlier today, so the new config gets it too, not a pass.
  2. PER YEAR        6 years at the recommended cell.
  3. ACCOUNT         paid / bust / stalled, mean, median, days, payout distribution.
  4. DAY ONE         worst first day, and the probability of failing in one session.
  5. DOWN $500       the user's actual position: floor pinned at $24,000.
  6. WINDOW          9:45-10:45 scored 4/6 years better with equal mean and lower
                     bust, so the shorter window is tested WITH the new parameter —
                     two marginal positives may or may not combine.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import funded_search as fs
import lucid_fast as LF
import sim_trace as ST
from clean_control import points as cc_points, shuffled

CAP, BUD = 440, 300
YRS = (2021, 2022, 2023, 2024, 2025, 2026)

df = fs.load_enriched()
end = df.index[-1]
cut = end - pd.DateOffset(months=5)


def build(frame, vol_look):
    c, o = frame["close"], frame["open"]
    v, atr, day = frame["volume"], frame["atr"], frame["_day"]
    pc = c.shift(1)
    same = (day == day.shift(1))
    lvl = np.floor(c / 100.0)
    rvol = v / v.rolling(vol_look).mean()
    el = (same & (lvl > np.floor(pc / 100.0)) & (c >= lvl * 100.0 + 0.15 * atr)
          & (c > o) & (rvol > 1.0)).fillna(False).to_numpy(bool)
    so = o.groupby(day).transform("first")
    pr = (frame["pdh"] - frame["pdl"]).abs()
    bod = frame.groupby(day).cumcount()
    hit = ((c < so - 0.5 * pr) & (bod > 0)).fillna(False)
    return el, (hit & (hit.groupby(day).cumsum() == 1)).to_numpy(bool)


CONFIGS = [("INCUMBENT vl20 9:45-11:00", 20, (9.75, 11.0)),
           ("NEW vl40 9:45-11:00", 40, (9.75, 11.0)),
           ("NEW vl40 9:45-10:45", 40, (9.75, 10.75))]

hold = df[df.index < cut]
recent = df[df.index >= cut]

# ── 1. CLEAN CONTROL ──
print("=" * 112)
print("1. CLEAN CONTROL on the holdout — is the new config's edge real, or worse timing?")
print("=" * 112)
d_ids = pd.factorize(hold["_day"])[0]
starts = np.flatnonzero(np.r_[True, d_ids[1:] != d_ids[:-1]])
ends = np.r_[starts[1:], len(d_ids)]
eth = hold["eth"].to_numpy(float)
atr_ok = hold["atr"].to_numpy(float) > 0
for name, vl, win in CONFIGS:
    el, es = build(hold, vl)
    ok = (eth >= win[0]) & (eth <= win[1]) & atr_ok
    ppt, n, w, tot = cc_points(hold, el & ok, es & ok)
    ctl = []
    for s in range(12):
        rng = np.random.default_rng(s)
        a, b = shuffled(starts, ends, ok, el, es, rng, False)
        ctl.append(cc_points(hold, a, b)[0])
    ctl = np.array(ctl)
    print(f"  {name:<28} {n:>4} trades  win {w:>4.1f}%  real {ppt:>+6.2f}  "
          f"ctl {np.median(ctl):>+6.2f}  EDGE {ppt-np.median(ctl):>+6.2f}  "
          f"beaten {int((ctl >= ppt).sum())}/12")

# ── 2-3. ACCOUNT + PER YEAR ──
def acct(frame, vl, win, cap=CAP, bud=BUD, deficit=0.0, horizon=365, stride=4):
    el, es = build(frame, vl)
    P = LF.prep(frame, el, es, win)
    out = []
    for k in range(0, len(P["per"]), stride):
        if len(P["per"]) - k < 20:
            continue
        if deficit:
            import starting_down as SD
            out.append(SD.run(P, k, deficit, bud))
        else:
            out.append(ST.trace(P, k, cap, bud, maxdays=horizon))
    return out


print("\n" + "=" * 112)
print("2. ACCOUNT LEVEL — holdout (1-yr horizon) and the untouched recent 5 months")
print("=" * 112)
print(f"  {'config':<28}{'paid':>7}{'bust':>7}{'stall':>7}{'mean':>9}{'med':>8}"
      f"{'p75':>9}{'days':>6}{'rec_mean':>10}{'rec_paid':>10}")
for name, vl, win in CONFIGS:
    h = ST.summarise(acct(hold, vl, win))
    r = ST.summarise(acct(recent, vl, win))
    print(f"  {name:<28}{h['paid']:>7.1f}{h['bust']:>7.1f}{h['stalled']:>7.1f}"
          f"{h['mean']:>9,.0f}{h['med']:>8,.0f}{h['p75']:>9,.0f}{h['days']:>6}"
          f"{r['mean']:>10,.0f}{r['paid']:>10.1f}")

print("\n" + "=" * 112)
print("3. PER YEAR — mean $ per account at cap440/bud300 (180-day horizon)")
print("=" * 112)
print(f"  {'config':<28}" + "".join(f"{y:>10}" for y in YRS) + f"{'yrs>inc':>9}")
base_y = {}
for name, vl, win in CONFIGS:
    vals, better = [], 0
    for y in YRS:
        sub = df[df.index.year == y]
        if len(sub) < 4000:
            vals.append(0); continue
        m = ST.summarise(acct(sub, vl, win, horizon=180))["mean"]
        vals.append(m)
        if name.startswith("INCUMBENT"):
            base_y[y] = m
        elif m > base_y.get(y, 0):
            better += 1
    tag = f"{'baseline':>9}" if name.startswith("INCUMBENT") else f"{better:>8}/6"
    print(f"  {name:<28}" + "".join(f"{v:>10,.0f}" for v in vals) + tag)

# ── 4. DAY ONE ──
print("\n" + "=" * 112)
print("4. DAY ONE — can it fail in a single session?")
print("=" * 112)
for name, vl, win in CONFIGS:
    el, es = build(df, vl)
    P = LF.prep(df, el, es, win)
    d1 = []
    for k in range(len(P["per"])):
        r = ST.trace(P, k, CAP, BUD, maxdays=0)
        d1.append(r["final"] - LF.START)
    d1 = np.array(d1)
    print(f"  {name:<28} worst first day ${d1.min():>+7,.0f}   "
          f"busted day 1: {int((d1 <= -LF.MLL).sum())}/{len(d1)}   "
          f"no trade {100*(d1 == 0).mean():>4.1f}%   lost >$200 {100*(d1 <= -200).mean():>4.1f}%")

# ── 5. STARTING DOWN $500 ──
print("\n" + "=" * 112)
print("5. STARTING $500 DOWN (floor pinned at $24,000) — the user's actual position")
print("=" * 112)
for name, vl, win in CONFIGS:
    res = acct(hold, vl, win, deficit=500.0)
    r = pd.DataFrame(res)
    f = r["first"].dropna()
    print(f"  {name:<28} paid {100*(r.fate=='PAID').mean():>5.1f}%  "
          f"bust {100*(r.fate=='BUST').mean():>4.1f}%  "
          f"stall {100*(r.fate=='STALLED').mean():>5.1f}%  "
          f"mean ${r.wd.mean():>6,.0f}  med ${r.wd.median():>6,.0f}  "
          f"days {int(f.median()) if len(f) else -1}")

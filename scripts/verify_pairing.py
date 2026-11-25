"""Robustness checks on the surviving two-sided pairing.

It cleared the best-of-grid control. These are the checks that killed earlier
candidates, run before calling it deployable:

  1. YEAR BY YEAR  — does it work in every year, or is it one good period?
  2. SLIPPAGE      — bb_fade_short's test period flipped negative on ONE tick.
                     The harness charges $1.22 RT commission but zero slippage.
  3. SIDE SPLIT    — is the short actually contributing, or is it a long strategy?
  4. EPISODES      — the real sequence of payouts and busts a single account sees.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import funded_search as fs
import funded_1yr as f1
from funded_longshort import replay_2s

LONG, SHORT = "sr_round100_break", "vol_lw_stretch_short"
CFG = dict(sl=1.0, tp=1.5, win=(9.75, 15.5), gate=None, cap=440, budget=300, maxc=10)

df = fs.load_enriched()
plugins = f1.load_plugins(df)


def get(n):
    e, s = plugins[n] if n in plugins else fs.sig(df, n)
    return pd.Series(e).reindex(df.index).fillna(False)


L, S = get(LONG), get(SHORT)
print(f"PAIRING: {LONG} (long) + {SHORT} (short)")
print(f"CONFIG : stop {CFG['sl']}xATR / target {CFG['tp']}xATR, "
      f"{CFG['win'][0]}-{CFG['win'][1]}, cap ${CFG['cap']}, {CFG['maxc']} ct max\n")


def run(d, slip_ticks=0.0):
    # replay_2s owns its own FEE constant, so slippage must be passed in
    # explicitly — patching fs.FEE silently did nothing (bug, now fixed).
    return replay_2s(d, L.reindex(d.index).fillna(False), S.reindex(d.index).fillna(False),
                     CFG["sl"], CFG["tp"], CFG["win"], CFG["gate"],
                     CFG["cap"], CFG["budget"], maxc=CFG["maxc"],
                     slip_ticks=slip_ticks)


print("=" * 92)
print("1. YEAR BY YEAR")
print("=" * 92)
print(f"  {'year':<8}{'sessions':>10}{'trades':>8}{'long':>7}{'short':>7}{'win%':>8}"
      f"{'net $':>11}{'payouts':>9}{'busts':>7}{'bust%':>8}")
allyears = []
for y in sorted(df.index.year.unique()):
    d = df[df.index.year == y]
    daily, tt, ww, nl, ns = run(d)
    if tt == 0:
        continue
    span = (d.index[-1] - d.index[0]).days
    m = f1.score(daily, span)
    allyears.append(m["net"])
    print(f"  {y:<8}{d['_day'].nunique():>10}{tt:>8}{nl:>7}{ns:>7}"
          f"{100*ww/tt:>7.1f}%{daily.sum():>11,.0f}{m['payouts']:>9}{m['busts']:>7}"
          f"{m['bust_pct']:>7.1f}%")
print(f"\n  years net-positive: {sum(1 for v in allyears if v > 0)}/{len(allyears)}")

print("\n" + "=" * 92)
print("2. SLIPPAGE SENSITIVITY  (harness charges $1.22 RT commission, no slippage)")
print("=" * 92)
print(f"  {'extra cost/ct':<16}{'net $':>12}{'payouts':>10}{'busts':>8}{'bust%':>9}{'cal/pay':>10}")
span_all = (df.index[-1] - df.index[0]).days
for extra, lbl in ((0.0, "0 (as tested)"), (1.0, "+1 tick/side"), (2.0, "+2 ticks/side"),
                   (3.0, "+3 ticks/side"), (4.0, "+4 ticks/side")):
    daily, tt, ww, nl, ns = run(df, slip_ticks=extra)
    m = f1.score(daily, span_all)
    print(f"  {lbl:<16}{daily.sum():>12,.0f}{m['payouts']:>10}{m['busts']:>8}"
          f"{m['bust_pct']:>8.1f}%{m['cal_per_payout']:>10}")

print("\n" + "=" * 92)
print("3. DOES THE SHORT ACTUALLY CONTRIBUTE?")
print("=" * 92)
span = (df.index[-1] - df.index[0]).days
empty = pd.Series(False, index=df.index)
for lbl, el, es in (("LONG only", L, empty), ("SHORT only", empty, S), ("BOTH", L, S)):
    daily, tt, ww, nl, ns = replay_2s(df, el.reindex(df.index).fillna(False),
                                      es.reindex(df.index).fillna(False),
                                      CFG["sl"], CFG["tp"], CFG["win"], CFG["gate"],
                                      CFG["cap"], CFG["budget"], maxc=CFG["maxc"])
    m = f1.score(daily, span)
    print(f"  {lbl:<12} trades {tt:>5} ({nl}L/{ns}S) | win {100*ww/tt if tt else 0:>5.1f}% | "
          f"net ${daily.sum():>9,.0f} | payouts {m['payouts']:>3} | bust {m['bust_pct']:>5.1f}% | "
          f"cal/pay {m['cal_per_payout']:>4}")

print("\n" + "=" * 92)
print("4. SEQUENTIAL EPISODES — what one account actually experiences")
print("=" * 92)
daily, tt, ww, nl, ns = run(df)
eps = f1.sequential_episodes(daily)
p = [e for e in eps if e[0] == "payout"]
b = [e for e in eps if e[0] == "bust"]
print(f"  {len(eps)} episodes: {len(p)} PAYOUT / {len(b)} BUST  "
      f"({100*len(b)/len(eps):.1f}% bust)")
cal = [(e[2] - e[1]).days for e in p]
if cal:
    print(f"  calendar days to payout: median {int(np.median(cal))}, "
          f"p90 {int(np.percentile(cal,90))}, worst {max(cal)}")
print(f"\n  {'#':<4}{'outcome':<9}{'start':<13}{'end':<13}{'cal days':>9}")
for i, e in enumerate(eps[:28], 1):
    print(f"  {i:<4}{e[0]:<9}{e[1]:%Y-%m-%d}   {e[2]:%Y-%m-%d}{(e[2]-e[1]).days:>9}")

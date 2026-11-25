"""Would the eval pass again? Sequential, non-overlapping eval attempts.

EVAL RULE (from the strategy header: "Lucid 25K eval goal = $1,250"):
    PASS when cumulative net reaches +$1,250
    FAIL when the trailing drawdown from the running peak is breached
    No 40% consistency rule and no buffer requirement (those are funded-side).

The eval's exact trailing-DD is not in the code, so three values are tested to
bracket it: $1,000 / $1,250 / $1,500. The conclusion is reported per assumption
rather than hidden behind one guess.

Each attempt runs to PASS or FAIL, then a fresh attempt starts the next day —
which is what actually happens when you reset an eval.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import funded_search as fs

WIN = (9.6667, 11.5)
TARGET = 1250.0
CFGS = {
    "EVAL settings  (500/1500/no-stop)":   dict(budget=500, cap=1500, stop_green=False),
    "FUNDED settings (300/440/stop-green)": dict(budget=300, cap=440, stop_green=True),
}

df = fs.load_enriched()
entry, side = fs.sig(df, "stoch30_long")
entry = entry.reindex(df.index).fillna(False)
end = df.index[-1]


def attempts(daily: pd.Series, dd: float):
    """Sequential eval attempts: pass at +TARGET, fail at -dd from peak."""
    vals, idx = daily.values, daily.index
    out, s = [], 0
    while s < len(vals):
        cum = peak = 0.0
        res = None
        for j in range(s, len(vals)):
            cum += vals[j]
            peak = max(peak, cum)
            if peak - cum >= dd:
                res = ("FAIL", j); break
            if cum >= TARGET:
                res = ("PASS", j); break
        if res is None:
            break
        out.append((res[0], idx[s], idx[res[1]], (idx[res[1]] - idx[s]).days))
        s = res[1] + 1
    return out


def series(d, c):
    daily, ntr, nwin = fs.replay(d, entry.reindex(d.index).fillna(False), side,
                                 0.75, 0.5, WIN, None, c["cap"], c["budget"],
                                 stop_green=c["stop_green"], maxc=10)
    return daily


for months, tag in ((12, "LAST 12 MONTHS"), (60, "FULL 5 YEARS")):
    w = end - pd.DateOffset(months=months)
    d = df[df.index >= w]
    print("\n" + "=" * 92)
    print(f"{tag}   ({d.index[0]:%Y-%m-%d} -> {d.index[-1]:%Y-%m-%d})   eval target +${TARGET:,.0f}")
    print("=" * 92)
    print(f"  {'config':<36}{'trailDD':>9}{'attempts':>10}{'PASS':>7}{'FAIL':>7}"
          f"{'pass%':>8}{'med days to pass':>18}")
    for lbl, c in CFGS.items():
        daily = series(d, c)
        for dd in (1000.0, 1250.0, 1500.0):
            a = attempts(daily, dd)
            p = [x for x in a if x[0] == "PASS"]
            f = [x for x in a if x[0] == "FAIL"]
            med = int(np.median([x[3] for x in p])) if p else -1
            print(f"  {lbl:<36}{dd:>9,.0f}{len(a):>10}{len(p):>7}{len(f):>7}"
                  f"{(100*len(p)/len(a) if a else 0):>7.1f}%{med:>18}")

# ── the real question: what happened on the actual attempt, and is it repeatable ──
print("\n" + "=" * 92)
print("THE ACTUAL EVAL WINDOW (2026-07-15 -> 2026-07-23, when the eval account traded)")
print("=" * 92)
seg = df[(df.index >= "2026-07-15") & (df.index <= "2026-07-24")]
for lbl, c in CFGS.items():
    daily = series(seg, c)
    print(f"  {lbl:<36} net ${daily.sum():>8,.0f}  over {len(daily)} traded days")

print("\n" + "=" * 92)
print("EVERY 7-TRADING-DAY WINDOW IN THE LAST YEAR — how often does a lucky start happen?")
print("=" * 92)
w = end - pd.DateOffset(months=12)
d = df[df.index >= w]
for lbl, c in CFGS.items():
    daily = series(d, c)
    roll = daily.rolling(7).sum().dropna()
    print(f"  {lbl}")
    print(f"    7-day windows: {len(roll)} | median ${roll.median():>7,.0f} | "
          f"best ${roll.max():>7,.0f} | worst ${roll.min():>8,.0f}")
    print(f"    windows >= +$1,250 (an instant pass): {int((roll >= TARGET).sum())} "
          f"({100*(roll >= TARGET).mean():.1f}%)")
    print(f"    windows <= -$1,000 (an instant bust): {int((roll <= -1000).sum())} "
          f"({100*(roll <= -1000).mean():.1f}%)")

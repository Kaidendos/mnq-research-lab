"""If I start on a Monday, what is the chance I reach a payout before busting?

Answers it three ways, because they differ and the difference matters:
  1. Every possible start day (what a single fresh attempt faces)
  2. Mondays only (the literal question)
  3. Recent regime only (last 12 months — is it still true now?)

Run for BOTH the live strategy and the verified two-sided pairing.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import funded_search as fs
import funded_1yr as f1
from funded_longshort import replay_2s

TRAIL_DD, BUFFER, CONSIST, MIN_D = 1000.0, 1100.0, 0.40, 3

df = fs.load_enriched()
pl = f1.load_plugins(df)
gs = lambda n: pd.Series((pl[n] if n in pl else fs.sig(df, n))[0]).reindex(df.index).fillna(False)


def live(d):
    e, side = fs.sig(df, "stoch30_long")
    return fs.replay(d, e.reindex(d.index).fillna(False), side, 0.75, 0.5,
                     (9.6667, 11.5), None, 440, 300, maxc=10)[0]


def pairing(d):
    L, S = gs("sr_round100_break"), gs("vol_lw_stretch_short")
    return replay_2s(d, L.reindex(d.index).fillna(False), S.reindex(d.index).fillna(False),
                     1.0, 1.5, (9.75, 15.5), None, 440, 300, maxc=10)[0]


def attempt_from(vals, idx, s, horizon_days=None):
    """One attempt starting at index s. Returns ('payout'|'bust'|'open', cal_days)."""
    cum = peak = biggest = 0.0
    for j in range(s, len(vals)):
        cum += vals[j]
        peak = max(peak, cum)
        biggest = max(biggest, vals[j])
        days = (idx[j] - idx[s]).days
        if horizon_days is not None and days > horizon_days:
            return ("open", days)
        if peak - cum >= TRAIL_DD:
            return ("bust", days)
        if (j - s + 1) >= MIN_D and cum >= BUFFER and biggest <= CONSIST * cum:
            return ("payout", days)
    return ("open", (idx[-1] - idx[s]).days)


def stats(daily, label, mondays_only=False):
    vals, idx = daily.values, daily.index
    starts = range(len(vals))
    if mondays_only:
        starts = [i for i in range(len(vals)) if idx[i].dayofweek == 0]
    res = [attempt_from(vals, idx, s) for s in starts]
    done = [r for r in res if r[0] != "open"]
    if not done:
        print(f"  {label:<34} (no resolved attempts)")
        return
    p = [r for r in done if r[0] == "payout"]
    d30 = [r for r in p if r[1] <= 30]
    d60 = [r for r in p if r[1] <= 60]
    print(f"  {label:<34}{len(done):>8}{100*len(p)/len(done):>10.1f}%"
          f"{100*len(d30)/len(done):>12.1f}%{100*len(d60)/len(done):>12.1f}%"
          f"{int(np.median([r[1] for r in p])) if p else -1:>10}")


end = df.index[-1]
windows = {
    "FULL 5 YEARS": df,
    "LAST 12 MONTHS": df[df.index >= end - pd.DateOffset(months=12)],
    "LAST 5 MONTHS": df[df.index >= end - pd.DateOffset(months=5)],
}

for strat_name, fn in (("LIVE StochReclaim30 (long-only 0.75/0.5)", live),
                       ("TWO-SIDED pairing (round100 + LW stretch)", pairing)):
    print("\n" + "=" * 96)
    print(strat_name)
    print("=" * 96)
    print(f"  {'window':<34}{'attempts':>8}{'PASS%':>10}{'pass<=30d':>12}"
          f"{'pass<=60d':>12}{'med days':>10}")
    for wname, d in windows.items():
        daily = fn(d)
        if len(daily) < 10:
            continue
        stats(daily, wname)
    daily = fn(df)
    stats(daily, "MONDAY STARTS ONLY (5yr)", mondays_only=True)

print("\n" + "=" * 96)
print("NOTE: every start day is counted, so attempts overlap and are correlated.")
print("The sequential non-overlapping figure for the pairing was 54/101 = 53.5% pass.")
print("=" * 96)

"""Withdrawal policy under the CORRECTED LucidPro 25K rules.

Withdrawing the instant you clear the 26,100 buffer nets about 100 dollars and
leaves you sitting on the floor. Waiting to accumulate is both more realistic
and materially safer. This measures how much that choice is worth.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import funded_search as fs
import funded_1yr as f1
import lucid_rules as LR
from funded_longshort import replay_2s

df = fs.load_enriched()
pl = f1.load_plugins(df)
gs = lambda n: pd.Series((pl[n] if n in pl else fs.sig(df, n))[0]).reindex(df.index).fillna(False)


def live(d):
    e, side = fs.sig(df, "stoch30_long")
    return fs.replay(d, e.reindex(d.index).fillna(False), side, 0.75, 0.5,
                     (9.6667, 11.5), None, 440, 300, maxc=10)[0]


def pair(d):
    return replay_2s(d, gs("sr_round100_break").reindex(d.index).fillna(False),
                     gs("vol_lw_stretch_short").reindex(d.index).fillna(False),
                     1.0, 1.5, (9.75, 15.5), None, 440, 300, maxc=10)[0]


print("CORRECTED LucidPro 25K rules — fresh account started on every day, full 5yr")
print("=" * 100)
print(f"{'strategy':<20}{'withdrawal policy':<24}{'bust%':>8}{'>=1 payout':>12}"
      f"{'med days':>10}{'median out':>12}{'mean out':>11}")
print("-" * 100)
for nm, fn in (("LIVE stoch30", live), ("TWO-SIDED pair", pair)):
    daily = fn(df)
    for mw, lbl in ((100, "withdraw ASAP"), (500, "wait for 500"),
                    (1000, "wait for full 1,000")):
        r = LR.rolling_starts(daily, min_withdraw=mw)
        gp = r[r.days_to_first >= 0]
        print(f"{nm:<20}{lbl:<24}{100*r.busted.mean():>7.1f}%"
              f"{100*(r.payouts>=1).mean():>11.1f}%"
              f"{int(gp.days_to_first.median()) if len(gp) else -1:>10}"
              f"{r.withdrawn.median():>12,.0f}{r.withdrawn.mean():>11,.0f}")

print("\n" + "=" * 100)
print("HOW FAR DOES ONE ACCOUNT GET?  (two-sided pairing, wait-for-1,000 policy)")
print("=" * 100)
daily = pair(df)
r = LR.rolling_starts(daily, min_withdraw=1000)
print(f"  accounts simulated              : {len(r):,}")
print(f"  reached the locked floor        : {100*r.locked.mean():>6.1f}%")
print(f"  took at least 1 payout          : {100*(r.payouts>=1).mean():>6.1f}%")
print(f"  took at least 2 payouts         : {100*(r.payouts>=2).mean():>6.1f}%")
print(f"  took at least 3 payouts         : {100*(r.payouts>=3).mean():>6.1f}%")
print(f"  eventually busted               : {100*r.busted.mean():>6.1f}%")
print(f"  mean total withdrawn            : ${r.withdrawn.mean():>8,.0f}")
print(f"  p25 / median / p75 withdrawn    : ${r.withdrawn.quantile(.25):,.0f} / "
      f"${r.withdrawn.median():,.0f} / ${r.withdrawn.quantile(.75):,.0f}")
print(f"  best account                    : ${r.withdrawn.max():>8,.0f}")

print("\n  NOTE: 'eventually busted' is near 100% because each account is run to the")
print("  end of the 5-year data. The economically relevant number is how much was")
print("  withdrawn BEFORE that happened, versus the cost of the account.")

print("\n" + "=" * 100)
print("EXPECTED VALUE PER ACCOUNT vs COST")
print("=" * 100)
mean_out = r.withdrawn.mean()
print(f"  mean withdrawn per account: ${mean_out:,.0f}")
print(f"  {'account cost':<18}{'net per account':>18}{'verdict':>12}")
for cost in (100, 150, 200, 300, 500):
    net = mean_out - cost
    print(f"  ${cost:<17,}{net:>18,.0f}{'PROFIT' if net > 0 else 'LOSS':>12}")

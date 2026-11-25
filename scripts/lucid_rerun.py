"""Re-run both strategies under the CORRECTED LucidPro 25K rules."""
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


def pairing(d):
    L, S = gs("sr_round100_break"), gs("vol_lw_stretch_short")
    return replay_2s(d, L.reindex(d.index).fillna(False), S.reindex(d.index).fillna(False),
                     1.0, 1.5, (9.75, 15.5), None, 440, 300, maxc=10)[0]


for name, fn in (("LIVE StochReclaim30", live), ("TWO-SIDED pairing", pairing)):
    daily = fn(df)
    print("\n" + "=" * 88)
    print(f"{name}   —  CORRECTED LucidPro 25K rules")
    print("=" * 88)

    r = LR.simulate(daily)
    print(f"  ONE continuous account run over the full 5 years:")
    print(f"    busted           : {r['busted']}" + (f" on {r['bust_date']:%Y-%m-%d}" if r['busted'] else ""))
    print(f"    payouts taken    : {r['payouts']}")
    print(f"    total withdrawn  : ${r['withdrawn']:,.0f}")
    print(f"    final balance    : ${r['final']:,.0f}")
    locked = [e for e in r["events"] if e[0] == "LOCKED"]
    print(f"    floor locked     : {'YES on ' + format(locked[0][1], '%Y-%m-%d') if locked else 'NO'}")

    roll = LR.rolling_starts(daily)
    if len(roll):
        print(f"\n  FRESH ACCOUNT STARTED ON ANY DAY  (n={len(roll):,}):")
        print(f"    reached the locked floor (safe) : {100*roll.locked.mean():>5.1f}%")
        print(f"    busted at some point            : {100*roll.busted.mean():>5.1f}%")
        print(f"    got >=1 payout                  : {100*(roll.payouts>=1).mean():>5.1f}%")
        gp = roll[roll.days_to_first >= 0]
        if len(gp):
            print(f"    median days to FIRST payout     : {int(gp.days_to_first.median()):>5}")
            print(f"    within 30 days                  : {100*(gp.days_to_first<=30).mean()*len(gp)/len(roll):>5.1f}%")
        print(f"    median payouts per account      : {int(roll.payouts.median()):>5}")
        print(f"    median withdrawn per account    : ${roll.withdrawn.median():>7,.0f}")

    # horizon-limited: what does the first 90 days look like?
    r90 = LR.rolling_starts(daily, horizon_days=90)
    if len(r90):
        print(f"\n  FIRST 90 DAYS ONLY (n={len(r90):,}):")
        print(f"    busted within 90d               : {100*r90.busted.mean():>5.1f}%")
        print(f"    reached locked floor within 90d : {100*r90.locked.mean():>5.1f}%")
        print(f"    >=1 payout within 90d           : {100*(r90.payouts>=1).mean():>5.1f}%")
        print(f"    median withdrawn in 90d         : ${r90.withdrawn.median():>7,.0f}")

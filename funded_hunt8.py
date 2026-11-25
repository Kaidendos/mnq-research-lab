"""Wave-7 run: 12 new indicator families x profit-cap/loss-budget sweep (the
'change the risk params' the user asked for). Runner exits, gated, morning.
Scored on 5mo + 5yr; report the 10 best."""

import numpy as np
import pandas as pd

import funded_lib as fl
import funded_lib2 as fl2
import funded_lib3 as fl3
import funded_lib6 as fl6
from funded_backtest import payout_sim

MORNING = (9.75, 11.5833)
FIVE_MO = "2026-02-16"
# profit cap + matched loss budget profiles (the varied risk params)
PROFILES = [(300, 200), (440, 300), (660, 450), (880, 600)]


def pay(daily):
    att, dtp, bust, _ = payout_sim(daily)
    if att == 0:
        return (0.0, 0.0, -1, 0)
    return (100*len(dtp)/att, 100*bust/att, int(np.median(dtp)) if dtp else -1, att)


def main():
    print("loading + enriching (wave 7: SuperTrend/PSAR/HA/Vortex/AO/MFI/CMO/EFI/ROC/swing/Fisher)...")
    d = fl6.enrich6(fl3.enrich3(fl2.enrich2(fl.load_enriched())))
    rows = []
    for fam in fl6.FAMILIES6:
        entry, side = fl6.sig6(d, fam)
        for cap, bud in PROFILES:
            dl, nt, nw = fl2.replay_runner(d, entry, +1, 1.0, MORNING, "gate_ema50",
                                           mode="eod", cap=cap, budget=bud)
            if nt == 0 or len(dl) == 0:
                continue
            d5 = dl[dl.index >= FIVE_MO]
            if len(d5) < 5:
                continue
            a5 = pay(d5); ay = pay(dl)
            rows.append(dict(
                strategy=fam.replace("_long", ""), cap=cap, bud=bud, tr=nt,
                wr=round(100*nw/nt), net5mo=int(d5.sum()), pay5mo=round(a5[0]),
                bust5mo=round(a5[1]), med5mo=a5[2], att5mo=a5[3],
                net5yr=int(dl.sum()), pay5yr=round(ay[0]),
                both=round(min(a5[0], ay[0]))))

    res = pd.DataFrame(rows)
    res.to_csv("data/databento/funded_hunt8.csv", index=False)
    pd.set_option("display.width", 200)
    cols = ["strategy", "cap", "bud", "tr", "wr", "net5mo", "pay5mo", "bust5mo",
            "med5mo", "net5yr", "pay5yr", "both"]

    print(f"\n{len(res)} configs tested (12 new indicators x 4 risk profiles).")
    print("=" * 100)
    print("ALL RESULTS (sorted by robustness = min(5mo,5yr) payout%)")
    print("=" * 100)
    print(res.sort_values(["both", "net5yr"], ascending=[False, False])[cols].head(24).to_string(index=False))

    print("\n" + "=" * 100)
    print("THE 10 BEST  (rank = robustness across both windows, then 5yr net $)")
    print("=" * 100)
    top = res[res["att5mo"] >= 12].sort_values(
        ["both", "net5yr"], ascending=[False, False]).head(10)
    print(top[cols].to_string(index=False))


if __name__ == "__main__":
    main()

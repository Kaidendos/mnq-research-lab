"""Funded strategy hunt: ~100 configs across many families, each scored under the
real LucidPro funded rules ($1k trailing DD / $1,100 buffer / 40% consistency /
3-day min), $440 cap + $300 budget + stop-when-green, fees in. Ranked by
robustness = worst of {last-18-months, full-5-years} payout-before-bust, so a
hot-window overfit can't top the board."""

import time
import numpy as np
import pandas as pd

import funded_lib as fl
from funded_backtest import payout_sim

MORNING = (9.75, 11.5833)      # 9:45-11:35 ET
ALLDAY = (9.75, 15.5)          # 9:45-15:30 ET
CUT18 = "2025-01-23"           # last 18 months
MIN_ATT = 25                   # min resolved attempts to trust a payout%

BREAKOUT_ALLDAY = ["donch20_long", "orb30_long", "pdh_break_long", "bb_break_long"]


def build_configs():
    cfgs = []
    for fam in fl.FAMILIES:
        for sl, tp in ((0.75, 0.5), (1.0, 1.0)):
            for gate in (None, "gate_ema50"):
                cfgs.append(dict(fam=fam, sl=sl, tp=tp, win=MORNING,
                                 gate=gate, tag="morn"))
    for fam in BREAKOUT_ALLDAY:
        for gate in (None, "gate_ema50"):
            cfgs.append(dict(fam=fam, sl=1.0, tp=1.5, win=ALLDAY,
                             gate=gate, tag="allday"))
    return cfgs


def score(daily):
    att, dtp, bust, unres = payout_sim(daily)
    if att == 0:
        return dict(att=0, payout=0.0, bust=0.0, med=-1)
    return dict(att=att, payout=100*len(dtp)/att, bust=100*bust/att,
                med=int(np.median(dtp)) if dtp else -1)


def main():
    t0 = time.time()
    print("loading + enriching 5yr data...")
    d = fl.load_enriched()
    print(f"  {len(d):,} RTH bars, {d['_day'].nunique()} sessions "
          f"({time.time()-t0:.0f}s)")

    cfgs = build_configs()
    print(f"testing {len(cfgs)} configs...\n")
    rows = []
    for k, cfg in enumerate(cfgs):
        entry, side = fl.sig(d, cfg["fam"])
        daily, ntr, nwin = fl.replay_sessions(
            d, entry, side, cfg["sl"], cfg["tp"], cfg["win"], cfg["gate"])
        if len(daily) == 0:
            continue
        d18 = daily[daily.index >= CUT18]
        s_full = score(daily)
        s_18 = score(d18)
        # robustness: worst payout across the two windows (need enough attempts)
        rob = min(s_full["payout"], s_18["payout"])
        if s_full["att"] < MIN_ATT or s_18["att"] < MIN_ATT:
            rob = -1
        rows.append(dict(
            name=cfg["fam"], side="L" if side > 0 else "S",
            sltp=f"{cfg['sl']:.2f}/{cfg['tp']:.2f}",
            gate="ema50" if cfg["gate"] else "none", win=cfg["tag"],
            trades=ntr, wr=round(100*nwin/ntr, 1) if ntr else 0,
            net5=int(daily.sum()), avgday=int(daily.mean()),
            worst=int(daily.min()),
            pay5=round(s_full["payout"], 1), bust5=round(s_full["bust"], 1),
            med5=s_full["med"], att5=s_full["att"],
            pay18=round(s_18["payout"], 1), bust18=round(s_18["bust"], 1),
            med18=s_18["med"], att18=s_18["att"],
            robust=round(rob, 1)))
        if (k + 1) % 20 == 0:
            print(f"  ...{k+1}/{len(cfgs)} ({time.time()-t0:.0f}s)")

    res = pd.DataFrame(rows)
    res = res.sort_values(["robust", "pay18", "net5"], ascending=[False, False, False])
    out = "data/databento/funded_hunt_results.csv"
    res.to_csv(out, index=False)

    pd.set_option("display.width", 200, "display.max_columns", 30)
    cols = ["name", "side", "sltp", "gate", "win", "trades", "wr", "net5",
            "worst", "pay18", "bust18", "med18", "pay5", "bust5", "med5", "robust"]
    print("\n" + "=" * 100)
    print("TOP 25 BY ROBUSTNESS (worst of 18mo / 5yr payout-before-bust %)")
    print("net5 = 5yr net $ (fees in) | pay/bust = % of start-days | med = trading days to payout")
    print("=" * 100)
    print(res[cols].head(25).to_string(index=False))

    print("\n" + "=" * 100)
    print("TOP 15 BY LAST-18-MONTHS payout% (current regime, may be overfit)")
    print("=" * 100)
    r18 = res.sort_values(["pay18", "net5"], ascending=[False, False])
    print(r18[cols].head(15).to_string(index=False))

    print("\n" + "=" * 100)
    print("MOST PROFITABLE OVER 5 YEARS (real edge, regime-robust $)")
    print("=" * 100)
    rnet = res.sort_values("net5", ascending=False)
    print(rnet[cols].head(15).to_string(index=False))

    print(f"\nfull results ({len(res)} configs) saved: {out}  ({time.time()-t0:.0f}s)")


if __name__ == "__main__":
    main()

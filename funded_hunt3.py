"""Wave-3 run: new families scored on the LAST 5 MONTHS (current regime) with the
$440 day cap under funded rules. Surface 5 'good' ones; show 5yr for robustness."""

import numpy as np
import pandas as pd

import funded_lib as fl
import funded_lib2 as fl2
import funded_lib3 as fl3
from funded_backtest import payout_sim

MORNING = (9.75, 11.5833)
FIVE_MO = "2026-02-16"          # last ~5 months of the data (ends 2026-07-16)
CUT18 = "2025-01-23"


def pay(daily):
    att, dtp, bust, _ = payout_sim(daily)
    if att == 0:
        return (0.0, 0.0, -1, 0)
    return (100*len(dtp)/att, 100*bust/att, int(np.median(dtp)) if dtp else -1, att)


def main():
    print("loading + enriching (wave 3)...")
    d = fl3.enrich3(fl2.enrich2(fl.load_enriched()))
    rows = []
    for fam in fl3.FAMILIES3:
        entry, side = fl3.sig3(d, fam)
        for sl, tp in ((0.75, 0.5), (1.0, 1.0), (1.0, 1.5)):
            for gate in (None, "gate_ema50"):
                daily, nt, nw = fl.replay_sessions(d, entry, side, sl, tp, MORNING, gate)
                if len(daily) < 5 or nt == 0:
                    continue
                d5 = daily[daily.index >= FIVE_MO]
                if len(d5) < 5:
                    continue
                a5mo = pay(d5)
                a5yr = pay(daily)
                rows.append(dict(
                    name=fam, side="L" if side > 0 else "S",
                    sltp=f"{sl:.2f}/{tp:.2f}", gate="g" if gate else "-",
                    tr5mo=len(d5), net5mo=int(d5.sum()), worst5mo=int(d5.min()),
                    pay5mo=round(a5mo[0]), bust5mo=round(a5mo[1]), med5mo=a5mo[2],
                    att5mo=a5mo[3], net5yr=int(daily.sum()),
                    pay5yr=round(a5yr[0]), bust5yr=round(a5yr[1])))

    res = pd.DataFrame(rows)
    res.to_csv("data/databento/funded_hunt3_results.csv", index=False)
    pd.set_option("display.width", 200, "display.max_columns", 30)

    print("\n" + "=" * 96)
    print("ALL WAVE-3 CONFIGS THAT MADE MONEY ON THE LAST 5 MONTHS (sorted by 5mo payout%)")
    print("net5mo/worst5mo = last-5-months $ | pay/bust5mo = last-5-mo funded survival | 5yr = robustness")
    print("=" * 96)
    prof = res[res["net5mo"] > 0].sort_values(
        ["pay5mo", "net5mo"], ascending=[False, False])
    cols = ["name", "side", "sltp", "gate", "tr5mo", "net5mo", "worst5mo",
            "pay5mo", "bust5mo", "med5mo", "att5mo", "net5yr", "pay5yr"]
    print(prof[cols].head(20).to_string(index=False))

    # 'good' = high recent survival + positive + enough attempts
    good = prof[(prof["pay5mo"] >= 70) & (prof["bust5mo"] <= 30)
                & (prof["att5mo"] >= 15)].copy()
    print("\n" + "=" * 96)
    print(f"THE 5 GOOD ONES  (last-5-mo payout >= 70%, bust <= 30%, >= 15 attempts)")
    print("=" * 96)
    if len(good) >= 5:
        pick = good.sort_values(["pay5mo", "net5mo", "pay5yr"],
                                ascending=[False, False, False]).head(5)
    else:
        print(f"(only {len(good)} met the strict bar; filling from next-best positive configs)")
        pick = prof.sort_values(["pay5mo", "net5mo"], ascending=[False, False]).head(5)
    print(pick[cols].to_string(index=False))
    print(f"\n{len(res)} configs tested, {len(prof)} positive on 5mo, "
          f"{len(good)} cleared the good bar. results saved.")


if __name__ == "__main__":
    main()

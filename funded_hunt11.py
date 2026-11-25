"""Wave-10 run: calendar & time-of-day anomalies, validated train/test.
$440 cap, funded rules. Genuinely different from any price-indicator strategy."""

import numpy as np
import pandas as pd

import funded_lib as fl
import funded_lib2 as fl2
import funded_lib3 as fl3
import funded_lib9 as fl9
from funded_backtest import payout_sim

SPLIT = "2025-01-01"
FIVE_MO = "2026-02-16"


def paypct(daily):
    att, dtp, bust, _ = payout_sim(daily)
    if att < 8:
        return (-1, -1)
    return (100*len(dtp)/att, int(np.median(dtp)) if dtp else -1)


def main():
    print("enriching (calendar/time anomalies)...")
    d = fl9.enrich9(fl3.enrich3(fl2.enrich2(fl.load_enriched())))
    rows = []
    for fam, win in fl9.FAMILIES9:
        entry, side = fl9.sig9(d, fam)
        for exit_kind in ("run", "brk"):
            for gate in ("gate_ema50", None):
                if exit_kind == "run":
                    dl, nt, nw = fl2.replay_runner(d, entry, +1, 1.0, win, gate, "eod", 440, 300)
                else:
                    dl, nt, nw = fl.replay_sessions(d, entry, +1, 1.0, 1.5, win, gate, 440, 300)
                if nt < 40 or len(dl) < 30:
                    continue
                tr = dl[dl.index < SPLIT]; te = dl[dl.index >= SPLIT]
                if len(tr) < 20 or len(te) < 12:
                    continue
                ptr, _ = paypct(tr); pte, mte = paypct(te)
                d5 = dl[dl.index >= FIVE_MO]
                if ptr < 0 or pte < 0:
                    continue
                rows.append(dict(strategy=fam.replace("_long", ""), exit=exit_kind,
                                 gate="g" if gate else "-", tr=nt, wr=round(100*nw/nt),
                                 train_pay=round(ptr), test_pay=round(pte), test_med=mte,
                                 net5mo=int(d5.sum()), net_all=int(dl.sum())))

    res = pd.DataFrame(rows)
    res.to_csv("data/databento/funded_hunt11.csv", index=False)
    pd.set_option("display.width", 200)
    cols = ["strategy", "exit", "gate", "tr", "wr", "train_pay", "test_pay",
            "test_med", "net5mo", "net_all"]
    print(f"\n{len(res)} tradable calendar/time configs.\n")
    print("=" * 88)
    print("ALL, sorted by out-of-sample (TEST) payout%")
    print("=" * 88)
    print(res.sort_values(["test_pay", "net_all"], ascending=[False, False])[cols].head(18).to_string(index=False))
    val = res[(res["train_pay"] >= 55) & (res["test_pay"] >= 55) & (res["net_all"] > 0)]
    print("\n" + "=" * 88)
    print(f"VALIDATED (good on BOTH windows AND positive 5yr): {len(val)} of {len(res)}")
    print("=" * 88)
    print(val.sort_values("test_pay", ascending=False)[cols].to_string(index=False) if len(val)
          else "(NONE of the calendar/time anomalies survived — no durable edge)")


if __name__ == "__main__":
    main()

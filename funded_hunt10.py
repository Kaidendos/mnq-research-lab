"""Wave-9 run: the 10 OHLCV-feasible strategies from the user's list, each x
exits x risk x gate, VALIDATED train(2021-24)/test(2025-26). $440-family caps."""

import numpy as np
import pandas as pd

import funded_lib as fl
import funded_lib2 as fl2
import funded_lib3 as fl3
import funded_lib4 as fl4
import funded_lib8 as fl8
from funded_backtest import payout_sim

SPLIT = "2025-01-01"
RISK = [(300, 200), (440, 300), (660, 450)]


def paypct(daily):
    att, dtp, bust, _ = payout_sim(daily)
    if att < 10:
        return (-1, -1)
    return (100*len(dtp)/att, int(np.median(dtp)) if dtp else -1)


def main():
    print("enriching...")
    d = fl8.enrich8(fl4.enrich4(fl3.enrich3(fl2.enrich2(fl.load_enriched()))))
    rows = []
    for fam, win in fl8.FAMILIES8:
        entry, side = fl8.sig8(d, fam)
        for exit_kind in ("run", "brk"):
            for cap, bud in RISK:
                for gate in ("gate_ema50", None):
                    if exit_kind == "run" and side > 0:
                        dl, nt, nw = fl2.replay_runner(d, entry, +1, 1.0, win, gate, "eod", cap, bud)
                    else:
                        dl, nt, nw = fl.replay_sessions(d, entry, side, 1.0, 1.5, win, gate, cap, bud)
                    if nt < 40 or len(dl) < 30:
                        continue
                    tr = dl[dl.index < SPLIT]; te = dl[dl.index >= SPLIT]
                    if len(tr) < 20 or len(te) < 12:
                        continue
                    ptr, _ = paypct(tr); pte, mte = paypct(te)
                    if ptr < 0 or pte < 0:
                        continue
                    rows.append(dict(strategy=fam.replace("_long", "").replace("_short", "»S"),
                                     exit=exit_kind, cap=cap, gate="g" if gate else "-",
                                     tr=nt, wr=round(100*nw/nt), train_pay=round(ptr),
                                     test_pay=round(pte), test_med=mte,
                                     net_test=int(te.sum()), net_all=int(dl.sum())))

    res = pd.DataFrame(rows)
    res.to_csv("data/databento/funded_hunt10.csv", index=False)
    pd.set_option("display.width", 200)
    cols = ["strategy", "exit", "cap", "gate", "tr", "wr", "train_pay",
            "test_pay", "test_med", "net_test", "net_all"]
    print(f"\n{len(res)} tradable configs from the 10 feasible strategies.\n")
    print("=" * 92)
    print("ALL, sorted by out-of-sample (TEST) payout%")
    print("=" * 92)
    print(res.sort_values(["test_pay", "net_test"], ascending=[False, False])[cols].head(20).to_string(index=False))

    val = res[(res["train_pay"] >= 55) & (res["test_pay"] >= 55)]
    val = val.sort_values(["test_pay", "net_all"], ascending=[False, False])
    print("\n" + "=" * 92)
    print(f"VALIDATED (good on BOTH train & test): {len(val)} of {len(res)}")
    print("=" * 92)
    print(val[cols].to_string(index=False) if len(val) else
          "(NONE of the user's price-action strategies survived out-of-sample validation)")


if __name__ == "__main__":
    main()

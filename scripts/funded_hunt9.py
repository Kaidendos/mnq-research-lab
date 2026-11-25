"""Wave-8: 1000+ configs (new NT indicators + best prior families) x exits x
risk profiles x gate x session, VALIDATED with a train/test split:
  TRAIN = 2021-07..2024-12   TEST = 2025-01..2026-07 (held out).
A config is only 'real' if it survives BOTH. Ranks by out-of-sample (TEST)."""

import time
import numpy as np
import pandas as pd

import funded_lib as fl
import funded_lib2 as fl2
import funded_lib3 as fl3
import funded_lib5 as fl5
import funded_lib6 as fl6
import funded_lib7 as fl7
from funded_backtest import payout_sim

MORNING = (9.75, 11.5833)
ALLDAY = (9.75, 15.5)
SPLIT = "2025-01-01"
RISK = [(300, 200), (440, 300), (660, 450), (880, 600)]


def ema_cross(df, f, s):
    ef = df["close"].ewm(span=f, adjust=False).mean()
    es = df["close"].ewm(span=s, adjust=False).mean()
    return (ef > es) & (ef.shift(1) <= es.shift(1))


def paypct(daily):
    att, dtp, bust, _ = payout_sim(daily)
    if att < 10:
        return (-1, -1, att)
    return (100*len(dtp)/att, int(np.median(dtp)) if dtp else -1, att)


def main():
    t0 = time.time()
    print("enriching (all indicator libs)...")
    d = fl7.enrich7(fl6.enrich6(fl5.enrich5(fl3.enrich3(fl2.enrich2(fl.load_enriched())))))
    print(f"  done ({time.time()-t0:.0f}s). building base signals...")

    bases = {}
    for f, s in ((12, 26), (20, 50), (10, 30), (9, 21)):
        bases[f"ema{f}/{s}"] = ema_cross(d, f, s)
    for nm, fn, key in [("keltner", fl2.sig2, "keltner_break_long"),
                        ("gap_go", fl2.sig2, "gap_go_long"),
                        ("orb15", fl.sig, "orb15_long"), ("donch20", fl.sig, "donch20_long"),
                        ("first_hour", fl3.sig3, "first_hour_break_long"),
                        ("stoch30", fl.sig, "stoch30_long"),
                        ("supertrend", fl6.sig6, "supertrend_long"),
                        ("psar", fl6.sig6, "psar_flip_long"), ("ao", fl6.sig6, "ao_cross_long"),
                        ("fisher", fl6.sig6, "fisher_turn_long"), ("roc", fl6.sig6, "roc_zero_long")]:
        bases[nm] = fn(d, key)[0]
    for fam in fl7.FAMILIES7:
        bases[fam.replace("_long", "")] = fl7.sig7(d, fam)[0]
    print(f"  {len(bases)} base signals.")

    rows = []
    n = 0
    for name, entry in bases.items():
        for exit_kind in ("run", "brk"):
            for cap, bud in RISK:
                for gate in ("gate_ema50", None):
                    for sess, win in (("morn", MORNING), ("all", ALLDAY)):
                        n += 1
                        if exit_kind == "run":
                            dl, nt, nw = fl2.replay_runner(d, entry, +1, 1.0, win, gate, "eod", cap, bud)
                        else:
                            dl, nt, nw = fl.replay_sessions(d, entry, +1, 1.0, 1.5, win, gate, cap, bud)
                        if nt < 40 or len(dl) < 30:
                            continue
                        tr = dl[dl.index < SPLIT]; te = dl[dl.index >= SPLIT]
                        if len(tr) < 20 or len(te) < 15:
                            continue
                        ptr, mtr, atr_ = paypct(tr)
                        pte, mte, ate = paypct(te)
                        if ptr < 0 or pte < 0:
                            continue
                        rows.append(dict(sig=name, exit=exit_kind, cap=cap, bud=bud,
                                         gate="g" if gate else "-", sess=sess, tr=nt,
                                         wr=round(100*nw/nt), train_pay=round(ptr),
                                         test_pay=round(pte), test_med=mte,
                                         net_test=int(te.sum()), net_all=int(dl.sum())))
        if n % 200 < 32:
            print(f"  ...{n} configs ({time.time()-t0:.0f}s)")

    res = pd.DataFrame(rows)
    res.to_csv("data/databento/funded_hunt9.csv", index=False)
    print(f"\n{n} configs generated, {len(res)} tradable. ({time.time()-t0:.0f}s)")

    # VALIDATED = good on BOTH train and test (not overfit)
    val = res[(res["train_pay"] >= 55) & (res["test_pay"] >= 55)].copy()
    val = val.sort_values(["test_pay", "net_test"], ascending=[False, False])
    overfit = res[(res["test_pay"] >= 75) & (res["train_pay"] < 45)]

    pd.set_option("display.width", 200)
    cols = ["sig", "exit", "cap", "bud", "gate", "sess", "tr", "wr",
            "train_pay", "test_pay", "test_med", "net_test", "net_all"]
    print("=" * 100)
    print(f"VALIDATED WINNERS: good on TRAIN (2021-24) AND held-out TEST (2025-26)  [{len(val)} of {len(res)}]")
    print("train_pay/test_pay = % of starts reaching payout | test_med = OOS days-to-payout")
    print("=" * 100)
    print(val[cols].head(15).to_string(index=False) if len(val) else "(NONE survived both — everything was overfit)")
    print(f"\nOverfit trap check: {len(overfit)} configs looked great on TEST (>=75%) "
          f"but FAILED on TRAIN (<45%) — pure data-mining flukes we correctly reject.")


if __name__ == "__main__":
    main()

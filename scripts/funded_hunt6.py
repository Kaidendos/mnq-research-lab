"""Wave-5 run: score the fresh families on the LAST 5 MONTHS, optimized for
5-DAY PAYOUTS — ranked by median trading-days-to-payout among the reliable ones.
Bracket + runner exits. $440 cap, funded rules."""

import numpy as np
import pandas as pd

import funded_lib as fl
import funded_lib2 as fl2
import funded_lib3 as fl3
import funded_lib4 as fl4
from funded_backtest import payout_sim

MORNING = (9.75, 11.5833)
FIVE_MO = "2026-02-16"


def pay(daily):
    att, dtp, bust, _ = payout_sim(daily)
    if att == 0:
        return (0.0, 0.0, -1, 0)
    return (100*len(dtp)/att, 100*bust/att, int(np.median(dtp)) if dtp else -1, att)


def rowfor(name, daily, ntr, nwin):
    if ntr == 0 or len(daily) == 0:
        return None
    d5 = daily[daily.index >= FIVE_MO]
    if len(d5) < 5:
        return None
    a5 = pay(d5); ay = pay(daily)
    return dict(strategy=name, tr5mo=len(d5), wr=round(100*nwin/ntr),
                net5mo=int(d5.sum()), pay5mo=round(a5[0]), bust5mo=round(a5[1]),
                med5mo=a5[2], att5mo=a5[3], pay5yr=round(ay[0]), net5yr=int(daily.sum()))


def main():
    print("loading + enriching (wave 5)...")
    d = fl4.enrich4(fl3.enrich3(fl2.enrich2(fl.load_enriched())))
    rows = []
    for fam in fl4.FAMILIES4:
        entry, side = fl4.sig4(d, fam)
        # bracket exits (tight = fast hit) + runner (bigger green days = fewer days)
        for sl, tp in ((0.75, 0.5), (1.0, 1.0)):
            for gate in (None, "gate_ema50"):
                dl, nt, nw = fl.replay_sessions(d, entry, side, sl, tp, MORNING, gate)
                r = rowfor(f"{fam} {sl}/{tp} {'g' if gate else '-'}", dl, nt, nw)
                if r: rows.append(r)
        for gate in (None, "gate_ema50"):
            dl, nt, nw = fl2.replay_runner(d, entry, +1, 1.0, MORNING, gate, mode="eod")
            r = rowfor(f"{fam} RUN-eod {'g' if gate else '-'}", dl, nt, nw)
            if r: rows.append(r)

    res = pd.DataFrame(rows)
    res.to_csv("data/databento/funded_hunt6.csv", index=False)
    pd.set_option("display.width", 200)
    cols = ["strategy", "tr5mo", "wr", "net5mo", "pay5mo", "bust5mo", "med5mo",
            "att5mo", "pay5yr", "net5yr"]

    print("\n" + "=" * 96)
    print("ALL FRESH FAMILIES — LAST 5 MONTHS (sorted by fastest median days-to-payout)")
    print("med5mo = trading days to reach the $1,100 buffer (want ~5) | pay/bust = funded survival")
    print("=" * 96)
    show = res[res["med5mo"] > 0].sort_values(["med5mo", "pay5mo"], ascending=[True, False])
    print(show[cols].head(18).to_string(index=False))

    print("\n" + "=" * 96)
    print("BEST FOR ~5-DAY PAYOUTS  (reliable: pay5mo >= 65%, bust <= 35%, then fastest)")
    print("=" * 96)
    fast = res[(res["pay5mo"] >= 65) & (res["bust5mo"] <= 35) & (res["att5mo"] >= 12)]
    fast = fast.sort_values(["med5mo", "pay5mo"], ascending=[True, False])
    print(fast[cols].head(8).to_string(index=False) if len(fast) else "(none cleared the reliability bar)")


if __name__ == "__main__":
    main()

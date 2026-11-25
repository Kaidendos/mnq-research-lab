"""Rank strategies by PAST 5 MONTHS funded performance (since 2026-02-16).
$440 cap / $300 budget, funded rules. 5yr net shown only as a fluke-flag."""

import numpy as np
import pandas as pd

import funded_lib as fl
import funded_lib2 as fl2
import funded_lib3 as fl3
import funded_lib4 as fl4
import funded_lib8 as fl8
from funded_backtest import payout_sim

FIVE_MO = "2026-02-16"


def pay(daily):
    att, dtp, bust, _ = payout_sim(daily)
    if att == 0:
        return (0.0, 0.0, -1)
    return (100*len(dtp)/att, 100*bust/att, int(np.median(dtp)) if dtp else -1)


def ema_cross(df, f, s):
    ef = df["close"].ewm(span=f, adjust=False).mean()
    es = df["close"].ewm(span=s, adjust=False).mean()
    return (ef > es) & (ef.shift(1) <= es.shift(1))


def main():
    d = fl8.enrich8(fl4.enrich4(fl3.enrich3(fl2.enrich2(fl.load_enriched()))))
    kelt = fl2.sig2(d, "keltner_break_long")[0]
    ema1226 = ema_cross(d, 12, 26)

    specs = []   # (label, entry, side, win, is_from_list)
    for fam, win in fl8.FAMILIES8:
        e, s = fl8.sig8(d, fam)
        specs.append((fam.replace("_long", "").replace("_short", "-S"), e, s, win, True))
    # known-good references
    specs += [
        ("EMA20/50 (validated)", ema_cross(d, 20, 50), +1, (9.75, 11.5833), False),
        ("Keltner break", kelt, +1, (9.75, 11.5833), False),
        ("Ensemble EMA12/26|Kelt", ema1226 | kelt, +1, (9.75, 11.5833), False),
        ("gap-and-go", fl2.sig2(d, "gap_go_long")[0], +1, (9.75, 11.5833), False),
        ("first-hour break", fl3.sig3(d, "first_hour_break_long")[0], +1, (9.75, 11.5833), False),
    ]

    rows = []
    for label, entry, side, win, from_list in specs:
        if side > 0:
            dl, nt, nw = fl2.replay_runner(d, entry, +1, 1.0, win, "gate_ema50", "eod", 440, 300)
        else:
            dl, nt, nw = fl.replay_sessions(d, entry, side, 1.0, 1.5, win, "gate_ema50", 440, 300)
        if nt == 0 or len(dl) == 0:
            continue
        d5 = dl[dl.index >= FIVE_MO]
        if len(d5) == 0:
            continue
        p = pay(d5)
        rows.append(dict(strategy=label, src="list" if from_list else "known",
                         tr5mo=len(d5), net5mo=int(d5.sum()), pay5mo=round(p[0]),
                         bust5mo=round(p[1]), med5mo=p[2], net5yr=int(dl.sum())))

    res = pd.DataFrame(rows).sort_values("net5mo", ascending=False)
    pd.set_option("display.width", 200)
    print("=" * 92)
    print("RANKED BY PAST 5 MONTHS NET $ (since 2026-02-16) — $440 cap")
    print("net5yr column: POSITIVE = real edge, NEGATIVE = recent fluke that loses long-run")
    print("=" * 92)
    print(res.to_string(index=False))
    res.to_csv("data/databento/funded_5mo.csv", index=False)


if __name__ == "__main__":
    main()

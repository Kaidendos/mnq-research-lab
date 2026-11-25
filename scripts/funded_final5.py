"""Final curation: score the best candidates from all 3 waves on the LAST 5 MONTHS
AND the full 5 YEARS ($440 cap, funded rules), and pick 5 that are good on BOTH
(not overfit to the recent window)."""

import numpy as np
import pandas as pd

import funded_lib as fl
import funded_lib2 as fl2
import funded_lib3 as fl3
from funded_backtest import payout_sim

MORNING = (9.75, 11.5833)
FIVE_MO = "2026-02-16"
CUT18 = "2025-01-23"


def pay(daily):
    att, dtp, bust, _ = payout_sim(daily)
    if att == 0:
        return (0.0, 0.0, -1, 0)
    return (100*len(dtp)/att, 100*bust/att, int(np.median(dtp)) if dtp else -1, att)


def ema_cross(df, f, s):
    ef = df["close"].ewm(span=f, adjust=False).mean()
    es = df["close"].ewm(span=s, adjust=False).mean()
    return (ef > es) & (ef.shift(1) <= es.shift(1))


def score(name, daily, ntr, nwin):
    d5 = daily[daily.index >= FIVE_MO]
    a5 = pay(d5); ay = pay(daily)
    return dict(strategy=name, trades=ntr, wr=round(100*nwin/ntr) if ntr else 0,
                net5mo=int(d5.sum()), pay5mo=round(a5[0]), bust5mo=round(a5[1]),
                med5mo=a5[2], net5yr=int(daily.sum()), pay5yr=round(ay[0]),
                bust5yr=round(ay[1]),
                both=round(min(a5[0], ay[0])))   # good on BOTH windows


def main():
    d = fl3.enrich3(fl2.enrich2(fl.load_enriched()))
    rows = []

    def br(name, entry, side, sl, tp):
        dl, nt, nw = fl.replay_sessions(d, entry, side, sl, tp, MORNING, "gate_ema50")
        rows.append(score(name, dl, nt, nw))

    def run(name, entry, mode):
        dl, nt, nw = fl2.replay_runner(d, entry, +1, 1.0, MORNING, "gate_ema50", mode=mode)
        rows.append(score(name, dl, nt, nw))

    # candidates from all 3 waves (all EMA50-gated, $440 cap)
    br("EMA20/50 cross 1/1  (champion)", ema_cross(d, 20, 50), +1, 1.0, 1.0)
    br("EMA20/50 cross 1/1.5 (bigger TP)", ema_cross(d, 20, 50), +1, 1.0, 1.5)
    run("EMA20/50 cross RUNNER-eod", ema_cross(d, 20, 50), "eod")
    br("gap-and-go long 1/1.5", fl2.sig2(d, "gap_go_long")[0], +1, 1.0, 1.5)
    br("first-hour breakout 1/1.5", fl3.sig3(d, "first_hour_break_long")[0], +1, 1.0, 1.5)
    br("first-hour breakout 1/1", fl3.sig3(d, "first_hour_break_long")[0], +1, 1.0, 1.0)
    br("keltner breakout 1/1", fl2.sig2(d, "keltner_break_long")[0], +1, 1.0, 1.0)
    br("OR-fade short 1/1.5", fl3.sig3(d, "or_fade_short")[0], -1, 1.0, 1.5)
    br("EMA9/21 cross 1/1", ema_cross(d, 9, 21), +1, 1.0, 1.0)
    br("EMA20/40 cross 1/1", ema_cross(d, 20, 40), +1, 1.0, 1.0)

    res = pd.DataFrame(rows).sort_values("both", ascending=False)
    pd.set_option("display.width", 200)
    cols = ["strategy", "trades", "wr", "net5mo", "pay5mo", "bust5mo", "med5mo",
            "net5yr", "pay5yr", "bust5yr", "both"]
    print("=" * 104)
    print("CANDIDATES SCORED ON BOTH WINDOWS ($440 cap, funded rules) — ranked by worst-window payout%")
    print("net5mo/net5yr = $ over that window | pay/bust = funded survival % | both = min(5mo,5yr) payout")
    print("=" * 104)
    print(res[cols].to_string(index=False))

    print("\n" + "=" * 104)
    print("THE 5 GOOD ONES  (best on the last 5 months AND still robust over 5 years)")
    print("=" * 104)
    print(res[cols].head(5).to_string(index=False))
    res.to_csv("data/databento/funded_final5.csv", index=False)


if __name__ == "__main__":
    main()

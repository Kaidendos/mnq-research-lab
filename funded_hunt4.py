"""Net-maximizing wave: hunt 5 MORE good strategies (distinct from the prior 5)
that clear +$4,000 over the 5yr backtest AND survive both windows. $440 cap.
Leans on higher-frequency families + runner-to-EOD exits to lift net $."""

import numpy as np
import pandas as pd

import funded_lib as fl
import funded_lib2 as fl2
import funded_lib3 as fl3
from funded_backtest import payout_sim

MORNING = (9.75, 11.5833)
ALLDAY = (9.75, 15.5)
FIVE_MO = "2026-02-16"
ALREADY = {"EMA20/50 1/1", "EMA20/50 RUN-eod", "EMA20/50 1/1.5",
           "keltner 1/1", "first-hour 1/1.5"}


def pay(daily):
    att, dtp, bust, _ = payout_sim(daily)
    if att == 0:
        return (0.0, 0.0, -1, 0)
    return (100*len(dtp)/att, 100*bust/att, int(np.median(dtp)) if dtp else -1, att)


def ema_cross(df, f, s):
    ef = df["close"].ewm(span=f, adjust=False).mean()
    es = df["close"].ewm(span=s, adjust=False).mean()
    return (ef > es) & (ef.shift(1) <= es.shift(1))


def row(name, daily, ntr, nwin):
    d5 = daily[daily.index >= FIVE_MO]
    a5 = pay(d5); ay = pay(daily)
    return dict(strategy=name, tr=ntr, wr=round(100*nwin/ntr) if ntr else 0,
                net5yr=int(daily.sum()), peryr=int(daily.sum()/5),
                pay5yr=round(ay[0]), bust5yr=round(ay[1]),
                net5mo=int(d5.sum()), pay5mo=round(a5[0]), bust5mo=round(a5[1]),
                med5mo=a5[2])


def main():
    d = fl3.enrich3(fl2.enrich2(fl.load_enriched()))
    rows = []

    def br(name, entry, side, sl, tp, gate="gate_ema50", win=MORNING):
        dl, nt, nw = fl.replay_sessions(d, entry, side, sl, tp, win, gate)
        if nt: rows.append(row(name, dl, nt, nw))

    def run(name, entry, gate="gate_ema50", mode="eod", win=MORNING):
        dl, nt, nw = fl2.replay_runner(d, entry, +1, 1.0, win, gate, mode=mode)
        if nt: rows.append(row(name, dl, nt, nw))

    # more EMA-cross spans, bracket + runner
    for f, s in ((10, 30), (15, 40), (20, 60), (10, 50), (12, 26)):
        br(f"EMA{f}/{s} 1/1.5", ema_cross(d, f, s), +1, 1.0, 1.5)
        run(f"EMA{f}/{s} RUN-eod", ema_cross(d, f, s))
    # runner exits on other families
    run("keltner RUN-eod", fl2.sig2(d, "keltner_break_long")[0])
    run("keltner RUN-eod nogate", fl2.sig2(d, "keltner_break_long")[0], gate=None)
    run("orb15 RUN-eod", fl.sig(d, "orb15_long")[0])
    run("orb30 RUN-eod", fl.sig(d, "orb30_long")[0])
    run("stoch20 RUN-eod", fl.sig(d, "stoch20_long")[0])
    run("donch10 RUN-eod", fl.sig(d, "donch10_long")[0])
    run("first-hour RUN-eod", fl3.sig3(d, "first_hour_break_long")[0])
    run("gap-go RUN-eod nogate", fl2.sig2(d, "gap_go_long")[0], gate=None)
    run("vwap-reclaim RUN-eod", fl.sig(d, "vwap_reclaim_long")[0])
    run("green2-mom RUN-eod", fl2.sig2(d, "green2_mom_long")[0])
    # bracket variants, higher-freq families
    br("keltner 1/1.5", fl2.sig2(d, "keltner_break_long")[0], +1, 1.0, 1.5)
    br("orb15 1/1.5", fl.sig(d, "orb15_long")[0], +1, 1.0, 1.5)
    br("stoch20 1/1", fl.sig(d, "stoch20_long")[0], +1, 1.0, 1.0)
    br("donch20 allday 1/1.5", fl.sig(d, "donch20_long")[0], +1, 1.0, 1.5, win=ALLDAY)

    res = pd.DataFrame(rows)
    res["both"] = res[["pay5yr", "pay5mo"]].min(axis=1)
    res = res.sort_values("net5yr", ascending=False)
    res.to_csv("data/databento/funded_hunt4.csv", index=False)
    pd.set_option("display.width", 210)
    cols = ["strategy", "tr", "wr", "net5yr", "peryr", "pay5yr", "bust5yr",
            "net5mo", "pay5mo", "bust5mo", "med5mo", "both"]
    print("=" * 108)
    print("NET-MAXIMIZING CANDIDATES ($440 cap) — sorted by 5yr net $")
    print("peryr = net5yr/5 (the realistic annual per-account figure) | both = worst-window payout%")
    print("=" * 108)
    print(res[cols].to_string(index=False))

    # 5 more good ones: >= +$4k over 5yr, survive both windows, not already shown
    good = res[(res["net5yr"] >= 4000) & (res["pay5yr"] >= 45)
               & (res["pay5mo"] >= 55)].sort_values("net5yr", ascending=False)
    print("\n" + "=" * 108)
    print("5 MORE GOOD ONES  (>= +$4k over 5yr, survive both windows >=45%/55%)")
    print("=" * 108)
    print(good[cols].head(5).to_string(index=False))


if __name__ == "__main__":
    main()

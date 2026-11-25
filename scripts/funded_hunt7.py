"""Wave-6 run: ensembles (combine proven edges), ADX-filtered breakouts, and
session-window variants. Scored on last 5 months + 5 years. $440 cap."""

import numpy as np
import pandas as pd

import funded_lib as fl
import funded_lib2 as fl2
import funded_lib3 as fl3
import funded_lib5 as fl5
from funded_backtest import payout_sim

MORNING = (9.75, 11.5833)
ALLDAY = (9.75, 15.5)
AFTERNOON = (12.0, 15.5)
FIVE_MO = "2026-02-16"


def pay(daily):
    att, dtp, bust, _ = payout_sim(daily)
    if att == 0:
        return (0.0, 0.0, -1, 0)
    return (100*len(dtp)/att, 100*bust/att, int(np.median(dtp)) if dtp else -1, att)


def ema_cross(df, f, s):
    ef = df["close"].ewm(span=f, adjust=False).mean()
    es = df["close"].ewm(span=s, adjust=False).mean()
    return (ef > es) & (ef.shift(1) <= es.shift(1))


def rowfor(name, daily, ntr, nwin):
    if ntr == 0 or len(daily) == 0:
        return None
    d5 = daily[daily.index >= FIVE_MO]
    if len(d5) < 5:
        return None
    a5 = pay(d5); ay = pay(daily)
    return dict(strategy=name, tr=ntr, wr=round(100*nwin/ntr),
                net5mo=int(d5.sum()), pay5mo=round(a5[0]), bust5mo=round(a5[1]),
                med5mo=a5[2], net5yr=int(daily.sum()), pay5yr=round(ay[0]),
                both=round(min(a5[0], ay[0])))


def main():
    print("loading + enriching (wave 6)...")
    d = fl5.enrich5(fl3.enrich3(fl2.enrich2(fl.load_enriched())))
    ema1226 = ema_cross(d, 12, 26)
    kelt = fl2.sig2(d, "keltner_break_long")[0]
    orb15 = fl.sig(d, "orb15_long")[0]
    donch20 = fl.sig(d, "donch20_long")[0]
    pdh = fl.sig(d, "pdh_break_long")[0]
    adx_ok = d["adx"] > 25

    rows = []

    def run(name, entry, gate, win=MORNING):
        dl, nt, nw = fl2.replay_runner(d, entry, +1, 1.0, win, gate, mode="eod")
        r = rowfor(name, dl, nt, nw)
        if r: rows.append(r)

    # A. ENSEMBLES (trade when EITHER proven edge fires -> more active days)
    run("ENS: EMA12/26 | Keltner", ema1226 | kelt, "gate_ema50")
    run("ENS: EMA12/26 | Keltner (nogate)", ema1226 | kelt, None)
    run("ENS: Keltner | ORB15", kelt | orb15, "gate_ema50")
    run("ENS: EMA | Keltner | ORB15", ema1226 | kelt | orb15, "gate_ema50")
    run("ENS: EMA12/26 | PDH-break", ema1226 | pdh, "gate_ema50")

    # B. ADX-FILTERED breakouts (only in trending conditions)
    run("ADX>25 Keltner", kelt & adx_ok, "gate_ema50")
    run("ADX>25 Keltner (nogate)", kelt & adx_ok, None)
    run("ADX>25 Donch20", donch20 & adx_ok, "gate_ema50")
    run("ADX>25 EMA12/26", ema1226 & adx_ok, "gate_ema50")

    # C. SESSION variants on the robust runners
    run("Keltner runner ALLDAY", kelt, None, ALLDAY)
    run("Keltner runner AFTERNOON", kelt, None, AFTERNOON)
    run("EMA12/26 runner ALLDAY", ema1226, "gate_ema50", ALLDAY)
    run("ORB15 runner ALLDAY", orb15, "gate_ema50", ALLDAY)
    run("ENS EMA|Kelt ALLDAY", ema1226 | kelt, "gate_ema50", ALLDAY)

    res = pd.DataFrame(rows).sort_values(["both", "net5yr"], ascending=[False, False])
    res.to_csv("data/databento/funded_hunt7.csv", index=False)
    pd.set_option("display.width", 200)
    cols = ["strategy", "tr", "wr", "net5mo", "pay5mo", "bust5mo", "med5mo",
            "net5yr", "pay5yr", "both"]
    print("\n" + "=" * 100)
    print("WAVE-6: ENSEMBLES / ADX FILTERS / SESSIONS (sorted by robustness = min(5mo,5yr) payout%)")
    print("=" * 100)
    print(res[cols].to_string(index=False))

    print("\n" + "=" * 100)
    print("BEST NEW ONES vs the current bar (Keltner runner: 80% recent / +$7.5k 5yr)")
    print("=" * 100)
    good = res[(res["net5yr"] >= 6000) & (res["pay5mo"] >= 70) & (res["both"] >= 45)]
    print(good[cols].to_string(index=False) if len(good) else "(none clearly beat the existing Keltner/EMA runners)")


if __name__ == "__main__":
    main()

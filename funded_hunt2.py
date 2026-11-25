"""Wave-2 run: new families (bracket exits) + runner/trailing exits on the best
families + a profit-cap frontier on the EMA20/50 champion (the real money lever)."""

import numpy as np
import pandas as pd

import funded_lib as fl
import funded_lib2 as fl2
from funded_backtest import payout_sim

MORNING = (9.75, 11.5833)
ALLDAY = (9.75, 15.5)
CUT18 = "2025-01-23"


def pay(daily):
    att, dtp, bust, _ = payout_sim(daily)
    if att == 0:
        return (0.0, 0.0, -1, 0)
    return (100*len(dtp)/att, 100*bust/att, int(np.median(dtp)) if dtp else -1, att)


def scoreline(name, daily, ntr, nwin):
    if len(daily) < 20 or ntr == 0:
        return None
    a18 = pay(daily[daily.index >= CUT18]); a5 = pay(daily)
    rob = min(a18[0], a5[0]) if (a18[3] >= 25 and a5[3] >= 25) else -1
    return dict(name=name, tr=ntr, wr=round(100*nwin/ntr), net5=int(daily.sum()),
                worst=int(daily.min()), p18=round(a18[0]), b18=round(a18[1]),
                p5=round(a5[0]), b5=round(a5[1]), med5=a5[2], robust=round(rob))


def ema_cross(df, fast, slow):
    ef = df["close"].ewm(span=fast, adjust=False).mean()
    es = df["close"].ewm(span=slow, adjust=False).mean()
    return (ef > es) & (ef.shift(1) <= es.shift(1))


def main():
    print("loading + enriching (wave 2)...")
    d = fl2.enrich2(fl.load_enriched())
    rows = []

    print("A. NEW FAMILIES (bracket exits, morning, gate on/off)...")
    for fam in fl2.FAMILIES2:
        entry, side = fl2.sig2(d, fam)
        for sl, tp in ((0.75, 0.5), (1.0, 1.0), (1.0, 1.5)):
            for gate in (None, "gate_ema50"):
                daily, nt, nw = fl.replay_sessions(d, entry, side, sl, tp, MORNING, gate)
                r = scoreline(f"{fam} {sl}/{tp} {'g' if gate else '-'}", daily, nt, nw)
                if r:
                    rows.append(r)

    print("B. RUNNER / TRAILING exits (ride trend days toward $440 cap)...")
    runner_cands = {
        "EMA20/50cross": ema_cross(d, 20, 50),
        "rsi2_dip": fl2.sig2(d, "rsi2_dip_long")[0],
        "keltner_break": fl2.sig2(d, "keltner_break_long")[0],
        "green2_mom": fl2.sig2(d, "green2_mom_long")[0],
        "gap_go": fl2.sig2(d, "gap_go_long")[0],
    }
    for nm, entry in runner_cands.items():
        for mode in ("eod", "trail"):
            for gate in (None, "gate_ema50"):
                daily, nt, nw = fl2.replay_runner(d, entry, +1, 1.0, MORNING, gate, mode=mode)
                r = scoreline(f"{nm} RUN-{mode} {'g' if gate else '-'}", daily, nt, nw)
                if r:
                    rows.append(r)

    res = pd.DataFrame(rows).sort_values(["robust", "p18", "net5"],
                                         ascending=[False, False, False])
    res.to_csv("data/databento/funded_hunt2_results.csv", index=False)
    pd.set_option("display.width", 200)
    print("\n" + "=" * 92)
    print("WAVE-2 TOP 22 BY ROBUSTNESS (new families + runner exits)")
    print("=" * 92)
    print(res.head(22).to_string(index=False))

    # C. profit-cap frontier on the champion — the real 'more money' lever
    print("\n" + "=" * 92)
    print("C. CAP FRONTIER — EMA20/50 champion, gate, 1/1 ATR, varying $ cap & budget")
    print("   (bigger cap = bigger payouts, but bigger red days on the $1k DD)")
    print("=" * 92)
    champ = ema_cross(d, 20, 50)
    print(f"{'cap':>5}{'budget':>7}{'net5':>9}{'/yr':>7}{'worst':>7}"
          f"{'p18':>6}{'b18':>6}{'p5':>6}{'b5':>6}{'med5':>6}")
    for cap, bud in ((440, 300), (660, 450), (880, 600), (1100, 750), (1500, 1000)):
        daily, nt, nw = fl.replay_sessions(d, champ, +1, 1.0, 1.0, MORNING,
                                           "gate_ema50", cap=cap, budget=bud)
        a18 = pay(daily[daily.index >= CUT18]); a5 = pay(daily)
        yrs = daily.index.year.nunique()
        print(f"{cap:>5}{bud:>7}{daily.sum():>+9,.0f}{daily.sum()/yrs:>+7,.0f}"
              f"{daily.min():>+7,.0f}{a18[0]:>6.0f}{a18[1]:>6.0f}"
              f"{a5[0]:>6.0f}{a5[1]:>6.0f}{a5[2]:>6}")


if __name__ == "__main__":
    main()

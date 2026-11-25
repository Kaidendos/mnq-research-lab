"""The best PAYOUT strategy under a hard $440 cap: rank the real strategies by
payout speed + reliability, and detail the winner (5mo + 5yr + monthly)."""

import numpy as np
import pandas as pd

import funded_lib as fl
import funded_lib2 as fl2
import funded_lib3 as fl3
from funded_backtest import payout_sim

FIVE_MO = "2026-02-16"
BUFFER, TRAIL = 1100, 1000
MORNING = (9.75, 11.5833)
ALLDAY = (9.75, 15.5)


def ema_cross(df, f, s):
    ef = df["close"].ewm(span=f, adjust=False).mean()
    es = df["close"].ewm(span=s, adjust=False).mean()
    return (ef > es) & (ef.shift(1) <= es.shift(1))


def cal(sub):
    v = sub.values; days = []; bust = 0; att = 0
    for s in range(len(v)):
        cum = peak = 0.0; out = None
        for j in range(s, len(v)):
            cum += v[j]; peak = max(peak, cum)
            if peak - cum >= TRAIL: out = "bust"; break
            if cum >= BUFFER: out = j - s + 1; break
        if out is None: continue
        att += 1; bust += (out == "bust")
        if out != "bust": days.append(out)
    return (100*len(days)/att if att else 0, 100*bust/att if att else 0,
            int(np.median(days)) if days else -1)


def main():
    d = fl3.enrich3(fl2.enrich2(fl.load_enriched()))
    sessions = d.index.normalize().unique().sort_values()
    kelt = fl2.sig2(d, "keltner_break_long")[0]
    e1226 = ema_cross(d, 12, 26)
    e2050 = ema_cross(d, 20, 50)

    cands = {
        "Ensemble EMA|Kelt ALL-DAY": (e1226 | kelt, ALLDAY),
        "Ensemble EMA|Kelt morning": (e1226 | kelt, MORNING),
        "Keltner ALL-DAY": (kelt, ALLDAY),
        "Keltner morning": (kelt, MORNING),
        "EMA20/50 morning": (e2050, MORNING),
    }
    print("=" * 92)
    print("BEST PAYOUT STRATEGY @ $440 CAP — ranked by calendar days to payout (past 5 months)")
    print("=" * 92)
    print(f"{'strategy':30}{'reach%':>8}{'bust%':>7}{'cal-days':>10}{'~weeks':>8}{'net5mo':>9}{'net5yr':>9}")
    rows = []
    for name, (sig, win) in cands.items():
        daily = fl2.replay_runner(d, sig, +1, 1.0, win, "gate_ema50", "eod", 440, 300)[0]
        full = daily.reindex(sessions).fillna(0.0)
        reach, bust, med = cal(full[full.index >= FIVE_MO])
        n5 = int(daily[daily.index >= FIVE_MO].sum()); ny = int(daily.sum())
        rows.append((med, name, reach, bust, n5, ny, daily))
    for med, name, reach, bust, n5, ny, _ in sorted(rows):
        print(f"{name:30}{reach:>7.0f}%{bust:>6.0f}%{med:>10}{med/5:>8.1f}{n5:>+9,d}{ny:>+9,d}")

    # detail the winner (fastest reliable)
    best = min(rows, key=lambda r: (r[0], -r[2]))
    print("\n" + "=" * 92)
    print(f"WINNER: {best[1]}  — monthly net (recent):")
    print("=" * 92)
    dl = best[6]
    m = dl.groupby(dl.index.to_period("M")).sum()
    for p in ["2025-11", "2025-12", "2026-01", "2026-02", "2026-03", "2026-04",
              "2026-05", "2026-06", "2026-07"]:
        v = m.get(pd.Period(p, "M"), None)
        print(f"  {p}: " + (f"{v:+,.0f}" if v is not None else "(no trades)"))


if __name__ == "__main__":
    main()

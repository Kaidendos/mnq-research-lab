"""For the REAL (validated) strategies: how many CALENDAR trading days to a
$1,100 payout, and how many accounts you'd need running in parallel to collect
a payout ~every week. Past 5 months, $440 cap, funded rules."""

import numpy as np
import pandas as pd

import funded_lib as fl
import funded_lib2 as fl2
import funded_lib3 as fl3
import funded_lib4 as fl4
import funded_lib8 as fl8

FIVE_MO = "2026-02-16"
BUFFER, TRAIL = 1100, 1000


def ema_cross(df, f, s):
    ef = df["close"].ewm(span=f, adjust=False).mean()
    es = df["close"].ewm(span=s, adjust=False).mean()
    return (ef > es) & (ef.shift(1) <= es.shift(1))


def calendar_sim(full_daily):
    v = full_daily.values
    days = []; bust = 0; att = 0
    for s in range(len(v)):
        cum = peak = 0.0; out = None
        for j in range(s, len(v)):
            cum += v[j]; peak = max(peak, cum)
            if peak - cum >= TRAIL:
                out = "bust"; break
            if cum >= BUFFER:
                out = j - s + 1; break
        if out is None:
            continue
        att += 1
        if out == "bust":
            bust += 1
        else:
            days.append(out)
    return att, days, bust


def main():
    d = fl8.enrich8(fl4.enrich4(fl3.enrich3(fl2.enrich2(fl.load_enriched()))))
    sessions = d.index.normalize().unique().sort_values()
    kelt = fl2.sig2(d, "keltner_break_long")[0]
    ema1226 = ema_cross(d, 12, 26)

    reals = {
        "Keltner break": fl2.replay_runner(d, kelt, +1, 1.0, (9.75, 11.5833), "gate_ema50", "eod", 440, 300)[0],
        "Ensemble EMA12/26|Kelt": fl2.replay_runner(d, ema1226 | kelt, +1, 1.0, (9.75, 11.5833), "gate_ema50", "eod", 440, 300)[0],
        "Lunchtime BB rev": fl2.replay_runner(d, fl8.sig8(d, "lunch_bb_long")[0], +1, 1.0, (11.5, 13.5), "gate_ema50", "eod", 440, 300)[0],
        "First-hour break": fl2.replay_runner(d, fl3.sig3(d, "first_hour_break_long")[0], +1, 1.0, (9.75, 11.5833), "gate_ema50", "eod", 440, 300)[0],
        "EMA20/50": fl2.replay_runner(d, ema_cross(d, 20, 50), +1, 1.0, (9.75, 11.5833), "gate_ema50", "eod", 440, 300)[0],
    }

    print("=" * 90)
    print("PAST 5 MONTHS — calendar days to a $1,100 payout, and accounts needed for WEEKLY")
    print("=" * 90)
    print(f"{'strategy':26}{'reach%':>8}{'med days':>10}{'~weeks':>8}{'accts/weekly':>14}")
    print("-" * 90)
    out = []
    for name, daily in reals.items():
        full = daily.reindex(sessions).fillna(0.0)
        sub = full[full.index >= FIVE_MO]
        att, days, bust = calendar_sim(sub)
        if att == 0 or not days:
            print(f"{name:26}{'n/a':>8}"); continue
        med = int(np.median(days)); wk = med / 5
        accts = max(1, round(med / 5))
        out.append((name, 100*len(days)/att, med, wk, accts))
    for name, reach, med, wk, accts in sorted(out, key=lambda x: x[2]):
        print(f"{name:26}{reach:>7.0f}%{med:>10}{wk:>8.1f}{accts:>14}")
    print("-" * 90)
    print("accts/weekly = accounts run in parallel (staggered) so a payout lands ~every 5 days")


if __name__ == "__main__":
    main()

"""HONEST time-to-payout: count CALENDAR trading sessions (including no-trade
days) from start to the $1,100 buffer, not just active-trade days. Also report
what fraction reach payout vs bust. Top strategies, 5mo + 5yr. $440 cap."""

import numpy as np
import pandas as pd

import funded_lib as fl
import funded_lib2 as fl2
import funded_lib3 as fl3
import funded_lib5 as fl5

MORNING = (9.75, 11.5833)
FIVE_MO = "2026-02-16"
BUFFER, TRAIL = 1100, 1000


def ema_cross(df, f, s):
    ef = df["close"].ewm(span=f, adjust=False).mean()
    es = df["close"].ewm(span=s, adjust=False).mean()
    return (ef > es) & (ef.shift(1) <= es.shift(1))


def calendar_sim(full_daily):
    """full_daily = P&L reindexed onto EVERY session (0 on no-trade days).
    Count sessions elapsed to reach +$1,100 before the -$1,000 trailing DD."""
    v = full_daily.values
    days = []; bust = 0; att = 0
    for s in range(len(v)):
        cum = peak = 0.0; out = None
        for j in range(s, len(v)):
            cum += v[j]; peak = max(peak, cum)
            if peak - cum >= TRAIL:
                out = "bust"; break
            if cum >= BUFFER:
                out = j - s + 1; break   # calendar sessions incl. no-trade days
        if out is None:
            continue
        att += 1
        if out == "bust":
            bust += 1
        else:
            days.append(out)
    return att, days, bust


def report(name, daily, sessions):
    full = daily.reindex(sessions).fillna(0.0)
    for label, sub in (("5mo", full[full.index >= FIVE_MO]), ("5yr", full)):
        att, days, bust = calendar_sim(sub)
        if att == 0:
            print(f"  {name:26} {label}: no resolved attempts"); continue
        pr = 100*len(days)/att
        med = int(np.median(days)) if days else -1
        p90 = int(np.percentile(days, 90)) if days else -1
        print(f"  {name:26} {label}: reach payout {pr:3.0f}% | "
              f"CALENDAR days-to-payout median {med}, p90 {p90} "
              f"(~{med/5:.1f} weeks) | bust {100*bust/att:.0f}%")


def main():
    d = fl5.enrich5(fl3.enrich3(fl2.enrich2(fl.load_enriched())))
    sessions = d.index.normalize().unique().sort_values()   # tz-aware, aligns with daily
    ema1226 = ema_cross(d, 12, 26)
    kelt = fl2.sig2(d, "keltner_break_long")[0]

    ens = fl2.replay_runner(d, ema1226 | kelt, +1, 1.0, MORNING, "gate_ema50", mode="eod")[0]
    champ = fl.replay_sessions(d, ema_cross(d, 20, 50), +1, 1.0, 1.0, MORNING, "gate_ema50")[0]
    keltrun = fl2.replay_runner(d, kelt, +1, 1.0, MORNING, None, mode="eod")[0]

    print("=" * 92)
    print("HONEST CALENDAR TIME-TO-PAYOUT (counts every trading session, not just trade days)")
    print("=" * 92)
    report("Ensemble EMA12/26|Keltner", ens, sessions)
    report("EMA20/50 champion", champ, sessions)
    report("Keltner runner", keltrun, sessions)
    print("\nreality: a $1,100 payout takes WEEKS of trading sessions, not ~5 calendar days.")
    print("no strategy on a $440-cap / $1k-DD account reaches payout in 5 calendar days.")


if __name__ == "__main__":
    main()

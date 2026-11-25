"""Distribution of calendar-days-to-payout for the best robust config (E3
ensemble, morning, $440 cap). Shows that ~2-week payouts DO happen (best case)
but the typical/median is longer — reconciling the user's live experience."""

import numpy as np
import pandas as pd

import funded_lib as fl
import funded_lib2 as fl2
import funded_lib3 as fl3

BUFFER, TRAIL = 1100, 1000
MORN = (9.75, 11.5833)


def ema_cross(df, f, s):
    ef = df["close"].ewm(span=f, adjust=False).mean()
    es = df["close"].ewm(span=s, adjust=False).mean()
    return (ef > es) & (ef.shift(1) <= es.shift(1))


def dist(sub):
    v = sub.values; days = []
    for s in range(len(v)):
        cum = peak = 0.0
        for j in range(s, len(v)):
            cum += v[j]; peak = max(peak, cum)
            if peak - cum >= TRAIL: break
            if cum >= BUFFER: days.append(j - s + 1); break
    return np.array(days)


def main():
    d = fl3.enrich3(fl2.enrich2(fl.load_enriched()))
    sess = d.index.normalize().unique().sort_values()
    sig = ema_cross(d, 12, 26) | fl2.sig2(d, "keltner_break_long")[0] | fl.sig(d, "orb15_long")[0]
    daily = fl2.replay_runner(d, sig, +1, 1.0, MORN, "gate_ema50", "eod", 440, 300)[0]
    full = daily.reindex(sess).fillna(0.0)

    print("=" * 82)
    print("E3 ensemble @ $440 — calendar days to $1,100 payout: full DISTRIBUTION")
    print("=" * 82)
    for label, sub in (("Last 5 months", full[full.index >= "2026-02-16"]),
                       ("Full 5 years", full)):
        ds = dist(sub)
        if len(ds) == 0:
            print(f"{label}: no payouts"); continue
        print(f"\n{label}  ({len(ds)} payout runs):")
        print(f"  FASTEST (best case) : {ds.min():>3} days  (~{ds.min()/5:.1f} weeks)")
        print(f"  25th pct            : {int(np.percentile(ds,25)):>3} days  (~{np.percentile(ds,25)/5:.1f} weeks)")
        print(f"  MEDIAN (typical)    : {int(np.median(ds)):>3} days  (~{np.median(ds)/5:.1f} weeks)")
        print(f"  75th pct            : {int(np.percentile(ds,75)):>3} days  (~{np.percentile(ds,75)/5:.1f} weeks)")
        print(f"  SLOWEST (p90)       : {int(np.percentile(ds,90)):>3} days  (~{np.percentile(ds,90)/5:.1f} weeks)")
        two_wk = 100 * (ds <= 10).mean()
        print(f"  % that paid out in <= 2 weeks (10 days): {two_wk:.0f}%")


if __name__ == "__main__":
    main()

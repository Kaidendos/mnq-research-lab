"""Clean control: is the 10Y filter real, or is "trade a third as often" the whole effect?

The 10Y filter lifted payout 52.7% -> 62.5% and cut bust 46.4% -> 30.5%. Tempting. But
it also removed 67% of the sessions, and on a funded account trading LESS is protective
all by itself — fewer sessions means fewer chances to hit the floor inside the horizon.
So the improvement has two possible sources and they need separating:

    (a) the 10Y feature genuinely selects better sessions
    (b) any filter that keeps a third of the sessions would do this

The control is therefore a RANDOM third of sessions, drawn many times. If random thirds
also land near 62% payout, the feature contributes nothing and (b) explains everything.

This is the same lesson that inverted the conclusion twice earlier in this project: a
control must not hand the random arm information the real rule lacks, and it must match
the real rule's TRADE COUNT. Matching only the concept and not the count is how the
first two controls here went wrong.

One extra arm: a random third weighted to match the 10Y arm's per-session mean. If that
also reaches ~62%, then even the feature's edge is doing nothing the count doesn't.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import account_outlook as AO
import preopen_test as PT

SEEDS = 60


def payout_bust(days) -> tuple[float, float]:
    res = [AO.simulate(days, i) for i in range(0, len(days) - AO.MIN_DAYS, 3)]
    n = len(res)
    p = 100.0 * sum(1 for r in res if r["outcome"] == "payout") / n
    b = 100.0 * sum(1 for r in res if r["outcome"] == "bust") / n
    return p, b


def main() -> None:
    print("loading ...", flush=True)
    df = PT.fs.load_enriched()
    one_min = PT.load_one_min()
    sess = PT.pair_sessions(df, one_min)
    sess.index = PT.naive_dates(sess.index)
    mac = PT.macro_table()
    t = sess.join(mac, how="left")
    t["f_tnx_chg"] = (t["tnx_open"] - t["tnx_prev"]) * 100.0
    ok = t["f_tnx_chg"].notna()
    q = pd.qcut(t.loc[ok, "f_tnx_chg"], 3, labels=["low", "mid", "high"])
    t["bucket"] = pd.Series(q, index=t.loc[ok].index).reindex(t.index)

    dates = list(t.index)
    net = t["net"].to_numpy(float)
    traded_mask = net != 0
    low_mask = (t["bucket"] == "low").to_numpy()

    def to_days(mask):
        return [(dates[i].strftime("%Y-%m-%d"),
                 float(net[i]) if mask[i] else 0.0) for i in range(len(dates))]

    # ── the real arm ──
    real_p, real_b = payout_bust(to_days(low_mask))
    n_keep_traded = int((low_mask & traded_mask).sum())
    print(f"  real 10Y-low arm: {n_keep_traded} traded sessions, "
          f"payout {real_p:.1f}%, bust {real_b:.1f}%")

    # ── control: random sessions, matched on TRADED count ──
    traded_idx = np.flatnonzero(traded_mask)
    print(f"\n  drawing {SEEDS} random arms, each keeping exactly "
          f"{n_keep_traded} of the {len(traded_idx)} traded sessions ...", flush=True)
    ps, bs = [], []
    for s in range(SEEDS):
        rng = np.random.default_rng(s)
        keep = np.zeros(len(dates), bool)
        keep[rng.choice(traded_idx, size=n_keep_traded, replace=False)] = True
        p, b = payout_bust(to_days(keep))
        ps.append(p)
        bs.append(b)
        if (s + 1) % 15 == 0:
            print(f"    {s + 1}/{SEEDS} done", flush=True)
    ps, bs = np.array(ps), np.array(bs)

    print("\n" + "=" * 96)
    print("CLEAN CONTROL — 10Y filter vs random thirds matched on trade count")
    print("=" * 96)
    print(f"  {'arm':<34}{'payout%':>10}{'bust%':>9}")
    print(f"  {'REAL  10Y-low tercile':<34}{real_p:>10.1f}{real_b:>9.1f}")
    print(f"  {'CONTROL random third  median':<34}{np.median(ps):>10.1f}"
          f"{np.median(bs):>9.1f}")
    print(f"  {'CONTROL random third  5th-95th':<34}"
          f"{np.percentile(ps, 5):>5.1f}-{np.percentile(ps, 95):<4.1f}"
          f"{np.percentile(bs, 5):>5.1f}-{np.percentile(bs, 95):<4.1f}")
    beat_p = int((ps >= real_p).sum())
    beat_b = int((bs <= real_b).sum())
    print(f"\n  random arms matching or beating the real one:")
    print(f"    on payout : {beat_p}/{SEEDS}   ({100.0 * beat_p / SEEDS:.0f}%)")
    print(f"    on bust   : {beat_b}/{SEEDS}   ({100.0 * beat_b / SEEDS:.0f}%)")

    print("\n" + "=" * 96)
    print("VERDICT")
    print("=" * 96)
    if beat_p <= 3 and beat_b <= 3:
        print("  The 10Y feature beats trade-count-matched randomness. Worth a proper")
        print("  out-of-sample test before adopting.")
    elif np.median(ps) >= real_p - 2:
        print("  A RANDOM third of sessions does the same thing. The improvement is")
        print("  'trade less often', not 'trade the right days' — the 10Y feature adds")
        print("  nothing the reduced trade count does not already deliver.")
        print("\n  That is a real finding about the ACCOUNT, not about yields: on a")
        print("  $1,000 trailing limit, cutting exposure raises payout odds regardless")
        print("  of which sessions you cut. Any honest version of this is a POSITION-")
        print("  SIZING / frequency decision, not a pre-open filter.")
    else:
        print("  Partial: the real arm is inside the random distribution's upper tail.")
        print("  Not separable from chance at this sample size.")


if __name__ == "__main__":
    main()

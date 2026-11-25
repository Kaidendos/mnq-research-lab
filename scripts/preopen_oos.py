"""Out-of-sample test of the 10Y pre-open filter. The decision, not another hint.

Where this stands: the 10Y-into-the-open filter lifted payout 52.7% -> 62.5% and beat
trade-count-matched random thirds (which came in at 48.7%, i.e. cutting frequency at
random makes things slightly WORSE, so the feature is not merely trading less). But
13% of random draws still reached it, and it was the single survivor of 27 comparisons
made on this same data. Selected-in-sample and then evaluated in-sample proves nothing.

So: freeze everything on a FIT period and evaluate once on a period never looked at.

    FIT   2021-08 .. 2024-12   -> the 33rd-percentile 10Y threshold, and nothing else
    TEST  2025-01 .. 2026-08   -> apply that frozen number, one evaluation

The threshold is the ONLY thing carried across. No re-tuning, no second look, no
picking the better of two boundaries. Whatever the test period says is the answer, and
the random control is re-run inside the test period so the comparison is like-for-like.

Pass condition, written down before running:
    the frozen filter must beat BOTH the test period's all-sessions payout AND the
    median of trade-count-matched random thirds within the test period.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import account_outlook as AO
import preopen_test as PT

FIT_END = pd.Timestamp("2025-01-01")
SEEDS = 40


def payout_bust(days):
    res = [AO.simulate(days, i) for i in range(0, len(days) - AO.MIN_DAYS, 3)]
    n = len(res)
    if n == 0:
        return 0.0, 0.0, 0
    p = 100.0 * sum(1 for r in res if r["outcome"] == "payout") / n
    b = 100.0 * sum(1 for r in res if r["outcome"] == "bust") / n
    return p, b, n


def main() -> None:
    print("loading ...", flush=True)
    df = PT.fs.load_enriched()
    one_min = PT.load_one_min()
    sess = PT.pair_sessions(df, one_min)
    sess.index = PT.naive_dates(sess.index)
    mac = PT.macro_table()
    t = sess.join(mac, how="left")
    t["f"] = (t["tnx_open"] - t["tnx_prev"]) * 100.0

    fit = t[t.index < FIT_END]
    test = t[t.index >= FIT_END]

    thresh = float(fit["f"].quantile(1 / 3))
    print(f"  FIT  {fit.index.min().date()} .. {fit.index.max().date()}  "
          f"{len(fit)} sessions -> frozen threshold: 10Y change <= {thresh:+.2f} bps")
    print(f"  TEST {test.index.min().date()} .. {test.index.max().date()}  "
          f"{len(test)} sessions   (never used to choose anything)")

    dates = list(test.index)
    net = test["net"].to_numpy(float)
    feat = test["f"].to_numpy(float)
    traded = net != 0
    keep = np.where(np.isfinite(feat), feat <= thresh, False)

    def to_days(mask):
        return [(dates[i].strftime("%Y-%m-%d"),
                 float(net[i]) if mask[i] else 0.0) for i in range(len(dates))]

    all_p, all_b, n_acc = payout_bust(to_days(np.ones(len(dates), bool)))
    real_p, real_b, _ = payout_bust(to_days(keep))
    n_keep = int((keep & traded).sum())
    n_traded = int(traded.sum())
    print(f"\n  test period: {n_traded} traded sessions, filter keeps {n_keep} "
          f"({100.0 * n_keep / max(n_traded, 1):.0f}%)")

    idx = np.flatnonzero(traded)
    ps, bs = [], []
    for s in range(SEEDS):
        rng = np.random.default_rng(1000 + s)
        m = np.zeros(len(dates), bool)
        m[rng.choice(idx, size=min(n_keep, len(idx)), replace=False)] = True
        p, b, _ = payout_bust(to_days(m))
        ps.append(p)
        bs.append(b)
    ps, bs = np.array(ps), np.array(bs)

    print("\n" + "=" * 96)
    print(f"OUT-OF-SAMPLE — {n_acc} accounts simulated inside the test period")
    print("=" * 96)
    print(f"  {'arm':<40}{'payout%':>10}{'bust%':>9}")
    print(f"  {'ALL sessions (test period)':<40}{all_p:>10.1f}{all_b:>9.1f}")
    print(f"  {'FROZEN 10Y filter':<40}{real_p:>10.1f}{real_b:>9.1f}")
    print(f"  {'random third, median':<40}{np.median(ps):>10.1f}{np.median(bs):>9.1f}")
    print(f"  {'random third, 5th-95th':<40}"
          f"{np.percentile(ps, 5):>5.1f}-{np.percentile(ps, 95):<4.1f}"
          f"{np.percentile(bs, 5):>5.1f}-{np.percentile(bs, 95):<4.1f}")
    beat = int((ps >= real_p).sum())
    print(f"\n  random arms matching/beating the frozen filter on payout: "
          f"{beat}/{SEEDS} ({100.0 * beat / SEEDS:.0f}%)")

    print("\n" + "=" * 96)
    print("VERDICT — against the pass condition written before the run")
    print("=" * 96)
    beats_all = real_p > all_p
    beats_rnd = real_p > np.median(ps)
    print(f"  beats all-sessions payout ({all_p:.1f}%)      : "
          f"{'YES' if beats_all else 'NO'}  ({real_p:.1f}%)")
    print(f"  beats random-third median ({np.median(ps):.1f}%)     : "
          f"{'YES' if beats_rnd else 'NO'}  ({real_p:.1f}%)")
    if beats_all and beats_rnd and beat <= SEEDS * 0.2:
        print("\n  PASSES out-of-sample. This is the first pre-open filter in this")
        print("  project to survive selection on one period and evaluation on another.")
        print("  Adoptable, with the usual caveat that one OOS window is one window.")
    else:
        print("\n  FAILS out-of-sample. The in-sample improvement did not carry over.")
        print("  It joins the rejected list — 18 now. The pre-open panel stays CONTEXT,")
        print("  not a filter, and the app should keep gating only on the event calendar.")


if __name__ == "__main__":
    main()

"""Full $50K Trading Combine rule simulator.

Rules modeled (Topstep 50K):
  - profit target +$3,000
  - Daily Loss Limit $1,000: a worse modeled day is clipped to -$1,000
    (Topstep auto-flattens at the DLL; it is a lock, not a violation)
  - Maximum Loss Limit $2,000 trailing on END-OF-DAY balance highs -> bust
  - 50% consistency rule: cannot pass until best single day <= 50% of total
    profit — the walk continues until that is ALSO satisfied
Fees must already be inside the daily series.
"""

import numpy as np


def combine_sim(daily, target=3000.0, mll=2000.0, dll=1000.0, frac=0.5):
    """daily: pd.Series of active-day net P&L. Returns (pass_rate_pct,
    days_to_pass_list, n_busted, n_unresolved)."""
    vals = np.minimum(daily.values, dll * 0 + daily.values)  # copy
    vals = np.maximum(vals, -dll)          # DLL clip
    passes, busted, unresolved = [], 0, 0
    for s in range(len(vals)):
        cum = peak = best = 0.0
        outcome = None
        for j in range(s, len(vals)):
            v = vals[j]
            cum += v
            best = max(best, v)
            peak = max(peak, cum)
            if peak - cum >= mll:
                outcome = "bust"
                break
            if cum >= target and best <= frac * cum:
                outcome = j - s + 1
                break
        if outcome is None:
            unresolved += 1
        elif outcome == "bust":
            busted += 1
        else:
            passes.append(outcome)
    resolved = len(passes) + busted
    rate = 100.0 * len(passes) / resolved if resolved else float("nan")
    return rate, passes, busted, unresolved


def describe(daily, label=""):
    rate, passes, busted, unresolved = combine_sim(daily)
    out = f"  Combine (full rules): {rate:.0f}% pass ({len(passes)}P/{busted}B"
    if unresolved:
        out += f", {unresolved} unresolved"
    out += ")"
    if passes:
        out += (f", days-to-pass median {int(np.median(passes))}, "
                f"p90 {int(np.percentile(passes, 90))}, worst {max(passes)}")
    return out

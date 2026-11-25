"""Why did the bust estimate move from ~2% to 17% to 46%? Reconcile the methods.

Three different numbers have been quoted for this account across sessions:

    ~2.1%   RETRACTED in an earlier session — it was wrong
    17%     the BUST TAIL at the 95th percentile, from a block bootstrap.
            A tail statement, not an unconditional rate.
    46.4%   today: unconditional bust rate over CONTIGUOUS real history

The suspicion this script tests is that the resampling method itself is the cause.
A block bootstrap with 10-session blocks cannot reproduce a losing streak longer than
its block length, and real history has them — the pair went 7-losing-days-in-9 during
2026-07-20..07-31. Break the streaks up and the account survives runs it would really
have died in.

So: same day-P&L series, same account rules, three resampling methods.

    CONTIGUOUS   walk real history forward from each start date  (what reality does)
    BLOCK        resample 10-session blocks                       (the old method)
    IID          shuffle single sessions                          (the naive method)

If BLOCK and IID come in far below CONTIGUOUS, the earlier low numbers were an
artefact of the resampler, not a different opinion about the strategy.
"""
from __future__ import annotations

import numpy as np

import account_outlook as AO
import preopen_test as PT
from rr_sweep import load_one_min

SIMS = 400
BLOCK = 10
HORIZON = AO.HORIZON


def outcomes(days) -> tuple[float, float, float]:
    res = [AO.simulate(days, i) for i in range(0, max(1, len(days) - AO.MIN_DAYS), 3)]
    n = len(res)
    p = 100.0 * sum(1 for r in res if r["outcome"] == "payout") / n
    b = 100.0 * sum(1 for r in res if r["outcome"] == "bust") / n
    s = 100.0 * sum(1 for r in res if r["outcome"] == "stall") / n
    return p, b, s


def one_path(pnl: np.ndarray, rng, mode: str) -> list:
    """Build a single HORIZON-length synthetic account path."""
    if mode == "block":
        out = []
        while len(out) < HORIZON:
            i = int(rng.integers(0, max(1, len(pnl) - BLOCK)))
            out.extend(pnl[i:i + BLOCK].tolist())
        seq = out[:HORIZON]
    else:                                   # iid
        seq = rng.choice(pnl, size=HORIZON, replace=True).tolist()
    return [(f"2020-01-{i % 28 + 1:02d}", float(v)) for i, v in enumerate(seq)]


def main() -> None:
    print("loading ...", flush=True)
    df = PT.fs.load_enriched()
    one_min = load_one_min()
    sess = PT.pair_sessions(df, one_min)
    pnl = sess["net"].to_numpy(float)
    days = [(d.strftime("%Y-%m-%d"), float(v))
            for d, v in zip(sess.index, pnl)]
    print(f"  {len(days)} sessions, {int((pnl != 0).sum())} with a trade")

    # longest real losing streak — the thing a 10-block bootstrap cannot reproduce
    streak = best = 0
    for v in pnl:
        if v < 0:
            streak += 1
            best = max(best, streak)
        elif v > 0:
            streak = 0
    print(f"  longest real losing streak: {best} sessions "
          f"(a {BLOCK}-session block bootstrap can only chain these by accident)")

    print("\n" + "=" * 88)
    print("SAME DATA, SAME RULES, THREE RESAMPLING METHODS")
    print("=" * 88)
    print(f"  {'method':<34}{'payout%':>10}{'bust%':>9}{'stall%':>9}")

    p, b, s = outcomes(days)
    print(f"  {'CONTIGUOUS real history':<34}{p:>10.1f}{b:>9.1f}{s:>9.1f}")
    real_bust = b

    for mode, label in (("block", f"BLOCK bootstrap ({BLOCK}-session)"),
                        ("iid", "IID shuffle (single sessions)")):
        ps, bs, ss = [], [], []
        for k in range(SIMS):
            rng = np.random.default_rng(k)
            path = one_path(pnl, rng, mode)
            r = AO.simulate(path, 0)
            ps.append(r["outcome"] == "payout")
            bs.append(r["outcome"] == "bust")
            ss.append(r["outcome"] == "stall")
        print(f"  {label:<34}{100 * np.mean(ps):>10.1f}{100 * np.mean(bs):>9.1f}"
              f"{100 * np.mean(ss):>9.1f}")

    print("\n" + "=" * 88)
    print("WHAT THE OLD NUMBERS ACTUALLY WERE")
    print("=" * 88)
    print("  '40% of days'  = share of SESSIONS producing no signal at all.")
    print(f"                   Actual here: "
          f"{100.0 * (pnl == 0).mean():.0f}% of sessions never trade.")
    print("                   That is a frequency stat, NOT a stall rate. Today's")
    print(f"                   stall rate is {s:.1f}%.")
    print("  '2.1% bust'    = retracted in an earlier session. It was wrong.")
    print("  '17% bust'     = the tail at the 95th PERCENTILE of a block bootstrap,")
    print("                   i.e. a conditional worst-case, not the average account.")
    print(f"  '{real_bust:.0f}% bust'      = today: unconditional, contiguous real history,")
    print("                   floor enforced on end-of-day balances.")


if __name__ == "__main__":
    main()

"""What if you used the website to decide whether to trade? Tested on the real pair.

The app's binding checks are: entry window, high-impact event gate, feed freshness.
The window is already inside the strategy, and feed freshness is an operational check
with no historical analogue. So the app's actual DECISION CONTENT is one thing:

    skip the whole session when a high-impact USD release prints before the window ends

That was tested once before, but badly for this purpose: on StochReclaim30 (the wrong
strategy — it has no edge to protect), over 48 sessions, with a bust margin of $6
deciding the headline. This redoes it properly:

  * the RESEARCHED PAIR, the only book with a measured edge
  * the full span the real ForexFactory file covers, 2026-02-18 .. 2026-07-15
  * ACCOUNT level — payout / bust under the LucidPro floor, not just P&L
  * against a CLEAN CONTROL: random day-removal matched on session count

That last one is the part that matters. Removing a third of the sessions changes the
account's exposure all by itself, so "gated beats ungated" proves nothing unless it
also beats removing the SAME NUMBER of random days. That control is what exposed the
10Y pre-open filter as noise, and it is applied here for the same reason.
"""
from __future__ import annotations

import csv
import datetime as dt

import numpy as np
import pandas as pd

import account_outlook as AO
import preopen_test as PT
from rr_sweep import load_one_min

EVENTS = PT.fs.D / "ff_high_usd_events_2026.csv"
WINDOW_END_MIN = 90          # 11:00 ET = 90 minutes past the 09:30 open
SEEDS = 60


def load_blocking_days() -> tuple[dict, str, str]:
    """Sessions with a high-impact USD release before the window closes."""
    rows = []
    with open(EVENTS, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            when = dt.datetime.fromtimestamp(int(r["epoch"]), dt.timezone.utc
                                             ).astimezone(PT.fs.TZ if isinstance(
                                                 PT.fs.TZ, dt.tzinfo) else None)
            rows.append((when, r["name"]))
    # fs.TZ is a string; redo cleanly
    from zoneinfo import ZoneInfo
    ET = ZoneInfo("America/New_York")
    rows = []
    with open(EVENTS, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            when = dt.datetime.fromtimestamp(int(r["epoch"]),
                                             dt.timezone.utc).astimezone(ET)
            rows.append((when, r["name"]))
    rows.sort()
    blocking: dict[str, list[str]] = {}
    for when, name in rows:
        sess_min = (when.hour - 9) * 60 + when.minute - 30
        if sess_min <= WINDOW_END_MIN:
            blocking.setdefault(when.strftime("%Y-%m-%d"), []).append(name)
    lo = min(r[0] for r in rows).strftime("%Y-%m-%d")
    hi = max(r[0] for r in rows).strftime("%Y-%m-%d")
    return blocking, lo, hi


def outcomes(days):
    res = [AO.simulate(days, i) for i in range(0, max(1, len(days) - AO.MIN_DAYS), 2)]
    n = len(res)
    return (100.0 * sum(1 for r in res if r["outcome"] == "payout") / n,
            100.0 * sum(1 for r in res if r["outcome"] == "bust") / n, n)


def main() -> None:
    print("loading ...", flush=True)
    df = PT.fs.load_enriched()
    one_min = load_one_min()
    sess = PT.pair_sessions(df, one_min)
    sess.index = PT.naive_dates(sess.index)

    blocking, cal_lo, cal_hi = load_blocking_days()
    print(f"  real calendar covers {cal_lo} .. {cal_hi}")

    lo, hi = pd.Timestamp(cal_lo), pd.Timestamp(cal_hi)
    win = sess[(sess.index >= lo) & (sess.index <= hi)]
    dates = [d.strftime("%Y-%m-%d") for d in win.index]
    net = win["net"].to_numpy(float)
    traded = net != 0
    blocked = np.array([d in blocking for d in dates])

    print(f"  {len(win)} sessions in the calendar-covered window, "
          f"{int(traded.sum())} with a trade")
    print(f"  the gate would block {int(blocked.sum())} sessions "
          f"({100.0 * blocked.mean():.0f}%), of which "
          f"{int((blocked & traded).sum())} had a trade")

    def to_days(keep):
        return [(dates[i], float(net[i]) if keep[i] else 0.0)
                for i in range(len(dates))]

    keep_all = np.ones(len(dates), bool)
    keep_gate = ~blocked

    p_all, b_all, n_acc = outcomes(to_days(keep_all))
    p_gate, b_gate, _ = outcomes(to_days(keep_gate))
    net_all = float(net.sum())
    net_gate = float(net[keep_gate].sum())

    # clean control: remove the same number of TRADED sessions, at random
    n_removed = int((blocked & traded).sum())
    idx = np.flatnonzero(traded)
    ps, bs = [], []
    for s in range(SEEDS):
        rng = np.random.default_rng(s)
        keep = np.ones(len(dates), bool)
        keep[rng.choice(idx, size=min(n_removed, len(idx)), replace=False)] = False
        p, b, _ = outcomes(to_days(keep))
        ps.append(p)
        bs.append(b)
    ps, bs = np.array(ps), np.array(bs)

    print("\n" + "=" * 96)
    print(f"USING THE WEBSITE TO GATE — researched pair, {n_acc} simulated accounts")
    print("=" * 96)
    print(f"  {'arm':<38}{'net $':>10}{'payout%':>10}{'bust%':>9}")
    print(f"  {'ALL sessions (ignore the app)':<38}{net_all:>10,.0f}"
          f"{p_all:>10.1f}{b_all:>9.1f}")
    print(f"  {'GATED by the app event check':<38}{net_gate:>10,.0f}"
          f"{p_gate:>10.1f}{b_gate:>9.1f}")
    print(f"  {'CONTROL random days, same count':<38}{'—':>10}"
          f"{np.median(ps):>10.1f}{np.median(bs):>9.1f}")
    print(f"  {'   control 5th-95th':<38}{'':>10}"
          f"{np.percentile(ps, 5):>5.1f}-{np.percentile(ps, 95):<4.1f}"
          f"{np.percentile(bs, 5):>5.1f}-{np.percentile(bs, 95):<4.1f}")

    beat_p = int((ps >= p_gate).sum())
    print(f"\n  random arms matching/beating the gate on payout: "
          f"{beat_p}/{SEEDS} ({100.0 * beat_p / SEEDS:.0f}%)")

    print("\n" + "=" * 96)
    print("VERDICT")
    print("=" * 96)
    print(f"  vs ignoring the app : payout {p_all:.1f}% -> {p_gate:.1f}% "
          f"({p_gate - p_all:+.1f} pts), bust {b_all:.1f}% -> {b_gate:.1f}% "
          f"({b_gate - b_all:+.1f} pts)")
    print(f"  vs random removal   : payout {np.median(ps):.1f}% -> {p_gate:.1f}% "
          f"({p_gate - np.median(ps):+.1f} pts)")
    better_than_all = p_gate > p_all
    better_than_rnd = beat_p <= SEEDS * 0.2
    if better_than_all and better_than_rnd:
        print("\n  The gate beats BOTH trading everything and count-matched randomness.")
        print("  Worth an out-of-sample test — which needs a calendar longer than the")
        print("  5 months ForexFactory's file covers. That is the blocker, not the bars.")
    elif better_than_all:
        print("\n  Beats trading everything, but NOT cleanly better than removing the")
        print("  same number of random days. On this sample the benefit is exposure")
        print("  reduction, not day selection.")
    else:
        print("\n  Does not beat trading everything. Using the app's gate would have")
        print("  made the account WORSE over this window.")
    print(f"\n  SAMPLE: {len(win)} sessions, {n_acc} account starts, "
          f"{n_removed} traded sessions removed. Thin — read as directional.")


if __name__ == "__main__":
    main()

"""Re-score sweep candidates with HONEST metrics.

Two defects in the first pass, both found by adversarial verification:

  1. med_days counted ACTIVE trading days. Configs trading 10-30% of sessions
     showed "13 days" that were really ~130 CALENDAR days.
  2. payout_sim starts an account on EVERY active day and lets attempts overlap,
     so one good stretch is scored as a success by ~19 correlated walks. A real
     single funded account runs SEQUENTIALLY: start, run to payout or bust,
     restart.

This module reports what a real account experiences:
    seq_payouts / seq_busts      over the whole 5 years, non-overlapping
    cal_per_payout               calendar days per payout  <-- THE metric
    seq_bust_pct                 true bust rate
    med_cal_to_payout            median calendar days of a winning episode

Usage:
    python funded_rescore.py --max-cal 60 --min-net 0 --out rescored.csv
    python funded_rescore.py --slice 0/4 --max-cal 60 --out rescored_0.csv
"""
from __future__ import annotations

import argparse
import glob
from pathlib import Path

import numpy as np
import pandas as pd

import funded_search as fs

DIR = Path(__file__).parent
SESSIONS_PER_YEAR = 252


def sequential_episodes(daily: pd.Series):
    """Non-overlapping: start, run to payout/bust, restart the next day.
    Returns list of (outcome, start_ts, end_ts, active_days)."""
    vals = daily.values
    idx = daily.index
    out, s = [], 0
    while s < len(vals):
        cum = peak = biggest = 0.0
        res = None
        for j in range(s, len(vals)):
            cum += vals[j]
            d = j - s + 1
            peak = max(peak, cum)
            biggest = max(biggest, vals[j])
            if peak - cum >= fs.TRAIL_DD:
                res = ("bust", j); break
            if d >= fs.MIN_DAYS and cum >= fs.BUFFER and biggest <= fs.CONSISTENCY * cum:
                res = ("payout", j); break
        if res is None:
            out.append(("unresolved", idx[s], idx[-1], len(vals) - s))
            break
        kind, j = res
        out.append((kind, idx[s], idx[j], j - s + 1))
        s = j + 1
    return out


def honest_metrics(daily: pd.Series, total_sessions: int) -> dict:
    if len(daily) < 10:
        return dict(seq_payouts=0, seq_busts=0, seq_bust_pct=100.0,
                    cal_per_payout=-1, med_cal_to_payout=-1, active_pct=0.0,
                    payouts_per_year=0.0)
    eps = sequential_episodes(daily)
    pays = [e for e in eps if e[0] == "payout"]
    busts = [e for e in eps if e[0] == "bust"]
    span_days = (daily.index[-1] - daily.index[0]).days or 1
    resolved = len(pays) + len(busts)
    cal_pay = [(e[2] - e[1]).days for e in pays]
    return dict(
        seq_payouts=len(pays),
        seq_busts=len(busts),
        seq_bust_pct=round(100 * len(busts) / resolved, 1) if resolved else 100.0,
        cal_per_payout=round(span_days / len(pays), 0) if pays else -1,
        med_cal_to_payout=int(np.median(cal_pay)) if cal_pay else -1,
        payouts_per_year=round(365.0 * len(pays) / span_days, 2) if pays else 0.0,
        active_pct=round(100 * len(daily) / total_sessions, 1),
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-cal", type=float, default=60.0,
                    help="only rescore configs whose IMPLIED calendar cadence is <= this")
    ap.add_argument("--min-net", type=float, default=0.0)
    ap.add_argument("--slice", default=None, help="i/n to split the candidate list")
    ap.add_argument("--out", default="rescored.csv")
    args = ap.parse_args()

    files = sorted(glob.glob(str(DIR / "slice_*.csv")))
    d = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
    df = fs.load_enriched()
    total_sessions = df["_day"].nunique()

    s = d[(d["attempts"] >= 30) & (d["med_days"] > 0) & (d["net"] > args.min_net)].copy()
    s["active_pct0"] = s["days"] / total_sessions
    s["implied_cal"] = s["med_days"] / s["active_pct0"] * 365 / SESSIONS_PER_YEAR
    cand = s[s["implied_cal"] <= args.max_cal].reset_index(drop=True)
    if args.slice:
        i, n = (int(x) for x in args.slice.split("/"))
        cand = cand.iloc[i::n].reset_index(drop=True)
    print(f"{len(d):,} configs -> {len(s):,} net-positive -> {len(cand):,} to rescore",
          flush=True)

    rows = []
    for k, r in cand.iterrows():
        win = tuple(float(x) for x in str(r["win"]).split("-"))
        gate = None if r["gate"] in ("-", "", None) or pd.isna(r["gate"]) else r["gate"]
        entry, side = fs.sig(df, r["cfg_family"])
        daily, ntr, nwin = fs.replay(df, entry, side, float(r["sl"]), float(r["tp"]),
                                     win, gate, int(r["cap"]), int(r["budget"]))
        m = honest_metrics(daily, total_sessions)
        rows.append({**{c: r[c] for c in ("cfg_family", "sl", "tp", "win", "gate",
                                          "cap", "budget", "trades", "win_pct", "net",
                                          "payout_pct", "bust_pct", "med_days",
                                          "tr_payout", "te_payout")}, **m})
        if (k + 1) % 25 == 0:
            print(f"  {k+1}/{len(cand)}", flush=True)

    out = pd.DataFrame(rows)
    out.to_csv(DIR / args.out, index=False)

    real = out[out["seq_payouts"] >= 3].sort_values("cal_per_payout")
    cols = ["cfg_family", "sl", "tp", "win", "gate", "cap", "trades", "win_pct", "net",
            "active_pct", "payout_pct", "seq_payouts", "seq_busts", "seq_bust_pct",
            "cal_per_payout", "med_cal_to_payout", "te_payout"]
    pd.set_option("display.width", 260)
    print("\n" + "=" * 120)
    print("HONEST RANKING — sequential non-overlapping, CALENDAR days per payout")
    print("(user goal: <= ~30 calendar days per payout)")
    print("=" * 120)
    print(real[cols].head(30).to_string(index=False, float_format=lambda v: f"{v:.1f}")
          if len(real) else "(no config produced >=3 sequential payouts)")

    hit = real[real["cal_per_payout"] <= 30]
    print(f"\nconfigs meeting the 30-calendar-day goal: {len(hit)}")
    if len(hit):
        print(hit[cols].to_string(index=False, float_format=lambda v: f"{v:.1f}"))


if __name__ == "__main__":
    main()

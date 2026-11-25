"""How long does M2 take to pass a $50K Combine? Traded days AND calendar
days, pass and bust attempt durations, from every possible start day.
Full rules: +$3k target, $1k DLL clip, $2k EOD-trailing MLL, 50% consistency.
"""

import numpy as np
import pandas as pd

from strat_search_5y import load
from strat_mega import BOOKS, run_book

TARGET, MLL, DLL, FRAC = 3000.0, 2000.0, 1000.0, 0.5


def attempt_spans(daily: pd.Series):
    vals = np.maximum(daily.values, -DLL)
    dates = daily.index
    passes, busts = [], []          # (traded_days, calendar_days)
    for s in range(len(vals)):
        cum = peak = best = 0.0
        for j in range(s, len(vals)):
            v = vals[j]
            cum += v
            best = max(best, v)
            peak = max(peak, cum)
            cal = (dates[j] - dates[s]).days + 1
            if peak - cum >= MLL:
                busts.append((j - s + 1, cal))
                break
            if cum >= TARGET and best <= FRAC * cum:
                passes.append((j - s + 1, cal))
                break
    return passes, busts


def describe(tag, daily, sessions):
    passes, busts = attempt_spans(daily)
    resolved = len(passes) + len(busts)
    rate = 100 * len(passes) / resolved if resolved else float("nan")
    ptd = np.array([p[0] for p in passes]); pcd = np.array([p[1] for p in passes])
    btd = np.array([b[0] for b in busts]); bcd = np.array([b[1] for b in busts])
    print(f"\n{tag}")
    print(f"  trades on {daily.size} of {sessions} sessions "
          f"({100*daily.size/sessions:.0f}% of days active)")
    print(f"  pass rate: {rate:.0f}% ({len(passes)}P / {len(busts)}B)")
    if len(ptd):
        print(f"  PASSING attempt : median {int(np.median(ptd))} traded days "
              f"= {int(np.median(pcd))} calendar days "
              f"(~{np.median(pcd)/7:.1f} wks); p90 {int(np.percentile(ptd,90))}td/"
              f"{int(np.percentile(pcd,90))}cd; fastest {ptd.min()}td, "
              f"slowest {ptd.max()}td/{pcd.max()}cd")
    if len(btd):
        print(f"  BUSTED attempt  : median {int(np.median(btd))} traded days "
              f"= {int(np.median(bcd))} calendar days")
    if len(ptd) and len(btd):
        p = rate / 100
        e_attempts = 1 / p
        e_days = (np.median(pcd) + (1 - p) / p * np.median(bcd))
        print(f"  expected: ~{e_attempts:.1f} attempts to a pass; "
              f"typical total ~{e_days:.0f} calendar days (~{e_days/7:.1f} wks) "
              f"incl. failed attempts (medians)")
        for k in (1, 2, 3, 4):
            print(f"    P(passed within {k} attempt{'s' if k>1 else ' '}): "
                  f"{100*(1-(1-p)**k):.0f}%")


def main():
    d = load()
    book = BOOKS["M2 or15+orb / bd"]
    sessions = d.index.normalize().nunique()
    for lots, cap in [(5, 1500), (10, 1500)]:
        t = run_book(d, book, lots, cap)
        daily = t.groupby("date")["pnl"].sum()
        describe(f"M2 x{lots} cap$1500 — full 5y history", daily, sessions)
        d26 = daily.loc["2026-01-01":]
        s26 = d.loc["2026-01-01":].index.normalize().nunique()
        describe(f"M2 x{lots} cap$1500 — 2026 conditions only", d26, s26)


if __name__ == "__main__":
    main()

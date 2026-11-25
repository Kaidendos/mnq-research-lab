"""Apply the one surviving pre-open filter to the ACCOUNT, not the average session.

`preopen_test.py` found exactly one of nine pre-open features holding its direction in
5+ of 6 years: the 10-year yield's move into the open. Sessions where yields FELL made
$38.83 on average; sessions where they ROSE made $10.28. Coherent mechanism too — the
pair is ~74% long, and rising yields are risk-off for the Nasdaq.

The tempting conclusion is "only trade the good tercile". This tests that against the
thing that actually matters, because a funded account is not scored on average session
quality — it has to reach $26,100 before a $1,000 trailing limit catches it, and
skipping two thirds of the sessions makes the race longer.

Three arms, identical in every other respect:
    ALL          every session (the baseline)
    FALLING 10Y  only the bottom tercile of the 10Y move into the open
    NOT-RISING   drop only the top tercile (a gentler version)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import account_outlook as AO
import preopen_test as PT


def sim_all(days, label: str) -> dict:
    res = [AO.simulate(days, i) for i in range(0, len(days) - AO.MIN_DAYS, 3)]
    n = len(res)
    pay = [r for r in res if r["outcome"] == "payout"]
    bust = [r for r in res if r["outcome"] == "bust"]
    return dict(
        label=label, n=n,
        payout=100.0 * len(pay) / n, bust=100.0 * len(bust) / n,
        med_pay=int(np.median([r["days"] for r in pay])) if pay else 0,
        med_bust=int(np.median([r["days"] for r in bust])) if bust else 0,
        med_final=float(np.median([r["final"] for r in res])),
    )


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

    print(f"  {len(t)} sessions, {int(t['trades'].sum())} trades, "
          f"net ${t['net'].sum():,.0f}")
    print(f"  10Y bucket coverage: "
          + ", ".join(f"{b}={int((t['bucket'] == b).sum())}"
                      for b in ("low", "mid", "high"))
          + f", unknown={int(t['bucket'].isna().sum())}")

    # An unknown bucket means no macro data for that date. Trading it is the honest
    # default: a live app that cannot fetch the yield would not skip the day silently.
    arms = {
        "ALL sessions": t["net"],
        "FALLING 10Y only (bottom tercile)": t["net"].where(t["bucket"] == "low", 0.0),
        "NOT-RISING 10Y (drop top tercile)": t["net"].where(t["bucket"] != "high", 0.0),
    }

    print("\n" + "=" * 104)
    print("PRE-OPEN 10Y FILTER — total profit vs what the funded account actually does")
    print("=" * 104)
    print(f"  {'arm':<36}{'sessions':>9}{'net $':>10}{'$/sess':>8}"
          f"{'payout%':>9}{'bust%':>8}{'med pay':>9}{'med bust':>10}")
    out = []
    for label, series in arms.items():
        days = [(d.strftime("%Y-%m-%d"), float(v)) for d, v in series.items()]
        traded = sum(1 for _, v in days if v != 0)
        r = sim_all(days, label)
        net = float(series.sum())
        print(f"  {label:<36}{traded:>9}{net:>10,.0f}"
              f"{net / max(traded, 1):>8.2f}{r['payout']:>9.1f}{r['bust']:>8.1f}"
              f"{r['med_pay']:>9}{r['med_bust']:>10}")
        out.append((label, net, traded, r))

    base = out[0]
    print("\n" + "=" * 104)
    print("VERDICT")
    print("=" * 104)
    for label, net, traded, r in out[1:]:
        d_net = net - base[1]
        d_pay = r["payout"] - base[3]["payout"]
        d_bust = r["bust"] - base[3]["bust"]
        print(f"  {label}")
        print(f"    net       ${base[1]:,.0f} -> ${net:,.0f}  ({d_net:+,.0f})")
        print(f"    payout    {base[3]['payout']:.1f}% -> {r['payout']:.1f}%  "
              f"({d_pay:+.1f} pts)")
        print(f"    bust      {base[3]['bust']:.1f}% -> {r['bust']:.1f}%  "
              f"({d_bust:+.1f} pts)")
        print(f"    sessions  {base[2]} -> {traded}  "
              f"({100.0 * traded / base[2] - 100:+.0f}%)")
    print("\n  The per-session average is not the objective. A funded account has to")
    print("  cross $26,100 before a $1,000 trailing limit catches it, so giving up")
    print("  sessions lengthens the race even when the ones you keep are better.")


if __name__ == "__main__":
    main()

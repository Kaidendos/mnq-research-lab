"""What a LucidPro $25K would actually do on the researched pair — with the floor on.

`live_vs_researched.py` reported +$28,157 raw over 5 years. That number is honest
about the strategy and DISHONEST about the account, because the harness never applied
the trailing max-loss limit: it let equity go to -$3,000 and keep trading. A real
funded account dies at -$1,000 and stops existing.

So this re-runs the same trades through the actual rules:

  floor      min(highest END-OF-DAY balance, $26,100) - $1,000, starting at $24,000
  payout     balance >= $26,100, at least 3 trading days, and no single day worth
             more than 40% of total profit (the consistency rule)
  bust       an end-of-day balance at or below the floor

and starts a fresh account every 3 trading days across the whole 5 years, so the
answer is a DISTRIBUTION over start dates rather than one lucky path. Starting on a
good week and starting on a bad one are both real futures; only the spread tells you
what to expect.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import funded_1yr as f1
import funded_search as fs
from live_vs_researched import run
from rr_sweep import load_one_min

START = 25_000.0
BUFFER = 1_100.0            # payout at 26,100
TRAIL = 1_000.0
CONSISTENCY = 0.40
MIN_DAYS = 3
HORIZON = 180               # trading days to give each account


def day_series(df, one_min, el, es, blo, bhi, sl, tp, swg, mode):
    """Re-run the replay but keep per-DAY net P&L, in date order."""
    # run() returns aggregates; redo the loop here keeping dates
    import live_vs_researched as LR
    t1, h1, l1 = one_min
    c = df["close"].to_numpy(float)
    h = df["high"].to_numpy(float)
    lo = df["low"].to_numpy(float)
    atr = df["atr"].to_numpy(float)
    ts = df.index.values.astype("datetime64[ns]")
    bod = df.groupby("_day").cumcount().to_numpy()
    day_ids = pd.factorize(df["_day"])[0]
    dates = df["_day"].dt.strftime("%Y-%m-%d").to_numpy()
    starts = np.flatnonzero(np.r_[True, day_ids[1:] != day_ids[:-1]])
    ends = np.r_[starts[1:], len(day_ids)]

    out = []
    for s, e in zip(starts, ends):
        day_pnl, day_trades, day_won = 0.0, 0, False
        busy = np.datetime64("1970-01-01", "ns")
        for i in range(s, e):
            if not (blo <= bod[i] <= bhi) or day_trades >= 6 or day_won:
                continue
            if ts[i] < busy:
                continue
            side = 1 if el[i] else (-1 if es[i] else 0)
            if side == 0:
                continue
            a = atr[i]
            if not np.isfinite(a) or a <= 0:
                continue
            stop_usd = a * sl * 2.0
            if mode == "nt":
                n = min(10, int((300.0 + day_pnl) // stop_usd),
                        int((440.0 - day_pnl) // (a * tp * 2.0)))
            else:
                n = min(10, int(min(300.0, 440.0) // stop_usd))
            if n < 1:
                continue
            entry = c[i]
            slt = max(1, round(a * sl / 0.25)) * 0.25
            tpt = max(1, round(a * tp / 0.25)) * 0.25
            s_ns = ts[i] + np.timedelta64(5, "m")
            dl = ts[e - 1] + np.timedelta64(5, "m")
            if side > 0:
                px, _, xt = LR.resolve_exit(t1, h1, l1, s_ns, entry - slt,
                                            entry + tpt, dl, c[e - 1])
            else:
                px, _, xt = LR.resolve_short(t1, h1, l1, s_ns, entry + slt,
                                             entry - tpt, dl, c[e - 1])
            net = (px - entry) * side * 2.0 * n - 1.22 * n
            day_pnl += net
            day_trades += 1
            if swg and day_pnl > 0:
                day_won = True
            busy = xt
        out.append((dates[s], day_pnl))
    return out


def simulate(days, start_idx: int) -> dict:
    """One account from `start_idx`. Returns outcome + days taken."""
    bal, peak = START, START
    best_day, profit_days = 0.0, 0
    for d in range(start_idx, min(start_idx + HORIZON, len(days))):
        _, pnl = days[d]
        bal += pnl
        if pnl != 0:
            profit_days += 1
            best_day = max(best_day, pnl)
        floor = min(peak, START + BUFFER) - TRAIL
        if bal <= floor:
            return dict(outcome="bust", days=d - start_idx + 1, final=bal)
        peak = max(peak, bal)
        profit = bal - START
        if (bal >= START + BUFFER and profit_days >= MIN_DAYS
                and best_day <= CONSISTENCY * profit):
            return dict(outcome="payout", days=d - start_idx + 1, final=bal)
    return dict(outcome="stall", days=HORIZON, final=bal)


def main() -> None:
    print("loading ...", flush=True)
    df = fs.load_enriched()
    one_min = load_one_min()
    pl = f1.load_plugins(df)

    def sig(name):
        e, _ = pl[name] if name in pl else fs.sig(df, name)
        return pd.Series(e).reindex(df.index).fillna(False).to_numpy(bool)

    el, es = sig("sr_round100_break"), sig("vol_lw_stretch_short")
    days = day_series(df, one_min, el, es, 2, 18, 2.0, 3.0, False, "funded")
    traded = [d for d in days if d[1] != 0]
    print(f"  {len(days)} sessions, {len(traded)} with a trade "
          f"({100 * len(traded) / len(days):.0f}%)")

    res = [simulate(days, i) for i in range(0, len(days) - MIN_DAYS, 3)]
    n = len(res)
    pay = [r for r in res if r["outcome"] == "payout"]
    bust = [r for r in res if r["outcome"] == "bust"]
    stall = [r for r in res if r["outcome"] == "stall"]

    print("\n" + "=" * 90)
    print(f"LucidPro $25K on the researched pair — {n} simulated accounts, "
          f"{HORIZON}-day horizon")
    print("=" * 90)
    print(f"  PAYOUT reached $26,100 : {len(pay):>4} / {n}  = {100*len(pay)/n:>5.1f}%"
          f"   median {int(np.median([r['days'] for r in pay])) if pay else 0} "
          f"trading days")
    print(f"  BUST   hit the floor   : {len(bust):>4} / {n}  = {100*len(bust)/n:>5.1f}%"
          f"   median {int(np.median([r['days'] for r in bust])) if bust else 0} "
          f"trading days")
    print(f"  STALL  neither in {HORIZON}d : {len(stall):>4} / {n}  = "
          f"{100*len(stall)/n:>5.1f}%")

    finals = np.array([r["final"] for r in res])
    print(f"\n  ending balance: 5th ${np.percentile(finals,5):,.0f} | "
          f"median ${np.median(finals):,.0f} | 95th ${np.percentile(finals,95):,.0f}")

    if bust:
        print(f"\n  Of the {len(bust)} busts, "
              f"{sum(1 for r in bust if r['days'] <= 20)} happened within 20 trading "
              f"days — the first month is where the risk lives.")

    # per-start-year, so a single good regime cannot carry the headline
    print("\n  by START year (does it depend on when you happen to begin?)")
    yr_of = {i: days[i][0][:4] for i in range(len(days))}
    for y in sorted({v for v in yr_of.values()}):
        sub = [simulate(days, i) for i in range(0, len(days) - MIN_DAYS, 3)
               if yr_of[i] == y]
        if not sub:
            continue
        p = 100 * sum(1 for r in sub if r["outcome"] == "payout") / len(sub)
        b = 100 * sum(1 for r in sub if r["outcome"] == "bust") / len(sub)
        print(f"    {y}: {len(sub):>3} accounts   payout {p:>5.1f}%   bust {b:>5.1f}%")


if __name__ == "__main__":
    main()

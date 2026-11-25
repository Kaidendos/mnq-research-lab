"""Run the WHOLE app as if it had been making the decisions, day by day, for 5 years.

Every test so far isolated one component — the event gate alone, one pre-open feature
alone, the timeframe alone. None of them asked the question that actually matters:
if the app had been sitting there every morning making its real decisions, would the
account have ended up better or worse than just running the strategy?

The deployed system makes exactly three market-facing decisions. Two are testable:

  1. WINDOW           already inside the strategy — nothing to add
  2. EVENT GATE       skip the session on a high-impact release before the window ends
                      (only testable over the 5 months the real FF calendar covers)
  3. FADE-LOW KILL    a TESTED kill rule: refuse a LONG when price sits in the bottom
                      third of the overnight range. This has NEVER been tested against
                      the researched pair, only against the 44 fade families it came
                      from — so applying it here is a genuinely open question.
  4. feed freshness   operational, no historical analogue

STRICTLY CAUSAL: the overnight range is complete at 09:30, before the window opens,
and the position test uses the price AT THE SIGNAL BAR, not the day's eventual close.
Nothing here reads a bar the app would not have had.

Reported at ACCOUNT level under the LucidPro floor, because "more net P&L" and "more
likely to get paid" are different questions and only the second one pays.
"""
from __future__ import annotations

import csv
import datetime as dt
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

import account_outlook as AO
import funded_1yr as f1
import funded_search as fs
import live_vs_researched as LR
import preopen_test as PT
from rr_sweep import load_one_min

ET = ZoneInfo("America/New_York")
PV, FEE, TICK = 2.0, 1.22, 0.25
SL_ATR, TP_ATR = 2.0, 3.0
BUDGET, CAP, MAXC, MAXTR = 300.0, 440.0, 10, 6
FADE_PCT = 33.0                    # killrules nq-fade-low threshold
WINDOW_END_MIN = 90                # 11:00 ET


def blocking_days() -> tuple[set, str, str]:
    rows = []
    with open(fs.D / "ff_high_usd_events_2026.csv", newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            rows.append(dt.datetime.fromtimestamp(int(r["epoch"]),
                                                  dt.timezone.utc).astimezone(ET))
    blk = {w.strftime("%Y-%m-%d") for w in rows
           if (w.hour - 9) * 60 + w.minute - 30 <= WINDOW_END_MIN}
    return blk, min(rows).strftime("%Y-%m-%d"), max(rows).strftime("%Y-%m-%d")


def replay(df, one_min, on_tbl, use_fade_kill: bool, blocked: set | None):
    """Per-session P&L with the app's decisions applied at signal time."""
    pl = f1.load_plugins(df)

    def sig(name):
        e, _ = pl[name] if name in pl else fs.sig(df, name)
        return pd.Series(e).reindex(df.index).fillna(False).to_numpy(bool)

    el, es = sig("sr_round100_break"), sig("vol_lw_stretch_short")
    t1, h1, l1 = one_min
    c = df["close"].to_numpy(float)
    atr = df["atr"].to_numpy(float)
    ts = df.index.values.astype("datetime64[ns]")
    bod = df.groupby("_day").cumcount().to_numpy()
    ids = pd.factorize(df["_day"])[0]
    dates = pd.to_datetime(df["_day"]).dt.strftime("%Y-%m-%d").to_numpy()
    starts = np.flatnonzero(np.r_[True, ids[1:] != ids[:-1]])
    ends = np.r_[starts[1:], len(ids)]

    onh = on_tbl["onh"].to_dict()
    onl = on_tbl["onl"].to_dict()

    out, killed_fade, killed_event = [], 0, 0
    for s, e in zip(starts, ends):
        day = dates[s]
        if blocked is not None and day in blocked:
            killed_event += 1
            out.append((day, 0.0, 0, 0))
            continue

        key = pd.Timestamp(day)
        hi, lo = onh.get(key), onl.get(key)
        rng = (hi - lo) if (hi is not None and lo is not None and hi > lo) else None

        net, ntr, nw = 0.0, 0, 0
        busy = np.datetime64("1970-01-01", "ns")
        for i in range(s, e):
            if not (2 <= bod[i] <= 18) or ntr >= MAXTR or ts[i] < busy:
                continue
            side = 1 if el[i] else (-1 if es[i] else 0)
            if side == 0:
                continue
            a = atr[i]
            if not np.isfinite(a) or a <= 0:
                continue

            # ── the app's TESTED kill rule, applied at the signal's own price ──
            if use_fade_kill and side > 0 and rng:
                pos = 100.0 * (c[i] - lo) / rng
                if pos < FADE_PCT:
                    killed_fade += 1
                    continue

            n = min(MAXC, int(min(BUDGET, CAP) // (a * SL_ATR * PV)))
            if n < 1:
                continue
            entry = c[i]
            slp = max(1, round(a * SL_ATR / TICK)) * TICK
            tpp = max(1, round(a * TP_ATR / TICK)) * TICK
            s_ns = ts[i] + np.timedelta64(5, "m")
            dl = ts[e - 1] + np.timedelta64(5, "m")
            if side > 0:
                px, _, xt = LR.resolve_exit(t1, h1, l1, s_ns, entry - slp,
                                            entry + tpp, dl, c[e - 1])
            else:
                px, _, xt = LR.resolve_short(t1, h1, l1, s_ns, entry + slp,
                                             entry - tpp, dl, c[e - 1])
            g = (px - entry) * side * PV * n
            net += g - FEE * n
            ntr += 1
            nw += g > 0
            busy = xt
        out.append((day, net, ntr, nw))
    return out, killed_fade, killed_event


def account(days) -> tuple[float, float, int]:
    res = [AO.simulate(days, i)
           for i in range(0, max(1, len(days) - AO.MIN_DAYS), 3)]
    n = len(res)
    return (100.0 * sum(1 for r in res if r["outcome"] == "payout") / n,
            100.0 * sum(1 for r in res if r["outcome"] == "bust") / n, n)


def summarise(rows):
    net = sum(r[1] for r in rows)
    tr = sum(r[2] for r in rows)
    w = sum(r[3] for r in rows)
    return net, tr, (100.0 * w / tr if tr else 0.0)


def main() -> None:
    print("loading ...", flush=True)
    df = fs.load_enriched()
    one_min = load_one_min()
    on_tbl = PT.overnight_table()
    blk, cal_lo, cal_hi = blocking_days()
    print(f"  {len(df):,} bars, calendar {cal_lo}..{cal_hi}", flush=True)

    years = sorted({int(y) for y in df.index.year})

    print("\n" + "=" * 104)
    print("FULL 5 YEARS — the one app decision testable over the whole span")
    print("=" * 104)
    base, _, _ = replay(df, one_min, on_tbl, False, None)
    fade, nk, _ = replay(df, one_min, on_tbl, True, None)

    print(f"  {'arm':<40}{'trades':>8}{'win%':>7}{'net $':>10}"
          f"{'payout%':>10}{'bust%':>8}")
    rows = []
    for label, r in (("strategy alone", base),
                     ("strategy + app's fade-low KILL", fade)):
        net, tr, win = summarise(r)
        days = [(d, v) for d, v, _, _ in r]
        p, b, nacc = account(days)
        rows.append((label, net, tr, win, p, b))
        print(f"  {label:<40}{tr:>8}{win:>7.1f}{net:>10,.0f}{p:>10.1f}{b:>8.1f}")
    print(f"\n  the fade-low rule killed {nk} long signals "
          f"({100.0 * nk / max(rows[0][2], 1):.0f}% of the baseline's trades)")

    d_net = rows[1][1] - rows[0][1]
    d_pay = rows[1][4] - rows[0][4]
    d_bust = rows[1][5] - rows[0][5]
    print(f"  effect: net {d_net:+,.0f}   payout {d_pay:+.1f} pts   "
          f"bust {d_bust:+.1f} pts")

    print("\n  per-year net (does the rule help consistently, or once?)")
    for label, r in (("strategy alone", base), ("+ fade-low kill", fade)):
        per = {}
        for d, v, _, _ in r:
            per[d[:4]] = per.get(d[:4], 0.0) + v
        print(f"    {label:<24}" + "".join(f"{per.get(str(y), 0):>10,.0f}"
                                           for y in years))

    # ── the 5-month window where the event gate is also testable ──
    print("\n" + "=" * 104)
    print(f"CALENDAR WINDOW {cal_lo}..{cal_hi} — the FULL stack, every decision on")
    print("=" * 104)
    # df.index is tz-aware ET; naive Timestamps cannot be compared against it
    lo = pd.Timestamp(cal_lo, tz=ET)
    hi = pd.Timestamp(cal_hi, tz=ET) + pd.Timedelta(days=1)
    mask = (df.index >= lo) & (df.index < hi)
    dfw = df[mask]
    combos = [
        ("nothing (strategy alone)", False, None),
        ("event gate only", False, blk),
        ("fade-low kill only", True, None),
        ("FULL app stack (both)", True, blk),
    ]
    print(f"  {'decisions applied':<40}{'trades':>8}{'win%':>7}{'net $':>10}"
          f"{'payout%':>10}{'bust%':>8}")
    for label, fk, bl in combos:
        r, _, _ = replay(dfw, one_min, on_tbl, fk, bl)
        net, tr, win = summarise(r)
        p, b, nacc = account([(d, v) for d, v, _, _ in r])
        print(f"  {label:<40}{tr:>8}{win:>7.1f}{net:>10,.0f}{p:>10.1f}{b:>8.1f}")
    print(f"\n  ({nacc} account starts in this window — thin, read as directional)")


if __name__ == "__main__":
    main()

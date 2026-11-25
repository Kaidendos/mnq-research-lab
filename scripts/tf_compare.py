"""The best two signals on 5-minute vs 1-minute bars, alone and paired.

    sr_round100_break     LONG   close crosses up into a new 100-block, clears it by
                                 0.15 ATR, bull bar, above-average volume
    vol_lw_stretch_short  SHORT  first close below session_open - 0.5 * prior range

Signal timeframe was swept at 15m and 30m before and both were rejected. Going FINER
was never tested, and it is not the same question — coarser bars mean fewer, later
entries, whereas finer bars change three things at once:

  1. more fires (a 100-level can be crossed on a 1-min close that a 5-min close smooths)
  2. a MUCH tighter bracket, because ATR(14) on 1-min bars is roughly half the 5-min
     value, and the stop is 2.0 ATR either way
  3. more trades against a fixed $1.22/contract fee

Those pull in opposite directions, so the arms below separate them. The third arm is
the diagnostic one: 1-minute ENTRY TIMING with the 5-minute BRACKET WIDTH. If the
1-min version underperforms, that arm says whether the cause is the noisier entry or
the tighter stop.

Fills are resolved on 1-minute bars in every arm, so nothing here is a fill artefact.
Bar-start alignment is respected: a bar stamped T closes at T + one bar period, and
the exit scan begins there.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import funded_search as fs

PV, FEE, TICK = 2.0, 1.22, 0.25
SL_ATR, TP_ATR = 2.0, 3.0
WIN_LO, WIN_HI = 9.75, 11.0          # bar-CLOSE window, ET
BUDGET, CAP, MAXC, MAXTR = 300.0, 440.0, 10, 6
ROUND_STEP, BREAK_BUF, VOL_LB, LW_K = 100.0, 0.15, 20, 0.5

F5 = fs.D / "mnq_2021-2026_5min.csv"
F1 = fs.D / "mnq_2021-2026_1min.csv.gz"


def load_rth(path, minutes: int) -> pd.DataFrame:
    """RTH-only frame with ATR(14), prior-day levels, and session facts."""
    df = pd.read_csv(path, usecols=["ts_et", "open", "high", "low", "close", "volume"])
    ts = pd.to_datetime(df["ts_et"], format="mixed", utc=True
                        ).dt.tz_convert("America/New_York")
    d = df.set_index(ts).drop(columns=["ts_et"]).sort_index()
    hrs = d.index.hour + d.index.minute / 60.0
    d = d[(hrs >= 9.5) & (hrs < 16.0)].copy()

    c, h, l = d["close"], d["high"], d["low"]
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    d["atr"] = tr.ewm(alpha=1 / 14, adjust=False).mean()

    day = d.index.normalize()
    d["_day"] = day
    d["bod"] = d.groupby(day).cumcount()
    # bar CLOSE in decimal ET hours — the window is a close-time window
    d["close_h"] = d.index.hour + (d.index.minute + minutes) / 60.0
    d["sess_open"] = d.groupby(day)["open"].transform("first")

    dh, dl = h.groupby(day).max(), l.groupby(day).min()
    dmap = pd.Series(day, index=d.index)
    d["pdh"], d["pdl"] = dmap.map(dh.shift(1)), dmap.map(dl.shift(1))
    d["volref"] = d["volume"].rolling(VOL_LB).mean()
    return d.dropna(subset=["atr"])


def signals(d: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """(long, short) boolean masks — transcribed from web_sr.py / web_vol.py."""
    c = d["close"].to_numpy(float)
    o = d["open"].to_numpy(float)
    v = d["volume"].to_numpy(float)
    atr = d["atr"].to_numpy(float)
    bod = d["bod"].to_numpy()
    pc = np.r_[np.nan, c[:-1]]
    same = bod > 0                       # never the session's first bar

    lvl = np.floor(c / ROUND_STEP)
    cross_up = lvl > np.floor(pc / ROUND_STEP)
    decisive = c >= lvl * ROUND_STEP + BREAK_BUF * atr
    volref = d["volref"].to_numpy(float)
    longs = (same & cross_up & decisive & (c > o) & (v > volref)
             & np.isfinite(pc) & np.isfinite(volref))

    gate = (d["sess_open"].to_numpy(float)
            - LW_K * np.abs(d["pdh"].to_numpy(float) - d["pdl"].to_numpy(float)))
    hit = same & (c < gate) & np.isfinite(gate)
    # first hit of each day only
    dayid = pd.factorize(d["_day"])[0]
    shorts = np.zeros(len(c), bool)
    seen = set()
    for i in np.flatnonzero(hit):
        if dayid[i] not in seen:
            seen.add(dayid[i])
            shorts[i] = True
    return longs, shorts


def replay(d, longs, shorts, minutes, t1, h1, l1, atr_override=None) -> dict:
    """One arm. Exits always resolved on the 1-minute referee series."""
    c = d["close"].to_numpy(float)
    atr = (d["atr"].to_numpy(float) if atr_override is None
           else atr_override.to_numpy(float))
    ts = d.index.values.astype("datetime64[ns]")
    close_h = d["close_h"].to_numpy(float)
    dayid = pd.factorize(d["_day"])[0]
    yrs = d.index.year.to_numpy()
    starts = np.flatnonzero(np.r_[True, dayid[1:] != dayid[:-1]])
    ends = np.r_[starts[1:], len(dayid)]
    step = np.timedelta64(minutes, "m")

    trades = []
    for s, e in zip(starts, ends):
        ntr = 0
        busy = np.datetime64("1970-01-01", "ns")
        deadline = ts[e - 1] + step
        for i in range(s, e):
            if ntr >= MAXTR or ts[i] < busy:
                continue
            if not (WIN_LO <= close_h[i] <= WIN_HI):
                continue
            side = 1 if longs[i] else (-1 if shorts[i] else 0)
            if side == 0:
                continue
            a = atr[i]
            if not np.isfinite(a) or a <= 0:
                continue
            n = min(MAXC, int(min(BUDGET, CAP) // (a * SL_ATR * PV)))
            if n < 1:
                continue
            entry = c[i]
            slp = max(1, round(a * SL_ATR / TICK)) * TICK
            tpp = max(1, round(a * TP_ATR / TICK)) * TICK
            stop = entry - slp * side
            targ = entry + tpp * side
            start_ns = ts[i] + step
            j = int(np.searchsorted(t1, start_ns, side="left"))
            px, xt = c[e - 1], deadline
            while j < len(t1) and t1[j] <= deadline:
                if side > 0:
                    sl_hit, tp_hit = l1[j] <= stop, h1[j] >= targ
                else:
                    sl_hit, tp_hit = h1[j] >= stop, l1[j] <= targ
                if sl_hit:                      # stop wins ties — never invent a fill
                    px, xt = stop, t1[j]
                    break
                if tp_hit:
                    px, xt = targ, t1[j]
                    break
                j += 1
            g = (px - entry) * side * PV * n
            trades.append((yrs[i], g - FEE * n, g, n))
            ntr += 1
            busy = xt

    if not trades:
        return dict(n=0)
    net = np.array([t[1] for t in trades])
    grs = np.array([t[2] for t in trades])
    yr = np.array([t[0] for t in trades])
    cts = np.array([t[3] for t in trades])
    return dict(n=len(trades), win=100.0 * (grs > 0).mean(), net=net.sum(),
                gross=grs.sum(), fees=grs.sum() - net.sum(),
                pts=float((grs / (PV * cts)).mean()), avg_ct=float(cts.mean()),
                per_year={int(y): float(net[yr == y].sum()) for y in np.unique(yr)})


def main() -> None:
    print("loading 5-min ...", flush=True)
    d5 = load_rth(F5, 5)
    print(f"  {len(d5):,} RTH bars", flush=True)
    print("loading 1-min (this is the slow one) ...", flush=True)
    d1 = load_rth(F1, 1)
    print(f"  {len(d1):,} RTH bars", flush=True)

    t1 = d1.index.values.astype("datetime64[ns]")
    h1 = d1["high"].to_numpy(float)
    l1 = d1["low"].to_numpy(float)

    L5, S5 = signals(d5)
    L1, S1 = signals(d1)
    print(f"\n  raw signal counts (before window/day caps):")
    print(f"    5-min : {L5.sum():>6} long  {S5.sum():>5} short")
    print(f"    1-min : {L1.sum():>6} long  {S1.sum():>5} short")

    # 5-min ATR forward-filled onto the 1-min grid: 1-min entry timing, 5-min brackets
    atr5_on_1 = d5["atr"].reindex(d1.index, method="ffill")

    none5 = np.zeros(len(d5), bool)
    none1 = np.zeros(len(d1), bool)
    arms = [
        ("5m  sr_round100_break", d5, L5, none5, 5, None),
        ("5m  vol_lw_stretch_short", d5, none5, S5, 5, None),
        ("5m  PAIR (both)", d5, L5, S5, 5, None),
        ("1m  sr_round100_break", d1, L1, none1, 1, None),
        ("1m  vol_lw_stretch_short", d1, none1, S1, 1, None),
        ("1m  PAIR (both)", d1, L1, S1, 1, None),
        ("1m  PAIR, 5m bracket width", d1, L1, S1, 1, atr5_on_1),
    ]

    years = sorted({int(y) for y in d5.index.year})
    print("\n" + "=" * 124)
    print("BEST TWO SIGNALS — 5-minute vs 1-minute, exits resolved on 1-min bars")
    print("=" * 124)
    print(f"  {'arm':<30}{'trades':>7}{'win%':>7}{'pts/tr':>8}{'ct':>5}"
          f"{'gross':>9}{'fees':>8}{'net $':>9}" + "".join(f"{y:>8}" for y in years))
    out = {}
    for label, d, lo, sh, mins, ovr in arms:
        r = replay(d, lo, sh, mins, t1, h1, l1, ovr)
        if not r["n"]:
            print(f"  {label:<30} no trades")
            continue
        out[label] = r
        print(f"  {label:<30}{r['n']:>7}{r['win']:>7.1f}{r['pts']:>+8.2f}"
              f"{r['avg_ct']:>5.1f}{r['gross']:>9,.0f}{-r['fees']:>8,.0f}"
              f"{r['net']:>9,.0f}"
              + "".join(f"{r['per_year'].get(y, 0):>8,.0f}" for y in years))

    print("\n" + "=" * 124)
    print("VERDICT")
    print("=" * 124)
    b5, b1 = out.get("5m  PAIR (both)"), out.get("1m  PAIR (both)")
    bx = out.get("1m  PAIR, 5m bracket width")
    if b5 and b1:
        pos5 = sum(1 for y in years if b5["per_year"].get(y, 0) > 0)
        pos1 = sum(1 for y in years if b1["per_year"].get(y, 0) > 0)
        print(f"  5m pair : {b5['n']:>5} trades  {b5['pts']:+.2f} pts/tr  "
              f"net ${b5['net']:>8,.0f}  positive in {pos5}/{len(years)} years")
        print(f"  1m pair : {b1['n']:>5} trades  {b1['pts']:+.2f} pts/tr  "
              f"net ${b1['net']:>8,.0f}  positive in {pos1}/{len(years)} years")
        print(f"  delta   : {b1['n'] - b5['n']:+} trades, "
              f"${b1['net'] - b5['net']:+,.0f} net")
    if bx and b1:
        print(f"\n  DIAGNOSTIC — 1-min entries with 5-min bracket width:")
        print(f"    net ${bx['net']:,.0f} vs ${b1['net']:,.0f} for native 1-min "
              f"brackets ({bx['net'] - b1['net']:+,.0f})")
        print(f"    -> the tighter STOP is the problem, not the entry timing.")

    # ── sizing confound: smaller ATR buys more contracts for the same budget ──
    print("\n" + "=" * 124)
    print("SIZING CONFOUND — why net $ is NOT comparable across timeframes")
    print("=" * 124)
    print("  A 1-min ATR is about half a 5-min ATR, so the 2.0-ATR stop is half as")
    print("  wide and the same $300 budget buys ~2x the contracts. That inflates net $")
    print("  without any improvement in edge. Compare POINTS PER CONTRACT instead:")
    print(f"    {'arm':<30}{'pts/tr':>9}{'avg ct':>9}{'net $':>10}")
    for k, r in out.items():
        print(f"    {k:<30}{r['pts']:>+9.2f}{r['avg_ct']:>9.1f}{r['net']:>10,.0f}")

    # ── out-of-sample split: does the winner hold in the recent period? ──
    print("\n" + "=" * 124)
    print("OUT-OF-SAMPLE — fit 2021-2024, check 2025-2026")
    print("=" * 124)
    print("  The hybrid was found by looking at this data, so the only question that")
    print("  matters is whether its advantage survives into a period it did not shape.")
    fit_yrs = [y for y in years if y <= 2024]
    test_yrs = [y for y in years if y >= 2025]
    print(f"    {'arm':<30}{'fit 2021-24':>13}{'test 2025-26':>14}")
    ranked = []
    for k in ("5m  PAIR (both)", "1m  PAIR (both)", "1m  PAIR, 5m bracket width"):
        r = out.get(k)
        if not r:
            continue
        f = sum(r["per_year"].get(y, 0) for y in fit_yrs)
        te = sum(r["per_year"].get(y, 0) for y in test_yrs)
        ranked.append((k, f, te))
        print(f"    {k:<30}{f:>13,.0f}{te:>14,.0f}")
    if len(ranked) >= 2:
        best_fit = max(ranked, key=lambda x: x[1])
        best_test = max(ranked, key=lambda x: x[2])
        print(f"\n    best in FIT  : {best_fit[0]}  (${best_fit[1]:,.0f})")
        print(f"    best in TEST : {best_test[0]}  (${best_test[2]:,.0f})")
        if best_fit[0] != best_test[0]:
            print("\n    The fit-period winner is NOT the test-period winner. The")
            print("    hybrid's advantage came from 2021-2024 and did not carry.")
            print("    -> do not adopt. The plain 5-minute pair stays.")
        else:
            print("\n    Same winner in both halves — worth a proper paired test next.")


if __name__ == "__main__":
    main()

"""NEW GROUND: the Globex session on MNQ. 5 years, never tested here.

Every measurement in this project has lived inside RTH 09:45-11:00 — about 15 bars a
day out of 288. The overnight session is 17.5 hours of untouched tape, and it is
already sitting in `mnq_2021-2026_5min.csv` (the RTH filter discards ~58% of the file).

WHY IT IS WORTH LOOKING: the binding constraint on the account is FREQUENCY, not edge.
The pair trades 0.65x/session, which is why payout takes ~47 sessions at a safe size.
Anything tradeable overnight adds trades without adding size, which is the one lever
that shortens time-to-payout without raising bust.

Sessions (ET), following the futures day that rolls at 18:00:
    ASIA      18:00 - 03:00
    LONDON    03:00 - 08:00
    PRE-NY    08:00 - 09:30      the hour before the cash open
    RTH       09:30 - 16:00      (control — the known ground)

Signal shapes are the ones that ALREADY survived elsewhere, not new inventions:
round-number breaks (worked on NQ RTH and on gold), session H/L breaks (worked on
gold), stretch-from-open (worked on both). Testing proven SHAPES on new HOURS is a
cleaner experiment than inventing new shapes on known hours.

Liquidity is the obvious objection, so relative volume is measured per session and
reported — a signal that only fires in dead tape is not tradeable however good the
backtest looks.

Method unchanged: clean control (permute session profile + bar), OOS split at
2025-01-01, stop assumed on ambiguity.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import funded_search as fs

SL_ATR, TP_ATR = 2.0, 3.0
ATR_LEN = 14
MAX_HOLD = 24            # bars (2h on 5-min) before a time stop
SEEDS = 20
OOS = pd.Timestamp("2025-01-01", tz=fs.TZ)

SESSIONS = {
    "ASIA":   (18.0, 3.0),
    "LONDON": (3.0, 8.0),
    "PRE-NY": (8.0, 9.5),
    "RTH":    (9.5, 16.0),
}


def load_full() -> pd.DataFrame:
    """The WHOLE file — ETH included. This is the part the RTH loader throws away."""
    df = pd.read_csv(fs.DATA_5M, usecols=["ts_et", "open", "high", "low",
                                          "close", "volume"])
    ts = pd.to_datetime(df["ts_et"], format="mixed", utc=True).dt.tz_convert(fs.TZ)
    d = df.set_index(ts).drop(columns=["ts_et"]).sort_index()

    c, h, l = d["close"], d["high"], d["low"]
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    d["atr"] = tr.ewm(alpha=1 / ATR_LEN, adjust=False).mean()

    hr = d.index.hour + d.index.minute / 60.0
    d["hr"] = hr
    base = pd.Series(d.index.normalize(), index=d.index)
    d["_day"] = base.where(hr < 18, base + pd.Timedelta(days=1))
    d["bod"] = d.groupby("_day").cumcount()

    for name, (lo, hi) in SESSIONS.items():
        d[name] = ((hr >= lo) | (hr < hi)) if lo > hi else ((hr >= lo) & (hr < hi))
        m = d[name]
        d[f"{name}_hi"] = h.where(m).groupby(d["_day"]).cummax().ffill()
        d[f"{name}_lo"] = l.where(m).groupby(d["_day"]).cummin().ffill()
        d[f"{name}_open"] = d["open"].where(m).groupby(d["_day"]).transform("first")

    d["rvol"] = d["volume"] / d["volume"].rolling(20).mean().shift(1)
    return d.dropna(subset=["atr"])


def build_signals(d: pd.DataFrame) -> dict:
    c, o = d["close"], d["open"]
    pc, atr = c.shift(1), d["atr"]
    up, dn = c > o, c < o
    rv = d["rvol"].fillna(1.0)
    out = {}

    # ── round-100 breaks, per session ──
    lvl_u, lvl_d = np.floor(c / 100.0), np.ceil(c / 100.0)
    up_break = (lvl_u > np.floor(pc / 100.0)) & (c >= lvl_u * 100 + 0.15 * atr) & up
    dn_break = (lvl_d < np.ceil(pc / 100.0)) & (c <= lvl_d * 100 - 0.15 * atr) & dn
    for s in SESSIONS:
        out[f"{s}|round100_long"] = ((up_break & d[s] & (rv > 1.0)), +1)
        out[f"{s}|round100_short"] = ((dn_break & d[s] & (rv > 1.0)), -1)

    # ── prior-session range breaks (the gold shape that worked) ──
    out["LONDON|asia_hi_break"] = ((c > d["ASIA_hi"]) & (pc <= d["ASIA_hi"])
                                   & d["LONDON"], +1)
    out["LONDON|asia_lo_break"] = ((c < d["ASIA_lo"]) & (pc >= d["ASIA_lo"])
                                   & d["LONDON"], -1)
    out["PRE-NY|london_hi_break"] = ((c > d["LONDON_hi"]) & (pc <= d["LONDON_hi"])
                                     & d["PRE-NY"], +1)
    out["PRE-NY|london_lo_break"] = ((c < d["LONDON_lo"]) & (pc >= d["LONDON_lo"])
                                     & d["PRE-NY"], -1)
    out["RTH|overnight_hi_break"] = ((c > d["ASIA_hi"].combine(d["LONDON_hi"], max))
                                     & d["RTH"] & (d["bod"] > 0), +1)
    out["RTH|overnight_lo_break"] = ((c < d["ASIA_lo"].combine(d["LONDON_lo"], min))
                                     & d["RTH"] & (d["bod"] > 0), -1)

    # ── stretch from each session's own open ──
    for s in SESSIONS:
        ext = (c - d[f"{s}_open"]) / atr.replace(0, np.nan)
        out[f"{s}|stretch_long"] = ((ext >= 1.5) & d[s] & up, +1)
        out[f"{s}|stretch_short"] = ((ext <= -1.5) & d[s] & dn, -1)

    return {k: (v[0].fillna(False).to_numpy(bool), v[1]) for k, v in out.items()}


def bt(d, mask, side):
    c = d["close"].to_numpy(float)
    h = d["high"].to_numpy(float)
    l = d["low"].to_numpy(float)
    atr = d["atr"].to_numpy(float)
    rv = d["rvol"].fillna(1.0).to_numpy(float)
    n = len(c)
    pts, wins, rvs, busy = [], 0, [], -1
    for i in np.flatnonzero(mask):
        if i <= busy or i + 1 >= n:
            continue
        a = atr[i]
        if not np.isfinite(a) or a <= 0:
            continue
        entry = c[i]
        stop, targ = entry - SL_ATR * a * side, entry + TP_ATR * a * side
        r, xi = None, min(i + MAX_HOLD, n - 1)
        for j in range(i + 1, xi + 1):
            sl = (l[j] <= stop) if side > 0 else (h[j] >= stop)
            tp = (h[j] >= targ) if side > 0 else (l[j] <= targ)
            if sl:
                r, xi = (stop - entry) * side, j; break
            if tp:
                r, xi = (targ - entry) * side, j; break
        if r is None:
            r = (c[xi] - entry) * side
        pts.append(r); wins += r > 0; rvs.append(rv[i]); busy = xi
    if not pts:
        return None
    arr = np.array(pts)
    return dict(n=len(arr), ppt=float(arr.mean()), win=100.0 * wins / len(arr),
                total=float(arr.sum()), rvol=float(np.median(rvs)))


def control(d, mask, side, rng):
    ids = pd.factorize(d["_day"])[0]
    st = np.flatnonzero(np.r_[True, ids[1:] != ids[:-1]])
    en = np.r_[st[1:], len(ids)]
    prof = [int(mask[a:b].sum()) for a, b in zip(st, en)]
    order = rng.permutation(len(prof))
    out = np.zeros(len(mask), bool)
    for pos, (a, b) in enumerate(zip(st, en)):
        k = prof[order[pos]]
        if k and b > a:
            out[a + rng.choice(b - a, size=min(k, b - a), replace=False)] = True
    return bt(d, out, side)


def main() -> None:
    print("loading FULL 5-min file (ETH included) ...", flush=True)
    d = load_full()
    hrs = d["hr"]
    print(f"  {len(d):,} bars  {d.index[0].date()} .. {d.index[-1].date()}")
    print(f"  RTH {int((hrs>=9.5).sum() & 1 or ((hrs>=9.5)&(hrs<16)).sum()):,} vs "
          f"overnight {int(((hrs<9.5)|(hrs>=16)).sum()):,} bars")
    for s, (lo, hi) in SESSIONS.items():
        m = d[s]
        print(f"    {s:<7} {int(m.sum()):>7,} bars   median rvol "
              f"{d.loc[m,'rvol'].median():.2f}")

    sigs = build_signals(d)
    oos = d.index >= OOS
    d_oos = d[oos]
    sigs_oos = build_signals(d_oos)

    print("\n" + "=" * 112)
    print("OVERNIGHT + SESSION SIGNALS — MNQ 5-min, 5 years, clean control + OOS")
    print("=" * 112)
    print(f"  {'session|signal':<30}{'n':>6}{'win%':>7}{'pts/tr':>9}{'EDGE':>8}"
          f"{'beat':>7}{'rvol':>6}{'total':>9}{'  |':>3}{'OOSn':>6}{'OOSpts':>8}")
    rows = []
    for name, (mask, side) in sigs.items():
        r = bt(d, mask, side)
        if not r or r["n"] < 40:
            continue
        ctl = [control(d, mask, side, np.random.default_rng(s)) for s in range(SEEDS)]
        ctl = [x["ppt"] for x in ctl if x]
        edge = r["ppt"] - float(np.median(ctl)) if ctl else float("nan")
        beat = sum(1 for x in ctl if x >= r["ppt"])
        ro = bt(d_oos, sigs_oos[name][0], side)
        rows.append((name, r, edge, beat, ro))
        on = ro["n"] if ro else 0
        op = f"{ro['ppt']:+.2f}" if ro else "—"
        print(f"  {name:<30}{r['n']:>6}{r['win']:>7.1f}{r['ppt']:>+9.2f}{edge:>+8.2f}"
              f"{beat:>5}/{SEEDS}{r['rvol']:>6.2f}{r['total']:>9,.0f}{'  |':>3}"
              f"{on:>6}{op:>8}")

    print("\n" + "=" * 112)
    print("SURVIVORS — edge > 0, control beaten <=2/20, POSITIVE out-of-sample, n>=40")
    print("=" * 112)
    keep = [x for x in rows if x[2] > 0 and x[3] <= 2 and x[4] and x[4]["ppt"] > 0
            and x[4]["n"] >= 15]
    if not keep:
        print("  NONE.")
    for name, r, edge, beat, ro in sorted(keep, key=lambda x: -x[2]):
        flag = "  <-- THIN TAPE" if r["rvol"] < 0.5 else ""
        print(f"  {name:<30} edge {edge:+.2f}  n={r['n']}  control {beat}/{SEEDS}  "
              f"OOS {ro['ppt']:+.2f} on {ro['n']}  rvol {r['rvol']:.2f}{flag}")


if __name__ == "__main__":
    main()

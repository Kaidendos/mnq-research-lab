"""New search axes: BAR TIMEFRAME and EXIT LOGIC.

Every prior sweep in this project used 5-minute bars and a fixed ATR bracket
(stop = k*ATR, target = m*ATR, first touch wins). Those are two unexplored
dimensions, and the current regime argues both matter:

  * Volatility roughly doubled (5-min ATR 25.9 -> 51.0 pts) while net direction
    went flat. In a choppy, high-noise tape, slower bars filter noise that a
    5-minute stop keeps getting clipped by.
  * Median daily range is 451 pts with body/range down at 44%. Big ranges, no
    progress: that punishes fixed targets and rewards exits that either bank
    quickly or ride with a trail.

Timeframes : 5m (baseline), 15m, 30m — resampled from the same 1-min-derived data.
Exits      : bracket (baseline) | time stop | trailing | breakeven-then-run |
             partial scale-out | end-of-day only

Everything is scored with the honest metrics (sequential episodes, calendar days).
"""
from __future__ import annotations

import argparse
import itertools

import numpy as np
import pandas as pd

import funded_search as fs
import funded_1yr as f1

PV, FEE, TICK = 2.0, 1.22, 0.25


# ───────────────────────── timeframe ─────────────────────────
def resample(df5: pd.DataFrame, minutes: int) -> pd.DataFrame:
    """Rebuild bars + indicators at a slower timeframe from the 5-min RTH frame."""
    if minutes == 5:
        return df5
    o = df5.resample(f"{minutes}min", origin="start_day", label="left", closed="left").agg(
        open=("open", "first"), high=("high", "max"), low=("low", "min"),
        close=("close", "last"), volume=("volume", "sum")).dropna(subset=["open"])
    hrs = o.index.hour + o.index.minute / 60.0
    o = o[(hrs >= 9.5) & (hrs < 16.0)].copy()
    c, h, l = o["close"], o["high"], o["low"]
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    o["atr"] = tr.ewm(alpha=1 / 14, adjust=False).mean()
    ll, hh = l.rolling(14).min(), h.rolling(14).max()
    o["stochK"] = np.where((hh - ll) > 0, 100 * (c - ll) / (hh - ll), np.nan)
    for n in (9, 20, 50):
        o[f"ema{n}"] = c.ewm(span=n, adjust=False).mean()
    o["eth"] = o.index.hour + o.index.minute / 60.0
    o["_day"] = o.index.normalize()
    day = o["_day"]
    tp_ = (h + l + c) / 3.0
    o["vwap"] = (tp_ * o["volume"]).groupby(day).cumsum() / o["volume"].groupby(day).cumsum()
    dc = c.groupby(day).last()
    ema50d = dc.ewm(span=50, adjust=False).mean()
    o["gate_ema50"] = pd.Series(day, index=o.index).map((dc > ema50d).shift(1).fillna(False)).astype(bool)
    return o.dropna(subset=["atr"])


# ───────────────────────── exits ─────────────────────────
def replay_exit(df, entry, side, sl, tp, win, gate, cap, budget, exit_mode,
                maxc=5, max_trades=6, tstop_bars=12, trail_atr=1.0, be_at=1.0,
                scale_at=1.0, scale_frac=0.5):
    """Funded replay with pluggable exit logic. Returns (daily Series, ntr, nwin)."""
    hi, lo, cl = df["high"].values, df["low"].values, df["close"].values
    atr, eth = df["atr"].values, df["eth"].values
    ent = np.asarray(entry, dtype=bool)
    gate_arr = df[gate].values if gate else np.ones(len(df), bool)
    dayid = df["_day"].values
    ws, we = win
    starts = np.flatnonzero(np.r_[True, dayid[1:] != dayid[:-1]])
    ends = np.r_[starts[1:], len(df)]

    out, tot_tr, tot_win = {}, 0, 0
    for s, e in zip(starts, ends):
        if not gate_arr[s]:
            continue
        net, ntr, day_won, pos = 0.0, 0, False, None
        for i in range(s, e):
            last = i == e - 1
            if pos is not None:
                px = None
                held = i - pos["i"]
                if side > 0:
                    if lo[i] <= pos["sl"]: px = pos["sl"]
                    elif hi[i] >= pos["tp"]: px = pos["tp"]
                else:
                    if hi[i] >= pos["sl"]: px = pos["sl"]
                    elif lo[i] <= pos["tp"]: px = pos["tp"]
                if px is None and exit_mode == "time" and held >= tstop_bars:
                    px = cl[i]
                if px is None and exit_mode in ("trail", "be", "scale"):
                    fav = side * (cl[i] - pos["entry"]) / pos["a"]
                    if exit_mode == "trail":
                        newsl = cl[i] - side * trail_atr * pos["a"]
                        pos["sl"] = max(pos["sl"], newsl) if side > 0 else min(pos["sl"], newsl)
                    elif exit_mode == "be" and fav >= be_at and not pos["moved"]:
                        pos["sl"] = pos["entry"]; pos["moved"] = True
                    elif exit_mode == "scale" and fav >= scale_at and not pos["moved"]:
                        part = int(pos["n"] * scale_frac)
                        if part >= 1:
                            net += side * (cl[i] - pos["entry"]) * PV * part - FEE * part
                            pos["n"] -= part
                        pos["sl"] = pos["entry"]; pos["moved"] = True
                if px is None and (eth[i] >= 16.0 or last):
                    px = cl[i]
                if px is not None:
                    pnl = side * (px - pos["entry"]) * PV * pos["n"] - FEE * pos["n"]
                    net += pnl; ntr += 1; tot_tr += 1
                    if pnl > 0: tot_win += 1
                    if net > 0: day_won = True
                    pos = None
            if (pos is None and not last and not day_won and ent[i]
                    and ws <= eth[i] <= we and atr[i] > 0 and not np.isnan(atr[i])
                    and ntr < max_trades):
                a = atr[i]
                stop_usd = a * sl * PV
                n = min(maxc, int((budget + net) / stop_usd),
                        int((cap - net) / max(a * tp * PV, 1e-9)))
                if n < 1:
                    continue
                big = 999999.0
                pos = dict(entry=cl[i], n=n, a=a, i=i, moved=False,
                           sl=cl[i] - side * a * sl,
                           tp=(cl[i] + side * a * tp) if exit_mode not in ("trail", "eod")
                               else (cl[i] + side * big))
        if ntr > 0:
            out[df.index[s].normalize()] = net
    return pd.Series(out).sort_index(), tot_tr, tot_win


EXITS = ("bracket", "time", "trail", "be", "scale", "eod")
TFS = (5, 15, 30)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prefix", default="so_")
    ap.add_argument("--months", type=int, default=5)
    ap.add_argument("--slice", default=None)
    ap.add_argument("--out", default="tfx.csv")
    args = ap.parse_args()

    df5 = fs.load_enriched()
    plugins = f1.load_plugins(df5)
    names = [n for n in (fs.FAMILIES + list(plugins)) if n.startswith(args.prefix)]
    if args.slice:
        i, n = (int(x) for x in args.slice.split("/"))
        names = names[i::n]

    end = df5.index[-1]
    w = end - pd.DateOffset(months=args.months)
    frames = {tf: resample(df5, tf) for tf in TFS}
    print(f"{len(names)} families | timeframes {TFS} | window {w:%Y-%m-%d} -> {end:%Y-%m-%d}",
          flush=True)

    SLS, TPS = (1.0, 1.5, 2.0), (1.0, 1.5, 2.0, 3.0)
    WINS = ((10.0, 13.0), (10.0, 12.0), (9.75, 15.5))
    SIZES = ((200, 200, 3), (300, 300, 5), (440, 300, 10))

    rows = []
    for nm in names:
        for tf in TFS:
            d = frames[tf]
            try:
                ent, side = (plugins[nm] if nm in plugins else fs.sig(df5, nm))
            except Exception:
                continue
            ent = pd.Series(ent).reindex(df5.index).fillna(False)
            # map the 5-min signal onto slower bars: fire on the slow bar that contains it
            if tf != 5:
                grp = ent.groupby(pd.Grouper(freq=f"{tf}min", origin="start_day")).max()
                e_tf = grp.reindex(d.index).fillna(False).astype(bool)
            else:
                e_tf = ent.reindex(d.index).fillna(False).astype(bool)
            sel = d[d.index >= w]
            hold = d[d.index < w]
            if len(sel) < 200:
                continue
            span_s = (sel.index[-1] - sel.index[0]).days
            span_h = (hold.index[-1] - hold.index[0]).days
            for xm, sl, tp, win, (cap, bud, mc) in itertools.product(
                    EXITS, SLS, TPS, WINS, SIZES):
                r = dict(family=nm, tf=tf, exit=xm, sl=sl, tp=tp,
                         win=f"{win[0]}-{win[1]}", cap=cap, maxc=mc)
                for tag, dd, sp in (("sel", sel, span_s), ("hold", hold, span_h)):
                    ee = e_tf.reindex(dd.index).fillna(False)
                    daily, ntr, nwin = replay_exit(dd, ee, side, sl, tp, win, None,
                                                   cap, bud, xm, maxc=mc)
                    m = f1.score(daily, sp)
                    r[f"{tag}_net"] = m["net"]; r[f"{tag}_pay"] = m["payouts"]
                    r[f"{tag}_bust"] = m["bust_pct"]; r[f"{tag}_cal"] = m["cal_per_payout"]
                    r[f"{tag}_tr"] = ntr
                    r[f"{tag}_win"] = round(100 * nwin / ntr, 1) if ntr else 0.0
                rows.append(r)
        print(f"  done {nm}", flush=True)

    out = pd.DataFrame(rows)
    out.to_csv(args.out, index=False)
    print(f"\n{len(out):,} configs -> {args.out}")


if __name__ == "__main__":
    main()

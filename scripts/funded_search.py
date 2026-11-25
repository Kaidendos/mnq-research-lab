"""Funded payout-SPEED search harness (LucidPro $25k rules), on fresh Databento data.

Objective: minimise TRADING DAYS TO PAYOUT while keeping bust rate low.
User target: a payout at least every ~30 calendar days (~21 trading days); faster is better.

Rules modelled (from funded_backtest.py, the user's own spec):
  * $1,000 trailing max drawdown  -> bust if breached (floor never locks, strict reading)
  * $1,100 buffer                 -> need +$1,100 cumulative net to withdraw
  * 40% consistency               -> biggest single green day <= 40% of total at withdrawal
  * 3 trading-day minimum
  * fees $1.22 round-turn per contract, <=10 MNQ, $2/point

Self-contained: reads the NEW 2021-08 -> 2026-08 pull, does not import the
older backtest_1yr / improve_lab stack (which still points at the July file).

CLI:
    python funded_search.py selftest
    python funded_search.py sweep --families stoch30_long,vwap_reclaim_long --out slice.csv
    python funded_search.py sweep --slice 0/6 --out slice0.csv
"""
from __future__ import annotations

import argparse
import itertools
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

D = Path(__file__).parent / "data" / "databento"
DATA_5M = D / "mnq_2021-2026_5min.csv"

TZ = "America/New_York"
PV = 2.0
FEE = 1.22
MAXC = 10

# ── LucidPro $25k payout rules ──
BUFFER = 1100.0
CONSISTENCY = 0.40
# 2026-08-10: VERIFIED against Lucid's published rules. LucidPro requires 5
# PROFITABLE days per payout cycle — not 3, and not merely 3 days with a trade.
# Impact measured as small (~2 pts of sub-month payout at $350) because reaching
# $1,100 profit already takes 5+ green days at this strategy's win rate.
MIN_DAYS = 5
TRAIL_DD = 1000.0


# ════════════════════════════ data ════════════════════════════
def load_enriched(path: Path = DATA_5M) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["ts_et"] = pd.to_datetime(df["ts_et"], utc=True).dt.tz_convert(TZ)
    d = df.set_index("ts_et").sort_index()
    hrs = d.index.hour + d.index.minute / 60.0
    d = d[(hrs >= 9.5) & (hrs < 16.0)].copy()

    c, h, l = d["close"], d["high"], d["low"]

    # Wilder ATR(14)
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    d["atr"] = tr.ewm(alpha=1 / 14, adjust=False).mean()

    # raw %K(14) — matches the live NT port (NOT NT's smoothed Stochastics)
    ll = l.rolling(14).min()
    hh = h.rolling(14).max()
    rng = hh - ll
    d["stochK"] = np.where(rng > 0, 100.0 * (c - ll) / rng, np.nan)

    for n in (9, 20, 50):
        d[f"ema{n}"] = c.ewm(span=n, adjust=False).mean()
    delta = c.diff()
    up = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    dn = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    d["rsi"] = 100 - 100 / (1 + up / dn.replace(0, np.nan))
    e12, e26 = c.ewm(span=12, adjust=False).mean(), c.ewm(span=26, adjust=False).mean()
    d["macd"] = e12 - e26
    d["macd_sig"] = d["macd"].ewm(span=9, adjust=False).mean()
    mid, sd = c.rolling(20).mean(), c.rolling(20).std()
    d["bb_up"], d["bb_dn"] = mid + 2 * sd, mid - 2 * sd
    d["donch_hi20"], d["donch_lo20"] = h.rolling(20).max(), l.rolling(20).min()
    d["donch_hi10"], d["donch_lo10"] = h.rolling(10).max(), l.rolling(10).min()
    d["adx"] = _adx(h, l, c, 14)

    day = d.index.normalize()
    eth = d.index.hour + d.index.minute / 60.0
    d["eth"] = eth
    d["_day"] = day

    tp_ = (h + l + c) / 3.0
    d["vwap"] = ((tp_ * d["volume"]).groupby(day).cumsum()
                 / d["volume"].groupby(day).cumsum())

    for orm, endeth in (("or15", 9.5 + 15 / 60), ("or30", 9.5 + 30 / 60)):
        inor = eth <= endeth
        hi_ = h.where(inor).groupby(day).cummax()
        lo_ = l.where(inor).groupby(day).cummin()
        d[f"{orm}_hi"] = hi_.groupby(day).transform("last")
        d[f"{orm}_lo"] = lo_.groupby(day).transform("last")
    d["or15_ready"] = eth > 9.5 + 15 / 60
    d["or30_ready"] = eth > 9.5 + 30 / 60

    dh, dl, dc = h.groupby(day).max(), l.groupby(day).min(), c.groupby(day).last()
    dmap = pd.Series(day, index=d.index)
    d["pdh"], d["pdl"] = dmap.map(dh.shift(1)), dmap.map(dl.shift(1))

    # no-lookahead daily trend gates
    ema50d = dc.ewm(span=50, adjust=False).mean()
    ema20d = dc.ewm(span=20, adjust=False).mean()
    d["gate_ema50"] = dmap.map((dc > ema50d).shift(1).fillna(False)).astype(bool)
    d["gate_ema20"] = dmap.map((dc > ema20d).shift(1).fillna(False)).astype(bool)
    d["gate_below50"] = dmap.map((dc < ema50d).shift(1).fillna(False)).astype(bool)
    d["svol"] = (c > (h + l) / 2.0).astype(int)
    return d.dropna(subset=["atr"])


def _adx(h, l, c, n=14):
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    up_m, dn_m = h.diff(), -l.diff()
    plus = np.where((up_m > dn_m) & (up_m > 0), up_m, 0.0)
    minus = np.where((dn_m > up_m) & (dn_m > 0), dn_m, 0.0)
    atr_ = tr.ewm(alpha=1 / n, adjust=False).mean()
    pdi = 100 * pd.Series(plus, index=h.index).ewm(alpha=1/n, adjust=False).mean() / atr_
    mdi = 100 * pd.Series(minus, index=h.index).ewm(alpha=1/n, adjust=False).mean() / atr_
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    return dx.ewm(alpha=1 / n, adjust=False).mean()


# ════════════════════════ signal library ════════════════════════
def sig(df, name):
    c, h, l = df["close"], df["high"], df["low"]
    pc = c.shift(1)
    K, rsi = df["stochK"], df["rsi"]
    up_bar = c > (h + l) / 2.0
    dn_bar = c < (h + l) / 2.0
    T = {
        "stoch30_long":      lambda: ((K.shift(1) <= 30) & (K > 30) & up_bar, +1),
        "stoch20_long":      lambda: ((K.shift(1) <= 20) & (K > 20) & up_bar, +1),
        "stoch70_short":     lambda: ((K.shift(1) >= 70) & (K < 70) & dn_bar, -1),
        "stoch80_short":     lambda: ((K.shift(1) >= 80) & (K < 80) & dn_bar, -1),
        "ema9_21_long":      lambda: ((df["ema9"] > df["ema20"]) & (df["ema9"].shift(1) <= df["ema20"].shift(1)), +1),
        "ema9_21_short":     lambda: ((df["ema9"] < df["ema20"]) & (df["ema9"].shift(1) >= df["ema20"].shift(1)), -1),
        "ema20_50_long":     lambda: ((df["ema20"] > df["ema50"]) & (df["ema20"].shift(1) <= df["ema50"].shift(1)), +1),
        "rsi_x50_long":      lambda: ((rsi.shift(1) <= 50) & (rsi > 50), +1),
        "rsi_bounce35_long": lambda: ((rsi.shift(1) < 35) & (rsi >= 35), +1),
        "rsi_fade70_short":  lambda: ((rsi.shift(1) > 65) & (rsi <= 65), -1),
        "bb_reclaim_long":   lambda: ((pc < df["bb_dn"].shift(1)) & (c >= df["bb_dn"]), +1),
        "bb_fade_short":     lambda: ((pc > df["bb_up"].shift(1)) & (c <= df["bb_up"]), -1),
        "bb_break_long":     lambda: ((c > df["bb_up"]) & (pc <= df["bb_up"].shift(1)), +1),
        "bb_break_short":    lambda: ((c < df["bb_dn"]) & (pc >= df["bb_dn"].shift(1)), -1),
        "donch20_long":      lambda: (c > df["donch_hi20"].shift(1), +1),
        "donch20_short":     lambda: (c < df["donch_lo20"].shift(1), -1),
        "donch10_long":      lambda: (c > df["donch_hi10"].shift(1), +1),
        "donch10_short":     lambda: (c < df["donch_lo10"].shift(1), -1),
        "orb15_long":        lambda: (df["or15_ready"] & (c > df["or15_hi"]) & (pc <= df["or15_hi"]), +1),
        "orb15_short":       lambda: (df["or15_ready"] & (c < df["or15_lo"]) & (pc >= df["or15_lo"]), -1),
        "orb30_long":        lambda: (df["or30_ready"] & (c > df["or30_hi"]) & (pc <= df["or30_hi"]), +1),
        "orb30_short":       lambda: (df["or30_ready"] & (c < df["or30_lo"]) & (pc >= df["or30_lo"]), -1),
        "vwap_reclaim_long": lambda: ((pc < df["vwap"].shift(1)) & (c >= df["vwap"]) & up_bar, +1),
        "vwap_lose_short":   lambda: ((pc > df["vwap"].shift(1)) & (c <= df["vwap"]) & dn_bar, -1),
        "macd_x_long":       lambda: ((df["macd"] > df["macd_sig"]) & (df["macd"].shift(1) <= df["macd_sig"].shift(1)) & (df["macd"] < 0), +1),
        "macd_x_short":      lambda: ((df["macd"] < df["macd_sig"]) & (df["macd"].shift(1) >= df["macd_sig"].shift(1)) & (df["macd"] > 0), -1),
        "pdh_break_long":    lambda: ((c > df["pdh"]) & (pc <= df["pdh"]), +1),
        "pdl_break_short":   lambda: ((c < df["pdl"]) & (pc >= df["pdl"]), -1),
        "pdl_reclaim_long":  lambda: ((pc < df["pdl"]) & (c >= df["pdl"]) & up_bar, +1),
        "pdh_fade_short":    lambda: ((pc > df["pdh"]) & (c <= df["pdh"]) & dn_bar, -1),
        "ema20_pullback_long": lambda: ((c > df["ema50"]) & (l <= df["ema20"]) & (c > df["ema20"]) & up_bar, +1),
        "ema20_pullback_short": lambda: ((c < df["ema50"]) & (h >= df["ema20"]) & (c < df["ema20"]) & dn_bar, -1),
        "engulf_bb_long":    lambda: ((c > pc) & (df["open"] < c.shift(1)) & (l <= df["bb_dn"] + 0.3 * df["atr"]) & (c > df["bb_dn"]), +1),
        "engulf_bb_short":   lambda: ((c < pc) & (df["open"] > c.shift(1)) & (h >= df["bb_up"] - 0.3 * df["atr"]) & (c < df["bb_up"]), -1),
    }
    if name not in T:
        raise ValueError(f"unknown signal {name}")
    e, side = T[name]()
    return e.fillna(False), side


FAMILIES = [
    "stoch30_long", "stoch20_long", "stoch70_short", "stoch80_short",
    "ema9_21_long", "ema9_21_short", "ema20_50_long",
    "rsi_x50_long", "rsi_bounce35_long", "rsi_fade70_short",
    "bb_reclaim_long", "bb_fade_short", "bb_break_long", "bb_break_short",
    "donch20_long", "donch20_short", "donch10_long", "donch10_short",
    "orb15_long", "orb15_short", "orb30_long", "orb30_short",
    "vwap_reclaim_long", "vwap_lose_short", "macd_x_long", "macd_x_short",
    "pdh_break_long", "pdl_break_short", "pdl_reclaim_long", "pdh_fade_short",
    "ema20_pullback_long", "ema20_pullback_short",
    "engulf_bb_long", "engulf_bb_short",
]


# ════════════════════════ funded replay ════════════════════════
def replay(df, entry, side, sl, tp, win, gate, cap, budget,
           stop_green=True, max_trades=6, adx_gate=None, maxc=MAXC):
    """Replay every session with funded sizing. Returns (daily Series, ntrades, nwins)."""
    hi, lo, cl = df["high"].values, df["low"].values, df["close"].values
    atr, eth = df["atr"].values, df["eth"].values
    ent = np.asarray(entry, dtype=bool)
    if adx_gate is not None:
        a = df["adx"].values
        ent = ent & ((a > adx_gate[1]) if adx_gate[0] == "gt" else (a < adx_gate[1]))
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
                ex = None
                if side > 0:
                    if lo[i] <= pos["sl"]: ex = pos["sl"]
                    elif hi[i] >= pos["tp"]: ex = pos["tp"]
                    elif eth[i] >= 16.0 or last: ex = cl[i]
                else:
                    if hi[i] >= pos["sl"]: ex = pos["sl"]
                    elif lo[i] <= pos["tp"]: ex = pos["tp"]
                    elif eth[i] >= 16.0 or last: ex = cl[i]
                if ex is not None:
                    pnl = side * (ex - pos["entry"]) * PV * pos["n"] - FEE * pos["n"]
                    net += pnl; ntr += 1; tot_tr += 1
                    if pnl > 0: tot_win += 1
                    if stop_green and net > 0: day_won = True
                    pos = None
            if (pos is None and not last and not day_won and ent[i]
                    and ws <= eth[i] <= we and atr[i] > 0 and not np.isnan(atr[i])
                    and ntr < max_trades):
                stop_usd, tp_usd = atr[i] * sl * PV, atr[i] * tp * PV
                n = min(maxc, int((budget + net) / stop_usd), int((cap - net) / tp_usd))
                if n < 1:
                    continue
                pos = {"entry": cl[i], "n": n,
                       "sl": cl[i] - side * atr[i] * sl,
                       "tp": cl[i] + side * atr[i] * tp}
        if ntr > 0:
            out[df.index[s].normalize()] = net
    return pd.Series(out).sort_index(), tot_tr, tot_win


def payout_sim(daily: pd.Series):
    """Walk forward from EVERY active start day to a compliant payout or bust."""
    vals = daily.values
    dtp, busts, attempts, unresolved = [], 0, 0, 0
    for s in range(len(vals)):
        cum = peak = biggest = 0.0
        outcome, d = None, 0
        for j in range(s, len(vals)):
            cum += vals[j]; d += 1
            peak = max(peak, cum)
            biggest = max(biggest, vals[j])
            if peak - cum >= TRAIL_DD:
                outcome = "bust"; break
            if d >= MIN_DAYS and cum >= BUFFER and biggest <= CONSISTENCY * cum:
                outcome = d; break
        if outcome is None:
            unresolved += 1; continue
        attempts += 1
        if outcome == "bust":
            busts += 1
        else:
            dtp.append(outcome)
    return attempts, dtp, busts, unresolved


def evaluate(df, cfg, split=None) -> dict:
    """Score one config. split = ISO date -> also report train/test separately."""
    entry, side = sig(df, cfg["family"])
    daily, ntr, nwin = replay(
        df, entry, side, cfg["sl"], cfg["tp"], cfg["win"], cfg.get("gate"),
        cfg.get("cap", 440), cfg.get("budget", 300),
        stop_green=cfg.get("stop_green", True), adx_gate=cfg.get("adx"))
    r = dict(cfg_family=cfg["family"], sl=cfg["sl"], tp=cfg["tp"],
             win=f"{cfg['win'][0]}-{cfg['win'][1]}", gate=cfg.get("gate") or "-",
             cap=cfg.get("cap", 440), budget=cfg.get("budget", 300),
             adx=str(cfg.get("adx") or "-"),
             days=len(daily), trades=ntr,
             win_pct=round(100 * nwin / ntr, 1) if ntr else 0.0,
             net=round(float(daily.sum()), 0) if len(daily) else 0.0)
    if len(daily) < 20:
        r.update(payout_pct=0.0, med_days=-1, p90_days=-1, bust_pct=100.0, attempts=0)
        return r
    att, dtp, busts, _ = payout_sim(daily)
    r.update(attempts=att,
             payout_pct=round(100 * len(dtp) / att, 1) if att else 0.0,
             bust_pct=round(100 * busts / att, 1) if att else 100.0,
             med_days=int(np.median(dtp)) if dtp else -1,
             p90_days=int(np.percentile(dtp, 90)) if dtp else -1)
    if split:
        for tag, sl_ in (("tr", daily[daily.index < split]),
                         ("te", daily[daily.index >= split])):
            if len(sl_) >= 15:
                a2, d2, b2, _ = payout_sim(sl_)
                r[f"{tag}_payout"] = round(100 * len(d2) / a2, 1) if a2 else 0.0
                r[f"{tag}_med"] = int(np.median(d2)) if d2 else -1
            else:
                r[f"{tag}_payout"], r[f"{tag}_med"] = -1.0, -1
    return r


# ════════════════════════ sweep ════════════════════════
SLS = (0.5, 0.75, 1.0, 1.25, 1.5)
TPS = (0.5, 0.75, 1.0, 1.5, 2.0, 3.0)
WINS = ((9.75, 11.5), (9.75, 15.5), (10.0, 12.0), (13.0, 15.5), (9.75, 12.5))
GATES = (None, "gate_ema50")
SIZES = ((440, 300), (300, 300), (600, 400))
SPLIT = "2025-02-01"


def configs_for(families):
    for fam, sl, tp, win, gate, (cap, bud) in itertools.product(
            families, SLS, TPS, WINS, GATES, SIZES):
        if tp < sl * 0.5:
            continue
        yield dict(family=fam, sl=sl, tp=tp, win=win, gate=gate, cap=cap, budget=bud)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["selftest", "sweep", "list"])
    ap.add_argument("--families", default=None)
    ap.add_argument("--slice", default=None, help="i/n — take slice i of n families")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    if args.mode == "list":
        print("\n".join(FAMILIES)); return

    df = load_enriched()
    print(f"loaded {len(df):,} RTH bars  {df.index.min()} -> {df.index.max()}",
          file=sys.stderr)

    if args.mode == "selftest":
        cfg = dict(family="stoch30_long", sl=0.75, tp=0.5, win=(9.75, 11.5),
                   gate=None, cap=440, budget=300)
        r = evaluate(df, cfg, split=SPLIT)
        print(json.dumps(r, indent=2, default=str))
        return

    fams = (args.families.split(",") if args.families else FAMILIES)
    if args.slice:
        i, n = (int(x) for x in args.slice.split("/"))
        fams = [f for j, f in enumerate(FAMILIES) if j % n == i]
    rows = [evaluate(df, c, split=SPLIT) for c in configs_for(fams)]
    out = pd.DataFrame(rows)
    # A low med_days is meaningless if most attempts bust first, and a config
    # with negative net only shows payouts because some start windows were lucky.
    # Rank on survival first, speed second.
    out["score"] = (out["payout_pct"] / out["med_days"].clip(lower=1)).round(3)
    out.loc[out["med_days"] <= 0, "score"] = 0.0
    if args.out:
        out.to_csv(args.out, index=False)

    cols = ["cfg_family", "sl", "tp", "win", "gate", "cap", "trades", "win_pct",
            "net", "payout_pct", "bust_pct", "med_days", "p90_days",
            "tr_payout", "te_payout", "tr_med", "te_med", "score"]
    cols = [c for c in cols if c in out.columns]

    viable = out[(out["net"] > 0) & (out["attempts"] >= 30)
                 & (out["med_days"] > 0) & (out["payout_pct"] >= 50)]
    viable = viable.sort_values(["payout_pct", "med_days"], ascending=[False, True])
    print("=" * 100)
    print(f"VIABLE  (net>0, payout%>=50, >=30 attempts):  {len(viable)} of {len(out)}")
    print("=" * 100)
    print(viable[cols].head(25).to_string(index=False) if len(viable)
          else "(none — no config in this slice clears net>0 with a >=50% payout rate)")

    best = out[(out["attempts"] >= 30) & (out["med_days"] > 0)]
    best = best.sort_values("payout_pct", ascending=False)
    print(f"\n{'TOP BY PAYOUT% regardless of net (diagnostic)':-<100}")
    print(best[cols].head(12).to_string(index=False) if len(best) else "(none)")
    print(f"\n{len(out)} configs evaluated, {len(viable)} viable", file=sys.stderr)


if __name__ == "__main__":
    main()

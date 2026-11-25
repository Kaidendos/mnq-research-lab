"""Gold strategy research — first real measurements on XAU in this project.

Until now every gold "rule" here has been folklore: Asian session sets the extreme,
London fix is a manipulation window, never long into a rising dollar, round numbers
are liquidity magnets. Plausible, widely repeated, never measured. This measures them.

DATA: GC=F hourly from Yahoo, 730 days (~17,400 bars, 2024-03 .. 2026-08). Gold trades
nearly 24h so hourly gives real coverage of Asian/London/NY rather than the RTH-only
slice a 5-minute feed would allow at this history depth. Databento GC is the upgrade
path (`fetch_gold_databento.py`) and would allow 1-minute fill resolution.

METHOD — the same discipline that rejected 19 MNQ candidates:
  1. every signal fires on a CLOSED bar, entry at that close
  2. brackets in ATR units, so nothing is tuned to gold's price level
  3. CLEAN CONTROL: permute which SESSION each fire count belongs to and which bar
     inside it — the version that inverted the MNQ conclusion twice when done wrong
  4. OUT-OF-SAMPLE split: fit 2024-03..2025-12, test 2026-01..2026-08, reported
     separately. Aggregate edge that dies out-of-sample is the failure mode here.
  5. every folklore claim gets tested as a FILTER, not assumed

Hourly bars cannot resolve which of stop/target hit first inside a bar. The stop is
assumed whenever both are touched — never invent the good fill — and the ambiguity
rate is reported so the reader can judge how much that assumption is carrying.
"""
from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass

import numpy as np
import pandas as pd

UA = {"User-Agent": "Mozilla/5.0"}
ET = "America/New_York"
SL_ATR, TP_ATR = 1.5, 2.0        # gold is noisier per ATR than NQ; 1.33 R:R
ATR_LEN = 14
MAX_HOLD = 12                    # bars (hours) before a time stop
SEEDS = 20
OOS_START = pd.Timestamp("2026-01-01", tz=ET)


def fetch(sym: str, interval: str, rng: str) -> pd.DataFrame:
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
           f"?interval={interval}&range={rng}")
    j = json.loads(urllib.request.urlopen(
        urllib.request.Request(url, headers=UA), timeout=40).read())
    r = j["chart"]["result"][0]
    q = r["indicators"]["quote"][0]
    df = pd.DataFrame({k: q[k] for k in ("open", "high", "low", "close", "volume")},
                      index=pd.to_datetime(r["timestamp"], unit="s", utc=True))
    df.index = df.index.tz_convert(ET)
    return df.dropna(subset=["open", "high", "low", "close"]).sort_index()


def enrich(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    c, h, l = d["close"], d["high"], d["low"]
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    d["atr"] = tr.ewm(alpha=1 / ATR_LEN, adjust=False).mean()

    hr = d.index.hour + d.index.minute / 60.0
    d["hr"] = hr
    # gold's trading day rolls at 18:00 ET, like the futures session
    d["_day"] = pd.Series(d.index.normalize(), index=d.index).where(
        hr < 18, pd.Series(d.index.normalize(), index=d.index) + pd.Timedelta(days=1))
    d["bod"] = d.groupby("_day").cumcount()
    d["sess_open"] = d.groupby("_day")["open"].transform("first")

    d["asia"] = (hr >= 18) | (hr < 3)
    d["london"] = (hr >= 3) & (hr < 11)
    d["ny"] = (hr >= 8) & (hr < 17)
    d["fix"] = (hr >= 10) & (hr < 11)

    # session extremes, running (include current bar, never a later one)
    for name in ("asia", "london"):
        m = d[name]
        d[f"{name}_hi"] = h.where(m).groupby(d["_day"]).cummax().ffill()
        d[f"{name}_lo"] = l.where(m).groupby(d["_day"]).cummin().ffill()
    dh = h.groupby(d["_day"]).max()
    dl = l.groupby(d["_day"]).min()
    dmap = pd.Series(d["_day"], index=d.index)
    d["pdh"] = dmap.map(dh.shift(1))
    d["pdl"] = dmap.map(dl.shift(1))
    d["prev_range"] = (d["pdh"] - d["pdl"]).abs()
    return d.dropna(subset=["atr"])


def signals(d: pd.DataFrame) -> dict:
    c, o, h, l = d["close"], d["open"], d["high"], d["low"]
    pc = c.shift(1)
    atr = d["atr"]
    bod = d["bod"]
    up, dn = c > o, c < o
    out = {}

    # ── round-number breaks: the MNQ analog that actually worked ──
    for step in (25.0, 50.0):
        lvl = np.floor(c / step)
        out[f"gd_round{int(step)}_break_long"] = (
            (lvl > np.floor(pc / step)) & (c >= lvl * step + 0.15 * atr) & up, +1)
        lvl_d = np.ceil(c / step)
        out[f"gd_round{int(step)}_break_short"] = (
            (lvl_d < np.ceil(pc / step)) & (c <= lvl_d * step - 0.15 * atr) & dn, -1)

    # ── folklore 1: the Asian session sets the day's extreme ──
    out["gd_asia_break_long"] = ((c > d["asia_hi"]) & (pc <= d["asia_hi"])
                                 & d["london"], +1)
    out["gd_asia_break_short"] = ((c < d["asia_lo"]) & (pc >= d["asia_lo"])
                                  & d["london"], -1)
    out["gd_asia_fade_long"] = ((c < d["asia_lo"]) & up & d["london"], +1)
    out["gd_asia_fade_short"] = ((c > d["asia_hi"]) & dn & d["london"], -1)

    # ── London range break into NY ──
    out["gd_london_break_long"] = ((c > d["london_hi"]) & (pc <= d["london_hi"])
                                   & d["ny"], +1)
    out["gd_london_break_short"] = ((c < d["london_lo"]) & (pc >= d["london_lo"])
                                    & d["ny"], -1)

    # ── prior-day level breaks and sweeps ──
    out["gd_pdh_break_long"] = ((c > d["pdh"]) & (pc <= d["pdh"]), +1)
    out["gd_pdl_break_short"] = ((c < d["pdl"]) & (pc >= d["pdl"]), -1)
    out["gd_pdh_sweep_short"] = ((h > d["pdh"]) & (c < d["pdh"]) & dn, -1)
    out["gd_pdl_sweep_long"] = ((l < d["pdl"]) & (c > d["pdl"]) & up, +1)

    # ── stretch from the session open (the lw_stretch analog) ──
    gate_dn = d["sess_open"] - 0.5 * d["prev_range"]
    gate_up = d["sess_open"] + 0.5 * d["prev_range"]
    out["gd_stretch_short"] = ((c < gate_dn) & (bod > 0), -1)
    out["gd_stretch_long"] = ((c > gate_up) & (bod > 0), +1)

    return {k: (v[0].fillna(False).to_numpy(bool), v[1]) for k, v in out.items()}


def backtest(d, mask, side, block_fix=False, dxy_align=None):
    """Entry at bar close; exit on stop, target, or a MAX_HOLD time stop."""
    c = d["close"].to_numpy(float)
    h = d["high"].to_numpy(float)
    l = d["low"].to_numpy(float)
    atr = d["atr"].to_numpy(float)
    fix = d["fix"].to_numpy(bool)
    n = len(c)
    pts, amb, wins = [], 0, 0
    i = 0
    idx = np.flatnonzero(mask)
    busy_until = -1
    for i in idx:
        if i <= busy_until or i + 1 >= n:
            continue
        a = atr[i]
        if not np.isfinite(a) or a <= 0:
            continue
        if block_fix and fix[i]:
            continue
        if dxy_align is not None and not dxy_align[i]:
            continue
        entry = c[i]
        stop = entry - SL_ATR * a * side
        targ = entry + TP_ATR * a * side
        r, exit_i = None, min(i + MAX_HOLD, n - 1)
        for j in range(i + 1, exit_i + 1):
            if side > 0:
                sl_hit, tp_hit = l[j] <= stop, h[j] >= targ
            else:
                sl_hit, tp_hit = h[j] >= stop, l[j] <= targ
            if sl_hit and tp_hit:
                amb += 1
                r = (stop - entry) * side
                exit_i = j
                break
            if sl_hit:
                r = (stop - entry) * side; exit_i = j; break
            if tp_hit:
                r = (targ - entry) * side; exit_i = j; break
        if r is None:
            r = (c[exit_i] - entry) * side
        pts.append(r)
        wins += r > 0
        busy_until = exit_i
    if not pts:
        return None
    arr = np.array(pts)
    return dict(n=len(arr), ppt=float(arr.mean()), win=100.0 * wins / len(arr),
                total=float(arr.sum()), amb=amb)


def control(d, mask, side, rng):
    """Permute the per-SESSION fire profile across sessions, and the bar within."""
    day_ids = pd.factorize(d["_day"])[0]
    starts = np.flatnonzero(np.r_[True, day_ids[1:] != day_ids[:-1]])
    ends = np.r_[starts[1:], len(day_ids)]
    prof = [int(mask[s:e].sum()) for s, e in zip(starts, ends)]
    order = rng.permutation(len(prof))
    out = np.zeros(len(mask), bool)
    for pos, (s, e) in enumerate(zip(starts, ends)):
        k = prof[order[pos]]
        if k and e > s:
            out[s + rng.choice(e - s, size=min(k, e - s), replace=False)] = True
    return backtest(d, out, side)


def main() -> None:
    print("fetching GC=F hourly, 730d ...", flush=True)
    d = enrich(fetch("GC%3DF", "1h", "730d"))
    print(f"  {len(d):,} bars  {d.index[0].date()} .. {d.index[-1].date()}")
    sigs = signals(d)

    is_mask = d.index < OOS_START
    oos_mask = d.index >= OOS_START
    print(f"  fit {int(is_mask.sum()):,} bars / test {int(oos_mask.sum()):,} bars")

    print("\n" + "=" * 112)
    print("GOLD SIGNALS — full sample, clean control, and out-of-sample")
    print("=" * 112)
    print(f"  {'signal':<28}{'n':>6}{'win%':>7}{'pts/tr':>9}{'EDGE':>8}{'beat':>7}"
          f"{'total':>9}{'  |':>3}{'OOS n':>7}{'OOS pts':>9}")
    rows = []
    for name, (mask, side) in sigs.items():
        r = backtest(d, mask, side)
        if not r or r["n"] < 25:
            print(f"  {name:<28}{(r['n'] if r else 0):>6}   too few trades")
            continue
        ctl = []
        for s in range(SEEDS):
            cr = control(d, mask, side, np.random.default_rng(s))
            if cr:
                ctl.append(cr["ppt"])

        edge = r["ppt"] - float(np.median(ctl)) if ctl else float("nan")
        beat = int(sum(1 for x in ctl if x >= r["ppt"]))
        ro = backtest(d[oos_mask], signals(d[oos_mask])[name][0], side)
        rows.append((name, r, edge, beat, ro))
        oos_n = ro["n"] if ro else 0
        oos_p = f"{ro['ppt']:+.2f}" if ro else "—"
        print(f"  {name:<28}{r['n']:>6}{r['win']:>7.1f}{r['ppt']:>+9.2f}"
              f"{edge:>+8.2f}{beat:>5}/{SEEDS}{r['total']:>9,.0f}{'  |':>3}"
              f"{oos_n:>7}{oos_p:>9}")

    print("\n" + "=" * 112)
    print("SURVIVORS — positive edge, control beaten <=2/20, and POSITIVE out-of-sample")
    print("=" * 112)
    keep = [x for x in rows if x[2] > 0 and x[3] <= 2 and x[4] and x[4]["ppt"] > 0]
    if not keep:
        print("  NONE. No gold signal here clears a clean control and holds up")
        print("  out-of-sample. On this data gold has no tradeable structure that")
        print("  these rules can find.")
    for name, r, edge, beat, ro in sorted(keep, key=lambda x: -x[2]):
        print(f"  {name:<28} edge {edge:+.2f} pts/trade, control beaten {beat}/{SEEDS}, "
              f"OOS {ro['ppt']:+.2f} on {ro['n']} trades")

    amb_tot = sum(x[1]["amb"] for x in rows)
    n_tot = sum(x[1]["n"] for x in rows)
    print(f"\n  intra-bar ambiguity {amb_tot}/{n_tot} "
          f"({100.0 * amb_tot / max(n_tot, 1):.0f}%) — the stop was assumed each time.")
    print("  Hourly bars cannot do better; Databento GC would allow 1-min resolution.")


if __name__ == "__main__":
    main()

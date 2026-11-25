"""Does the briefing's PRE-OPEN information predict a good day for the researched pair?

The app computes several things that are genuinely known before 09:45: the overnight
range and where the open sits in it, the gap, VIX / 10Y / DXY, prior-day levels. The
question is whether any of them separate good sessions from bad ones.

STRICT NO-LOOKAHEAD RULE
------------------------
Every feature uses only information timestamped before 09:45 ET:
  overnight range   18:00 prior day -> 09:30, from the ETH bars the RTH frame discards
  gap               09:30 open vs prior RTH close  (known at 09:30)
  VIX / 10Y / DXY   prior daily CLOSE, and the same-day daily OPEN (both pre-09:45).
                    The same-day CLOSE would be lookahead — 16:15 — and is never used.
  ATR / prior range the PRIOR session's final ATR, never today's evolving value

METHOD, and why it is this fussy
--------------------------------
This project has already rejected 17 candidates, including volatility-regime gating
(no predictive information), recent-performance adaptation (persistence +0.065), and
384 edge-ranked pairings (0 of 384 improved). The prior that a pre-open feature works
is therefore LOW, and the risk of finding a fake winner is HIGH: testing 9 features x
3 buckets is 27 chances to get lucky.

So the bar is deliberately high and set before looking:
  1. split each feature into terciles, not a tuned threshold — no threshold search
  2. report PER-YEAR net for the extreme buckets
  3. a feature only counts if the direction holds in >= 5 of 6 years
  4. the total number of comparisons is printed, so the reader can discount for it
A feature that only separates in aggregate is noise wearing a result's clothes.
"""
from __future__ import annotations

import json
import urllib.request

import numpy as np
import pandas as pd

import funded_1yr as f1
import funded_search as fs
import live_vs_researched as LR
from rr_sweep import load_one_min

RAW_5M = fs.D / "mnq_2021-2026_5min.csv"
UA = {"User-Agent": "Mozilla/5.0"}
MIN_YEARS_AGREE = 5


def naive_dates(idx) -> pd.DatetimeIndex:
    """Coerce any index to tz-NAIVE midnight dates so the joins line up.

    The pieces arrive mixed: `_day` survives a numpy round-trip tz-naive, the ETH
    grouping and the Yahoo daily frames stay tz-aware in ET. Joining those raises
    "Cannot join tz-naive with tz-aware DatetimeIndex". Calendar date is the only
    key that means anything here, so everything is flattened to that.
    """
    i = pd.DatetimeIndex(pd.to_datetime(idx))
    if i.tz is not None:
        i = i.tz_localize(None)
    return i.normalize()


# ───────────────────────────── pre-open features ─────────────────────────────

def overnight_table() -> pd.DataFrame:
    """ONH / ONL / open per session, from bars strictly before 09:30 ET."""
    raw = pd.read_csv(RAW_5M, usecols=["ts_et", "open", "high", "low", "close"])
    ts = pd.to_datetime(raw["ts_et"], format="mixed", utc=True
                        ).dt.tz_convert("America/New_York")
    raw = raw.set_index(ts).drop(columns=["ts_et"]).sort_index()
    hr = raw.index.hour + raw.index.minute / 60.0

    # an overnight block belongs to the NEXT session: 18:00-23:59 rolls forward
    sess = pd.Series(raw.index.normalize(), index=raw.index)
    roll = hr >= 18.0
    sess[roll] = sess[roll] + pd.Timedelta(days=1)

    pre = raw[(hr >= 18.0) | (hr < 9.5)].copy()
    pre["_s"] = sess[(hr >= 18.0) | (hr < 9.5)].values
    on = pre.groupby("_s").agg(onh=("high", "max"), onl=("low", "min"))
    on.index = naive_dates(on.index)
    return on


def macro_table() -> pd.DataFrame:
    """Daily prior-close and same-day open for VIX / 10Y / DXY."""
    out = {}
    for sym, name in (("%5EVIX", "vix"), ("%5ETNX", "tnx"), ("DX-Y.NYB", "dxy")):
        url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
               f"?interval=1d&range=6y")
        j = json.loads(urllib.request.urlopen(
            urllib.request.Request(url, headers=UA), timeout=30).read())
        r = j["chart"]["result"][0]
        q = r["indicators"]["quote"][0]
        idx = pd.to_datetime(r["timestamp"], unit="s", utc=True
                             ).tz_convert("America/New_York").normalize()
        df = pd.DataFrame({f"{name}_open": q["open"], f"{name}_close": q["close"]},
                          index=idx).dropna(how="all")
        df = df[~df.index.duplicated(keep="last")]
        out[name] = df
    m = pd.concat(out.values(), axis=1, sort=True).sort_index()
    m.index = naive_dates(m.index)
    for name in ("vix", "tnx", "dxy"):
        m[f"{name}_prev"] = m[f"{name}_close"].shift(1)
    return m


# ───────────────────────── the pair's per-session result ─────────────────────

def pair_sessions(df, one_min):
    """(date, net, n_trades, n_wins) per session for the researched pair."""
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
    dates = df["_day"].to_numpy()
    starts = np.flatnonzero(np.r_[True, ids[1:] != ids[:-1]])
    ends = np.r_[starts[1:], len(ids)]

    rows = []
    for s, e in zip(starts, ends):
        net, ntr, nw = 0.0, 0, 0
        busy = np.datetime64("1970-01-01", "ns")
        for i in range(s, e):
            if not (2 <= bod[i] <= 18) or ntr >= 6 or ts[i] < busy:
                continue
            side = 1 if el[i] else (-1 if es[i] else 0)
            if side == 0:
                continue
            a = atr[i]
            if not np.isfinite(a) or a <= 0:
                continue
            n = min(10, int(300.0 // (a * 2.0 * 2.0)))
            if n < 1:
                continue
            entry = c[i]
            slt = max(1, round(a * 2.0 / 0.25)) * 0.25
            tpt = max(1, round(a * 3.0 / 0.25)) * 0.25
            s_ns = ts[i] + np.timedelta64(5, "m")
            dl = ts[e - 1] + np.timedelta64(5, "m")
            fn = LR.resolve_exit if side > 0 else LR.resolve_short
            if side > 0:
                px, _, xt = fn(t1, h1, l1, s_ns, entry - slt, entry + tpt, dl, c[e - 1])
            else:
                px, _, xt = fn(t1, h1, l1, s_ns, entry + slt, entry - tpt, dl, c[e - 1])
            g = (px - entry) * side * 2.0 * n
            net += g - 1.22 * n
            ntr += 1
            nw += g > 0
            busy = xt
        rows.append((pd.Timestamp(dates[s]).normalize(), net, ntr, nw))
    return pd.DataFrame(rows, columns=["date", "net", "trades", "wins"]
                        ).set_index("date")


# ─────────────────────────────── the analysis ────────────────────────────────

def bucket_report(tbl: pd.DataFrame, feat: str, label: str, years) -> dict:
    """Terciles of `feat`, per-bucket result plus per-year direction agreement."""
    sub = tbl.dropna(subset=[feat])
    if len(sub) < 200:
        return dict(label=label, skip=f"only {len(sub)} sessions")
    try:
        q = pd.qcut(sub[feat], 3, labels=["low", "mid", "high"], duplicates="drop")
    except ValueError:
        return dict(label=label, skip="not enough distinct values")
    if q.nunique() < 3:
        return dict(label=label, skip="degenerate buckets")

    stats = {}
    for b in ("low", "mid", "high"):
        m = sub[q == b]
        tr = int(m["trades"].sum())
        stats[b] = dict(
            sessions=len(m), trades=tr,
            win=100.0 * m["wins"].sum() / tr if tr else 0.0,
            net=float(m["net"].sum()),
            per_sess=float(m["net"].mean()))
    # does high-minus-low keep its sign year by year?
    agree, signs = 0, []
    overall = stats["high"]["per_sess"] - stats["low"]["per_sess"]
    for y in years:
        yl = sub[(q == "low") & (sub.index.year == y)]["net"].mean()
        yh = sub[(q == "high") & (sub.index.year == y)]["net"].mean()
        if np.isnan(yl) or np.isnan(yh):
            signs.append(".")
            continue
        d = yh - yl
        signs.append("+" if d > 0 else "-")
        if (d > 0) == (overall > 0):
            agree += 1
    return dict(label=label, stats=stats, spread=overall, agree=agree,
                signs="".join(signs))


def main() -> None:
    print("loading ...", flush=True)
    df = fs.load_enriched()
    one_min = load_one_min()
    sess = pair_sessions(df, one_min)
    print(f"  {len(sess)} sessions, {int(sess['trades'].sum())} trades, "
          f"net ${sess['net'].sum():,.0f}", flush=True)

    on = overnight_table()
    mac = macro_table()

    # per-session RTH facts, all from the PRIOR session or the 09:30 open
    g = df.groupby("_day")
    rth = pd.DataFrame({
        "sess_open": g["open"].first(),
        "day_hi": g["high"].max(),
        "day_lo": g["low"].min(),
        "day_close": g["close"].last(),
        "atr_last": g["atr"].last(),
    })
    rth.index = naive_dates(rth.index)
    rth["prev_close"] = rth["day_close"].shift(1)
    rth["prev_range"] = (rth["day_hi"] - rth["day_lo"]).shift(1)
    rth["atr_prev"] = rth["atr_last"].shift(1)

    sess.index = naive_dates(sess.index)
    t = sess.join(rth, how="left").join(on, how="left")
    t = t.join(mac, how="left")

    a = t["atr_prev"].replace(0, np.nan)
    t["f_on_width"] = (t["onh"] - t["onl"]) / a
    t["f_on_pos"] = 100.0 * (t["sess_open"] - t["onl"]) / (t["onh"] - t["onl"])
    t["f_gap"] = (t["sess_open"] - t["prev_close"]) / a
    t["f_gap_abs"] = t["f_gap"].abs()
    t["f_pd_range"] = t["prev_range"] / a
    t["f_vix_lvl"] = t["vix_prev"]
    t["f_vix_chg"] = t["vix_open"] - t["vix_prev"]
    t["f_tnx_chg"] = (t["tnx_open"] - t["tnx_prev"]) * 100.0
    t["f_dxy_chg"] = 100.0 * (t["dxy_open"] - t["dxy_prev"]) / t["dxy_prev"]

    feats = [
        ("f_on_width", "Overnight range width (xATR)"),
        ("f_on_pos", "Open's position in overnight range (%)"),
        ("f_gap", "Gap, signed (xATR)"),
        ("f_gap_abs", "Gap, absolute size (xATR)"),
        ("f_pd_range", "Prior-day range (xATR)"),
        ("f_vix_lvl", "VIX level (prior close)"),
        ("f_vix_chg", "VIX change into the open"),
        ("f_tnx_chg", "10Y change into the open (bps)"),
        ("f_dxy_chg", "DXY change into the open (%)"),
    ]
    years = sorted({int(y) for y in t.index.year})

    print("\n" + "=" * 114)
    print("PRE-OPEN FEATURES vs the researched pair — 5 years, no lookahead")
    print("=" * 114)
    print(f"  {'feature':<40}{'bucket':>7}{'sess':>6}{'trades':>7}{'win%':>7}"
          f"{'net $':>9}{'$/sess':>8}   yr-signs  agree")
    results = []
    for key, label in feats:
        r = bucket_report(t, key, label, years)
        if "skip" in r:
            print(f"  {label:<40} SKIPPED — {r['skip']}")
            continue
        for i, b in enumerate(("low", "mid", "high")):
            s = r["stats"][b]
            head = label if i == 0 else ""
            tail = (f"   {r['signs']}    {r['agree']}/{len(years)}"
                    if b == "high" else "")
            print(f"  {head:<40}{b:>7}{s['sessions']:>6}{s['trades']:>7}"
                  f"{s['win']:>7.1f}{s['net']:>9,.0f}{s['per_sess']:>8.2f}{tail}")
        results.append(r)

    print("\n" + "=" * 114)
    print("VERDICT")
    print("=" * 114)
    ncomp = len(results) * 3
    print(f"  {len(results)} features x 3 buckets = {ncomp} comparisons on one "
          f"dataset. With that many looks,")
    print(f"  the largest spread WILL look impressive by chance. The only thing that "
          f"survives that is")
    print(f"  per-year agreement, so that is the filter applied here.\n")
    keep = [r for r in results if r["agree"] >= MIN_YEARS_AGREE]
    for r in sorted(results, key=lambda x: -abs(x["spread"])):
        mark = "SURVIVES" if r["agree"] >= MIN_YEARS_AGREE else "rejected"
        print(f"  [{mark}] {r['label']:<44} spread ${r['spread']:>+7.2f}/session, "
              f"holds {r['agree']}/{len(years)} years")
    print(f"\n  {len(keep)} of {len(results)} features hold their direction in "
          f"{MIN_YEARS_AGREE}+ of {len(years)} years.")
    if not keep:
        print("  -> No pre-open feature separates good sessions from bad ones. The "
              "app's pre-open\n     panel is useful CONTEXT, but it is not a filter.")


if __name__ == "__main__":
    main()

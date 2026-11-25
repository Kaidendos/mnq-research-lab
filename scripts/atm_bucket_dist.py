"""How many fixed-tick ATM templates does the live book actually need?

A NinjaTrader ATM template holds a FIXED stop distance. Our stop is ATR-adaptive
(2.0 x ATR, rounded to whole ticks). So handing the stop to an ATM means snapping
each signal to the nearest pre-built template. This measures how wide the spread of
required distances really is, per arm, so the template set can be chosen from data
rather than guessed.

The two arms are NEVER pooled. The RTH pair's ATR comes from an RTH-ONLY series; the
Asia break's from the 24-hour series. ATR(14) over RTH bars and ATR(14) over 24-hour
bars are different numbers at the same instant — overnight bars are far smaller — so a
pooled histogram would be meaningless and would size the template set wrong.

Only TRADEABLE signals count: a setup the $175 budget cannot take at one contract is a
SKIP, and skipped setups never need a template. That filter is most of the story for
the RTH arm in the current regime.

Second-order effects on the distribution SHAPE (the 6-trade daily cap, and the rule that
a new signal is ignored while a prior trade is still open) are not applied here. They
change WHICH signals fire, not the ATR at which they fire, so the percentiles move by
noise. The account-level cost run is where those matter and they are applied there.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import funded_1yr as f1
import funded_search as fs
import overnight_hunt as OH

TICK, PV = 0.25, 2.0
SL_ATR = 2.0
BUDGET, MAXC = 175.0, 10
RECENT_MONTHS = 6


def stop_ticks(atr: np.ndarray) -> np.ndarray:
    return np.maximum(1, np.round(atr * SL_ATR / TICK)).astype(int)


def contracts(atr: np.ndarray) -> np.ndarray:
    per = atr * SL_ATR * PV
    with np.errstate(divide="ignore", invalid="ignore"):
        n = np.floor(BUDGET / per)
    return np.clip(np.nan_to_num(n, nan=0.0), 0, MAXC).astype(int)


def asia_signals() -> pd.Series:
    """ATR at each ASIA round-100 break long, on the 24-HOUR series."""
    d = OH.load_full()
    sigs = OH.build_signals(d)
    mask, _ = sigs["ASIA|round100_long"]
    m = pd.Series(mask, index=d.index).fillna(False).to_numpy(bool)
    return d.loc[m, "atr"]


def rth_signals() -> pd.Series:
    """ATR at each RTH-pair signal, on the RTH-ONLY series, inside 09:45-11:00 ET."""
    df = fs.load_enriched()
    pl = f1.load_plugins(df)

    def sig(name):
        e, _ = pl[name] if name in pl else fs.sig(df, name)
        return pd.Series(e).reindex(df.index).fillna(False).to_numpy(bool)

    both = sig("sr_round100_break") | sig("vol_lw_stretch_short")
    hr = df.index.hour + df.index.minute / 60.0
    win = (hr >= 9.75) & (hr < 11.0)
    return df.loc[both & win, "atr"]


def describe(atr: pd.Series, label: str) -> dict:
    a = atr.to_numpy(float)
    a = a[np.isfinite(a) & (a > 0)]
    n_all = len(a)
    keep = contracts(a) >= 1
    a = a[keep]
    if not len(a):
        print(f"\n  {label}: {n_all} signals, ZERO tradeable at ${BUDGET:.0f}")
        return {}
    t = stop_ticks(a)
    q = np.percentile(t, [0, 5, 25, 50, 75, 95, 100])
    print(f"\n  {label}")
    print(f"    signals {n_all}, tradeable at ${BUDGET:.0f}: {len(a)} "
          f"({100.0 * len(a) / n_all:.1f}%)")
    print(f"    stop ticks   min {q[0]:.0f}  p05 {q[1]:.0f}  p25 {q[2]:.0f}  "
          f"MED {q[3]:.0f}  p75 {q[4]:.0f}  p95 {q[5]:.0f}  max {q[6]:.0f}")
    print(f"    stop dollars/contract  med ${q[3] * TICK * PV:.0f}   "
          f"p05-p95 ${q[1] * TICK * PV:.0f}-${q[5] * TICK * PV:.0f}")
    ct = contracts(a)
    uc, cc = np.unique(ct, return_counts=True)
    print("    contracts    " + "  ".join(
        f"n={u}:{100.0 * c / len(ct):.0f}%" for u, c in zip(uc, cc)))
    return dict(ticks=t, atr=a)


def bucket_error(t: np.ndarray, k: int, label: str) -> None:
    """If K templates are pre-built, how far off is the snapped stop?"""
    print(f"\n    {label}: how well do K fixed templates fit?")
    print(f"      {'K':>3}{'template ticks':>46}{'med err':>10}{'p95 err':>10}"
          f"{'within 5%':>11}")
    lo, hi = np.percentile(t, 2), np.percentile(t, 98)
    for kk in k:
        if hi <= lo:
            edges = np.array([np.median(t)])
        else:
            # geometric spacing: a 4-tick miss matters far more on an 80-tick stop
            # than on a 400-tick one, so equal RATIO buckets beat equal spacing.
            edges = np.unique(np.round(np.geomspace(lo, hi, kk)).astype(int))
        snapped = edges[np.abs(t[:, None] - edges[None, :]).argmin(axis=1)]
        err = np.abs(snapped - t) / t
        shown = ", ".join(str(e) for e in edges)
        if len(shown) > 44:
            shown = shown[:41] + "..."
        print(f"      {kk:>3}{shown:>46}{100 * np.median(err):>9.1f}%"
              f"{100 * np.percentile(err, 95):>9.1f}%"
              f"{100.0 * (err <= 0.05).mean():>10.1f}%")


def main() -> None:
    print("loading ...", flush=True)
    asia_all = asia_signals()
    rth_all = rth_signals()

    cut = max(asia_all.index.max(), rth_all.index.max()) - pd.DateOffset(
        months=RECENT_MONTHS)
    print(f"\n{'=' * 96}")
    print(f"STOP-DISTANCE DISTRIBUTION — what an ATM template has to reproduce")
    print(f"{'=' * 96}")
    print(f"  MNQ tick {TICK} pts, ${TICK * PV:.2f}/tick.  stop = round(ATR x "
          f"{SL_ATR} / {TICK}) ticks.  budget ${BUDGET:.0f}")

    for period, sel in (("FULL 5 YEARS", None), (f"LAST {RECENT_MONTHS} MONTHS", cut)):
        print(f"\n  ---- {period} ----")
        for label, s in (("ASIA arm  (24-hour ATR)", asia_all),
                         ("RTH pair  (RTH-only ATR)", rth_all)):
            sub = s if sel is None else s[s.index >= sel]
            r = describe(sub, label)
            if r and period == "FULL 5 YEARS":
                bucket_error(r["ticks"], [3, 5, 8, 12], label)


if __name__ == "__main__":
    main()

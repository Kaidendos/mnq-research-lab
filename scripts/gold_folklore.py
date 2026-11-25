"""Test the gold folklore as FILTERS on the four signals that survived.

`gold_research.py` found four gold signals that clear a clean control AND stay
positive out-of-sample. Every "gold rule" in the app's kill-list is still folklore
though, so this puts each one to work as a filter on those four and measures it:

    London fix  10:00-11:00 ET is a manipulation window — avoid entries
    DXY         never fight the dollar: no gold longs while DXY is up on the day,
                no gold shorts while DXY is down
    Round-number magnets — already covered, gd_round50 IS that rule

A filter is only adopted if it improves the SURVIVORS. Two ways to fail:
  * it makes points-per-trade worse -> the rule is wrong
  * it improves points but guts the trade count -> a frequency tax, same trap that
    made the 10Y filter on MNQ look good before it failed out-of-sample

Both are reported. DXY comes from Yahoo daily (prior close vs same-day open, both
known before any gold entry that day) so nothing here reads the future.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import gold_research as GR

SURVIVORS = ["gd_round50_break_short", "gd_asia_break_short",
             "gd_london_break_long", "gd_stretch_long"]


def dxy_daily() -> pd.DataFrame:
    d = GR.fetch("DX-Y.NYB", "1d", "3y")
    d = d[~d.index.duplicated(keep="last")]
    d["prev_close"] = d["close"].shift(1)
    d["chg_pct"] = 100.0 * (d["open"] - d["prev_close"]) / d["prev_close"]
    d.index = d.index.normalize()
    return d[["chg_pct"]]


def main() -> None:
    print("fetching ...", flush=True)
    d = GR.enrich(GR.fetch("GC%3DF", "1h", "730d"))
    sigs = GR.signals(d)
    dxy = dxy_daily()

    # map each gold bar to that calendar day's DXY move into the open
    day = pd.Series(d.index.normalize(), index=d.index)
    chg = day.map(dxy["chg_pct"]).to_numpy(float)
    print(f"  {len(d):,} gold bars; DXY available on "
          f"{100.0 * np.isfinite(chg).mean():.0f}% of them")

    print("\n" + "=" * 108)
    print("GOLD FOLKLORE AS FILTERS — tested on the four surviving signals")
    print("=" * 108)
    print(f"  {'signal':<26}{'filter':<22}{'n':>6}{'win%':>7}{'pts/tr':>9}"
          f"{'total':>9}{'d pts':>8}{'d n%':>7}")

    verdicts = {}
    for name in SURVIVORS:
        mask, side = sigs[name]
        base = GR.backtest(d, mask, side)
        if not base:
            continue
        print(f"  {name:<26}{'NONE (baseline)':<22}{base['n']:>6}{base['win']:>7.1f}"
              f"{base['ppt']:>+9.2f}{base['total']:>9,.0f}{'—':>8}{'—':>7}")

        # ── folklore 1: avoid the London fix ──
        r = GR.backtest(d, mask, side, block_fix=True)
        if r:
            _row("  ", "", "skip London fix", r, base)
            verdicts.setdefault("London fix", []).append(r["ppt"] - base["ppt"])

        # ── folklore 2: do not fight the dollar ──
        # long only when DXY is DOWN on the day; short only when DXY is UP
        align = (chg < 0) if side > 0 else (chg > 0)
        align = np.where(np.isfinite(chg), align, False)
        r = GR.backtest(d, mask, side, dxy_align=align)
        if r:
            _row("  ", "", "DXY-aligned only", r, base)
            verdicts.setdefault("DXY alignment", []).append(r["ppt"] - base["ppt"])

        # ── the inverse, as a sanity check: does fighting the dollar do WORSE? ──
        anti = (chg > 0) if side > 0 else (chg < 0)
        anti = np.where(np.isfinite(chg), anti, False)
        r = GR.backtest(d, mask, side, dxy_align=anti)
        if r:
            _row("  ", "", "DXY-OPPOSED only", r, base)
        print()

    print("=" * 108)
    print("VERDICT ON EACH FOLKLORE RULE")
    print("=" * 108)
    for rule, deltas in verdicts.items():
        arr = np.array(deltas)
        helped = int((arr > 0).sum())
        print(f"  {rule:<18} mean change {arr.mean():+.2f} pts/trade, "
              f"helped {helped}/{len(arr)} signals")
        if arr.mean() <= 0 or helped <= len(arr) / 2:
            print(f"    -> NOT SUPPORTED. Keep it labelled ANECDOTAL in killrules.py.")
        else:
            print(f"    -> supported on this sample; still needs its own OOS split "
                  f"before it can KILL anything.")


def _row(pad, name, label, r, base):
    dn = 100.0 * (r["n"] - base["n"]) / max(base["n"], 1)
    print(f"{pad}{name:<26}{label:<22}{r['n']:>6}{r['win']:>7.1f}{r['ppt']:>+9.2f}"
          f"{r['total']:>9,.0f}{r['ppt'] - base['ppt']:>+8.2f}{dn:>+7.0f}")


if __name__ == "__main__":
    main()

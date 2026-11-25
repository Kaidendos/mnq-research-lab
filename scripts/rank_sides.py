"""Rank EVERY signal family individually by side, on selection + holdout.

The first two-sided sweep paired 6 hand-picked shorts. There are ~35 short signals
already built and audited. This ranks all of them (and all longs) on a fixed,
sensible bracket so the pairing stage is driven by measured performance rather
than by which names I happened to remember.
"""
from __future__ import annotations

import pandas as pd

import funded_search as fs
import funded_1yr as f1

# fixed reference bracket — not swept here; this is a like-for-like family ranking
REF = dict(sl=1.0, tp=1.0, win=(9.6667, 11.5), gate=None, cap=300, budget=300, maxc=5)

df = fs.load_enriched()
plugins = f1.load_plugins(df)
end = df.index[-1]
w5 = end - pd.DateOffset(months=5)
sel, hold = df[df.index >= w5], df[df.index < w5]
sp_s = (sel.index[-1] - sel.index[0]).days
sp_h = (hold.index[-1] - hold.index[0]).days

names = fs.FAMILIES + list(plugins)
rows = []
for nm in names:
    try:
        e, side = plugins[nm] if nm in plugins else fs.sig(df, nm)
    except Exception:
        continue
    e = pd.Series(e).reindex(df.index).fillna(False)
    r = dict(family=nm, side=side, fires=int(e.sum()))
    for tag, d, sp in (("sel", sel, sp_s), ("hold", hold, sp_h)):
        daily, ntr, nwin = fs.replay(d, e.reindex(d.index).fillna(False), side,
                                     REF["sl"], REF["tp"], REF["win"], REF["gate"],
                                     REF["cap"], REF["budget"], maxc=REF["maxc"])
        m = f1.score(daily, sp)
        r[f"{tag}_tr"] = ntr
        r[f"{tag}_win"] = round(100 * nwin / ntr, 1) if ntr else 0.0
        r[f"{tag}_net"] = m["net"]
        r[f"{tag}_bust"] = m["bust_pct"]
        r[f"{tag}_pay"] = m["payouts"]
    rows.append(r)

out = pd.DataFrame(rows)
out["both_pos"] = (out.sel_net > 0) & (out.hold_net > 0)
out.to_csv("rank_sides.csv", index=False)
pd.set_option("display.width", 200)
cols = ["family", "fires", "sel_tr", "sel_win", "sel_net", "hold_tr", "hold_win",
        "hold_net", "hold_bust", "hold_pay", "both_pos"]

for sd, lbl in ((-1, "SHORT"), (1, "LONG")):
    s = out[out.side == sd].sort_values("hold_net", ascending=False)
    print("\n" + "=" * 104)
    print(f"{lbl} FAMILIES ranked by HOLDOUT net   (reference bracket 1.0/1.0, "
          f"09:40-11:30, cap300, 5 ct)")
    print("=" * 104)
    print(s[cols].head(22).to_string(index=False))
    print(f"  {lbl}: {len(s)} families | net-positive on holdout {int((s.hold_net>0).sum())}"
          f" | positive BOTH {int(s.both_pos.sum())}")

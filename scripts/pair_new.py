"""Do any of the 9 new trader methodologies beat or improve the incumbent pair?

The standalone ranking (`rank_sides.csv`) puts several new families high:
    LONGS   wy_lps_long $6,121 · qm_ep_long $5,662 · bs_avwap_open_vol_long $5,042
            rh_irb_long $4,883 · ww_psar_long $4,697
    SHORTS  ww_volsys_short $6,439 · ww_psar_short $6,101 · rh_irb_short_fast $5,242
            ic_judas_short $5,082 · bw_ao_zero_short $4,438

Standalone rank has already been shown to mislead here. mf_wkpiv_long topped the
whole 271-family registry on its own and then placed 6th of 10 when paired,
losing 91% of 1,080 matched head-to-heads. A family can be strong alone and
useless in a pair if it fires in the same conditions as its partner, because then
its drawdowns stack instead of offsetting.

So each candidate is tested two ways, both against a FIXED base:
    REPLACE — candidate takes the incumbent's place on its side
    ADD     — candidate is OR'd in alongside the incumbent

Both windows are reported. The recent 5 months matter more than usual here: the
cap-$250 config has produced ZERO payouts in that window at every runway length,
so a candidate that only improves the 4.5-year holdout is not solving the
problem the user actually has.
"""
from __future__ import annotations

import itertools

import pandas as pd

import funded_search as fs
import funded_1yr as f1
import sim_trace as ST

BASE_L, BASE_S = "sr_round100_break", "vol_lw_stretch_short"
WIN = (9.75, 11.0)

CAND_L = ["wy_lps_long", "bs_avwap_open_vol_long", "rh_irb_long", "ww_psar_long",
          "qm_ep_long", "bw_fractal_break_long", "jr_hook_long", "ae_ray_long",
          "ic_sweep_mss_long", "wy_spring_long"]
CAND_S = ["ww_volsys_short", "ww_psar_short", "rh_irb_short_fast", "ic_judas_short",
          "bw_ao_zero_short", "ww_psar_dmi_short", "wy_upthrust_short",
          "jr_hook_short", "ic_sweep_mss_short", "bs_avwap_open_vol_short"]

df = fs.load_enriched()
pl = f1.load_plugins(df)
end = df.index[-1]
cut = end - pd.DateOffset(months=5)
WINDOWS = (("hold", df[df.index < cut]), ("sel", df[df.index >= cut]))


def resolve(frame, name):
    e, _ = pl[name] if name in pl else fs.sig(df, name)
    return pd.Series(e).reindex(frame.index).fillna(False).to_numpy(bool)


def score(frame, longs, shorts, cap, bud):
    P = ST.build(frame, longs, shorts, WIN, resolve)
    res = [ST.trace(P, k, cap, bud) for k in range(0, len(P["per"]), 4)
           if len(P["per"]) - k >= 20]
    return ST.summarise(res)


CASES = [("BASELINE", "-", [BASE_L], [BASE_S])]
for c in CAND_L:
    CASES.append(("replace_L", c, [c], [BASE_S]))
    CASES.append(("add_L", c, [BASE_L, c], [BASE_S]))
for c in CAND_S:
    CASES.append(("replace_S", c, [BASE_L], [c]))
    CASES.append(("add_S", c, [BASE_L], [BASE_S, c]))

rows = []
for mode, cand, longs, shorts in CASES:
    row = dict(mode=mode, candidate=cand)
    for cap, bud in ((440, 300), (250, 400)):
        for wname, frame in WINDOWS:
            m = score(frame, longs, shorts, cap, bud)
            for k in ("paid", "bust", "mean", "med", "days"):
                row[f"{wname}{cap}_{k}"] = m[k]
    rows.append(row)
    print(f"  {mode:10s} {cand}", flush=True)

out = pd.DataFrame(rows)
out.to_csv("pair_new.csv", index=False)
pd.set_option("display.width", 240)

base = out[out["mode"] == "BASELINE"].iloc[0]
print("\n" + "=" * 160)
print("BASELINE  sr_round100_break + vol_lw_stretch_short, 9:45-11:00, SL2/TP3")
print(f"  cap 440  hold: paid {base.hold440_paid}%  bust {base.hold440_bust}%  "
      f"mean ${base.hold440_mean:,.0f}  med ${base.hold440_med:,.0f}  {base.hold440_days}d")
print(f"  cap 440  sel : paid {base.sel440_paid}%  bust {base.sel440_bust}%  "
      f"mean ${base.sel440_mean:,.0f}")
print(f"  cap 250  hold: paid {base.hold250_paid}%  bust {base.hold250_bust}%  "
      f"mean ${base.hold250_mean:,.0f}  med ${base.hold250_med:,.0f}  {base.hold250_days}d")
print("=" * 160)

COLS = ["mode", "candidate", "hold440_paid", "hold440_bust", "hold440_mean",
        "hold440_med", "hold440_days", "sel440_paid", "sel440_mean",
        "hold250_paid", "hold250_bust", "hold250_mean", "hold250_med"]
for mode in ("replace_L", "add_L", "replace_S", "add_S"):
    g = out[out["mode"] == mode].sort_values("hold440_mean", ascending=False)
    print(f"\n  ### {mode}")
    print(g[COLS].to_string(index=False))

print("\n" + "=" * 160)
print("BEATS BASELINE ON THE 27-DAY CONFIG (cap 440): higher hold mean AND not worse bust")
print("=" * 160)
win = out[(out["mode"] != "BASELINE")
          & (out.hold440_mean > base.hold440_mean)
          & (out.hold440_bust <= base.hold440_bust)]
print(win[COLS].sort_values("hold440_mean", ascending=False).to_string(index=False)
      if len(win) else "  none")

print("\n" + "=" * 160)
print("ALSO POSITIVE IN THE RECENT 5 MONTHS (sel440_mean above baseline)")
print("=" * 160)
win2 = win[win.sel440_mean > base.sel440_mean] if len(win) else win
print(win2[COLS].to_string(index=False) if len(win2) else "  none")

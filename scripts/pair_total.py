"""Pair on TOTAL EDGE (edge x trades), the metric that actually predicts account outcome.

Three metrics have now been compared, and they disagree:
  net P&L        — reads the market, not the rule (Spearman +0.265 vs edge)
  edge/trade     — reads the rule, but ignores that a rare signal cannot climb
                   $1,100 to the buffer inside a year
  edge x trades  — where the account-level winners actually cluster:
      sr_round100_break     edge/trade rank 68  ->  TOTAL rank 13
      vol_lw_stretch_short  edge/trade rank  5  ->  TOTAL rank  2
      vwap_avwap_pdhigh     edge/trade rank  3  ->  TOTAL rank 16  (only 101 trades)

The previous sweep was built from the edge/trade list and returned 0 of 384 beating
the incumbent — because it was stocked with rare, edge-dense signals that cannot
generate enough trades. This uses the total-edge list instead, which surfaces
families the last run never tested: ic_fvg_long has 505 trades at +7.24 edge
(total 3,656, better than the incumbent long's 2,976) and was not in that list at all.
"""
import argparse, itertools, os, pandas as pd
import funded_search as fs, funded_1yr as f1, lucid_fast as LF, sim_trace as ST
WIN = (9.75, 11.0)
BRACKETS = ((2.0, 3.0),)
SIZES = ((440, 300), (440, 400))
LONGS = ["sr_round100_break","ic_fvg_long","vwap_reclaim_long","lw_gsv_long",
         "qm_ep_long","wy_lps_long","bs_avwap_2day_long","ww_psar_dmi_long"]
SHORTS = ["vol_lw_stretch_short","lw_gsv_short","rh_irb_gated_short","macd_x_short",
          "donch20_short","tm_open_newlow","bs_avwap_2day_short","wy_sow_short"]
ap = argparse.ArgumentParser(); ap.add_argument("--slice"); ap.add_argument("--out", required=True)
a = ap.parse_args()
df = fs.load_enriched(); pl = f1.load_plugins(df)
end = df.index[-1]; cut = end - pd.DateOffset(months=5)
FR = (("hold", df[df.index < cut]), ("recent", df[df.index >= cut]))
r = lambda fr, n: pd.Series((pl[n] if n in pl else fs.sig(df, n))[0]).reindex(fr.index).fillna(False).to_numpy(bool)
pairs = list(itertools.product(LONGS, SHORTS))
if a.slice:
    i,k = (int(x) for x in a.slice.split("/")); pairs = pairs[i::k]
first = not os.path.exists(a.out)
for ln, sn in pairs:
    rows = []
    try: P = {w: LF.prep(f, r(f, ln), r(f, sn), WIN) for w, f in FR}
    except Exception as e: print(f"  !! {ln}+{sn}: {e}", flush=True); continue
    for (sl,tp),(cap,bud) in itertools.product(BRACKETS, SIZES):
        row = dict(long=ln, short=sn, sl=sl, tp=tp, cap=cap, budget=bud); ok=True
        for w in ("hold","recent"):
            res = [ST.trace(P[w], k, cap, bud, sl=sl, tp=tp)
                   for k in range(0, len(P[w]["per"]), 4) if len(P[w]["per"]) - k >= 20]
            if not res: ok=False; break
            m = ST.summarise(res)
            for k2 in ("paid","bust","mean","med","days"): row[f"{w}_{k2}"] = m[k2]
        if ok: rows.append(row)
    if rows:
        pd.DataFrame(rows).to_csv(a.out, mode="a", header=first, index=False); first=False
    print(f"  {ln} + {sn}", flush=True)

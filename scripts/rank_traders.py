"""How do the 85 named-trader strategies rank against the incumbents?"""
import pandas as pd

pd.set_option("display.width", 210)
d = pd.read_csv("rank_sides.csv")
PREF = ("cn_", "lr_", "lw_", "mf_", "tt_", "jc_", "ab_")
t = d[d.family.str.startswith(PREF)]
C = ["family", "fires", "sel_tr", "sel_win", "sel_net", "hold_tr", "hold_win",
     "hold_net", "hold_bust", "hold_pay", "both_pos"]

print(f"total families {len(d)}   trader strategies {len(t)}")

for sd, lbl in ((-1, "SHORT"), (1, "LONG")):
    s = t[t.side == sd].sort_values("hold_net", ascending=False)
    print(f"\n===== TRADER {lbl}S — top by holdout net =====")
    print(s[C].head(12).to_string(index=False))
    print(f"  {lbl}: {len(s)} trader families, "
          f"{int((s.hold_net > 0).sum())} holdout-positive, "
          f"{int(s.both_pos.sum())} positive in BOTH")

print("\n===== OVERALL LEADERBOARD (all 278 families) =====")
for sd, lbl in ((-1, "SHORT"), (1, "LONG")):
    s = d[d.side == sd].sort_values("hold_net", ascending=False).head(10)
    s = s.copy()
    s["src"] = ["TRADER" if f.startswith(PREF) else "" for f in s.family]
    print(f"\n  top {lbl}S:")
    print(s[C + ["src"]].to_string(index=False))

print("\n===== INCUMBENTS FOR REFERENCE =====")
inc = d[d.family.isin(["vol_lw_stretch_short", "sr_round100_break",
                       "ema20_50_long", "pdh_fade_short", "bb_break_short"])]
print(inc[C].to_string(index=False))

print("\n===== VERDICT =====")
best_tr_short = t[t.side == -1].hold_net.max()
best_tr_long = t[t.side == 1].hold_net.max()
inc_short = d[d.family == "vol_lw_stretch_short"].hold_net.iloc[0]
inc_long = d[d.family == "sr_round100_break"].hold_net.iloc[0]
print(f"  best TRADER short holdout net : ${best_tr_short:,.0f}")
print(f"  incumbent vol_lw_stretch_short: ${inc_short:,.0f}")
print(f"  best TRADER long  holdout net : ${best_tr_long:,.0f}")
print(f"  incumbent sr_round100_break   : ${inc_long:,.0f}")

# candidates worth pairing
cand_s = t[(t.side == -1) & (t.hold_net > 0)].sort_values("hold_net", ascending=False).head(8)
cand_l = t[(t.side == 1) & (t.hold_net > 0)].sort_values("hold_net", ascending=False).head(8)
print("\n  PAIRING CANDIDATES (write to trader_pairs.txt):")
print("   shorts:", list(cand_s.family))
print("   longs :", list(cand_l.family))
with open("trader_pairs.txt", "w") as fh:
    fh.write(",".join(cand_l.family) + "\n")
    fh.write(",".join(cand_s.family) + "\n")

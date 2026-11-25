"""Why do random signals beat real ones 7x even with in-window fire counts matched?

Fixing the randomiser made the anomaly WORSE (random max mean $9,753-16,083 vs
real $2,295; 51% of all random cells beat the real best). A random entry cannot
out-earn a real one by 7x after fees. So the bug is not in the randomiser — it is
in what the harness rewards.

HYPOTHESIS: matched SIGNALS is not matched TRADES. The replay consumes every
signal between entry and exit:

    while j < len(idxs) and idxs[j] <= m: j += 1

Real signals arrive in CLUSTERS (a breakout fires repeatedly as price pushes), so
one trade swallows several of them. Random signals are spread uniformly across the
window, so far fewer get swallowed and far more become actual trades.

That matters because this account model is structurally biased toward trade COUNT:
the $1,000 MLL bounds the downside, floor-aware sizing shrinks positions before
they can breach it, the daily cap limits per-day upside, and withdrawals bank gains
permanently. Under those rules a coin flip taken often beats an edge taken rarely.

This measures trades taken and win rate directly. If random takes far more trades
at a similar win rate, the control is measuring frequency, not timing — and so is
every "mean withdrawn" comparison in this project between signals of different
firing density.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import funded_search as fs
import funded_1yr as f1
import lucid_fast as LF
import sim_trace as ST
from bog_control import randomise

WIN, SL, TP, CAP, BUD = (9.75, 11.0), 2.0, 3.0, 440, 300
PAIR = ("sr_round100_break", "vol_lw_stretch_short")

df = fs.load_enriched()
pl = f1.load_plugins(df)
end = df.index[-1]
hold = df[df.index < end - pd.DateOffset(months=5)]
day_ids = pd.factorize(hold["_day"])[0]
eth = hold["eth"].to_numpy(float)
elig = (eth >= WIN[0]) & (eth <= WIN[1]) & (hold["atr"].to_numpy(float) > 0)


def get(name):
    e, _ = pl[name] if name in pl else fs.sig(df, name)
    return pd.Series(e).reindex(hold.index).fillna(False).to_numpy(bool)


def trade_stats(el, es, label):
    """Count actual TRADES and their win rate, independent of account state."""
    P = LF.prep(hold, el, es, WIN)
    hi, lo, cl, atr, ethv = P["hi"], P["lo"], P["cl"], P["atr"], P["eth"]
    wins = losses = 0
    pnl_pts = 0.0
    trades_per_day = []
    for s, e, idxs, sides in P["per"]:
        j, n_today = 0, 0
        while j < len(idxs) and n_today < 6:
            i, sd = idxs[j], int(sides[j])
            a = atr[i]
            entry = cl[i]
            stop_px, targ_px = entry - sd * a * SL, entry + sd * a * TP
            px, m = None, i + 1
            while m < e:
                if sd > 0:
                    if lo[m] <= stop_px: px = stop_px; break
                    if hi[m] >= targ_px: px = targ_px; break
                else:
                    if hi[m] >= stop_px: px = stop_px; break
                    if lo[m] <= targ_px: px = targ_px; break
                if ethv[m] >= 16.0 or m == e - 1:
                    px = cl[m]; break
                m += 1
            if px is None:
                px, m = cl[e - 1], e - 1
            r = sd * (px - entry)
            pnl_pts += r
            wins += r > 0
            losses += r <= 0
            n_today += 1
            while j < len(idxs) and idxs[j] <= m:
                j += 1
        trades_per_day.append(n_today)
    tot = wins + losses
    tpd = np.array(trades_per_day)
    print(f"  {label:<12} signals={int(el.sum()+es.sum()):>5}  "
          f"TRADES={tot:>5}  trades/day={tpd.mean():>4.2f}  "
          f"win%={100*wins/max(tot,1):>5.1f}  "
          f"pts/trade={pnl_pts/max(tot,1):>+7.2f}")
    return tot


def account(el, es, label):
    P = LF.prep(hold, el, es, WIN)
    res = [ST.trace(P, k, CAP, BUD, sl=SL, tp=TP)
           for k in range(0, len(P["per"]), 8) if len(P["per"]) - k >= 20]
    m = ST.summarise(res)
    print(f"  {label:<12} paid={m['paid']:>5.1f}%  bust={m['bust']:>4.1f}%  "
          f"mean=${m['mean']:>7,.0f}  med=${m['med']:>7,.0f}  "
          f"pays/yr={m['avg_pays']:>5.2f}")


rl, rs = get(PAIR[0]), get(PAIR[1])
print("=" * 108)
print("TRADE-LEVEL (no account rules) — signals matched in-window, are TRADES matched?")
print("=" * 108)
trade_stats(rl, rs, "REAL")
for seed in (0, 1, 2):
    rng = np.random.default_rng(seed)
    trade_stats(randomise(rl, day_ids, rng, elig),
                randomise(rs, day_ids, rng, elig), f"RND{seed}")

print("\n" + "=" * 108)
print("ACCOUNT-LEVEL (full LucidPro rules) — the same signals through the simulator")
print("=" * 108)
account(rl, rs, "REAL")
for seed in (0, 1, 2):
    rng = np.random.default_rng(seed)
    account(randomise(rl, day_ids, rng, elig),
            randomise(rs, day_ids, rng, elig), f"RND{seed}")

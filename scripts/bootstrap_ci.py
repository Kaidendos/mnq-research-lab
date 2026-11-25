"""Confidence intervals for the headline numbers. Everything so far is a point estimate.

"56% get paid, 2.1% bust, mean $2,352, median $334" has been quoted all session with
no error bar. Those figures come from 291 overlapping account starts on ONE realised
5-year path — which is a single draw from the distribution of paths the strategy
could have produced. The overlap also means the 291 accounts are far from
independent, so the naive spread across them understates uncertainty badly.

A block bootstrap fixes both. Sessions are resampled in contiguous blocks (default
10 sessions, ~2 weeks) so that volatility clustering and streaks survive; only the
ORDER and SELECTION of blocks is randomised. Each resampled path gets a full account
simulation, and the spread across paths is an honest interval.

Blocks matter: an i.i.d. bootstrap would shuffle individual sessions, destroy the
clustering that drives drawdowns, and produce intervals that are far too tight.

Reports 5th/50th/95th percentiles for paid%, bust%, mean and median — i.e. what a
good, typical and bad five-year run of this strategy actually looks like.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import funded_search as fs
import funded_1yr as f1
import lucid_fast as LF

WIN, SL, TP, CAP, BUD, MC = (9.75, 11.0), 2.0, 3.0, 440, 300, 10
LONG_SIG, SHORT_SIG = "sr_round100_break", "vol_lw_stretch_short"
N_PATHS = 400
BLOCK = 10
SESSIONS_PER_ACCOUNT = 250       # ~1 year of trading days
ACCOUNTS_PER_PATH = 12

df = fs.load_enriched()
pl = f1.load_plugins(df)
end = df.index[-1]
hold = df[df.index < end - pd.DateOffset(months=5)]


def g(n):
    e, _ = pl[n] if n in pl else fs.sig(df, n)
    return pd.Series(e).reindex(hold.index).fillna(False).to_numpy(bool)


P = LF.prep(hold, g(LONG_SIG), g(SHORT_SIG), WIN)
HI, LO, CL, ATR, ETH = P["hi"], P["lo"], P["cl"], P["atr"], P["eth"]
PER = P["per"]
NS = len(PER)
print(f"{NS} sessions available, {N_PATHS} bootstrap paths x {ACCOUNTS_PER_PATH} accounts")


def day_net(k, bal, floor):
    """Realised P&L for session k given the account's state. Same rules as sim_trace."""
    s, e, idxs, sides = PER[k]
    room = bal - floor
    if room <= 0:
        return 0.0, 0
    budget = min(BUD, room)
    net, ntr, j = 0.0, 0, 0
    while j < len(idxs) and ntr < 6:
        i, sd = idxs[j], int(sides[j])
        a, entry = ATR[i], CL[i]
        n = min(MC, int((budget + net) / (a * SL * LF.PV)),
                int((CAP - net) / (a * TP * LF.PV)))
        if n < 1:
            j += 1
            continue
        stop_px, targ_px = entry - sd * a * SL, entry + sd * a * TP
        px, m = None, i + 1
        while m < e:
            if sd > 0:
                if LO[m] <= stop_px: px = stop_px; break
                if HI[m] >= targ_px: px = targ_px; break
            else:
                if HI[m] >= stop_px: px = stop_px; break
                if LO[m] <= targ_px: px = targ_px; break
            if ETH[m] >= 16.0 or m == e - 1:
                px = CL[m]; break
            m += 1
        if px is None:
            px, m = CL[e - 1], e - 1
        net += sd * (px - entry) * LF.PV * n - LF.FEE * n
        ntr += 1
        while j < len(idxs) and idxs[j] <= m:
            j += 1
    return net, ntr


def run_path(order):
    """One account over a resampled session ordering."""
    bal, floor, locked = LF.START, LF.START - LF.MLL, False
    cyc_d, cyc_p, cyc_b = 0, 0.0, 0.0
    wd, npay = 0.0, 0
    for k in order:
        net, ntr = day_net(k, bal, floor)
        if ntr == 0:
            continue
        bal += net
        cyc_d += 1; cyc_p += net; cyc_b = max(cyc_b, net)
        if bal <= floor:
            return "BUST", wd, npay
        if not locked:
            floor = max(floor, bal - LF.MLL)
            if bal >= LF.BUFFER:
                floor, locked = LF.LOCK_FLOOR, True
        if bal > LF.BUFFER and cyc_d >= LF.MIN_DAYS and cyc_p > 0 \
                and cyc_b <= LF.CONSISTENCY * cyc_p:
            amt = min(bal - LF.BUFFER, LF.CAP_FIRST if npay == 0 else LF.CAP_AFTER)
            if amt >= 250:
                bal -= amt; wd += amt; npay += 1
                cyc_d, cyc_p, cyc_b = 0, 0.0, 0.0
    return ("PAID" if npay else "STALLED"), wd, npay


rng = np.random.default_rng(0)
n_blocks = SESSIONS_PER_ACCOUNT // BLOCK
paths = []
for p_i in range(N_PATHS):
    fates, wds = [], []
    for _ in range(ACCOUNTS_PER_PATH):
        starts = rng.integers(0, NS - BLOCK, size=n_blocks)
        order = np.concatenate([np.arange(s, s + BLOCK) for s in starts])
        fate, wd, npay = run_path(order)
        fates.append(fate); wds.append(wd)
    w = np.array(wds)
    paths.append(dict(paid=100 * np.mean([f == "PAID" for f in fates]),
                      bust=100 * np.mean([f == "BUST" for f in fates]),
                      mean=w.mean(), med=float(np.median(w))))
    if (p_i + 1) % 50 == 0:
        print(f"  {p_i+1}/{N_PATHS} paths", flush=True)

b = pd.DataFrame(paths)
b.to_csv("bootstrap_ci.csv", index=False)
print("\n" + "=" * 96)
print(f"BLOCK BOOTSTRAP — {N_PATHS} resampled 5-year paths, {BLOCK}-session blocks")
print("Point estimates from the single realised path: paid 56.0%, bust 2.1%, "
      "mean $2,352, med $334")
print("=" * 96)
print(f"  {'metric':<14}{'5th pct':>12}{'median':>12}{'95th pct':>12}{'realised':>12}")
for col, real, fmt in (("paid", 56.0, "{:.1f}%"), ("bust", 2.1, "{:.1f}%"),
                       ("mean", 2352, "${:,.0f}"), ("med", 334, "${:,.0f}")):
    lo_, mid, hi_ = np.percentile(b[col], [5, 50, 95])
    print(f"  {col:<14}{fmt.format(lo_):>12}{fmt.format(mid):>12}"
          f"{fmt.format(hi_):>12}{fmt.format(real):>12}")

print(f"\n  paths where NOBODY got paid            : "
      f"{100*(b.paid == 0).mean():.1f}%")
print(f"  paths with bust above 10%              : {100*(b.bust > 10).mean():.1f}%")
print(f"  paths with mean below $0               : {100*(b['mean'] <= 0).mean():.1f}%")
print(f"  paths with mean below the realised $2,352 : {100*(b['mean'] < 2352).mean():.1f}%")
print("\n  If the realised path sits near the TOP of the bootstrap range, the headline")
print("  numbers quoted all session are a lucky draw and should be discounted.")

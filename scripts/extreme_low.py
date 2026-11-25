"""Does buying the low work if you only buy when it is REALLY low?

The fade sweep tested shallow dips and they were worse than random. But "buy the
dip" and "buy a genuine capitulation" are different hypotheses, and the first
failing does not settle the second. If mean reversion exists at all, it should live
in the tail — so the question is whether EDGE RISES MONOTONICALLY WITH EXTREMITY.

Five different definitions of "low" are swept from mild to extreme, because "low"
is ambiguous and the answer may depend on which one is meant:

  vs SESSION OPEN   how far price has fallen today
  vs PRIOR-DAY LOW  how far it has broken yesterday's floor
  vs 5-DAY LOW      a multi-day washout rather than one bad session
  vs VWAP           how far below the day's average participation price
  RSI(2)            the classic oversold oscillator, pushed to its limit

Read the EDGE column, not ppt — and read `n` alongside it. Tightening any filter
raises per-trade edge simply by trading less, and past ~30 trades the estimate is
noise. The pattern that would confirm the hypothesis is edge climbing steadily as
the threshold tightens, while n stays large enough to believe. The pattern that
refutes it is edge wandering without direction, or only "improving" once n collapses.

Run on the WIDE window (9:45-15:30) so the extreme thresholds still have a usable
sample; the narrow window would leave single digits.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import funded_search as fs
import lucid_fast as LF

WIN, SL, TP = (9.75, 15.5), 2.0, 3.0
SEEDS = 10

df = fs.load_enriched()
end = df.index[-1]
hold = df[df.index < end - pd.DateOffset(months=5)]
c, o, h, l = hold["close"], hold["open"], hold["high"], hold["low"]
atr, day = hold["atr"], hold["_day"]
bod = hold.groupby(day).cumcount()
sess_open = o.groupby(day).transform("first")
vwap = hold["vwap"]
lo5 = l.rolling(5 * 78).min().shift(1)          # ~5 sessions of 5-min bars


def rsi(s, n=2):
    d = s.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


r2 = rsi(c, 2)
eth = hold["eth"].to_numpy(float)
ok = (eth >= WIN[0]) & (eth <= WIN[1]) & (atr.to_numpy(float) > 0)
d_ids = pd.factorize(day)[0]
starts = np.flatnonzero(np.r_[True, d_ids[1:] != d_ids[:-1]])
ends = np.r_[starts[1:], len(d_ids)]

# every variant requires an up-close so it is a REJECTION of the low, not a
# falling knife caught mid-bar
confirm = (c > o) & (bod > 2)

DEPTH_OPEN = (c - sess_open) / atr
DEPTH_PDL = (c - hold["pdl"]) / atr
DEPTH_LO5 = (c - lo5) / atr
DEPTH_VWAP = (c - vwap) / atr

CONCEPTS = [
    ("below SESSION OPEN (xATR)", DEPTH_OPEN, (-1.0, -1.5, -2.0, -2.5, -3.0, -4.0, -5.0)),
    ("below PRIOR-DAY LOW (xATR)", DEPTH_PDL, (0.0, -0.5, -1.0, -1.5, -2.0, -3.0)),
    ("below 5-DAY LOW (xATR)", DEPTH_LO5, (0.0, -0.25, -0.5, -1.0, -1.5)),
    ("below VWAP (xATR)", DEPTH_VWAP, (-1.0, -1.5, -2.0, -2.5, -3.0, -4.0)),
]


def points(el):
    es = np.zeros(len(el), bool)
    P = LF.prep(hold, el, es, WIN)
    hi_, lo_, cl_, atr_, ev = P["hi"], P["lo"], P["cl"], P["atr"], P["eth"]
    tot, n, w = 0.0, 0, 0
    for s, e, idxs, sides in P["per"]:
        j, t = 0, 0
        while j < len(idxs) and t < 6:
            i = idxs[j]
            a, en = atr_[i], cl_[i]
            sp, tp_ = en - a * SL, en + a * TP
            px, m = None, i + 1
            while m < e:
                if lo_[m] <= sp: px = sp; break
                if hi_[m] >= tp_: px = tp_; break
                if ev[m] >= 16.0 or m == e - 1:
                    px = cl_[m]; break
                m += 1
            if px is None:
                px, m = cl_[e - 1], e - 1
            r = px - en
            tot += r; n += 1; w += r > 0; t += 1
            while j < len(idxs) and idxs[j] <= m:
                j += 1
    return tot, n, w


def shuf(mask, rng):
    prof = [int((mask[s:e] & ok[s:e]).sum()) for s, e in zip(starts, ends)]
    order = rng.permutation(len(prof))
    out = np.zeros(len(mask), bool)
    for pos, (s, e) in enumerate(zip(starts, ends)):
        k = prof[order[pos]]
        if not k:
            continue
        slot = np.flatnonzero(ok[s:e])
        if len(slot):
            out[s + rng.choice(slot, size=min(k, len(slot)), replace=False)] = True
    return out


def score(mask):
    tot, n, w = points(mask)
    if n < 12:
        return n, None, None, None, None
    ctl = []
    for s_ in range(SEEDS):
        t2, n2, _ = points(shuf(mask, np.random.default_rng(s_)))
        if n2:
            ctl.append(t2 / n2)
    if not ctl:
        return n, None, None, None, None
    ppt = tot / n
    med = float(np.median(ctl))
    return n, 100 * w / n, ppt, ppt - med, int((np.array(ctl) >= ppt).sum())


print("=" * 104)
print("DOES BUYING THE LOW WORK IF YOU ONLY BUY WHEN IT IS REALLY LOW?")
print(f"holdout, {WIN[0]}-{WIN[1]}, SL2/TP3, long only, up-close confirmation required")
print("=" * 104)
for label, depth, thresholds in CONCEPTS:
    print(f"\n  ### {label}")
    print(f"    {'threshold':>10}{'trades':>8}{'win%':>8}{'ppt':>9}{'EDGE':>9}{'beaten':>8}{'total':>9}")
    for th in thresholds:
        mask = ((depth <= th) & confirm).fillna(False).to_numpy(bool)
        n, w, ppt, edge, beaten = score(mask)
        if edge is None:
            print(f"    {th:>10}{n:>8}   (too few trades to estimate)")
            continue
        flag = "  <- thin" if n < 30 else ""
        print(f"    {th:>10}{n:>8}{w:>8.1f}{ppt:>+9.2f}{edge:>+9.2f}"
              f"{beaten:>6}/10{edge*n:>9,.0f}{flag}")

print(f"\n  ### RSI(2) pushed to its limit")
print(f"    {'threshold':>10}{'trades':>8}{'win%':>8}{'ppt':>9}{'EDGE':>9}{'beaten':>8}{'total':>9}")
for th in (10, 5, 3, 2, 1):
    mask = ((r2 < th) & confirm).fillna(False).to_numpy(bool)
    n, w, ppt, edge, beaten = score(mask)
    if edge is None:
        print(f"    {th:>10}{n:>8}   (too few trades to estimate)")
        continue
    flag = "  <- thin" if n < 30 else ""
    print(f"    {th:>10}{n:>8}{w:>8.1f}{ppt:>+9.2f}{edge:>+9.2f}{beaten:>6}/10{edge*n:>9,.0f}{flag}")

print("\n" + "=" * 104)
print("Confirmation would be EDGE rising steadily as the threshold tightens, with n")
print("still large. Refutation is edge wandering, or only rising once n collapses.")

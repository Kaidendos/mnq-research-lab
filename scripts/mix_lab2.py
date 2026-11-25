"""mix_lab2.py - (1) robust partner selection, (2) pre-set size ramps for EMA pullback + news fade.
Same news-legal window / data as mix_lab.py (Feb 18 - Jul 15 2026; TUNE Feb 18 - Apr 30, VALID May 1 - Jul 15).
Robust partner = >=15 Feb-Apr trades, positive pts/trade in EACH of 3 Feb-Apr slices, daily-P&L correlation with
the base mix < 0.3 in Feb-Apr. Added at 1 MNQ. Ramps are fixed rules, not tuned. Analysis only."""
import numpy as np, pandas as pd
src = open(r'C:\Users\YOU\daytrading-automation\mix_lab.py').read().split('# ---- standalone partner table ----')[0]
exec(src)

def perday(trs, days):
    by = {}
    for dd_, pts, sd in trs: by[dd_] = by.get(dd_, 0.) + pts * 2
    return np.array([by.get(x, 0.) for x in days])           # $ per 1 contract per day

def eval_dyn(comps, days, rule):
    """comps: dict name -> per-contract daily $ array; rule(prof, peak_dd) -> dict name -> contracts"""
    res = []
    for s0 in range(0, len(days) - 5):
        bal, fl, mx, best, out, nd = 50000., 48000., 50000., 0., 'open', 0
        for k in range(s0, len(days)):
            nd += 1; sz = rule(bal - 50000, bal - mx)
            p = max(-1200., sum(sz[n] * comps[n][k] for n in sz)); bal += p
            if bal <= fl: out = 'bust'; break
            best = max(best, p); prof = bal - 50000
            if prof >= 3000 and best <= 0.5 * prof: out = 'pass'; break
            mx = max(mx, bal); fl = 50100. if mx >= 52100 else max(fl, mx - 2000)
        res.append((out, nd))
    n = max(1, len(res)); pas = [r[1] for r in res if r[0] == 'pass']
    return 100 * len(pas) / n, 100 * sum(r[0] == 'bust' for r in res) / n, (float(np.median(pas)) if pas else np.nan)

def show(label, extra=None, rule=None):
    out = [label]
    for nm, days in (('Feb-Apr', TD), ('May-Jul', VD)):
        comps = {'ema': perday(base_news, days), 'fade': perday(NEWSFADE, days)}
        for x in (extra or []): comps[x] = perday(POOL[x], days)
        r = rule or (lambda prof, dd: dict({'ema': 3, 'fade': 3}, **{x: 1 for x in (extra or [])}))
        p, b, md = eval_dyn(comps, days, r)
        out.append(f'{nm} pass {p:3.0f}% bust {b:3.0f}% median {md} d')
    print(' | '.join(out))

TD = [x for x in DAYS if x < SPLIT]; VD = [x for x in DAYS if x >= SPLIT]
print('\n=== SIZE RAMPS on EMA pullback + news fade (fixed rules) ===')
show('base: EMA 3 / fade 3                         ')
show('ramp: EMA 4 once profit >= $1,000            ', rule=lambda p, dd: {'ema': 4 if p >= 1000 else 3, 'fade': 3})
show('ramp: both 4 once profit >= $1,500           ', rule=lambda p, dd: {'ema': 4 if p >= 1500 else 3, 'fade': 4 if p >= 1500 else 3})
show('defend: EMA 2 / fade 2 while down > $800     ', rule=lambda p, dd: {'ema': 2 if p < -800 else 3, 'fade': 2 if p < -800 else 3})
show('ramp + defend                                ', rule=lambda p, dd: {'ema': 2 if p < -800 else 4 if p >= 1000 else 3, 'fade': 2 if p < -800 else 3})
show('start small: EMA 2 / fade 2 -> 3/3 at +$500 -> 4/3 at +$1,500', rule=lambda p, dd: {'ema': 2 if p < 500 else 3 if p < 1500 else 4, 'fade': 2 if p < 500 else 3})

# ---- robust partners ----
blocks = np.array_split(np.array(TD), 3)
base_t = perday(base_news, TD) * 3 + perday(NEWSFADE, TD) * 3
rob = []
for nm, trs in POOL.items():
    if nm == 'news_fade': continue
    t_ = [x for x in trs if x[0] < SPLIT]
    if len(t_) < 15: continue
    bpts = [np.mean([x[1] for x in t_ if b[0] <= x[0] <= b[-1]] or [-1]) for b in blocks]
    if min(bpts) <= 0: continue
    c = np.corrcoef(base_t, perday(trs, TD))[0, 1]
    if not (c < 0.3): continue
    v_ = [x[1] for x in trs if x[0] >= SPLIT]
    rob.append(dict(partner=nm, tune_n=len(t_), min_block_pts=min(bpts), corr=c,
                    valid_n=len(v_), valid_pts=np.mean(v_) if v_ else np.nan))
R = pd.DataFrame(rob).sort_values('min_block_pts', ascending=False)
print(f'\n=== ROBUST PARTNERS (positive in all 3 Feb-Apr slices, corr<0.3): {len(R)} of {len(POOL)-1} ===')
pd.set_option('display.width', 250)
print(R.head(12).round(2).to_string(index=False))
print(f'of these, positive pts/trade in May-Jul: {(R.valid_pts > 0).sum()} / {len(R)}  (all partners: see mix_lab: 101/760 both halves)')
print('\n=== BASE + top-K robust partners at 1 MNQ (chosen on Feb-Apr only) ===')
for K in (1, 2, 3, 5):
    show(f'EMA3 + fade3 + top {K} robust @1               ', extra=list(R.partner.head(K)))

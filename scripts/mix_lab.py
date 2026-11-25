"""mix_lab.py - combine the EMA pullback with frequent and rare partner strategies, LucidDaily news-legal.
Window = news-calendar coverage only (2026-02-18 .. 2026-07-15) so the red-folder rule is real:
  no entries on bars closing from T-15 to T+2 min; any open position exits at the last bar close <= T-2 min.
TUNE = Feb 18 - Apr 30, VALID = May 1 - Jul 15 (never used to choose).
Partners: every family in their backtest_lab (13 families, their signal code) x side x bracket x ADX gate,
plus the post-news FADE (T+5, 1x release-bar stop, 50% retrace target, 60 min) as a rare trader.
Portfolio: components trade independently (NT runs each strategy on its own), daily P&L summed, DLL -$1,200.
Greedy build on TUNE starting from EMA pullback @3 MNQ; each step adds the (component, size) that most
improves eval score = pass% - 2 x bust%. Costs 1.1 pts/contract (2.0 for the news fade). Analysis only.
"""
import numpy as np, pandas as pd, itertools
src = open(r'C:\Users\YOU\daytrading-automation\ts_backtest.py').read().split("LAST = np.r_[")[0]
exec(src)
LAST = np.r_[DAY[1:] != DAY[:-1], True]; ADX = d.adx.values
W0, W1, SPLIT = pd.Timestamp('2026-02-18').date(), pd.Timestamp('2026-07-15').date(), pd.Timestamp('2026-05-01').date()

closeET = (d.index + pd.Timedelta(minutes=5)).tz_convert('America/New_York')
NOENT = np.zeros(len(d), bool); FORCEX = np.zeros(len(d), bool)
cl_ns = closeET.as_unit('ns').asi8
for T in ev_t:
    t = pd.Timestamp(T).as_unit('ns').value
    NOENT |= (cl_ns >= t - 15 * 60e9) & (cl_ns < t + 2 * 60e9)
    FORCEX |= (cl_ns <= t - 2 * 60e9) & (cl_ns > t - 7 * 60e9)
print('bars needing forced exit:', FORCEX.sum(), ' entry-blocked bars:', NOENT.sum())

FAMCACHE = {}
def comp_trades(fam_, p, side, sl, tp, gate, news=True, h1=15.5):
    key = (fam_, tuple(sorted(p.items())))
    if key not in FAMCACHE:
        lo, sh = backtest_lab.fam(d, fam_, p); FAMCACHE[key] = (lo.fillna(False).values, sh.fillna(False).values)
    lo, sh = FAMCACHE[key]
    out, pos = [], None
    for i in range(len(d)):
        if pos:
            if pos['s'] > 0: ex = pos['sl'] if L[i] <= pos['sl'] else pos['tp'] if H[i] >= pos['tp'] else None
            else: ex = pos['sl'] if H[i] >= pos['sl'] else pos['tp'] if L[i] <= pos['tp'] else None
            if ex is None and (LAST[i] or (news and FORCEX[i])): ex = Cc[i]
            if ex is not None:
                out.append((DAY[i], (ex - pos['e']) * pos['s'] - COST, pos['sd'])); pos = None
        if pos or LAST[i] or not (9.6667 <= EH[i] <= h1) or not ATR[i] > 0: continue
        if news and (NOENT[i] or FORCEX[i]): continue
        if gate == 'adx>25' and not ADX[i] >= 25: continue
        if gate == 'adx<25' and not ADX[i] < 25: continue
        s = 1 if side in ('both', 'long') and lo[i] else -1 if side in ('both', 'short') and sh[i] else 0
        if s: pos = dict(s=s, e=Cc[i], sl=Cc[i] - s * sl * ATR[i], tp=Cc[i] + s * tp * ATR[i], sd=sl * ATR[i])
    return [x for x in out if W0 <= x[0] <= W1]

# news fade from news_v2 (separate namespace: it uses Globex data)
ns = {}
exec(open(r'C:\Users\YOU\daytrading-automation\news_v2.py').read().split('GRID = list(')[0], ns)
NEWSFADE = [(t.date(), pts, sd) for t in ns['EVT'] for r in [ns['trade'](t, 5, 0, 'r1.0', 'half', 60)] if r
            for pts, sd in [r]]
DAYS = sorted({x for x in DAY if W0 <= x <= W1})

def daily_usd(comps, days):
    """comps: list of (trades, ncon). returns np.array of daily $ over days (DLL capped)."""
    by = {}
    for trs, n in comps:
        for dd_, pts, sd in trs: by[dd_] = by.get(dd_, 0.) + pts * 2 * n
    return np.array([max(-1200., by.get(x, 0.)) for x in days])

def evalw(dv):
    res = []
    for s0 in range(0, len(dv) - 5):
        bal, fl, mx, best, out, nd = 50000., 48000., 50000., 0., 'open', 0
        for p in dv[s0:]:
            nd += 1; bal += p
            if bal <= fl: out = 'bust'; break
            best = max(best, p); prof = bal - 50000
            if prof >= 3000 and best <= 0.5 * prof: out = 'pass'; break
            mx = max(mx, bal); fl = 50100. if mx >= 52100 else max(fl, mx - 2000)
        res.append((out, nd))
    n = max(1, len(res)); pas = [r[1] for r in res if r[0] == 'pass']
    eq = np.cumsum(dv); dd = (eq - np.maximum.accumulate(np.r_[0, eq])[1:]).min() if len(dv) else 0
    return dict(pass_=100 * len(pas) / n, bust=100 * sum(r[0] == 'bust' for r in res) / n,
                days=float(np.median(pas)) if pas else np.nan, usd=float(dv.sum()), dd=float(dd))
TD = [x for x in DAYS if x < SPLIT]; VD = [x for x in DAYS if x >= SPLIT]
def split(trs): return [x for x in trs if x[0] < SPLIT], [x for x in trs if x[0] >= SPLIT]
def score(e): return e['pass_'] - 2 * e['bust']

# ---- base: EMA pullback with and without the news rule ----
pd.set_option('display.width', 300); pd.set_option('display.max_columns', 30)
base_news = comp_trades('ema_pullback', {}, 'both', 1.0, 0.5, 'adx>25', news=True)
base_raw = comp_trades('ema_pullback', {}, 'both', 1.0, 0.5, 'adx>25', news=False)
for lab, b in (('EMA pullback, NO news rule (as before)', base_raw), ('EMA pullback, WITH LucidDaily news rule', base_news)):
    t_, v_ = split(b); et, ev_ = evalw(daily_usd([(t_, 3)], TD)), evalw(daily_usd([(v_, 3)], VD))
    print(f"{lab:42s} trades {len(b):3d} pts/tr {np.mean([x[1] for x in b]):+.2f} | Feb-Apr pass {et['pass_']:.0f}% bust {et['bust']:.0f}% "
          f"${et['usd']:+,.0f} | May-Jul pass {ev_['pass_']:.0f}% bust {ev_['bust']:.0f}% ${ev_['usd']:+,.0f}")

# ---- candidate pool ----
GRIDP = {'vwap_rev': [{'k': 1.0}, {'k': 1.5}, {'k': 2.0}], 'rsi_rev': [{'th': 25}, {'th': 30}, {'th': 35}],
         'bb_rev': [{'k': 1.5}, {'k': 2.0}, {'k': 2.5}], 'keltner_rev': [{'k': 1.0}, {'k': 1.5}, {'k': 2.0}],
         'or_fade': [{}], 'pdhl_fade': [{}], 'ema_pullback': [{}], 'vwap_bounce': [{}], 'orb_retest': [{}],
         'orb_break': [{}], 'donchian': [{'n': 10}, {'n': 20}], 'macd': [{}], 'ema_cross': [{}]}
POOL = {'news_fade': NEWSFADE}
for f_, ps in GRIDP.items():
    for p in ps:
        for side, (sl, tp), gate in itertools.product(('both', 'long', 'short'), ((1.0, 0.5), (1.0, 1.0), (1.25, 0.5), (1.0, 1.5)),
                                                      ('none', 'adx>25', 'adx<25')):
            nm = f"{f_}{''.join(f'-{k}{v}' for k, v in p.items())}|{side}|{sl}/{tp}|{gate}"
            if nm.startswith('ema_pullback|both|1.0/0.5|adx>25'): continue
            POOL[nm] = comp_trades(f_, p, side, sl, tp, gate)
print('candidate partners:', len(POOL))

# ---- standalone partner table ----
rows = []
for nm, trs in POOL.items():
    t_, v_ = split(trs)
    if len(t_) < 8: continue
    rows.append(dict(partner=nm, tune_n=len(t_), per_day=len(t_) / len(TD), tune_pts=np.mean([x[1] for x in t_]),
                     valid_n=len(v_), valid_pts=np.mean([x[1] for x in v_]) if v_ else np.nan))
P = pd.DataFrame(rows)
print(f"\npartners with >=8 Feb-Apr trades: {len(P)}; positive in Feb-Apr: {(P.tune_pts > 0).sum()}; "
      f"positive in both halves: {((P.tune_pts > 0) & (P.valid_pts > 0)).sum()}; corr(tune,valid) {P[['tune_pts','valid_pts']].corr().iloc[0,1]:+.2f}")

# ---- greedy portfolio build on TUNE ----
def build(base_n, max_add=4):
    port = [('ema_pullback|both|1.0/0.5|adx>25', base_news, base_n)]
    cand = [r.partner for _, r in P.iterrows() if r.tune_pts > 0]
    log_ = []
    for step in range(max_add):
        cur = evalw(daily_usd([(split(t)[0], n) for _, t, n in port], TD))
        best = None
        for nm in cand:
            if nm in [x[0] for x in port]: continue
            for n in (1, 2, 3):
                e = evalw(daily_usd([(split(t)[0], k) for _, t, k in port] + [(split(POOL[nm])[0], n)], TD))
                if score(e) > score(cur) + 1e-9 and (best is None or (score(e), e['usd']) > (score(best[2]), best[2]['usd'])):
                    best = (nm, n, e)
        if best is None: break
        port.append((best[0], POOL[best[0]], best[1]))
    return port

def report(port, label):
    comps_t = [(split(t)[0], n) for _, t, n in port]; comps_v = [(split(t)[1], n) for _, t, n in port]
    et, ev_ = evalw(daily_usd(comps_t, TD)), evalw(daily_usd(comps_v, VD))
    nt = sum(len(c) for c, _ in comps_t) / len(TD); nv = sum(len(c) for c, _ in comps_v) / len(VD)
    print(f"\n### {label}")
    for nm, t, n in port: print(f"    {n} MNQ  {nm}   ({len(split(t)[0])/len(TD):.2f} trades/day Feb-Apr)")
    print(f"    Feb-Apr (tuned): {nt:.1f} trades/day  ${et['usd']:+,.0f}  maxDD ${et['dd']:,.0f}  eval pass {et['pass_']:.0f}% bust {et['bust']:.0f}% median {et['days']} days")
    print(f"    May-Jul (unseen): {nv:.1f} trades/day  ${ev_['usd']:+,.0f}  maxDD ${ev_['dd']:,.0f}  eval pass {ev_['pass_']:.0f}% bust {ev_['bust']:.0f}% median {ev_['days']} days")
    return et, ev_

report([('ema_pullback|both|1.0/0.5|adx>25 (news-legal)', base_news, 3)], 'BASE ALONE @3')
report([('ema_pullback|both|1.0/0.5|adx>25 (news-legal)', base_news, 4)], 'BASE ALONE @4')
report([('ema_pullback (news-legal)', base_news, 3), ('news_fade', NEWSFADE, 3)], 'BASE @3 + NEWS FADE @3 (rare partner, not tuned)')
for bn in (2, 3):
    report(build(bn), f'GREEDY MIX tuned on Feb-Apr, base @{bn}')
# robust-only partners: positive in both halves standalone (uses hindsight on VALID -> labelled as such)
rob = P[(P.tune_pts > 0) & (P.valid_pts > 0) & (P.tune_n >= 15)].sort_values('tune_pts', ascending=False).head(3)
report([('ema_pullback (news-legal)', base_news, 3)] + [(r.partner, POOL[r.partner], 1) for _, r in rob.iterrows()],
       'HINDSIGHT CHECK ONLY: base @3 + top-3 partners positive in BOTH halves @1 (uses May-Jul to pick)')
P.sort_values('tune_pts', ascending=False).to_csv(BASE + r'\mix_lab_partners.csv', index=False)

"""strat500.py - 504 new AUTOMATED strategies + StochReclaim30 (the live NinjaTrader bot) + round-3
candidates, 2026 ONLY. Tune sizing on Jan-Apr 2026, check on May-Aug 2026 (never used to choose).

Each strategy = entry signal x direction x trend filter x trade management:
  14 new signals: stoch_reclaim, macd_zero, bb_break, donchian20, ha_flip, supertrend, pivot_bounce,
                  cpr_break, inside_break, engulf_vwap, pin_level, three_bar_rev, rsi14_trend, keltner_break
  directions: long / short / both      filters: none / vwap (trade only on the VWAP side of the trade)
  management: fixed 1.0xATR 1.5R | fixed 0.75xATR 2R | fixed 1.5xATR 1R | breakeven@1R, 2R target |
              time stop 60 min, 1.0xATR 2R | trailing 1.0xATR chandelier, no target
Account: LucidDaily 50K eval (EOD trail $2,000 -> lock $50,100, DLL $1,200, target $3,000, 50% consistency).
Sizing tuned on Jan-Apr from $200/$300/$400 risk per trade or RAMP. Costs 1.1 pts/trade.
Analysis only - no order execution.
"""
import numpy as np, pandas as pd
_s = open(r'C:\Users\YOU\daytrading-automation\strat300.py').read().split('# ---------- simulation / account')[0]
exec(_s)

# ---------- extra indicators (RTH-only series) ----------
def rser(x): a = np.full(len(C), np.nan); a[ri] = x; return a
hh14 = pd.Series(rh).rolling(14).max().values; ll14 = pd.Series(rl).rolling(14).min().values
K14 = rser(100 * (rc - ll14) / np.maximum(hh14 - ll14, 1e-9))
m12 = pd.Series(rc).ewm(span=12, adjust=False).mean(); m26 = pd.Series(rc).ewm(span=26, adjust=False).mean()
MACD = rser((m12 - m26).values)
d1 = np.diff(rc, prepend=rc[0]); g = pd.Series(np.maximum(d1, 0)).ewm(alpha=1/14).mean()
lss = pd.Series(np.maximum(-d1, 0)).ewm(alpha=1/14).mean(); RSI14 = rser((100 - 100 / (1 + g / lss.replace(0, 1e-9))).values)
ro = O[ri]; hac = (ro + rh + rl + rc) / 4; hao = np.empty_like(hac); hao[0] = ro[0]
for q in range(1, len(hac)): hao[q] = (hao[q-1] + hac[q-1]) / 2
HAUP = rser((hac > hao).astype(float))
atr10 = pd.Series(np.maximum(rh - rl, np.maximum(abs(rh - np.r_[rc[0], rc[:-1]]), abs(rl - np.r_[rc[0], rc[:-1]])))).rolling(10).mean().values
mid = (rh + rl) / 2; ub, lb = mid + 3 * atr10, mid - 3 * atr10; st = np.ones(len(rc)); fu, fl_ = ub.copy(), lb.copy()
for q in range(1, len(rc)):
    if np.isnan(atr10[q]): continue
    fu[q] = ub[q] if (ub[q] < fu[q-1] or rc[q-1] > fu[q-1]) else fu[q-1]
    fl_[q] = lb[q] if (lb[q] > fl_[q-1] or rc[q-1] < fl_[q-1]) else fl_[q-1]
    st[q] = 1 if rc[q] > fu[q-1] else -1 if rc[q] < fl_[q-1] else st[q-1]
STDIR = rser(st)
for d in days:
    P = (d['PDH'] + d['PDL'] + d['PDC']) / 3; d['P'] = P
    d['S1'], d['R1'] = 2 * P - d['PDH'], 2 * P - d['PDL']
    bc = (d['PDH'] + d['PDL']) / 2; tc = 2 * P - bc; d['CPRH'], d['CPRL'] = max(bc, tc), min(bc, tc)
log('indicators ready')

# ---------- 14 new entry signals (generators in time order: (k, side) or (k, side, limit_px)) ----------
def J(d, k): return d['s'] + k
def stoch_reclaim(d):
    for k in range(3, 26):
        j = J(d, k); mid_ = (H[j] + L[j]) / 2
        if K14[j-1] < 30 <= K14[j] and C[j] > mid_: yield k, 1
        if K14[j-1] > 70 >= K14[j] and C[j] < mid_: yield k, -1
def macd_zero(d):
    for k in range(3, 26):
        j = J(d, k)
        if MACD[j-1] <= 0 < MACD[j]: yield k, 1
        if MACD[j-1] >= 0 > MACD[j]: yield k, -1
def bb_break(d):
    for k in range(3, 26):
        j = J(d, k); u, lo = S20[j] + 2 * SD20[j], S20[j] - 2 * SD20[j]
        pu, pl = S20[j-1] + 2 * SD20[j-1], S20[j-1] - 2 * SD20[j-1]
        if C[j] > u and C[j-1] <= pu: yield k, 1
        if C[j] < lo and C[j-1] >= pl: yield k, -1
def donchian20(d):
    for k in range(3, 26):
        j = J(d, k)
        if C[j] > H[j-20:j].max(): yield k, 1
        if C[j] < L[j-20:j].min(): yield k, -1
def ha_flip(d):
    for k in range(4, 26):
        j = J(d, k)
        if HAUP[j] == 1 and (HAUP[j-3:j] == 0).all(): yield k, 1
        if HAUP[j] == 0 and (HAUP[j-3:j] == 1).all(): yield k, -1
def supertrend(d):
    for k in range(2, 26):
        j = J(d, k)
        if STDIR[j] == 1 and STDIR[j-1] == -1: yield k, 1
        if STDIR[j] == -1 and STDIR[j-1] == 1: yield k, -1
def pivot_bounce(d):
    for k in range(1, 26):
        j = J(d, k)
        if L[j] <= d['S1'] < C[j] and C[j] > O[j]: yield k, 1
        if H[j] >= d['R1'] > C[j] and C[j] < O[j]: yield k, -1
def cpr_break(d):
    if (d['CPRH'] - d['CPRL']) / d['P'] > 0.0025: return          # narrow-CPR days only
    for k in range(1, 26):
        j = J(d, k)
        if C[j] > d['CPRH'] >= C[j-1]: yield k, 1
        if C[j] < d['CPRL'] <= C[j-1]: yield k, -1
def inside_break(d):
    for k in range(3, 26):
        j = J(d, k)
        if H[j-1] <= H[j-2] and L[j-1] >= L[j-2]:
            if C[j] > H[j-1]: yield k, 1
            if C[j] < L[j-1]: yield k, -1
def engulf_vwap(d):
    for k in range(2, 26):
        j = J(d, k); near = abs(L[j] - d['vw'][k]) < 0.3 * ATR[j] or abs(H[j] - d['vw'][k]) < 0.3 * ATR[j]
        if near and C[j-1] < O[j-1] and C[j] > O[j] and C[j] > O[j-1] and O[j] <= C[j-1]: yield k, 1
        if near and C[j-1] > O[j-1] and C[j] < O[j] and C[j] < O[j-1] and O[j] >= C[j-1]: yield k, -1
def pin_level(d):
    for k in range(1, 26):
        j = J(d, k); body = abs(C[j] - O[j]); rng_ = H[j] - L[j]
        if rng_ <= 0: continue
        lv = [d['PDL'], d['ONL'], d['vw'][k], d['PDH'], d['ONH']]
        lw, uw = min(O[j], C[j]) - L[j], H[j] - max(O[j], C[j])
        if lw > 2 * body and C[j] > L[j] + 0.66 * rng_ and any(abs(L[j] - x) < 0.3 * ATR[j] for x in lv): yield k, 1
        if uw > 2 * body and C[j] < H[j] - 0.66 * rng_ and any(abs(H[j] - x) < 0.3 * ATR[j] for x in lv): yield k, -1
def three_bar_rev(d):
    for k in range(3, 26):
        j = J(d, k)
        if C[j-2] < O[j-2] and C[j-1] < O[j-1] and C[j] > O[j] and C[j] > H[j-1]: yield k, 1
        if C[j-2] > O[j-2] and C[j-1] > O[j-1] and C[j] < O[j] and C[j] < L[j-1]: yield k, -1
def rsi14_trend(d):
    for k in range(3, 26):
        j = J(d, k); sl_ = E20[j] - E20[j-3]
        if RSI14[j-1] < 50 <= RSI14[j] and sl_ > 0: yield k, 1
        if RSI14[j-1] > 50 >= RSI14[j] and sl_ < 0: yield k, -1
def keltner_break(d):
    for k in range(3, 26):
        j = J(d, k)
        if C[j] > E20[j] + 1.5 * ATR[j] and C[j-1] <= E20[j-1] + 1.5 * ATR[j-1]: yield k, 1
        if C[j] < E20[j] - 1.5 * ATR[j] and C[j-1] >= E20[j-1] - 1.5 * ATR[j-1]: yield k, -1

NEW5 = {'stoch_reclaim': stoch_reclaim, 'macd_zero': macd_zero, 'bb_break': bb_break, 'donchian20': donchian20,
        'ha_flip': ha_flip, 'supertrend': supertrend, 'pivot_bounce': pivot_bounce, 'cpr_break': cpr_break,
        'inside_break': inside_break, 'engulf_vwap': engulf_vwap, 'pin_level': pin_level,
        'three_bar_rev': three_bar_rev, 'rsi14_trend': rsi14_trend, 'keltner_break': keltner_break}
MGMT = {'fix1.0x1.5R': dict(sl=1.0, rr=1.5), 'fix0.75x2R': dict(sl=0.75, rr=2.0), 'fix1.5x1R': dict(sl=1.5, rr=1.0),
        'be1R_2R': dict(sl=1.0, rr=2.0, be=True), 'time60_2R': dict(sl=1.0, rr=2.0, tbars=12),
        'trail1.0': dict(sl=1.0, rr=None, trail=1.0)}

# ---------- trade management simulation ----------
def sim_m(d, k, side, entry, sd, mg, limit=False):
    s = d['s']; j0 = s + k; stop = entry - side * sd
    tgt = entry + side * mg['rr'] * sd if mg.get('rr') else None
    if limit and ((side > 0 and L[j0] <= stop) or (side < 0 and H[j0] >= stop)): return -sd, k
    ext = entry
    for j in range(j0 + 1, s + 78):
        if side > 0:
            if O[j] <= stop: return O[j] - entry, j - s
            if L[j] <= stop: return stop - entry, j - s
            if tgt is not None and H[j] >= tgt: return tgt - entry, j - s
            ext = max(ext, H[j])
        else:
            if O[j] >= stop: return entry - O[j], j - s
            if H[j] >= stop: return entry - stop, j - s
            if tgt is not None and L[j] <= tgt: return entry - tgt, j - s
            ext = min(ext, L[j])
        if mg.get('be') and (ext - entry) * side >= sd: stop = max(stop, entry) if side > 0 else min(stop, entry)
        if mg.get('trail'):
            ts = ext - side * mg['trail'] * ATR[j]; stop = max(stop, ts) if side > 0 else min(stop, ts)
        if mg.get('tbars') and j - j0 >= mg['tbars']: return (C[j] - entry) * side, j - s
    return (C[s + 77] - entry) * side, 77

def trades_m(sig, allowed, filt, mg, win, rng=None):
    out = {}
    for d in win:
        r = None
        try:
            for x in sig(d):
                if not x or x[1] not in allowed: continue
                if filt == 'vwap' and (C[d['s'] + x[0]] - d['vw'][x[0]]) * x[1] <= 0: continue
                r = x; break
        except (IndexError, ValueError, TypeError): r = None
        if not r: continue
        if rng is not None: r = (int(rng.integers(1, 24)), int(rng.choice(list(allowed))))
        j = d['s'] + r[0]; entry = r[2] if len(r) > 2 else C[j]; sd = max(4.0, mg['sl'] * ATR[j])
        if not np.isfinite(sd): continue
        g, _ = sim_m(d, r[0], r[1], entry, sd, mg, limit=len(r) > 2)
        out[d['date']] = [(g - COST, sd)]
    return out

def run_eval(win, day_fn):
    ds = [d['date'] for d in win]; res = []
    for s0 in range(0, len(ds) - 10):
        bal, fl, mx, best, out, nd, allwin = 50000., 48000., 50000., 0., 'open', 0, True
        for x in ds[s0:]:
            nd += 1; p = day_fn(x, bal - 50000)
            if p < 0: allwin = False
            bal += p
            if bal <= fl: out = 'bust'; break
            best = max(best, p); prof = bal - 50000
            if prof >= 3000 and best <= 0.5 * prof: out = 'pass'; break
            mx = max(mx, bal); fl = 50100. if mx >= 52100 else max(fl, mx - 2000)
        res.append((out, nd, out == 'pass' and allwin))
    n = max(1, len(res)); pas = [r for r in res if r[0] == 'pass']
    return dict(pass_=100 * len(pas) / n, bust=100 * sum(r[0] == 'bust' for r in res) / n,
                days=float(np.median([r[1] for r in pas])) if pas else np.nan,
                fastest=min([r[1] for r in pas]) if pas else np.nan,
                fast5=sum(r[1] <= 5 for r in pas), flawless5=sum(r[1] <= 5 and r[2] for r in pas))

def std_dayfn(trd, mode):
    def f(x, prof):
        p = 0.
        for pts, sd in trd.get(x, []):
            n = min(40, int(risk_of(mode, prof) // (sd * 2)))
            if n >= 1: p = max(-1200., p + pts * 2 * n)
        return p
    return f
R_ = lambda trd: np.mean([pts / sd for v in trd.values() for pts, sd in v]) if trd else np.nan
W_ = lambda trd: 100 * np.mean([pts > 0 for v in trd.values() for pts, sd in v]) if trd else np.nan

pick = lambda a, b: [d for d in days if pd.Timestamp(a).date() <= d['date'] <= pd.Timestamp(b).date()]
TUNE, VALID = pick('2026-01-01', '2026-04-30'), pick('2026-05-01', '2026-08-07')
MODES = [200, 300, 400, 'ramp']
DIRS = {'both': (1, -1), 'long': (1,), 'short': (-1,)}

def risk_of(mode, prof):
    if mode != 'ramp': return mode
    return 200 if prof < 1000 else 300 if prof < 2000 else 400

# ---------- StochReclaim30 (the live NinjaTrader bot, per CONTINUE.md) + tweaks ----------
def stoch_seq(d, sl, tp):
    """all sequential long trades: %K14 up through 30 + close in upper half, entries 09:45-11:35"""
    s, out, k = d['s'], [], 3
    while k <= 25:
        j = s + k
        if K14[j-1] < 30 <= K14[j] and C[j] > (H[j] + L[j]) / 2 and np.isfinite(ATR[j]):
            sd = max(1.0, sl * ATR[j])
            g, xk = sim_m(d, k, 1, C[j], sd, dict(sl=sl, rr=tp / sl))
            out.append((g - COST, sd)); k = xk + 1
        else: k += 1
    return out
def stoch_dayfn(seqs, budget, maxct, maxloss, maxprof, maxtr, green):
    def f(x, prof):
        p, nt = 0., 0
        for pts, sd in seqs.get(x, []):
            if nt >= maxtr or p <= -maxloss or p >= maxprof or (green and p > 0): break
            n = min(maxct, int((budget + p) // (sd * 2)))
            if n < 1: break
            p = max(-1200., p + pts * 2 * n); nt += 1
        return p
    return f
SR_VARIANTS = {
    'StochReclaim30 ORIGINAL (SL0.75/TP0.5, $300 budget, 10ct, -300/+440, 6tr, stop-green)': (0.75, 0.5, 300, 10, 300, 440, 6, True),
    'SR30 same, 20ct cap': (0.75, 0.5, 300, 20, 300, 440, 6, True),
    'SR30 TP1.0 (R:R 1.33)': (0.75, 1.0, 300, 10, 300, 440, 6, True),
    'SR30 SL1.0/TP1.5': (1.0, 1.5, 300, 10, 300, 440, 6, True),
    'SR30 SL0.75/TP1.5, no stop-green': (0.75, 1.5, 300, 10, 300, 900, 6, False),
    'SR30 original, $600 budget, -600/+900': (0.75, 0.5, 600, 20, 600, 900, 6, True),
}
sr_rows = []
for nm, (sl, tp, bud, mc, ml, mp, mt, gr) in SR_VARIANTS.items():
    r = dict(strategy=nm)
    for wn, win in (('tune', TUNE), ('valid', VALID)):
        seqs = {d['date']: stoch_seq(d, sl, tp) for d in win}
        allt = [pts for v in seqs.values() for pts, _ in v]
        e = run_eval(win, stoch_dayfn(seqs, bud, mc, ml, mp, mt, gr))
        r.update({f'{wn}_trades': len(allt), f'{wn}_win': 100 * np.mean([x > 0 for x in allt]) if allt else np.nan,
                  f'{wn}_pass': e['pass_'], f'{wn}_bust': e['bust'], f'{wn}_days': e['days'],
                  f'{wn}_fastest': e['fastest'], f'{wn}_flawless5': e['flawless5']})
    sr_rows.append(r); log(nm, {k: (round(v, 1) if isinstance(v, float) else v) for k, v in r.items() if k != 'strategy'})
pd.DataFrame(sr_rows).to_csv(BASE / 'strat500_stochreclaim.csv', index=False)

# ---------- round-3 candidates, same harness, sizing NOT re-tuned ----------
CANDS = [('brooks_h2|both|sl2.0|rr1.5', NEW['brooks_h2'], (1, -1), dict(sl=2.0, rr=1.5), 400),
         ('orb5_break|short|sl0.75|rr2', SIGNALS['orb5_break'], (-1,), dict(sl=0.75, rr=2.0), 'ramp'),
         ('fvg_retest|long|sl1.25|rr2', SIGNALS['fvg_retest'], (1,), dict(sl=1.25, rr=2.0), 300)]
cand_rows = []
for nm, sig, al, mg, mode in CANDS:
    r = dict(strategy=nm, size=mode)
    for wn, win in (('tune', TUNE), ('valid', VALID)):
        trd = trades_m(sig, al, 'none', mg, win); e = run_eval(win, std_dayfn(trd, mode))
        r.update({f'{wn}_n': len(trd), f'{wn}_R': R_(trd), f'{wn}_pass': e['pass_'], f'{wn}_bust': e['bust']})
    cand_rows.append(r); log('candidate', nm, {k: round(v, 2) if isinstance(v, float) else v for k, v in r.items()})

# ---------- the 504 new strategies ----------
rows = []
for sn, sig in NEW5.items():
    for dn, al in DIRS.items():
        for filt in ('none', 'vwap'):
            for mn, mg in MGMT.items():
                tt, tv = trades_m(sig, al, filt, mg, TUNE), trades_m(sig, al, filt, mg, VALID)
                name = f'{sn}|{dn}|{filt}|{mn}'
                if len(tt) < 8:
                    rows.append(dict(strategy=name, signal=sn, dir=dn, filt=filt, mgmt=mn, tune_n=len(tt), skipped=True)); continue
                sc = lambda e: (e['pass_'] - e['bust'], e['pass_'])
                best = max(MODES, key=lambda md: sc(run_eval(TUNE, std_dayfn(tt, md))))
                et, ev = run_eval(TUNE, std_dayfn(tt, best)), run_eval(VALID, std_dayfn(tv, best))
                lk = [run_eval(TUNE, std_dayfn(trades_m(sig, al, filt, mg, TUNE, np.random.default_rng(q)), best)) for q in range(3)] + \
                     [run_eval(VALID, std_dayfn(trades_m(sig, al, filt, mg, VALID, np.random.default_rng(q + 9)), best)) for q in range(3)]
                rows.append(dict(strategy=name, signal=sn, dir=dn, filt=filt, mgmt=mn, size=str(best), skipped=False,
                    tune_n=len(tt), tune_win=W_(tt), tune_R=R_(tt), tune_pass=et['pass_'], tune_bust=et['bust'],
                    tune_days=et['days'], tune_fastest=et['fastest'], tune_flawless5=et['flawless5'],
                    valid_n=len(tv), valid_win=W_(tv), valid_R=R_(tv), valid_pass=ev['pass_'], valid_bust=ev['bust'],
                    valid_days=ev['days'], valid_fastest=ev['fastest'], valid_flawless5=ev['flawless5'],
                    rand_flawless5=np.mean([x['flawless5'] > 0 for x in lk]),
                    rand_pass=np.mean([x['pass_'] for x in lk]), rand_bust=np.mean([x['bust'] for x in lk])))
    log('done', sn)

X = pd.DataFrame(rows); X.to_csv(BASE / 'strat500_2026.csv', index=False)
T = X[~X.skipped].copy(); T['tune_score'] = T.tune_pass - T.tune_bust
pd.set_option('display.width', 320); pd.set_option('display.max_columns', 40)
c = ['strategy', 'size', 'tune_n', 'tune_win', 'tune_R', 'tune_pass', 'tune_bust', 'valid_n', 'valid_win',
     'valid_R', 'valid_pass', 'valid_bust', 'valid_days']
print(f'\nBUILT {len(X)} strategies; {len(T)} traded often enough to test (>=8 trades Jan-Apr)')
print('\n=== StochReclaim30 (live bot) and tweaks, 2026 ===')
print(pd.DataFrame(sr_rows).round(1).to_string(index=False))
print('\n=== round-3 candidates re-run (sizing not re-tuned) ===')
print(pd.DataFrame(cand_rows).round(2).to_string(index=False))
print('\n=== TOP 20 BY JAN-APR SCORE -> MAY-AUG (unseen) ===')
print(T.sort_values(['tune_score', 'tune_R'], ascending=False).head(20)[c].round(2).to_string(index=False))
ROB = T[(T.tune_pass >= 20) & (T.valid_pass >= 20) & (T.tune_bust <= 10) & (T.valid_bust <= 10)]
print('\n=== HELD UP IN BOTH HALVES (pass>=20% and bust<=10% in Jan-Apr AND May-Aug) ===')
print(ROB.sort_values('valid_pass', ascending=False)[c].round(2).to_string(index=False) if len(ROB) else 'none')
for col in ('dir', 'filt', 'mgmt'):
    print(f'\nBY {col.upper()}:'); print(T.groupby(col)[['tune_R', 'valid_R', 'tune_pass', 'tune_bust', 'valid_pass', 'valid_bust']].mean().round(3).to_string())
print(f"\ncorr(tune_R, valid_R) = {T[['tune_R','valid_R']].corr().iloc[0,1]:+.2f}   "
      f"corr(tune score, valid pass-bust) = {np.corrcoef(T.tune_score, T.valid_pass - T.valid_bust)[0,1]:+.2f}")
print(f"flawless <=5-day passes: real {((T.tune_flawless5 + T.valid_flawless5) > 0).mean()*100:.1f}% of strategies | "
      f"random twins {T.rand_flawless5.mean()*100:.1f}%")
with open(BASE / 'CANDIDATES_2026.md', 'a') as fh:
    fh.write('\n## From strat500.py (round 4) - pass>=20% and bust<=10% in BOTH 2026 halves\n')
    if len(ROB):
        for _, x in ROB.sort_values('valid_pass', ascending=False).iterrows():
            fh.write(f"- {x.strategy} (risk {x['size']}): Jan-Apr {x.tune_pass:.0f}%/{x.tune_bust:.0f}%, "
                     f"May-Aug {x.valid_pass:.0f}%/{x.valid_bust:.0f}%, R/trade {x.tune_R:+.2f}/{x.valid_R:+.2f}\n")
    else: fh.write('- none met the bar\n')
log('finished')

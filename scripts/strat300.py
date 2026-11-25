"""strat300.py - 14 new named-trader signals x {long, short, both} x 5 brackets (210 new strategies)
+ the 20 strat100 signals as long-only and short-only (200 more). 2026 only, same protocol as strat100:
choose sizing on TUNE (Jan-Apr), report VALID (May-Aug, unseen), 2021-25 R as a sanity column,
random twins (same days, random bar, random allowed side) as the luck baseline.
Account: LucidDaily 50K eval, EOD trail $2,000, DLL $1,200, target $3,000, 50% consistency.
Sizing options: fixed $200/$300/$400/$600 risk per trade, or RAMP ($200 -> $300 after +$1,000 -> $400 after +$2,000).
Analysis only - no order execution.
"""
import re, numpy as np, pandas as pd
src = open(r'C:\Users\YOU\daytrading-automation\strat100.py').read()
data_part, rest = src.split('# ---------------- 20 entry signals', 1)
sig_part = rest.split('# ---------------- simulation', 1)[0]
sig_part = sig_part.replace('return None', 'return')
sig_part = re.sub(r'return (?=\(|k\b|k,|11)', 'yield ', sig_part)       # signal functions -> generators
exec(data_part); exec('#' + sig_part)

# ---------- extra per-day fields ----------
E20 = np.full(len(C), np.nan); E20[ri] = pd.Series(rc).ewm(span=20, adjust=False).mean().values
S20 = np.full(len(C), np.nan); S20[ri] = pd.Series(rc).rolling(20).mean().values
SD20 = np.full(len(C), np.nan); SD20[ri] = pd.Series(rc).rolling(20).std().values
for i, d in enumerate(days):
    s = d['s']; d['o0'] = O[s]; d['rng'] = H[s:s+78].max() - L[s:s+78].min()
    d['str1'] = min(H[s:s+78].max() - O[s], O[s] - L[s:s+78].min())
    d['stretch'] = np.mean([days[i-q]['str1'] for q in range(1, 11)]) if i >= 10 else np.nan
    d['adr10'] = np.mean([days[i-q]['rng'] for q in range(1, 11)]) if i >= 10 else np.nan
    d['nr4'] = i >= 4 and days[i-1]['rng'] <= min(days[i-q]['rng'] for q in range(1, 5))
    d['pclose_pos'] = (d['PDC'] - d['PDL']) / max(d['PDH'] - d['PDL'], 1e-9)
    j0 = s - 1
    while j0 > 0 and m[j0] != 0 and s - j0 < 200: j0 -= 1
    d['mid_open'] = O[j0] if m[j0] == 0 else np.nan
    tp = (H[s:s+78] + L[s:s+78] + C[s:s+78]) / 3; vv = np.maximum(V[s:s+78], 1)
    d['vsd'] = np.sqrt(np.maximum(np.cumsum(vv * tp**2) / np.cumsum(vv) - d['vw']**2, 0))

# ---------- 14 named-trader signals (generators, time order) ----------
def lw_volbreak(d):                       # Larry Williams volatility breakout: open +/- 0.5 x prior range
    rgp = d['PDH'] - d['PDL']
    for k in range(1, 30):
        c = cl(d, k)
        if c > d['o0'] + 0.5 * rgp: yield k, 1
        if c < d['o0'] - 0.5 * rgp: yield k, -1
def crabel_stretch(d):                    # Toby Crabel stretch: open +/- 10-day avg stretch
    if not np.isfinite(d['stretch']): return
    for k in range(1, 30):
        c = cl(d, k)
        if c > d['o0'] + d['stretch']: yield k, 1
        if c < d['o0'] - d['stretch']: yield k, -1
def lw_oops(d):                           # Larry Williams Oops: gap beyond prior H/L, trade back through
    for k in W:
        c = cl(d, k)
        if d['o0'] < d['PDL'] and c > d['PDL']: yield k, 1
        if d['o0'] > d['PDH'] and c < d['PDH']: yield k, -1
def raschke_8020(d):                      # Linda Raschke 80-20: prior close in outer 20%, open beyond, reverse
    for k in W:
        c = cl(d, k)
        if d['pclose_pos'] <= 0.2 and d['o0'] < d['PDL'] and c > d['PDL']: yield k, 1
        if d['pclose_pos'] >= 0.8 and d['o0'] > d['PDH'] and c < d['PDH']: yield k, -1
def turtle_soup(d):                       # Raschke/Connors Turtle Soup on 5-min: false 20-bar breakout
    s = d['s']
    for k in W:
        j = s + k
        lo_prev = L[j-21:j-1].min(); lo_age = j - 1 - (j - 21 + int(np.argmin(L[j-21:j-1])))
        hi_prev = H[j-21:j-1].max(); hi_age = j - 1 - (j - 21 + int(np.argmax(H[j-21:j-1])))
        if L[j] < lo_prev and lo_age >= 4 and C[j] > lo_prev: yield k, 1
        if H[j] > hi_prev and hi_age >= 4 and C[j] < hi_prev: yield k, -1
def holy_grail(d):                        # Raschke Holy Grail: strong trend, pullback to 20 EMA, resume
    s = d['s']
    for k in range(6, 30):
        j = s + k; slope = E20[j] - E20[j-6]
        if slope > 0.5 * ATR[j] and L[j-1] <= E20[j-1] and C[j] > H[j-1] and C[j] > E20[j]: yield k, 1
        if slope < -0.5 * ATR[j] and H[j-1] >= E20[j-1] and C[j] < L[j-1] and C[j] < E20[j]: yield k, -1
def fisher_acd(d):                        # Mark Fisher ACD: A-up / A-down = OR15 +/- 15% of 10-day range
    if not np.isfinite(d['adr10']): return
    s = d['s']; hi, lo = H[s:s+3].max(), L[s:s+3].min(); A = 0.15 * d['adr10']
    for k in range(3, 30):
        c = cl(d, k)
        if c > hi + A: yield k, 1
        if c < lo - A: yield k, -1
def crabel_nr4(d):                        # Crabel: ORB15 only after an NR4 day
    if not d['nr4']: return
    s = d['s']; hi, lo = H[s:s+3].max(), L[s:s+3].min()
    for k in range(3, 24):
        c = cl(d, k)
        if c > hi: yield k, 1
        if c < lo: yield k, -1
def brooks_h2(d):                         # Al Brooks H2/L2: second pullback-leg entry in trend
    s = d['s']; up_legs = dn_legs = 0; in_pb_up = in_pb_dn = False
    for k in range(2, 30):
        j = s + k
        if H[j-1] < H[j-2]: in_pb_up = True
        if in_pb_up and H[j] > H[j-1]:
            up_legs += 1; in_pb_up = False
            if up_legs >= 2 and C[j] > E20[j] and E20[j] > E20[j-3]: yield k, 1
        if L[j-1] > L[j-2]: in_pb_dn = True
        if in_pb_dn and L[j] < L[j-1]:
            dn_legs += 1; in_pb_dn = False
            if dn_legs >= 2 and C[j] < E20[j] and E20[j] < E20[j-3]: yield k, -1
        if H[j] >= H[s:j].max(): dn_legs = 0
        if L[j] <= L[s:j].min(): up_legs = 0
def carter_squeeze(d):                    # John Carter TTM squeeze fire (BB inside KC >= 6 bars, then out)
    s = d['s']
    for k in range(3, 30):
        j = s + k
        sq = [(2 * SD20[q] < 1.5 * ATR[q]) for q in range(j - 6, j)]
        if all(sq) and 2 * SD20[j] >= 1.5 * ATR[j]:
            yield k, (1 if C[j] > S20[j] else -1)
def ict_judas(d):                         # ICT Judas swing: 9:30-10:00 run of ON H/L, close back past midnight open
    if not np.isfinite(d['mid_open']): return
    s = d['s']
    for k in range(1, 12):
        j = s + k
        if H[s:j+1].max() > d['ONH'] and C[j] < d['mid_open']: yield k, -1
        if L[s:j+1].min() < d['ONL'] and C[j] > d['mid_open']: yield k, 1
def vwap_2sd_fade(d):                     # VWAP 2-sigma band re-entry fade
    for k in range(6, 30):
        j = d['s'] + k; vw, sd = d['vw'], d['vsd']
        if C[j-1] > vw[k-1] + 2 * sd[k-1] and C[j] < vw[k] + 2 * sd[k]: yield k, -1
        if C[j-1] < vw[k-1] - 2 * sd[k-1] and C[j] > vw[k] - 2 * sd[k]: yield k, 1
def cameron_flag(d):                      # Ross Cameron micro pullback / bull-bear flag
    s = d['s']
    for k in range(3, 30):
        j = s + k
        for fl in (1, 2, 3):
            p = j - fl - 1; big = H[p] - L[p]
            if big < 1.5 * ATR[p]: continue
            flag = slice(p + 1, j)
            if C[p] > O[p] and (C[p] - L[p]) > 0.75 * big and (H[flag] - L[flag]).max() < 0.6 * big \
                    and L[flag].min() > (H[p] + L[p]) / 2 and C[j] > H[flag].max(): yield k, 1
            if C[p] < O[p] and (H[p] - C[p]) > 0.75 * big and (H[flag] - L[flag]).max() < 0.6 * big \
                    and H[flag].max() < (H[p] + L[p]) / 2 and C[j] < L[flag].min(): yield k, -1
def dalton_drive(d):                      # Jim Dalton open drive: strong first bar, second bar continues
    s = d['s']; r0 = H[s] - L[s]
    if r0 < 1.2 * ATR[s]: return
    if C[s] - L[s] > 0.8 * r0 and C[s+1] > H[s]: yield 1, 1
    if H[s] - C[s] > 0.8 * r0 and C[s+1] < L[s]: yield 1, -1

NEW = {'lw_volbreak': lw_volbreak, 'crabel_stretch': crabel_stretch, 'lw_oops': lw_oops,
       'raschke_8020': raschke_8020, 'turtle_soup': turtle_soup, 'holy_grail': holy_grail,
       'fisher_acd': fisher_acd, 'crabel_nr4': crabel_nr4, 'brooks_h2': brooks_h2,
       'carter_squeeze': carter_squeeze, 'ict_judas': ict_judas, 'vwap_2sd_fade': vwap_2sd_fade,
       'cameron_flag': cameron_flag, 'dalton_drive': dalton_drive}

# ---------- simulation / account ----------
def sim(d, k, side, entry, sd, td, limit=False):
    s = d['s']; j0 = s + k; stop, tgt = entry - side * sd, entry + side * td
    if limit and ((side > 0 and L[j0] <= stop) or (side < 0 and H[j0] >= stop)): return -sd
    for j in range(j0 + 1, s + 78):
        if side > 0:
            if O[j] <= stop: return O[j] - entry
            if L[j] <= stop: return -sd
            if H[j] >= tgt: return td
        else:
            if O[j] >= stop: return entry - O[j]
            if H[j] >= stop: return -sd
            if L[j] <= tgt: return td
    return (C[s + 77] - entry) * side

def first_allowed(gen, allowed):
    try:
        for r in gen:
            if r and r[1] in allowed: return r
    except (IndexError, ValueError, TypeError): return None
    return None

def trades_for(sig, allowed, sl, rr, win, rng=None):
    out = []
    for d in win:
        r = first_allowed(sig(d), allowed)
        if not r: continue
        if rng is not None: r = (int(rng.integers(1, 24)), int(rng.choice(list(allowed))))
        k, side = r[0], r[1]; j = d['s'] + k
        entry = r[2] if len(r) > 2 else C[j]
        sd = max(4.0, sl * ATR[j])
        if not np.isfinite(sd): continue
        g = sim(d, k, side, entry, sd, rr * sd, limit=len(r) > 2)
        out.append(dict(date=d['date'], sd=sd, pts=g - COST, R=(g - COST) / sd))
    return out

def risk_of(mode, prof):
    if mode != 'ramp': return mode
    return 200 if prof < 1000 else 300 if prof < 2000 else 400

def evalsim(tr, win, mode):
    by = {t['date']: t for t in tr}; ds = [d['date'] for d in win]; res = []
    for s0 in range(0, len(ds) - 10):
        bal, fl, mx, best, out, nd, wins, ntr = 50000., 48000., 50000., 0., 'open', 0, 0, 0
        for x in ds[s0:]:
            nd += 1; p = 0.
            if x in by:
                t = by[x]; n = min(40, int(risk_of(mode, bal - 50000) // (t['sd'] * 2)))
                if n >= 1: p = max(-1200., t['pts'] * 2 * n); ntr += 1; wins += p > 0
            bal += p
            if bal <= fl: out = 'bust'; break
            best = max(best, p); prof = bal - 50000
            if prof >= 3000 and best <= 0.5 * prof: out = 'pass'; break
            mx = max(mx, bal); fl = 50100. if mx >= 52100 else max(fl, mx - 2000)
        res.append((out, nd, out == 'pass' and wins == ntr))
    n = max(1, len(res)); pas = [r for r in res if r[0] == 'pass']
    return dict(pass_=100 * len(pas) / n, bust=100 * sum(r[0] == 'bust' for r in res) / n,
                days=float(np.median([r[1] for r in pas])) if pas else np.nan,
                fastest=min([r[1] for r in pas]) if pas else np.nan,
                fast5=sum(r[1] <= 5 for r in pas), allwin5=sum(r[1] <= 5 and r[2] for r in pas))

pick = lambda a, b: [d for d in days if pd.Timestamp(a).date() <= d['date'] <= pd.Timestamp(b).date()]
TUNE, VALID, OLD = pick('2026-01-01', '2026-04-30'), pick('2026-05-01', '2026-08-07'), pick('2021-09-01', '2025-12-31')
MODES = [200, 300, 400, 600, 'ramp']
DIRS = {'both': (1, -1), 'long': (1,), 'short': (-1,)}
JOBS = [(n, f, dn) for n, f in NEW.items() for dn in DIRS] + \
       [(n, f, dn) for n, f in SIGNALS.items() for dn in ('long', 'short')]

rows = []
for sn, sig, dn in JOBS:
    al = DIRS[dn]
    for sl, rr in BRACKETS:
        tt, tv, to = (trades_for(sig, al, sl, rr, w) for w in (TUNE, VALID, OLD))
        if len(tt) < 8: continue
        sc = lambda e: (e['pass_'] - e['bust'], e['pass_'])
        best = max(MODES, key=lambda md: sc(evalsim(tt, TUNE, md)))
        et, ev = evalsim(tt, TUNE, best), evalsim(tv, VALID, best)
        R = lambda t: np.mean([x['R'] for x in t]) if t else np.nan
        Wr = lambda t: 100 * np.mean([x['R'] > 0 for x in t]) if t else np.nan
        lk = [evalsim(trades_for(sig, al, sl, rr, TUNE, np.random.default_rng(q)), TUNE, best) for q in range(4)] + \
             [evalsim(trades_for(sig, al, sl, rr, VALID, np.random.default_rng(q + 50)), VALID, best) for q in range(4)]
        rows.append(dict(strategy=f'{sn}|{dn}|sl{sl}|rr{rr}', signal=sn, dir=dn, new=sn in NEW, size=str(best),
            tune_n=len(tt), tune_win=Wr(tt), tune_R=R(tt), tune_pass=et['pass_'], tune_bust=et['bust'],
            tune_fastest=et['fastest'], tune_fast5=et['fast5'], tune_allwin5=et['allwin5'],
            valid_n=len(tv), valid_win=Wr(tv), valid_R=R(tv), valid_pass=ev['pass_'], valid_bust=ev['bust'],
            valid_days=ev['days'], valid_fastest=ev['fastest'], valid_fast5=ev['fast5'], valid_allwin5=ev['allwin5'],
            old_R=R(to), old_n=len(to),
            rand_fast5=np.mean([x['fast5'] > 0 for x in lk]), rand_allwin5=np.mean([x['allwin5'] > 0 for x in lk])))
    log('done', sn, dn)

X = pd.DataFrame(rows); X['tune_score'] = X.tune_pass - X.tune_bust
X.to_csv(BASE / 'strat300_2026.csv', index=False)
pd.set_option('display.width', 320); pd.set_option('display.max_columns', 40)
c = ['strategy', 'size', 'tune_n', 'tune_win', 'tune_R', 'tune_pass', 'tune_bust', 'valid_n', 'valid_win',
     'valid_R', 'valid_pass', 'valid_bust', 'valid_days', 'old_R']
print(f'\nSTRATEGIES TESTED: {len(X)}  (new named-trader: {X.new.sum()}, old signals long/short-only: {(~X.new).sum()})')
print('\nTOP 20 BY TUNE (Jan-Apr) score -> how they did in VALID (May-Aug, unseen):')
print(X.sort_values(['tune_score', 'tune_R'], ascending=False).head(20)[c].round(2).to_string(index=False))
S = X[(X.tune_R > 0) & (X.valid_R > 0) & (X.old_R > 0) & (X.tune_bust < 25) & (X.valid_bust < 25)]
print('\nSURVIVORS (R>0 in Jan-Apr, May-Aug AND 2021-25; bust <25% in both 2026 halves):')
print(S.sort_values('valid_pass', ascending=False)[c].round(2).to_string(index=False) if len(S) else 'none')
print('\nBY DIRECTION (mean over strategies):')
print(X.groupby('dir')[['tune_R', 'valid_R', 'old_R', 'tune_pass', 'tune_bust', 'valid_pass', 'valid_bust']].mean().round(3))
print('\nBY SIGNAL (mean R, all brackets & directions):')
print(X.groupby('signal')[['tune_R', 'valid_R', 'old_R']].mean().sort_values('valid_R', ascending=False).round(3).to_string())
print('\nSIZING chosen on Jan-Apr:', X['size'].value_counts().to_dict())
print(f"\ncorr(tune_R, valid_R) = {X[['tune_R','valid_R']].corr().iloc[0,1]:+.2f}   "
      f"corr(tune_score, valid pass-bust) = {np.corrcoef(X.tune_score, X.valid_pass - X.valid_bust)[0,1]:+.2f}")
print(f"<=5-day passes: real {((X.tune_fast5 + X.valid_fast5) > 0).mean()*100:.0f}% of strategies "
      f"(all-wins {((X.tune_allwin5 + X.valid_allwin5) > 0).mean()*100:.0f}%) | random twins "
      f"{X.rand_fast5.mean()*100:.0f}% (all-wins {X.rand_allwin5.mean()*100:.0f}%)")
log('finished')

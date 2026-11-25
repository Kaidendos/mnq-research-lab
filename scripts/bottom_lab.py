"""bottom_lab.py - methods that try to buy the bottom / sell the top, news-legal, Feb 18 - Jul 15 2026.
Signals (long = buy a low, short = sell a high; mirror rules):
  capitulation : bar range > 2 ATR, prior 6-bar drop > 2 ATR, bar closes in its top 30%
  vwap_band_k  : low pierces VWAP - k*sigma (k = 2, 2.5, 3), bar closes back above the band
  rsi_div      : new 30-bar low with RSI(14) higher than at the prior 30-bar low, close > prior bar high
  double_bottom: low within 0.15 ATR of a low 5-30 bars earlier, then close above the high between them
  sweep_reclaim: wick below PDL / session low-so-far / ON-equivalent (prior 60-bar low), close back above it
  vol_climax   : volume > 2.5x 20-bar avg, lower wick > 50% of range, close in top half
  wr_engulf    : Williams %R(14) < -90 on prior bar, bullish engulfing now
  limit_flush  : resting BUY LIMIT 0.5 ATR below the prior 60-bar low (fills only on a flush)
Exits: '1R','2R' fixed (stop 1 ATR or beyond the signal extreme), 'vwap' = target VWAP (stop 1 ATR).
Bottom accuracy = how far the entry was from the day's eventual low (high for shorts), in ATR.
News rule: no entries T-15..T+2 min, flat 2 min before red-folder events. Costs 1.1 pts/contract.
Partner test: added at 1 or 2 MNQ to the current plan (EMA pullback 3->4 at +$1k, news fade 3). Analysis only.
"""
import numpy as np, pandas as pd, itertools
src = open(r'C:\Users\YOU\daytrading-automation\mix_lab.py').read().split('# ---- candidate pool ----')[0]
exec(src)
mix2 = open(r'C:\Users\YOU\daytrading-automation\mix_lab2.py').read()
exec(mix2.split('TD = [x for x in DAYS')[0].split('exec(src)', 1)[1])          # perday, eval_dyn
V = d.volume.values; RSI = d.rsi.values; VW = d.vwap.values
VSD = d.vwap_dev_std.values if 'vwap_dev_std' in d else pd.Series(Cc - VW).rolling(20).std().values
VAVG = pd.Series(V).rolling(20).mean().values
hh14 = pd.Series(H).rolling(14).max().values; ll14 = pd.Series(L).rolling(14).min().values
WR = -100 * (hh14 - Cc) / np.maximum(hh14 - ll14, 1e-9)
PDL, PDH = d.pdl.values, d.pdh.values
DAYLOW = d.groupby(DAY).low.transform('min').values; DAYHIGH = d.groupby(DAY).high.transform('max').values
N = len(d)
def sigs(name):
    lo = np.zeros(N, bool); sh = np.zeros(N, bool); lim_lo = np.full(N, np.nan); lim_sh = np.full(N, np.nan)
    for i in range(61, N):
        a = ATR[i]; rg = H[i] - L[i]
        if not a > 0 or DAY[i] != DAY[i-1]: continue
        if name == 'capitulation':
            lo[i] = rg > 2*a and Cc[i-6] - Cc[i] > 2*a and Cc[i] > L[i] + 0.7*rg
            sh[i] = rg > 2*a and Cc[i] - Cc[i-6] > 2*a and Cc[i] < H[i] - 0.7*rg
        elif name.startswith('vwap_band'):
            k = float(name.split('_')[-1]); bl, bu = VW[i] - k*VSD[i], VW[i] + k*VSD[i]
            lo[i] = L[i] < bl < Cc[i]; sh[i] = H[i] > bu > Cc[i]
        elif name == 'rsi_div':
            pl = L[i-30:i].min(); j = i - 30 + int(np.argmin(L[i-30:i]))
            lo[i] = L[i] < pl and RSI[i] > RSI[j] and Cc[i] > H[i-1] and i - j >= 5
            ph = H[i-30:i].max(); j2 = i - 30 + int(np.argmax(H[i-30:i]))
            sh[i] = H[i] > ph and RSI[i] < RSI[j2] and Cc[i] < L[i-1] and i - j2 >= 5
        elif name == 'double_bottom':
            for j in range(i - 30, i - 5):
                if abs(L[j] - L[i-1]) < 0.15*a and L[j] <= L[j:i].min() + 0.15*a and Cc[i] > H[j:i].max(): lo[i] = True; break
            for j in range(i - 30, i - 5):
                if abs(H[j] - H[i-1]) < 0.15*a and H[j] >= H[j:i].max() - 0.15*a and Cc[i] < L[j:i].min(): sh[i] = True; break
        elif name == 'sweep_reclaim':
            lv = min(L[i-60:i].min(), PDL[i] if PDL[i] == PDL[i] else 1e9)
            lo[i] = L[i] < lv < Cc[i]
            hv = max(H[i-60:i].max(), PDH[i] if PDH[i] == PDH[i] else -1e9)
            sh[i] = H[i] > hv > Cc[i]
        elif name == 'vol_climax':
            big = V[i] > 2.5 * VAVG[i] and rg > 0
            lo[i] = big and (min(O[i], Cc[i]) - L[i]) > 0.5*rg and Cc[i] > L[i] + 0.5*rg
            sh[i] = big and (H[i] - max(O[i], Cc[i])) > 0.5*rg and Cc[i] < L[i] + 0.5*rg
        elif name == 'wr_engulf':
            lo[i] = WR[i-1] < -90 and Cc[i-1] < O[i-1] and Cc[i] > O[i] and Cc[i] > O[i-1] and O[i] <= Cc[i-1]
            sh[i] = WR[i-1] > -10 and Cc[i-1] > O[i-1] and Cc[i] < O[i] and Cc[i] < O[i-1] and O[i] >= Cc[i-1]
        elif name == 'limit_flush':
            lim_lo[i] = L[i-60:i].min() - 0.5*a; lim_sh[i] = H[i-60:i].max() + 0.5*a
    return lo, sh, lim_lo, lim_sh

def run(lo, sh, lim_lo, lim_sh, side, exit_, stop_mode):
    out, pos = [], None
    for i in range(1, N):
        if pos:
            s = pos['s']
            if s > 0: ex = pos['sl'] if L[i] <= pos['sl'] else pos['tp'] if (pos['tp'] and H[i] >= pos['tp']) else None
            else: ex = pos['sl'] if H[i] >= pos['sl'] else pos['tp'] if (pos['tp'] and L[i] <= pos['tp']) else None
            if ex is None and exit_ == 'vwap' and (Cc[i] - VW[i]) * s >= 0: ex = Cc[i]
            if ex is None and (LAST[i] or FORCEX[i]): ex = Cc[i]
            if ex is not None:
                out.append((DAY[i], (ex - pos['e']) * s - COST, pos['sd'], pos['acc'])); pos = None
        if pos or LAST[i] or not (9.6667 <= EH[i] <= 15.5) or not ATR[i] > 0 or NOENT[i] or FORCEX[i]: continue
        a = ATR[i]; cands = []
        if side in ('both', 'long'):
            if lo[i]: cands.append((1, Cc[i], L[i]))
            if lim_lo[i] == lim_lo[i] and L[i] <= lim_lo[i] < O[i]: cands.append((1, lim_lo[i], L[i]))
        if side in ('both', 'short'):
            if sh[i]: cands.append((-1, Cc[i], H[i]))
            if lim_sh[i] == lim_sh[i] and H[i] >= lim_sh[i] > O[i]: cands.append((-1, lim_sh[i], H[i]))
        if not cands: continue
        s, e, ext = cands[0]
        sd = max(4.0, (e - ext + 0.25) if s > 0 else (ext - e + 0.25)) if stop_mode == 'ext' else a
        if stop_mode == 'ext' and sd > 2 * a: sd = 2 * a
        tp = None if exit_ == 'vwap' else e + s * (1 if exit_ == '1R' else 2) * sd
        acc = (e - DAYLOW[i]) / a if s > 0 else (DAYHIGH[i] - e) / a
        pos = dict(s=s, e=e, sl=e - s * sd, tp=tp, sd=sd, acc=acc)
        if lim_lo[i] == lim_lo[i] and e == lim_lo[i] and Cc[i] <= pos['sl']:          # limit fill bar closes through stop
            out.append((DAY[i], -sd - COST, sd, acc)); pos = None
    return [x for x in out if W0 <= x[0] <= W1]

NAMES = ['capitulation', 'vwap_band_2', 'vwap_band_2.5', 'vwap_band_3', 'rsi_div', 'double_bottom',
         'sweep_reclaim', 'vol_climax', 'wr_engulf', 'limit_flush']
ramp = lambda p, dd: {'ema': 4 if p >= 1000 else 3, 'fade': 3}
rows = []
for nm in NAMES:
    S = sigs(nm)
    for side, ex_, sm in itertools.product(('long', 'short', 'both'), ('1R', '2R', 'vwap'), ('atr', 'ext')):
        trs = run(*S, side, ex_, sm)
        t_ = [x for x in trs if x[0] < SPLIT]; v_ = [x for x in trs if x[0] >= SPLIT]
        if len(t_) < 8: continue
        r = dict(method=nm, side=side, exit=ex_, stop=sm, tune_n=len(t_), valid_n=len(v_),
                 tune_pts=np.mean([x[1] for x in t_]), valid_pts=np.mean([x[1] for x in v_]) if v_ else np.nan,
                 win=100 * np.mean([x[1] > 0 for x in trs]),
                 acc_atr=np.median([x[3] for x in trs]), within_half_atr=100 * np.mean([x[3] <= 0.5 for x in trs]))
        trs3 = [(a_, b_, c_) for a_, b_, c_, _ in trs]
        for n in (1, 2):
            for per, days in (('t', TD), ('v', VD)):
                comps = {'ema': perday(base_news, days), 'fade': perday(NEWSFADE, days), 'x': perday(trs3, days)}
                p, b, _ = eval_dyn(comps, days, lambda pr, dd, n=n: dict(ramp(pr, dd), x=n))
                r[f'{per}_pass_{n}'], r[f'{per}_bust_{n}'] = p, b
        rows.append(r)
    print('done', nm, flush=True)
X = pd.DataFrame(rows); X.to_csv(BASE + r'\bottom_lab.csv', index=False)
pd.set_option('display.width', 320); pd.set_option('display.max_columns', 30)
bt = {}
for per, days in (('t', TD), ('v', VD)):
    bt[per] = eval_dyn({'ema': perday(base_news, days), 'fade': perday(NEWSFADE, days)}, days, ramp)
print(f"\nPLAN ALONE (EMA 3->4 ramp + fade 3): Feb-Apr pass {bt['t'][0]:.0f}% bust {bt['t'][1]:.0f}% | May-Jul pass {bt['v'][0]:.0f}% bust {bt['v'][1]:.0f}%")
print(f"\nmethods x side x exit x stop tested: {len(X)} | positive pts both halves: {((X.tune_pts>0)&(X.valid_pts>0)).sum()} | "
      f"corr(tune,valid) {X[['tune_pts','valid_pts']].corr().iloc[0,1]:+.2f}")
print('\nBOTTOM/TOP ACCURACY by method (median distance from the day\'s real low/high, in ATR; % within 0.5 ATR):')
print(X.groupby('method')[['acc_atr', 'within_half_atr', 'win', 'tune_pts', 'valid_pts']].mean().round(2).sort_values('acc_atr').to_string())
print('\nBY SIDE:'); print(X.groupby('side')[['tune_pts', 'valid_pts']].mean().round(2).to_string())
c = ['method', 'side', 'exit', 'stop', 'tune_n', 'valid_n', 'win', 'acc_atr', 'tune_pts', 'valid_pts', 't_pass_1', 't_bust_1', 'v_pass_1', 'v_bust_1', 'v_pass_2', 'v_bust_2']
X['tscore'] = X.t_pass_1 - 2 * X.t_bust_1
print('\nTOP 12 AS PARTNER @1 MNQ, CHOSEN ON FEB-APR -> MAY-JUL:')
print(X.sort_values(['tscore', 'tune_pts'], ascending=False).head(12)[c].round(1).to_string(index=False))
G = X[(X.tune_pts > 0) & (X.valid_pts > 0) & (X.v_bust_1 <= 0) & (X.v_pass_1 > bt['v'][0]) & (X.t_pass_1 >= bt['t'][0])]
print(f'\nIMPROVE THE PLAN IN BOTH HALVES without busts (@1 MNQ): {len(G)}')
if len(G): print(G[c].round(1).to_string(index=False))

import numpy as np, pandas as pd
raw = pd.read_csv(r'C:\Users\YOU\daytrading-automation\data\databento\mnq_2021-2026_5min.csv')
raw.index = pd.to_datetime(raw.ts_et, utc=True).dt.tz_convert('America/New_York')
r = raw[raw.index >= '2025-12-01']
gap = (r.open - r.close.shift(1)).abs()
big = r[gap > 60][['symbol', 'open', 'close']].copy(); big['gap'] = (r.open - r.close.shift(1))[gap > 60]
print('bar-to-bar jumps > 60 pts since Dec 2025:'); print(big.to_string())
print('\nsymbol column values:', r.symbol.unique()[:10])
for f in ('nq_2021-2026_5min.csv',):
    pass
A = pd.read_csv(r'C:\Users\YOU\daytrading-automation\asia_lab_trades.csv')
dr = A[A.strategy == 'drift|long|in18:05|out08:25|stop6ATR'].sort_values('pts', ascending=False)
print('\nbiggest drift nights:'); print(dr.head(8).to_string(index=False))

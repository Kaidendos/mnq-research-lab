src = open(r'C:\Users\YOU\daytrading-automation\merge_night.py').read().split("print('=== DAY PLAN + NIGHT ===')")[0]
exec(src)
import numpy as np
print('=== DAY PLAN (day) + LONDON BREAKOUT (night, 02:00-05:00 ET entries, flat by 08:25) ===')
report('day plan only', {})
for nm in ('london_break|both|2/2', 'london_break|both|1/1', 'london_break|long|2/2', 'london_break|long|1/1'):
    for n in (1, 2, 3):
        report(f'+ {nm} @{n}', {'lb': (night(nm), n)})
for nm in ('london_break|both|2/2', 'london_break|both|1/1'):
    x = np.array([p for _, p, _ in night(nm) if W0 <= _ <= W1]) if False else np.array([p for d_, p, _ in night(nm) if W0 <= d_ <= W1])
    print(f'{nm}: {len(x)} trades Feb18-Jul15, win {100*(x>0).mean():.0f}%, avg {x.mean():+.1f} pts, worst {x.min():+.0f}, best {x.max():+.0f}')

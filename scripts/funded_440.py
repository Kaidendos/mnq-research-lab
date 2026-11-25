"""Test: the CURRENT live strategy (budget $500, no stop-after-win, max 10)
with the day profit cap set to $440 -- the value where a max day == 40% of the
$1,100 buffer, so payout is possible in ~3 days. Funded LucidPro rules applied."""

import improve_lab as il
from funded_backtest import run_config

d = il.load()
full = d.loc[il.START:]
yr = d.loc["2025-07-17":]

daily_close = d["close"].groupby(d.index.normalize()).last()
ema50 = daily_close.ewm(span=50, adjust=False).mean()
gate = (daily_close > ema50).shift(1).fillna(False).to_dict()

# (label, cap, budget, stop_after_win, gate?)
configs = [
    ("$440 cap, CURRENT config (budget 500, no stop-after-win)", 440, 500, False, None),
    ("$440 cap, CURRENT config + EMA50 gate", 440, 500, False, gate),
    ("$440 cap, clean (budget 660, stop-after-win)", 440, 660, True, None),
    ("$440 cap, clean (budget 660, stop-after-win) + EMA50 gate", 440, 660, True, gate),
]

for win_name, dd in (("FULL 5 YEARS  (2021-07-18 -> 2026-07-16)", full),
                     ("LAST 12 MONTHS  (2025-07-17 -> 2026-07-16)", yr)):
    print("=" * 68); print(win_name); print("=" * 68)
    for name, cap, bud, saw, ga in configs:
        print(name)
        run_config(name, dd, cap, bud, saw, "440", day_allowed=ga)

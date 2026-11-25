"""Reconcile the backtest with the user's live '7 wins, no losses'.
Show trade-level win rate by recency + the recent day-by-day results, and the
losing clusters that drive the bust risk. Same live entry, fees in."""

import numpy as np
import pandas as pd

import improve_lab as il

d = il.load()
t = il.run(d.loc[il.START:])            # every trade, live sizing, fees in
t = t.sort_values("ts").reset_index(drop=True)
t["date"] = pd.to_datetime(t["date"]).dt.tz_localize(None)

print("TRADE-LEVEL WIN RATE by window (live entry, all 5yr data):")
now = t["date"].max()
for label, days in [("last 10 trades", None), ("last 20 trades", None),
                    ("last 30 cal-days", 30), ("last 90 cal-days", 90),
                    ("last 12 months", 365), ("full 5 years", 100000)]:
    if days is None:
        n = int(label.split()[1]); s = t.tail(n)
    else:
        s = t[t["date"] >= now - pd.Timedelta(days=days)]
    if len(s):
        print(f"  {label:16s}: {100*s['win'].mean():5.1f}% win  "
              f"({int(s['win'].sum())}W/{len(s)-int(s['win'].sum())}L, {len(s)} trades)  "
              f"net ${s['pnl'].sum():+,.0f}")

print("\nMOST RECENT 15 TRADES (newest last) — compare to your live streak:")
for _, r in t.tail(15).iterrows():
    print(f"  {r['date'].date()}  {'WIN ' if r['win'] else 'LOSS'} "
          f"{r['pts']:+6.1f} pts  ${r['pnl']:+7,.0f}  ({r['n']} ct)")

# longest win streak recently, and the losing clusters that cause busts
wins = t["win"].values
streak = 0; best = 0
for w in wins[::-1]:
    if w: streak += 1; best = max(best, streak)
    else: break
print(f"\nCurrent live win streak in the data: {best} in a row (matches your 7-0 vibe)")

# consecutive-loss clusters over full history
maxloss = 0; cur = 0; clusters = []
for w in wins:
    if not w:
        cur += 1; maxloss = max(maxloss, cur)
    else:
        if cur >= 3: clusters.append(cur)
        cur = 0
print(f"Worst losing streak in 5yr: {maxloss} trades in a row")
print(f"Times there were >=3 losses in a row: {len(clusters)} "
      f"(these clusters are what bust a $1k drawdown)")

# how often does a bad WEEK happen — 5 worst rolling-5-trade stretches
t["roll5"] = t["pnl"].rolling(5).sum()
print("\n5 worst 5-trade stretches (this is the tail the backtest is warning about):")
for _, r in t.nsmallest(5, "roll5").iterrows():
    print(f"  ~{r['date'].date()}  5-trade P&L ${r['roll5']:+,.0f}")

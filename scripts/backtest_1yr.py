"""Backtest the LIVE Claude 2 rules over 1 year of Databento MNQ 5-min bars.

Faithful replication of _session_strategy() in
C:\\trading_system\\MNQ-Signal-System\\claude2_app.py (the app's own replay):

  entry : stochK(14) crosses up through 30, bar in 9:40-11:30 ET window,
          svol > 0 (bar closes upper half), ATR valid
  bracket: SL = entry - 0.75*ATR, TP = entry + 0.5*ATR (entry = signal close)
  exits : from NEXT bar - SL first if low <= sl, else TP if high >= tp,
          else EOD close on last RTH bar
  sizing: n = min(10, floor((500+dayPnL)/stop$), floor((1500-dayPnL)/tp$))
  locks : max 6 trades/day, n<1 -> skip signal, STOP_AFTER_WIN=False
  NOT modeled (matches the app's replay): news guard, skip dates, slippage.
"""

from pathlib import Path

import numpy as np
import pandas as pd

DATA_CSV = Path(__file__).parent / "data" / "databento" / "mnq_5min_2021-2026.csv"
TZ = "America/New_York"

WARMUP_START = "2025-06-15"   # indicator warm-up only, no trades recorded
TEST_START = "2025-07-17"
TEST_END = "2026-07-16"

STOCH_TH, SL_ATR, TP_ATR = 30, 0.75, 0.5
ENTRY_START, ENTRY_END = 9.6667, 15.5
MORNING_END = 11.5
POINT_VALUE = 2.0
MAX_CONTRACTS = 10
DAY_MAX_LOSS = 500
DAY_MAX_PROFIT = 1500
DAY_MAX_TRADES = 6

COMBINE_TARGET = 3000   # $50K Combine: +$3k on $50k
COMBINE_MLL = 2000      # trailing max-loss limit (EOD basis approximation)


def load_rth_bars() -> pd.DataFrame:
    df = pd.read_csv(DATA_CSV)
    df["ts_et"] = pd.to_datetime(df["ts_et"], utc=True).dt.tz_convert(TZ)
    df = df.set_index("ts_et").sort_index()
    df = df.loc[WARMUP_START:]
    hrs = df.index.hour + df.index.minute / 60.0
    return df[(hrs >= 9.5) & (hrs < 16.0)]


def enrich(d: pd.DataFrame) -> pd.DataFrame:
    """Same math as claude2_app._enrich / indicators.atr (Wilder RMA)."""
    d = d.copy()
    prev_close = d["close"].shift(1)
    tr = pd.concat([
        d["high"] - d["low"],
        (d["high"] - prev_close).abs(),
        (d["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    d["atr"] = tr.ewm(alpha=1.0 / 14, adjust=False).mean()
    ll = d["low"].rolling(14).min()
    hh = d["high"].rolling(14).max()
    d["stochK"] = 100 * (d["close"] - ll) / (hh - ll).replace(0, np.nan)
    pressure = ((d["close"] - d["low"]) / (d["high"] - d["low"]).replace(0, np.nan)).fillna(0.5)
    d["svol"] = d["volume"] * (2 * pressure - 1)
    return d


def size_for(atr_val: float, day_pnl: float) -> int:
    stop_usd = atr_val * SL_ATR * POINT_VALUE
    tp_usd = atr_val * TP_ATR * POINT_VALUE
    n = min(MAX_CONTRACTS, int((DAY_MAX_LOSS + day_pnl) / stop_usd))
    n = min(n, int((DAY_MAX_PROFIT - day_pnl) / tp_usd))
    return max(n, 0)


def replay_day(day: pd.DataFrame) -> list[dict]:
    """One RTH session, identical control flow to _session_strategy."""
    if len(day) < 3:
        return []
    h = day["high"].values
    l = day["low"].values
    c = day["close"].values
    atr = day["atr"].values
    K = day["stochK"].values
    sv = day["svol"].values
    eth = (day.index.hour + day.index.minute / 60.0).values
    times = day.index
    trades: list[dict] = []
    net = 0.0
    pos = None
    for i in range(1, len(day)):
        last = i == len(day) - 1
        if pos is not None:
            ex = kind = None
            if l[i] <= pos["sl"]:
                ex, kind = pos["sl"], "SL"
            elif h[i] >= pos["tp"]:
                ex, kind = pos["tp"], "TP"
            elif eth[i] >= 16.0 or last:
                ex, kind = c[i], "EOD"
            if ex is not None:
                usd = (ex - pos["entry"]) * POINT_VALUE * pos["n"]
                net += usd
                trades.append({"date": times[i].date(), "etime": pos["etime"],
                               "xtime": times[i].strftime("%H:%M"), "kind": kind,
                               "n": pos["n"], "entry": pos["entry"], "exit": ex,
                               "pnl": usd, "win": usd > 0})
                pos = None
        if (pos is None and not last
                and ENTRY_START <= eth[i] <= ENTRY_END
                and eth[i] <= MORNING_END
                and len(trades) < DAY_MAX_TRADES):
            if (K[i - 1] <= STOCH_TH and K[i] > STOCH_TH
                    and atr[i] > 0 and not np.isnan(atr[i]) and sv[i] > 0):
                nsz = size_for(atr[i], net)
                if nsz < 1:
                    continue
                pos = {"entry": c[i], "sl": c[i] - atr[i] * SL_ATR,
                       "tp": c[i] + atr[i] * TP_ATR, "n": nsz,
                       "etime": times[i].strftime("%H:%M")}
    return trades


def combine_pass_stats(daily: pd.Series) -> tuple[float, list[int]]:
    """From each possible start day: traded days to +$3k vs trailing $2k MLL (EOD)."""
    vals = daily.values
    passes: list[int] = []
    attempts = 0
    for s in range(len(vals)):
        cum = 0.0
        peak = 0.0
        outcome = None
        for j in range(s, len(vals)):
            cum += vals[j]
            peak = max(peak, cum)
            if cum >= COMBINE_TARGET:
                outcome = j - s + 1
                break
            if peak - cum >= COMBINE_MLL:
                outcome = -1
                break
        if outcome is None:
            continue  # ran out of data, not a resolved attempt
        attempts += 1
        if outcome > 0:
            passes.append(outcome)
    rate = 100 * len(passes) / attempts if attempts else float("nan")
    return rate, passes


def main() -> None:
    bars = load_rth_bars()
    d = enrich(bars)
    d = d.loc[TEST_START:TEST_END + " 23:59"]

    all_trades: list[dict] = []
    for _, day in d.groupby(d.index.normalize(), sort=True):
        all_trades.extend(replay_day(day))

    t = pd.DataFrame(all_trades)
    if t.empty:
        print("No trades.")
        return
    t["date"] = pd.to_datetime(t["date"])

    daily = t.groupby("date")["pnl"].sum()
    sessions = d.index.normalize().nunique()
    wins = int(t["win"].sum())
    gross_w = t.loc[t["pnl"] > 0, "pnl"].sum()
    gross_l = -t.loc[t["pnl"] <= 0, "pnl"].sum()
    equity = daily.cumsum()
    dd = (equity - equity.cummax()).min()

    print(f"period          : {TEST_START} -> {TEST_END}  ({sessions} sessions)")
    print(f"trades          : {len(t)}  ({len(t)/sessions:.2f}/day, "
          f"{daily.size} active days)")
    print(f"win rate        : {100*wins/len(t):.1f}%  ({wins}W / {len(t)-wins}L)")
    print(f"net P&L         : ${daily.sum():+,.0f}")
    print(f"profit factor   : {gross_w/gross_l:.2f}" if gross_l else "profit factor   : inf")
    print(f"avg trade       : ${t['pnl'].mean():+,.0f}   avg day: ${daily.mean():+,.0f}")
    print(f"best day        : ${daily.max():+,.0f}   worst day: ${daily.min():+,.0f}")
    print(f"max drawdown    : ${dd:+,.0f} (daily-close equity)")
    print(f"exit mix        : {t['kind'].value_counts().to_dict()}")
    print(f"size mix (n)    : {t['n'].value_counts().sort_index().to_dict()}")

    print("\nmonthly P&L:")
    monthly = daily.resample("ME").agg(["sum", "count"])
    monthly.index = monthly.index.strftime("%Y-%m")
    for m, row in monthly.iterrows():
        print(f"  {m}  ${row['sum']:+8,.0f}   ({int(row['count'])} active days)")

    print("\nworst 5 days:")
    for dt, v in daily.nsmallest(5).items():
        print(f"  {dt.date()}  ${v:+,.0f}")

    # Combine sim on active-day P&L (zero-trade days can't move cum or peak)
    rate, passes = combine_pass_stats(daily)
    print(f"\n$50K Combine sim (start any active day, EOD-trailing $2k MLL):")
    print(f"  pass rate     : {rate:.1f}% of resolved attempts")
    if passes:
        print(f"  traded days to pass: median {int(np.median(passes))}, "
              f"p90 {int(np.percentile(passes, 90))}, worst {max(passes)}")

    out = Path(__file__).parent / "data" / "databento" / "backtest_1yr_trades.csv"
    t.to_csv(out, index=False)
    print(f"\ntrade log saved: {out}")


if __name__ == "__main__":
    main()

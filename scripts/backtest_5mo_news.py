"""5-month backtest of the EXACT live Claude 2 config, adding the two things
the bot's own replay never models:

  1. News guard (real scraped ForexFactory high-impact USD events):
     - blackout: no entry while bar CLOSE is within [event-30min, event+10min]
     - pre-open settle: event 07:00-09:30 ET -> no entries before 10:30 ET
  2. Commissions: $1.22 round-trip per MNQ contract (TopstepX published rate).
     Fees flow into the running day P&L, which is what live sizing/locks see
     (broker-truth sync reports profitAndLoss minus fees).

Everything else identical to backtest_1yr.py (which replicates
claude2_app._session_strategy): stoch %K(14) reclaim of 30, SL 0.75*ATR /
TP 0.5*ATR, entries 9:40-11:30 ET, svol>0, cap-fitted sizing, 6 trades max.
Blocked signals are shadow-tracked like the live bot does.
"""

from pathlib import Path

import numpy as np
import pandas as pd

from backtest_1yr import (
    DATA_CSV, TZ, STOCH_TH, SL_ATR, TP_ATR, ENTRY_START, ENTRY_END,
    MORNING_END, POINT_VALUE, DAY_MAX_TRADES, enrich, size_for,
    combine_pass_stats,
)

WARMUP_START = "2026-01-15"
TEST_START = "2026-02-17"
TEST_END = "2026-07-16"

COMMISSION_RT = 1.22            # $ per contract round trip (TopstepX MNQ)
NEWS_WINDOW_MIN = 30            # config.NEWS_WINDOW
NEWS_POST_MIN = 10              # config.NEWS_WINDOW_POST
SETTLE_HR = 10.5                # config.NEWS_PREOPEN_SETTLE_HR
EVENTS_CSV = Path(__file__).parent / "data" / "databento" / "ff_high_usd_events_2026.csv"

BAR_MIN = 5                     # guard is checked at bar close, like live


def load_events() -> pd.DataFrame:
    ev = pd.read_csv(EVENTS_CSV)
    ev["when"] = pd.to_datetime(ev["epoch"], unit="s", utc=True).dt.tz_convert(TZ)
    ev["et_hr"] = ev["when"].dt.hour + ev["when"].dt.minute / 60.0
    ev["date"] = ev["when"].dt.normalize()
    return ev


class NewsGuard:
    def __init__(self, events: pd.DataFrame):
        self.times = events["when"]
        self.settle_days = set(
            events.loc[(events["et_hr"] >= 7.0) & (events["et_hr"] <= 9.5), "date"])

    def blocked(self, bar_close_et: pd.Timestamp) -> str | None:
        mins = (self.times - bar_close_et).dt.total_seconds() / 60.0
        if ((mins >= -NEWS_POST_MIN) & (mins <= NEWS_WINDOW_MIN)).any():
            return "blackout"
        hr = bar_close_et.hour + bar_close_et.minute / 60.0
        if hr < SETTLE_HR and bar_close_et.normalize() in self.settle_days:
            return "settle"
        return None


def replay_day(day: pd.DataFrame, guard: NewsGuard) -> tuple[list[dict], list[dict]]:
    """Same control flow as the live replay + guard + fees. Returns
    (trades, shadow) where shadow = news-blocked signals played out."""
    if len(day) < 3:
        return [], []
    h = day["high"].values
    l = day["low"].values
    c = day["close"].values
    atr = day["atr"].values
    K = day["stochK"].values
    sv = day["svol"].values
    eth = (day.index.hour + day.index.minute / 60.0).values
    times = day.index
    trades: list[dict] = []
    shadow: list[dict] = []
    net = 0.0                     # running day P&L NET of fees (broker truth)
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
                fees = COMMISSION_RT * pos["n"]
                usd = (ex - pos["entry"]) * POINT_VALUE * pos["n"] - fees
                net += usd
                trades.append({"date": times[i].date(), "etime": pos["etime"],
                               "xtime": times[i].strftime("%H:%M"), "kind": kind,
                               "n": pos["n"], "entry": pos["entry"], "exit": ex,
                               "fees": fees, "pnl": usd, "win": usd > 0})
                pos = None
        if (pos is None and not last
                and ENTRY_START <= eth[i] <= ENTRY_END
                and eth[i] <= MORNING_END
                and len(trades) < DAY_MAX_TRADES):
            if (K[i - 1] <= STOCH_TH and K[i] > STOCH_TH
                    and atr[i] > 0 and not np.isnan(atr[i]) and sv[i] > 0):
                why = guard.blocked(times[i] + pd.Timedelta(minutes=BAR_MIN))
                if why is not None:
                    shadow.append({"date": times[i].date(),
                                   "etime": times[i].strftime("%H:%M"),
                                   "why": why, "entry": c[i],
                                   "sl": c[i] - atr[i] * SL_ATR,
                                   "tp": c[i] + atr[i] * TP_ATR})
                    continue
                nsz = size_for(atr[i], net)
                if nsz < 1:
                    continue
                pos = {"entry": c[i], "sl": c[i] - atr[i] * SL_ATR,
                       "tp": c[i] + atr[i] * TP_ATR, "n": nsz,
                       "etime": times[i].strftime("%H:%M")}
    return trades, shadow


def resolve_shadow(day: pd.DataFrame, sig: dict) -> float:
    """Points a blocked signal would have made (bracket replay, 1-contract pts)."""
    after = day[day.index.strftime("%H:%M") > sig["etime"]]
    for _, bar in after.iterrows():
        if bar["low"] <= sig["sl"]:
            return sig["sl"] - sig["entry"]
        if bar["high"] >= sig["tp"]:
            return sig["tp"] - sig["entry"]
    return (after["close"].iloc[-1] - sig["entry"]) if len(after) else 0.0


def main() -> None:
    events = load_events()
    guard = NewsGuard(events)
    print("event sanity anchors (should be 08:30/10:00/14:00 ET types):")
    for _, r in events.drop_duplicates("epoch").head(3).iterrows():
        print(f"  {r['when'].strftime('%a %Y-%m-%d %H:%M ET')}  {r['name']}")
    for ep in (1773856800, 1784032200):
        r = events[events["epoch"] == ep].iloc[0]
        print(f"  {r['when'].strftime('%a %Y-%m-%d %H:%M ET')}  {r['name']}")

    df = pd.read_csv(DATA_CSV)
    df["ts_et"] = pd.to_datetime(df["ts_et"], utc=True).dt.tz_convert(TZ)
    df = df.set_index("ts_et").sort_index().loc[WARMUP_START:]
    hrs = df.index.hour + df.index.minute / 60.0
    bars = df[(hrs >= 9.5) & (hrs < 16.0)]
    d = enrich(bars).loc[TEST_START:TEST_END + " 23:59"]

    all_trades: list[dict] = []
    all_shadow: list[dict] = []
    shadow_pts: list[float] = []
    for _, day in d.groupby(d.index.normalize(), sort=True):
        trades, shadow = replay_day(day, guard)
        all_trades.extend(trades)
        for sig in shadow:
            pts = resolve_shadow(day, sig)
            sig["pts"] = pts
            shadow_pts.append(pts)
        all_shadow.extend(shadow)

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

    print(f"\nperiod          : {TEST_START} -> {TEST_END}  ({sessions} sessions)")
    print(f"trades          : {len(t)} taken, {len(all_shadow)} news-blocked")
    print(f"win rate        : {100*wins/len(t):.1f}%  ({wins}W / {len(t)-wins}L)")
    print(f"net P&L (fees in): ${daily.sum():+,.0f}   (fees paid: ${t['fees'].sum():,.0f})")
    print(f"profit factor   : {gross_w/gross_l:.2f}")
    print(f"avg trade       : ${t['pnl'].mean():+,.0f}   avg active day: ${daily.mean():+,.0f}")
    print(f"best day        : ${daily.max():+,.0f}   worst day: ${daily.min():+,.0f}")
    print(f"max drawdown    : ${dd:+,.0f}")
    print(f"exit mix        : {t['kind'].value_counts().to_dict()}")

    print("\nmonthly P&L (net of fees):")
    monthly = daily.resample("ME").agg(["sum", "count"])
    monthly.index = monthly.index.strftime("%Y-%m")
    for m, row in monthly.iterrows():
        print(f"  {m}  ${row['sum']:+8,.0f}   ({int(row['count'])} active days)")

    if all_shadow:
        s = pd.DataFrame(all_shadow)
        sw = int((s["pts"] > 0).sum())
        print(f"\nnews-blocked signals: {len(s)} "
              f"({s['why'].value_counts().to_dict()}) — "
              f"would-have-been: {sw}W/{len(s)-sw}L, "
              f"{s['pts'].sum():+,.1f} pts (unsized)")

    rate, passes = combine_pass_stats(daily)
    print(f"\n$50K Combine sim (start any active day, EOD-trailing $2k MLL):")
    print(f"  pass rate: {rate:.1f}% of resolved attempts")
    if passes:
        print(f"  traded days to pass: median {int(np.median(passes))}, "
              f"p90 {int(np.percentile(passes, 90))}, worst {max(passes)}")

    out = Path(__file__).parent / "data" / "databento" / "backtest_5mo_news_trades.csv"
    t.to_csv(out, index=False)
    print(f"\ntrade log saved: {out}")


if __name__ == "__main__":
    main()

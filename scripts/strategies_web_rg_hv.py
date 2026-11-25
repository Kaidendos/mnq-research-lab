"""HIGH-VOLATILITY-SPECIFIC entry triggers for MNQ 5-min RTH bars.

Area: hv.  Rules that are documented to work when realised volatility is
elevated: volatility mean-reversion, exhaustion after the day's ATR budget is
spent, fading gap extensions, and ATR-percentile-gated fades.

Every rule below is a port of a published, mechanical rule set.  The source URL
sits directly above each implementation.  Where a source leaves a number to the
reader, the concrete choice is flagged with a comment beginning "READING:".

ENTRY TRIGGERS ONLY - the harness owns stops / targets / sizing / exits.

WHY THESE, FOR THIS REGIME
--------------------------
Measured: median daily range 451pt vs 229pt, median 5-min ATR 51pt vs 26pt,
net 3-month move +1.8%, body/range 44.3% vs 51.6%.  Huge ranges, no net
progress, more wick than body.  That is the textbook fade-the-extreme tape, and
it is hostile to fixed-point levels.  So every level used here is DERIVED FROM
MEASURED VOLATILITY and rescales itself as the regime moves:

  * Camarilla H3/L3   -> 0.275 x PRIOR DAY'S RANGE
  * VWAP 2-sigma      -> 2 x the SESSION'S OWN volume-weighted dispersion
  * ATR exhaustion    -> 80% of the 14-day DAILY ATR
  * gap-extension     -> gap measured in units of daily ATR

None of them needs re-tuning when the range doubles, which is precisely the
failure mode of the user's fixed oversold-reclaim entry.

CAUSALITY
---------
*  Prior-day values (pdh / pdl / prior close / daily ATR) are daily aggregates
   passed through `.shift(1)` before being mapped back onto bars, exactly the
   way the harness builds its own `pdh` / `pdl` / `gate_ema50`.
*  Session aggregates use `cummax` / `cummin` / `cumsum` only, plus
   `transform("first")` on the session's opening bar (a value already known at
   the close of bar 0).
*  The opening-hour range uses `where(...).cummax().ffill()` so that after
   10:30 it freezes at the opening-hour extreme WITHOUT ever calling
   `transform("max")` / `transform("last")` on the live session.
*  Every rolling window is backward-looking and includes at most the current
   bar.  No `.rank()` over the full series, no forward fills from the future.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# ───────────────────────── tunables (all documented) ─────────────────────────
# Camarilla offsets, prior-session range R:  Ln/Hn = C -/+ R * mult
CAM3 = 1.1 / 4.0          # 0.275  -> H3 / L3, the "reversion rungs"
CAM4 = 1.1 / 2.0          # 0.55   -> H4 / L4, the "breakout into trend" rungs

# ATR-percentile volatility gate (Desire To Trade): ATR(14), 200-period rank.
# "Extreme volatility" = top of the rank; those are news spikes, skip them.
ATR_RANK_LEN = 200
ATR_RANK_MAX = 0.90

# CrossTrade VWAP-reversion parameters
VWAP_SD = 2.0             # "price extends 2 x session standard deviations"
PIN_WICK = 2.0            # "lower wick exceeding 2x body size for longs"
VOL_SPIKE = 1.5           # READING: "volume spike on the rejection bar", 20-bar avg
ADX_MAX = 25.0            # "skip when ADX(14) on 5-minute > 25"
OH_END = 10.5             # opening hour ends 10:30 ET
OH_MULT = 2.0             # "skip when opening-hour range > 2x 20-day average"
OH_AVG_DAYS = 20

# edgeful ATR-consumption exhaustion
DATR_LEN = 14             # "14-day ATR"
ATR_CONSUMED = 0.80       # "price trades approximately 80%+ of the ATR"

# gap-extension fade
GAP_MIN_FRAC = 0.10       # READING: minimum gap worth fading, in daily-ATR units
GAP_FADE_END = 12.0       # "most gap moves play out within 30 to 90 minutes"


# ───────────────────────── helpers ─────────────────────────
def _prev_daily(dmap: pd.Series, daily: pd.Series) -> pd.Series:
    """Map a DAILY series, lagged one session, back onto bars.  Causal: the
    value used on day D is day D-1's, which was final before D opened."""
    return dmap.map(daily.shift(1))


def _wicks(o, h, l, c):
    mx = np.maximum(o.to_numpy(), c.to_numpy())
    mn = np.minimum(o.to_numpy(), c.to_numpy())
    up = pd.Series(h.to_numpy() - mx, index=o.index)
    dn = pd.Series(mn - l.to_numpy(), index=o.index)
    return up, dn


def _same_day_prev(day: pd.Series) -> pd.Series:
    """True when the previous bar belongs to the same session."""
    return (day.shift(1) == day).fillna(False)


# ───────────────────────── register ─────────────────────────
def register(df: pd.DataFrame) -> dict:
    o, h, l, c, v = df["open"], df["high"], df["low"], df["close"], df["volume"]
    day, eth, atr, adx, vwap = df["_day"], df["eth"], df["atr"], df["adx"], df["vwap"]
    dmap = pd.Series(day.to_numpy(), index=df.index)
    prev_bar_same_day = _same_day_prev(day)

    # ── prior-session daily values (causal) ────────────────────────────────
    dh = h.groupby(day).max()
    dl = l.groupby(day).min()
    dc = c.groupby(day).last()
    pdh = _prev_daily(dmap, dh)
    pdl = _prev_daily(dmap, dl)
    pdc = _prev_daily(dmap, dc)

    # Wilder ATR(14) on DAILY bars, built from completed sessions, then lagged
    dpc = dc.shift(1)
    dtr = pd.concat([dh - dl, (dh - dpc).abs(), (dl - dpc).abs()], axis=1).max(axis=1)
    datr = dtr.ewm(alpha=1.0 / DATR_LEN, adjust=False).mean()
    prev_datr = _prev_daily(dmap, datr)

    # ── session running aggregates (causal) ────────────────────────────────
    sess_hi = h.groupby(day).cummax()
    sess_lo = l.groupby(day).cummin()
    sess_open = o.groupby(day).transform("first")   # known at the close of bar 0

    # ── ATR percentile gate ────────────────────────────────────────────────
    # https://www.desiretotrade.com/docs/volatility-filter-indicator-atr-percentile-volatility/
    # "use a 14-period ATR for the indicator and a 200 Percentile Rank Period";
    # "avoid taking trades when the Relative ATR is at its highest percentiles".
    # READING: "highest percentiles" = the top decile of the 200-bar rank.
    atr_rank = atr.rolling(ATR_RANK_LEN).rank(pct=True)
    vol_ok = (atr_rank <= ATR_RANK_MAX).fillna(False)

    # ── session VWAP standard-deviation bands (causal, volume weighted) ────
    tp = (h + l + c) / 3.0
    cv = v.groupby(day).cumsum()
    cpv = (tp * v).groupby(day).cumsum()
    cp2v = (tp * tp * v).groupby(day).cumsum()
    vwap_var = (cp2v / cv) - (cpv / cv) ** 2
    vsd = np.sqrt(vwap_var.clip(lower=0.0))

    # ── opening-hour range vs its own 20-day average (causal) ──────────────
    inoh = eth <= OH_END
    oh_hi = h.where(inoh).groupby(day).cummax().groupby(day).ffill()
    oh_lo = l.where(inoh).groupby(day).cummin().groupby(day).ffill()
    oh_rng = oh_hi - oh_lo
    oh_avg = _prev_daily(dmap, oh_rng.groupby(day).last().rolling(OH_AVG_DAYS).mean())
    oh_ok = (oh_rng <= OH_MULT * oh_avg).fillna(False)

    up_wick, dn_wick = _wicks(o, h, l, c)
    body = (c - o).abs()

    out: dict[str, tuple[pd.Series, int]] = {}

    # ═══════════════════════════════════════════════════════════════════════
    # 1 & 2.  CAMARILLA H3 / L3 ROTATION FADE
    # https://www.luxalgo.com/library/concept/camarilla/
    # https://arongroups.co/forex-articles/camarilla-pivot-trading-strategy/
    #
    #   "H3 = C + Range x (1.1/4)",  "L3 = C - Range x (1.1/4)",
    #   "H4 = C + Range x (1.1/2)",  "L4 = C - Range x (1.1/2)"     (prior day H/L/C)
    #   "when price opens and holds inside the band between L3 and H3, the
    #    classic play is shorting tests of H3 and buying tests of L3, targeting
    #    rotation across the trading range with stops beyond the level-4 rungs"
    #   "On trend days these fades simply fail, so most playbooks require
    #    rejection behavior at the rung, not a touch alone."
    #
    # This is THE rule for the measured regime: the rung distance is 27.5% of
    # the PRIOR DAY'S RANGE, so when the median range went 229 -> 451 the fade
    # level moved out with it.  A fixed-point level would now be inside noise.
    # ═══════════════════════════════════════════════════════════════════════
    prng = pdh - pdl
    h3 = pdc + CAM3 * prng
    l3 = pdc - CAM3 * prng
    h4 = pdc + CAM4 * prng
    l4 = pdc - CAM4 * prng

    opens_inside = (sess_open > l3) & (sess_open < h3)      # "opens ... inside the band"
    # "holds inside": the session has not accepted beyond the level-4 rungs.
    # cummax / cummin -> only bars up to and including this one.
    holds_up = sess_hi < h4
    holds_dn = sess_lo > l4

    # a FRESH test of the rung (previous bar had not reached it), same session
    test_h3 = (h >= h3) & (h.shift(1) < h3) & prev_bar_same_day
    test_l3 = (l <= l3) & (l.shift(1) > l3) & prev_bar_same_day
    # "rejection behavior at the rung, not a touch alone" / arongroups:
    # "bearish rejection (failure to hold above)" -> the bar tagged the rung but
    # could not CLOSE beyond it.
    reject_h3 = c < h3
    reject_l3 = c > l3
    # "a quick re-entry back inside the ladder is the standard false breakout
    # warning" - a bar that closed beyond the rung and is immediately given back.
    reenter_h3 = (c < h3) & (c.shift(1) > h3) & prev_bar_same_day
    reenter_l3 = (c > l3) & (c.shift(1) < l3) & prev_bar_same_day

    fade_h3 = (test_h3 & reject_h3) | reenter_h3
    fade_l3 = (test_l3 & reject_l3) | reenter_l3

    out["hv_cam_h3_fade"] = (
        (opens_inside & holds_up & fade_h3 & vol_ok).fillna(False), -1)
    out["hv_cam_l3_fade"] = (
        (opens_inside & holds_dn & fade_l3 & vol_ok).fillna(False), +1)

    # ═══════════════════════════════════════════════════════════════════════
    # 3 & 4.  VWAP 2-SIGMA REVERSION  (CrossTrade)
    # https://crosstrade.io/learn/trading-strategies/vwap-reversion
    #
    #   trigger : "Price extends 2 x session standard deviations from VWAP"
    #   confirm : any one of the three listed - "Pin bar (long lower wick for
    #             longs, long upper wick for shorts)" implemented as "lower wick
    #             exceeding 2x body size for longs, upper wick exceeding 2x body
    #             for shorts"; "Engulfing bar in the reversion direction";
    #             "Volume spike on the rejection bar"
    #   skip if : "ADX(14) on 5-minute > 25 (indicates strong trending regime)"
    #   skip if : "Opening-hour range > 2x 20-day average"
    #   windows : "10:00-11:30 ET - mid-morning chop",
    #             "13:30-14:30 ET - early afternoon, often rotational"
    #   avoid   : "9:30-10:00 ET"
    #
    # Self-scaling by construction: the band is 2x the session's own
    # volume-weighted dispersion, so a doubled ATR doubles the required stretch.
    # The published time windows also happen to dodge the 09:00 hour, which the
    # regime measurement shows has flipped negative.
    # ═══════════════════════════════════════════════════════════════════════
    win_ct = ((eth >= 10.0) & (eth <= 11.5)) | ((eth >= 13.5) & (eth <= 14.5))
    regime_ok = (adx <= ADX_MAX) & oh_ok & (vsd > 0)

    ext_up = h >= vwap + VWAP_SD * vsd
    ext_dn = l <= vwap - VWAP_SD * vsd

    # all three published confirmations, ORed as the source lists them
    pin_up = up_wick > PIN_WICK * body      # bearish pin  -> fade the upside
    pin_dn = dn_wick > PIN_WICK * body      # bullish pin  -> fade the downside
    engulf_up = ((c > o) & (c > o.shift(1)) & (o < c.shift(1))
                 & (c.shift(1) < o.shift(1)) & prev_bar_same_day)
    engulf_dn = ((c < o) & (c < o.shift(1)) & (o > c.shift(1))
                 & (c.shift(1) > o.shift(1)) & prev_bar_same_day)
    # READING: "volume spike" is unquantified in the source; 1.5x the 20-bar
    # average volume is the conventional reading and is backward-looking.
    vspike = v > VOL_SPIKE * v.rolling(20).mean()

    conf_short = pin_up | engulf_dn | vspike
    conf_long = pin_dn | engulf_up | vspike

    out["hv_vwap2sd_short"] = (
        (win_ct & regime_ok & ext_up & conf_short & vol_ok).fillna(False), -1)
    out["hv_vwap2sd_long"] = (
        (win_ct & regime_ok & ext_dn & conf_long & vol_ok).fillna(False), +1)

    # ═══════════════════════════════════════════════════════════════════════
    # 5.  ATR-BUDGET EXHAUSTION FADE  (edgeful)
    # https://www.edgeful.com/blog/posts/average-true-range-trading-strategy
    #
    #   "you can make an educated guess that the day's extremes have been
    #    established when price trades approximately 80%+ of the ATR"
    #   "Once 80%+ traded, initiate trendline break entries ... Target profits
    #    at high-of-day (HOD) or within the established ATR range"
    #
    # Once the session has already spent 80% of the 14-day daily ATR, a bar that
    # pokes to a NEW session high and closes back down is the extension failing.
    # READING: "trendline break" is discretionary; the mechanical stand-in used
    # here is a new-session-high bar that closes below the previous bar's close
    # and below its own open.
    # ═══════════════════════════════════════════════════════════════════════
    consumed = (sess_hi - sess_lo) / prev_datr
    budget_spent = consumed >= ATR_CONSUMED
    new_sess_hi = (h > sess_hi.shift(1)) & prev_bar_same_day
    fails_back = (c < c.shift(1)) & (c < o)

    out["hv_atrexh_short"] = (
        (budget_spent & new_sess_hi & fails_back & vol_ok).fillna(False), -1)

    # ═══════════════════════════════════════════════════════════════════════
    # 6.  GAP-EXTENSION FADE  (gap up, extension fails, target the gap fill)
    # https://www.mypivots.com/article/details/43/fading-the-gap
    # https://arongroups.co/technical-analyze/gap-fill-trading-strategy/
    #
    #   mypivots: gap is measured "from the close of the previous trading
    #   session to the opening price of the following trading session's Regular
    #   Trading Hours (RTH)"; the trade is entered against the gap and closed
    #   when the gap fills - "76% ... of all gaps close at some point during RTH".
    #   arongroups / gap-fade playbooks: do NOT enter into the opening thrust,
    #   "wait for evidence that the initial strong movement is losing steam",
    #   and "most gap moves play out within 30 to 90 minutes of the open".
    #
    #   Mechanical form used here:
    #     * gap up >= GAP_MIN_FRAC x prior daily ATR  (READING: mypivots quoted
    #       absolute ES points, which do not travel across instruments or across
    #       a regime where the range doubled - normalising by daily ATR does)
    #     * the session has extended ABOVE the opening print at some point
    #     * steam loss = close crosses back BELOW the opening print
    #     * the gap-fill target is still below us (close > prior close)
    #     * before GAP_FADE_END, i.e. inside the window where gaps resolve
    # ═══════════════════════════════════════════════════════════════════════
    gap = sess_open - pdc
    gap_up_big = gap >= GAP_MIN_FRAC * prev_datr
    extended_up = sess_hi > sess_open
    lost_steam = (c < sess_open) & (c.shift(1) >= sess_open) & prev_bar_same_day
    room_to_fill = c > pdc

    out["hv_gapx_fade"] = (
        (gap_up_big & extended_up & lost_steam & room_to_fill
         & (eth <= GAP_FADE_END) & vol_ok).fillna(False), -1)

    return out

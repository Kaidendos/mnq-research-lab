"""JOE ROSS — Law of Charts: 1-2-3 reversals, Ross Hook, Trader's Trick Entry.

Area: jr.  Ross has taught the same three patterns since 1988 and publishes them
free ("The Law of Charts" is a giveaway PDF, not a paid signal). The patterns are
defined purely by bar geometry, which is exactly what a mechanical port needs.

RULES, as published
-------------------
https://forexsb.com/wiki/trading/tte
https://www.tradingeducators.com/free-ebook-traders-trick-entry
  "Once a Ross Hook or point 2 of a 1-2-3 pattern is in place, we watch the
   correction and want to buy a violation of the high of any of the first three
   bars after the Ross Hook."
  "The initial stop is placed on the opposite side of the bar."
  "Beyond 3 bars of correction, the odds begin to favor consolidation, and so
   there is no reason to attempt the TTE."
  "In the case of a double high (low) the two bars count as only one correcting
   bar."

THE THREE OBJECTS
-----------------
  1-2-3 LOW   point 1 = a swing low, point 2 = the swing high after it,
              point 3 = a HIGHER low. Trigger = price takes out point 2.
  ROSS HOOK   after a breakout of a prior high, the FIRST failure to continue —
              i.e. the first lower high — is the hook. Trigger = taking out
              the hook's high.
  TTE         do not wait for the trigger; buy the break of the high of one of
              the first three correction bars, which is EARLIER and is the whole
              point of the "trick".

CAUSALITY
---------
Swing points carry the mandatory 2-bar confirmation lag; an unconfirmed swing is
lookahead. The "first three bars after the hook" counter is a forward scan from a
CONFIRMED hook, so every bar it reads is at or before the signal bar. Triggers are
close-based, so the signal is known at the close the harness enters on.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

SWING_N = 2          # bars either side; Ross draws these by eye, 2 is the minimum
TTE_BARS = 3         # published: "the first three bars after the Ross Hook"
BREAKOUT_LOOK = 20   # READING: the prior high a breakout must clear to arm a hook


def _confirmed_swings(h, l, n):
    is_hi = (h.shift(n) == h.rolling(2 * n + 1).max())
    is_lo = (l.shift(n) == l.rolling(2 * n + 1).min())
    return is_hi.fillna(False), is_lo.fillna(False)


def register(df: pd.DataFrame) -> dict:
    h, l, c = df["high"], df["low"], df["close"]
    idx = df.index
    n = SWING_N

    is_hi, is_lo = _confirmed_swings(h, l, n)
    hi_lv = h.shift(n).where(is_hi)
    lo_lv = l.shift(n).where(is_lo)

    H = h.to_numpy(float)
    L = l.to_numpy(float)
    C = c.to_numpy(float)
    HI = hi_lv.to_numpy(float)
    LO = lo_lv.to_numpy(float)
    N = len(C)

    # ── 1-2-3 low: swing low (1), swing high (2), higher swing low (3) ──
    one23_long = np.zeros(N, bool)
    one23_short = np.zeros(N, bool)
    tte_long = np.zeros(N, bool)
    tte_short = np.zeros(N, bool)

    p1 = p2 = None                      # long side: last low, last high after it
    q1 = q2 = None                      # short side mirror
    armed_l = armed_s = None            # (level, bars_since_arm)
    tte_l = tte_s = None                # (level, correction_bar_count)

    for i in range(N):
        # trigger checks come FIRST so an arm set on bar i cannot fire on bar i
        if armed_l is not None:
            lv, age = armed_l
            if C[i] > lv:
                one23_long[i] = True
                armed_l = None
            else:
                armed_l = (lv, age + 1) if age < 30 else None
        if armed_s is not None:
            lv, age = armed_s
            if C[i] < lv:
                one23_short[i] = True
                armed_s = None
            else:
                armed_s = (lv, age + 1) if age < 30 else None
        if tte_l is not None:
            lv, k = tte_l
            if C[i] > lv:
                tte_long[i] = True
                tte_l = None
            elif k >= TTE_BARS:
                tte_l = None
            else:
                # "a violation of the high of ANY of the first three bars" — so
                # the level to beat is the current correction bar's own high.
                tte_l = (H[i], k + 1)
        if tte_s is not None:
            lv, k = tte_s
            if C[i] < lv:
                tte_short[i] = True
                tte_s = None
            elif k >= TTE_BARS:
                tte_s = None
            else:
                tte_s = (L[i], k + 1)

        # then update the pattern state from newly confirmed swings
        if np.isfinite(LO[i]):
            if p2 is not None and LO[i] > p1:
                # point 3 confirmed above point 1 -> arm the break of point 2
                armed_l = (p2, 0)
                tte_l = (H[i], 0)
                p1, p2 = LO[i], None
            else:
                p1, p2 = LO[i], None
        if np.isfinite(HI[i]):
            if p1 is not None and (p2 is None or HI[i] > p2):
                p2 = HI[i]
            if q2 is not None and HI[i] < q1:
                armed_s = (q2, 0)
                tte_s = (L[i], 0)
                q1, q2 = HI[i], None
            else:
                q1, q2 = HI[i], None
        if np.isfinite(LO[i]) and q1 is not None and (q2 is None or LO[i] < q2):
            q2 = LO[i]

    # ── Ross Hook: first lower high AFTER a breakout of the prior N-bar high ──
    prior_hi = h.rolling(BREAKOUT_LOOK).max().shift(1)
    prior_lo = l.rolling(BREAKOUT_LOOK).min().shift(1)
    broke_up = (c > prior_hi)
    broke_dn = (c < prior_lo)

    hook_long = np.zeros(N, bool)
    hook_short = np.zeros(N, bool)
    BU = broke_up.to_numpy(bool)
    BD = broke_dn.to_numpy(bool)
    state_l = None        # ("wait_hook", running_high) | ("armed", level, age)
    state_s = None
    for i in range(N):
        if state_l is not None and state_l[0] == "armed":
            _, lv, age = state_l
            if C[i] > lv:
                hook_long[i] = True
                state_l = None
            else:
                state_l = ("armed", lv, age + 1) if age < 20 else None
        elif state_l is not None:
            _, run_hi = state_l
            if np.isfinite(HI[i]) and HI[i] < run_hi:
                state_l = ("armed", HI[i], 0)      # the hook
            elif H[i] > run_hi:
                state_l = ("wait_hook", H[i])

        if state_s is not None and state_s[0] == "armed":
            _, lv, age = state_s
            if C[i] < lv:
                hook_short[i] = True
                state_s = None
            else:
                state_s = ("armed", lv, age + 1) if age < 20 else None
        elif state_s is not None:
            _, run_lo = state_s
            if np.isfinite(LO[i]) and LO[i] > run_lo:
                state_s = ("armed", LO[i], 0)
            elif L[i] < run_lo:
                state_s = ("wait_hook", L[i])

        if BU[i] and (state_l is None or state_l[0] != "armed"):
            state_l = ("wait_hook", H[i])
        if BD[i] and (state_s is None or state_s[0] != "armed"):
            state_s = ("wait_hook", L[i])

    S = lambda a: pd.Series(a, index=idx)
    return {
        "jr_123_long": (S(one23_long), +1),
        "jr_123_short": (S(one23_short), -1),
        "jr_tte_long": (S(tte_long), +1),
        "jr_tte_short": (S(tte_short), -1),
        "jr_hook_long": (S(hook_long), +1),
        "jr_hook_short": (S(hook_short), -1),
    }

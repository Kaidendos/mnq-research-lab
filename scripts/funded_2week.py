"""Day-by-day P&L of the two Keltner strategies over the past ~2 weeks
(2026-07-02 -> 2026-07-16, the end of the data). $440 cap, funded sizing, fees in."""

import pandas as pd

import funded_lib as fl
import funded_lib2 as fl2
import funded_lib3 as fl3

WIN = (9.75, 11.5833)
START = "2026-07-02"


def main():
    d = fl3.enrich3(fl2.enrich2(fl.load_enriched()))
    kelt = fl2.sig2(d, "keltner_break_long")[0]

    runner = fl2.replay_runner(d, kelt, +1, 1.0, WIN, None, mode="eod")[0]      # no gate
    bracket = fl.replay_sessions(d, kelt, +1, 1.0, 1.5, WIN, "gate_ema50")[0]   # 1/1.5 gated

    r2 = runner[runner.index >= START]
    b2 = bracket[bracket.index >= START]
    alld = sorted(set(r2.index) | set(b2.index))

    print("=" * 60)
    print("PAST 2 WEEKS — daily net $ (only days with a trade shown)")
    print("=" * 60)
    print(f"{'date':12}{'Keltner runner':>16}{'Keltner 1/1.5':>16}")
    print("-" * 60)
    cr = cb = 0.0
    for dt in alld:
        rv = r2.get(dt, None); bv = b2.get(dt, None)
        cr += rv or 0; cb += bv or 0
        rs = f"{rv:>+9,.0f}" if rv is not None else f"{'--':>9}"
        bs = f"{bv:>+9,.0f}" if bv is not None else f"{'--':>9}"
        print(f"{str(dt.date()):12}{rs:>16}{bs:>16}")
    print("-" * 60)
    print(f"{'TOTAL 2wk':12}{cr:>+16,.0f}{cb:>+16,.0f}")
    print(f"{'trading days':12}{len(r2):>16}{len(b2):>16}")
    print(f"{'buffer $1,100':12}{'HIT' if cr>=1100 else 'no':>16}{'HIT' if cb>=1100 else 'no':>16}")
    print("\nNote: ~11 trading days is a TINY sample — good for a sanity check of")
    print("recent behavior, NOT for judging a strategy. Use the 5mo/5yr numbers for that.")


if __name__ == "__main__":
    main()

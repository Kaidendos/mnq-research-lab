"""Refine the H3 shape: stop-after-win vs dollar day-targets, short-sleeve
bracket variants, short session windows."""

from eval_hunt import run, report
from strat_search_5y import load

def main():
    d = load()
    for tag, cfg, cap, saw in [
        ("J1 saw + Sbd1.25-.75", dict(Lstoch=1, Sbd=(1.25, 0.75)), 1500, True),
        ("J2 cap450 Sbd1.5-1.0", dict(Lstoch=1, Sbd=(1.5, 1.0)), 450, False),
        ("J3 cap600 Sbd1.5-1.0", dict(Lstoch=1, Sbd=(1.5, 1.0)), 600, False),
        ("J4 cap600 Sbd1.25-.75", dict(Lstoch=1, Sbd=(1.25, 0.75)), 600, False),
        ("J5 cap900 Sbd1.25-.75", dict(Lstoch=1, Sbd=(1.25, 0.75)), 900, False),
        ("J6 saw cap900 Sbd1.5-1", dict(Lstoch=1, Sbd=(1.5, 1.0)), 900, True),
    ]:
        report(tag, run(d, cfg, cap, saw))

if __name__ == "__main__":
    main()

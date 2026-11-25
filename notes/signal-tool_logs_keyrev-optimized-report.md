# Key-reversal optimization — eval-feasibility hardened (2026-06-30)

Confluence tweaks of *KeyRev @ Bollinger band*, risk-control grid, scored **net of fee+2-tick slippage** on 4 samples. PASS = chronological $50K Combine (reach +$3,000 before −$2,000 trailing DD or −$1,000 day). MC% = Monte-Carlo return-order stress (10k shuffles) that still reach +$3k before −$2k DD.

Survivors (net+ & feasible on 90d & 58d, net+ recent-13d): **148**.

| Method | Config | 90d Net | 90d Win | 90d PF | 90d DD | 58d Net | 13d-cached | Recent-13d | Combine PASS | MC pass% |
|---|---|---:|---:|---:|---:|---:|---:|---:|:--:|---:|
| KeyRev @ BB + close-back-inside | s1.5/t2 $200 2/d -700 | +$4,776 | 54.5% | 1.52 | -$1604 | +$2,001 | +$857 | +$1,754 (58.3%) | ✅ | 99% |
| KeyRev @ BB + close-back-inside | s1.5/t2 $200 2/d -500 | +$4,776 | 54.5% | 1.52 | -$1604 | +$2,001 | +$857 | +$1,754 (58.3%) | ✅ | 98.7% |
| KeyRev @ BB band | s1.5/t2 $200 2/d -500 | +$4,659 | 53.7% | 1.48 | -$1301 | +$1,635 | +$1,312 | +$1,906 (60%) | ✅ | 98.7% |
| KeyRev @ BB + close-back-inside | s1.5/t1.5 $200 2/d -700 | +$3,089 | 59% | 1.37 | -$1354 | +$1,240 | +$870 | +$1,213 (62.5%) | ✅ | 98.7% |
| KeyRev @ BB + close-back-inside | s1.5/t1.5 $200 2/d -500 | +$3,089 | 59% | 1.37 | -$1354 | +$1,240 | +$870 | +$1,213 (62.5%) | ✅ | 98.6% |
| KeyRev @ BB band | s1.5/t2 $200 2/d -700 | +$4,659 | 53.7% | 1.48 | -$1301 | +$1,635 | +$1,312 | +$1,906 (60%) | ✅ | 98.5% |
| KeyRev @ BB + volume thrust | s1.5/t2 $200 2/d -500 | +$3,134 | 51.3% | 1.38 | -$1525 | +$1,935 | +$1,336 | +$2,176 (73.7%) | ✅ | 98.3% |
| KeyRev @ BB + volume thrust | s1.5/t2 $200 2/d -700 | +$3,134 | 51.3% | 1.38 | -$1525 | +$1,935 | +$1,336 | +$2,176 (73.7%) | ✅ | 98.2% |
| KeyRev @ BB + volume thrust | s1.5/t2 $200 3/d -700 | +$3,896 | 50.3% | 1.4 | -$1849 | +$2,172 | +$1,795 | +$3,030 (76%) | ✅ | 97.7% |
| KeyRev @ BB + close-back-inside | s1.5/t2.5 $200 2/d -500 | +$5,163 | 49.6% | 1.52 | -$1604 | +$2,840 | +$139 | +$996 (47.8%) | ✅ | 97.6% |
| KeyRev @ BB + volume thrust | s1.5/t2 $200 3/d -500 | +$3,896 | 50.3% | 1.4 | -$1849 | +$2,172 | +$1,795 | +$3,030 (76%) | ✅ | 97.5% |
| KeyRev @ BB + close-back-inside | s1/t2 $200 2/d -500 | +$7,558 | 45.9% | 1.65 | -$1435 | +$4,049 | +$1,247 | +$1,521 (48%) | ✅ | 97.5% |

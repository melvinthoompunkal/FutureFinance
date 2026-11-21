# Phase 3 completion log

**Implemented November 21, 2026.** The market and sector views passed offline acceptance. Live coverage depends on verified exports for the intended universe.

## Delivered

- The market view pairs dividend-adjusted SPY and QQQ performance with split-adjusted trend and 50- and 200-session breadth. It shows the numerator, eligible and expected counts, five-session changes, and the closes and averages behind each reading. The RSP/SPY chart is labeled as a concentration proxy when the selected session lacks dated membership.
- The sector view ranks all 11 ETFs with available 20-session relative returns, keeps 5- and 60-session relative returns beside the 20-session absolute return, and shows each sector’s dated breadth and eligible count. Drilldowns expose the member fraction beating SPY, a member table, and the existing stock detail. Market, sector, and stock navigation preserves the date and chart window.
- The market view shows dated VIX and VIX3M closes, the percentile of VIX against available observations in its trailing 252 sessions, the latest same-date term structure ratio, and the 20-session change in high-yield spreads in basis points. HYG/IEF can supply a separately labeled credit proxy. Optional `stress.csv` observations are archived with release timestamps. The selected NYSE close plus 30 minutes limits which observations and revisions appear. [Import instructions](../README.md#try-a-local-price-export)

## Offline acceptance

| Scenario | Verified reading |
| --- | --- |
| SPY rose on narrow participation on August 8, 2025 | SPY rose **0.84%**. Independent counting across the dated list produced **38 of 100** members above the 50-session average, down **7 pp** from five sessions earlier. The 200-session reading was **45 of 100**. |
| Rank all 11 sectors on August 8, 2025 | Independently sorted all 11 endpoint ratios. XLK ranked **1st** with **+4.573927%** vs. SPY and **+5.096125%** absolute. The four input closes were XLK **131.08 → 137.76** and SPY **606.78 → 609.81**. |
| A sector led while falling on August 1, 2025 | XLF fell **0.167%** while SPY fell **0.239%**, so XLF gained **0.072%** relative to SPY. Market-to-sector navigation kept the selected date and window and exposed the member table. |
| Membership file absent | The import reported member breadth unavailable and displayed RSP/SPY as a concentration proxy. An eligible HYG/IEF series appeared as the fallback for absent high-yield spread data. |
| Late or mismatched stress observations | Offline replay showed VIX **24.00** from August 7 with a term ratio of **0.90×** from August 6, the latest common date by the cutoff. The spread was **425 bp**, up **75 bp** from July 11. A late VIX3M close and a late VIX revision stayed out of the readings. |

The test suite passed with 18 tests. Ruff, Python compilation, the local Streamlit health endpoint, and replay of Phase 2 archive version 3 passed. Browser layout and narrow-screen rendering remain unverified.

## Remaining live work

- Phase 2 still needs the real bar backfill, a dated membership import, the first verified SEC filing snapshot, and Windows task registration with observed run outcomes. [Phase 2 progress log](phase-2.md)
- Phase 3 still needs a verified price export covering all 11 ETFs and the intended breadth universe, plus permitted volatility and credit inputs or verified proxies. This workstation had synthetic fixtures and no configured data-provider credentials during verification.

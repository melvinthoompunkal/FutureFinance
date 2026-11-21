# Phase 4 completion log

**Implemented November 21, 2026.** Stock detail and its archive workflow passed offline acceptance. The local Streamlit server passed its health check. Live scheduled capture and browser accessibility verification remain open.

## Delivered

- The watchlist and sector member picker open the same stock detail and preserve the New York session and chart window. The page compares dividend-adjusted stock, sector ETF, and SPY returns. Dated watchlist sector mappings leave the breadth universe intact.
- Stock detail displays split-adjusted trend, 14-session average true range, annualized 20- and 60-session realized volatility, chart-window drawdown, 52-week high distance, and relative volume. Missing bars and short histories affect the measures that depend on them.
- SEC-linked filing snapshots supply revenue growth, operating margin and its year-over-year change, trailing free cash flow, leverage, interest coverage, and valuation. Comparable sector members contribute the median and eligible issuer count. The page distinguishes loss-making earnings, inapplicable accounting measures, and unknown, estimated, or confirmed earnings dates.
- Capture and replay preserve point-in-time accessions, earnings announcements, and ticker aliases. Older archive versions still open. Optional issuer export errors appear in the affected panel and archive manifest. [Import and recovery instructions](../README.md#add-issuer-filings-and-earnings-dates)

## Filing reconciliation

The [hand-checked inputs](../tests/fixtures/phase4-filings.csv) use the figures available at the original EDGAR acceptance times. Tests use controlled prices to exercise yield and P/E. The built-in preview uses synthetic financials for its walkthrough.

| Issuer | Quarter and EDGAR acceptance | Reconciled figures |
| --- | --- | --- |
| Apple | June 28, 2025. Accepted August 1 at 6:00:42 a.m. ET. | Revenue **$94.036B** vs. **$85.777B**. Operating margin **29.99%**, up **0.43 pp**. Trailing CFO **$108.565B** less capex **$12.381B** gives FCF **$96.184B**. Four reported quarterly diluted EPS values total **$6.59**. [Quarterly filing](https://www.sec.gov/Archives/edgar/data/320193/000032019325000073/aapl-20250628.htm) · [Acceptance record](https://www.sec.gov/Archives/edgar/data/320193/000032019325000073/0000320193-25-000073-index.htm) · [2024 annual filing](https://www.sec.gov/Archives/edgar/data/320193/000032019324000123/aapl-20240928.htm) |
| Rivian | June 30, 2025. Accepted August 5 at 5:00:52 p.m. ET. | Revenue **$1.303B** vs. **$1.158B**. Operating margin **−85.50%**, up **33.24 pp**. Trailing CFO **$183M** less capex **$1.404B** gives FCF **−$1.221B**. Four reported quarterly diluted EPS values total **−$3.23**, so the dashboard displays **Loss-making**. [Quarterly filing](https://www.sec.gov/Archives/edgar/data/1874178/000187417825000036/rivn-20250630.htm) · [Acceptance record](https://www.sec.gov/Archives/edgar/data/1874178/000187417825000036/0001874178-25-000036-index.htm) · [2024 annual filing](https://www.sec.gov/Archives/edgar/data/1874178/000187417825000007/rivn-20241231.htm) |

Trailing cash flows reconcile from the last annual total plus current year-to-date less prior year-to-date. The standalone EPS amounts come from the June filings and the preceding three quarters. [Apple September](https://www.sec.gov/Archives/edgar/data/320193/000032019324000120/a8-kex991q4202409282024.htm) · [Apple December](https://www.sec.gov/Archives/edgar/data/320193/000032019325000008/aapl-20241228.htm) · [Apple March](https://www.sec.gov/Archives/edgar/data/320193/000032019325000055/a8-kex991q2202503292025.htm) · [Rivian September](https://www.sec.gov/Archives/edgar/data/1874178/000187417824000063/rivn-20240930.htm) · [Rivian December](https://www.sec.gov/Archives/edgar/data/1874178/000187417825000004/ex-9924q24shareholderletter.htm) · [Rivian March](https://www.sec.gov/Archives/edgar/data/1874178/000187417825000026/rivn-20250331.htm)

## Offline acceptance

| Scenario | Verified result |
| --- | --- |
| Index rises on narrow participation | SPY rose **0.84%** while **38 of 100** members were above their 50-session average, down **7 pp**. The 200-session numerator was **45 of 100**. |
| Sector leadership and participation | All 11 eligible ETFs ranked on the same session. XLF fell on August 1 and still outperformed SPY. Opening a member kept the selected session and window. |
| Stock leads while the business weakens | Synthetic AAPL rose **1.30%** while operating margin fell **2 pp** year over year. It showed sector and market comparisons with two eligible valuation peers. RIVN and CRCL exercised loss-making earnings, an unknown sector and short trading history. |
| Information available that evening | RIVN's August 5 filing stayed out of the replay that evening. A controlled amendment appeared at its new cutoff and kept the previous session and immutable version intact. An announcement after an early-close cutoff first appeared on the following session. |
| Failure and recovery | Tested split-adjusted volatility, P/E and volume across a split, dividend-adjusted returns, a holiday and early close, duplicate and interrupted captures, missing inputs, and an invalid optional filing file. Replayed matching results from an isolated backup after removing its filing input. |

All 22 tests passed. Ruff, Python compilation, and a separate CLI replay of Phase 2 archive version 3 passed. With the synthetic data cached, Streamlit's test harness measured **0.13–0.18 s** for the overview and **0.05–0.06 s** for stock detail. These timings measure server-side reruns. The browser tool could not verify the local URL, so keyboard navigation, narrow-screen rendering, and end-to-end browser timings remain unverified.

## Local launch and remaining work

- The dashboard ran on `127.0.0.1:8501`. [Start and watchlist instructions](../README.md#start-on-windows)
- The scheduler registration script's `-WhatIf` check passed. The Windows task query was denied in this session, and there was no verified live bundle in `data/inbox`. Task registration, verification after a machine restart, and five consecutive scheduled run outcomes remain open. [Scheduler and failed-run instructions](../README.md#windows-capture-schedule) · [Backup and recovery](../README.md#back-up-and-recover-a-session)

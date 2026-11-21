# Phase 1 completion log

**Audited November 21, 2026.** The local preview passed its offline acceptance checks. Phase 1 remains open for live source verification.

## Delivered

- Selected SPY as the benchmark, QQQ as the comparison, the 11 sector ETFs, a 20-symbol watchlist, dated IVV equity holdings as the membership candidate, and the current Windows workstation with a $0 data budget.
- Built the Streamlit market, sector, and stock preview. It preserves the New York session and chart window during drilldown and identifies its synthetic data.
- Added a normalized CSV import for quoted, split-adjusted, and dividend-adjusted closes, plus optional dated membership. The market view can show the RSP/SPY concentration proxy when membership is unavailable.
- Added an on-demand Alpaca and SEC probe and documented public sample observations, measure definitions, and decisions for optional feeds. [Phase 1 feasibility record](../Plans/phase-1-feasibility.md)

## Tests and results

The first pass saved three analytics tests and ran separate walkthrough, import, and provider pagination checks. The audit added those checks to the test suite so they can be rerun with `python -m unittest discover -s tests -v`.

| Test file | What passed |
| --- | --- |
| [test_analytics.py](../tests/test_analytics.py) | SPY rose 0.84% with 38 of 100 eligible constituents above their 50-session average, down 7 percentage points. Also verified the minimum coverage rule, missing membership, XLK ranking against a hand-calculated return ratio, and CRCL's short history. |
| [test_preview.py](../tests/test_preview.py) | Market → sector → AAPL preserved the selected date and window. AAPL showed a 1.30% gain and a 2-point margin decline. RIVN showed negative earnings and hid a simulated filing until the cutoff allowed it. CRCL showed short history and an unknown sector. The suite also checked zero earnings, absent dividend-adjusted data, the concentration proxy, a split, an explicitly missing session, dated membership, and rejected CSV rows. |
| [test_probe.py](../tests/test_probe.py) | Mocked provider responses verified pagination, the date and price at a split checkpoint, reporting an absent ticker, and rejecting a repeated page token. |

All **10 tests passed** on Python 3.12.7 and Streamlit 1.54.0. Ruff and Python compilation passed, and the running dashboard returned `ok` from its local health endpoint. Temporarily substituting an incorrect breadth label caused the intended test to fail. Streamlit interaction tests used its test harness. Browser layout and narrow-screen rendering remain unverified.

## Audit findings and fixes

| Finding | Resolution |
| --- | --- |
| A comparison chart could silently omit a ticker when its dividend-adjusted series was missing. | Name each missing ticker. When populated series have no session in common, explain why the chart cannot be rebased. |
| Zero or missing trailing EPS fell into the loss-making display state. | Reserve that state for negative EPS and show P/E as unavailable for zero or missing EPS. |
| Pandas could treat an extra CSV field as an implicit row index and accept the remaining fields. | Reject files that use an inferred index, with a regression test for a row that previously slipped through. |
| Sector breadth omitted the five-session change shown on the market view. | Use the same evidence formatting for the chosen sector when both readings are available. |

## Remaining Phase 1 checks

- Confirm authenticated price coverage or obtain a permitted export. Compare the split, dividend, and volume checkpoints and measure the observed delay, history, field completeness, and request count.
- Verify the intended membership and volatility retention rights, and validate an actual dated membership import. Run the SEC tag and acceptance-time reconciliation with a declared contact identity.
- Check two consecutive sessions of dated options open interest against matching contracts. The current probe run reported missing Alpaca credentials and SEC contact configuration. Mocked responses verify the code path. Provider entitlement and timing still require live evidence.

The completion condition and open sampling task are tracked in the [dashboard plan](../Plans/stock-market-dashboard-plan.md).

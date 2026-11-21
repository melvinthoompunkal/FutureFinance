# Phase 5 completion log

**Implemented November 21, 2026.** The deeper research panels, dated imports and offline replay passed local verification. Live release still needs provider access, entitlements and matched samples for each feed.

## Delivered

- **Market and sector.** Advance/decline, yearly highs and lows, weekly sector rotation trails, Treasury yields, the broad dollar index, and market put/call ratios. Internals show counts against dated membership. Headlines use a seven-day window, stable issuer and story IDs, duplicate-title checks, equal issuer weights, coverage thresholds, and inspectable titles and source counts.
- **Options.** Quote quality, ATM volatility and straddles, IV-based expected moves, interpolated 30-day IV, 25-delta risk reversal, IV rank and percentile, dated OI changes and separate OI and volume put/call. The gamma model shows gross and net exposure, coverage, expiry buckets, walls, and detected zero crossings across ±20% of spot. Same-day expiry analysis uses a timed pre-settlement capture.
- **Stock research.** Wilder ADX and directional indicators, Bollinger bandwidth, confirmed swing levels, bar-based VWAP and volume profile, filing and historical valuation context, matched earnings surprises and estimates, open-market Form 4 activity, and separate short interest, ATS and off-exchange short-volume measures.
- **Archive.** Pre-open capture preserves dated OI. Options chains and estimate snapshots accumulate across publications under the same permitted feed label. Late observations can appear in a later publication when they are known at its cutoff. Unapproved optional source files are excluded from raw storage. Archived inputs support research replay through `replay --research`. [Export fields and usage](../README.md#add-phase-5-research-exports)

## Offline acceptance

| Check | Result |
| --- | --- |
| Chain quality and IV | A matched $3.20 call and $3.20 put gave a $6.40 straddle. A $100 spot and 20% one-year IV gave a $20 standard-deviation move. Tests exercised crossed, zero-bid, stale, adjusted and wide-spread contracts, missing IV brackets, and 60- and 252-session history rules. |
| Gamma and open interest | Reconciled gross and net gamma against a hand-calculated ATM contract. Tested no crossing, one crossing and two crossings. A previous effective session and a pre-open update gave call and put OI changes of 10 and 5 contracts. Repeated capture left the publication unchanged. |
| Tone and dated participation | Ten scored technology headlines across three issuers produced a score of 0.167 after deduplication. Sparse coverage withheld the score. A later headline was excluded. Recomputed market counts and sector rotation from the aligned inputs. |
| Stock and intraday | A controlled EPS release gave a 5.71% surprise against the prior consensus. No realized earnings move was shown before the first post-release close. Matched positioning counts gave 37.5% off-exchange short volume and two days to cover. Two complete bars gave a $100.75 VWAP approximation. A swing first appeared on its third confirming session. |
| Replay and interface | An earnings observation at 4:31 p.m. stayed out of that session and appeared in the next publication even after its source file was removed. Phase 2 archive version 3 still returned 38 of 100 members above their 50-session average. Streamlit tests covered all three views, including populated synthetic research and missing-chain states. |

All 31 tests passed. Ruff, Python compilation, a separate CLI replay, and the local Streamlit health endpoint passed. Browser verification stopped because the Windows computer-use tool could not confirm the local URL. Keyboard navigation and narrow-screen layout remain unverified in a browser.

## Live release checks

- Confirm the intended account's options entitlement and delayed or indicative feed behavior. Reconcile effective OI dates, contract terms, full expiry coverage and one timed pre-expiry capture. Build 60 valid sessions for provisional IV rank and 252 valid sessions for the full-window label. [Alpaca historical options data](https://docs.alpaca.markets/us/docs/historical-option-data) · [OCC open interest](https://www.theocc.com/market-data/market-data-reports/volume-and-open-interest/open-interest)
- Confirm storage and display rights for both the news feed and dictionary. Hand-score a permitted sample and check issuer mapping and syndication. [Dictionary terms](https://sraf.nd.edu/loughranmcdonald-master-dictionary/)
- Reconcile actual rate and put/call series, as-published same-basis consensus, Form 4 transaction details, FINRA coverage and denominators, and intraday venue coverage. The local collector reads prepared exports. Provider integrations and Windows scheduled-run outcomes remain open. [FRED Treasury yields](https://fred.stlouisfed.org/series/DGS10) · [FINRA datasets](https://developer.finra.org/catalog) · [Phase 4 completion log](phase-4.md)

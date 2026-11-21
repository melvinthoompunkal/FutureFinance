# Stock market dashboard project plan

**First release.** Build a personal, end-of-day dashboard that lets someone start at the U.S. market, open a sector, and inspect a stock without losing the benchmark or date. Each view should answer three questions in plain language. What changed? How widely is it confirmed? Which observations explain it?

**First milestone.** Start collecting dated snapshots as soon as each data source passes a small feasibility check. Prices and filings have useful history on day one. A missed options chain, consensus estimate, or sector membership snapshot can leave a permanent gap. Build the market, sector, and stock views while that history accumulates. [Research on the product and its limits](../StockResearch/Stock1.txt) · [Research on data collection and indicators](../StockResearch/Stock2.txt)

## 1. Coverage and release boundary

| Decision | Proposed starting point | Reason |
| --- | --- | --- |
| Audience and cadence | One person using a private, read-only dashboard after the U.S. close. Use a selectable session date and show times in New York time. | Matches the research and makes a daily observation reproducible. |
| Market universe | Use the S&P 500 for large-cap participation, SPY as its tradable proxy, and QQQ for the Nasdaq-100 comparison. Name this coverage on the overview. | An index can rise while most members weaken. A defined universe makes that difference measurable. |
| Market segments | Start with the 11 U.S. equity sectors. Keep a dated mapping of stock, sector and representative ETF. | Gives each stock a relevant comparison and makes sector breadth possible. Industries, size groups and international markets can use the same approach later. |
| Stock coverage | Offer price and sector comparisons for covered constituents. Start detailed filings and options collection with an editable watchlist of about 20 U.S. stocks. Accept a local symbol list or CSV. | Breadth needs broad daily prices. Full chains and checked financial statements can cover a smaller universe at much lower cost. |
| Budget and platform | Start with permitted free data and local storage on an available Windows machine. Measure coverage and cost before choosing a paid feed or hosted deployment. | The main unresolved cost is reliable historical and options data. A desktop is sufficient for testing the daily workflow. |

The first usable release includes market health, sector leadership and participation, and stock price **and** business health. It also includes source dates, coverage, and a working archive. Use deterministic calculations and sentence templates, as proposed in the research. Headline sentiment, estimated dealer positioning, intraday charts and external integrations each have a later release condition below.

## 2. What each screen should tell the user

### Market overview — is strength broad or concentrated?

Lead with a chart of SPY returns and an aligned chart of the percentage of index members above their 50- and 200-session simple moving averages. Add QQQ for comparison. Show the count of eligible members beside breadth. Under the charts, show the VIX and 3-month VIX relationship, credit conditions, and the sectors gaining or losing relative strength.

Use a short, reproducible description of **trend, participation and stress**. The following are proposed display rules to test on historical sessions. They describe conditions at the selected close.

| Evidence | Calculation | Initial wording rule |
| --- | --- | --- |
| Market trend | Compare SPY close with its 50- and 200-session averages. Show the distances and the 20-session change in the 200-session average. | Above both averages gives “uptrend,” below both gives “downtrend,” and any other combination gives “mixed trend.” Show QQQ disagreement separately. |
| Participation | Count eligible members above each average and divide by members with a valid close and sufficient history for that window. Also show the five-session change in percentage points. | For 50-session breadth, use “broad” at 60% or more, “narrow” at 40% or less, and “mixed” between. Require at least 90% coverage of the dated universe for each window before assigning its label. |
| Volatility and credit | Compare VIX with its own history, VIX divided by 3-month VIX with 1, and the high-yield option-adjusted spread with its level 20 sessions earlier. Show spread change in basis points. | Report observations such as “near-term volatility elevated” when the ratio exceeds 1 and “credit spreads widening” when the spread change is positive. Show each observation and its date. |

With sufficient coverage, the overview could read *“SPY is above both averages. Only 38% of members are above their 50-day average, down 7 percentage points this week.”* This illustrative case should be part of acceptance testing. If constituent history is unavailable, show equal-weight versus cap-weight S&P 500 performance (RSP/SPY) as a concentration proxy and mark member breadth unavailable.

### Sector comparison — where is sentiment strengthening, and what supports that reading?

The first release measures **market-implied sector sentiment** through relative performance and participation. Rank sectors by the 20-session change in sector ETF/SPY on aligned, dividend-adjusted closes. Include 5- and 60-session changes, absolute return, member breadth, and coverage. A sector can lead during a selloff because it fell less than SPY. Keeping the absolute return beside the relative return makes that case visible.

Show a sorted horizontal bar chart around zero beside a table. Selecting a sector opens its ratio history, a breadth chart, and the members with the strongest and weakest relative returns. Calculate “share outperforming SPY” from equal-count member comparisons on the same 20-session window. Count dual share classes according to the selected constituent universe and disclose that choice.

| Sector | ETF | Sector | ETF |
| --- | --- | --- | --- |
| Communication services | XLC | Consumer discretionary | XLY |
| Consumer staples | XLP | Energy | XLE |
| Financials | XLF | Health care | XLV |
| Industrials | XLI | Information technology | XLK |
| Materials | XLB | Real estate | XLRE |
| Utilities | XLU | | |

Describe leadership from the sign of the 20-session ratio change and participation from the 50-session breadth rule above. For example, *“Technology is outperforming SPY, but only 37% of its members are above their 50-day average.”* If the sector mapping is unknown, keep the stock-to-market comparison and identify the missing sector.

**Headline sentiment.** Add a distinct news-tone column once a feed and finance dictionary permit the intended use. Map time-stamped headlines to issuers, deduplicate syndicated stories, count positive and negative dictionary terms, and calculate their difference divided by their sum per headline. Average scored headlines by issuer, then give each covered issuer equal weight within its sector. Show the seven-day window, issuer count, scored/total headline count, and source mix. As a pilot threshold, require ten scored headlines across at least three issuers. Below that threshold display “limited news coverage.” Exclude headlines without matched sentiment words from the score and show representative headlines so a reader can inspect negation or ambiguous language. The Loughran–McDonald dictionary is a candidate whose stated free-use terms cover academic research. [Dictionary and usage terms](https://sraf.nd.edu/loughranmcdonald-master-dictionary/)

### Stock detail — is the price move company-specific, and does the business support it?

Start with the close, session change, next earnings date if known, and three return lines rebased to 100 on the first common date. Compare the stock, its sector ETF and SPY over the same window. Follow with the evidence below.

| Dimension | First-release measures | Interpretation and edge cases |
| --- | --- | --- |
| Price and leadership | Close vs. 20/50/200-session averages, 20-session changes in stock/sector and stock/SPY, distance from the 52-week high | Use the market trend rule for a consistent label. Show whether the stock beat its sector and whether its sector beat SPY. Mark short histories explicitly. |
| Risk and participation | 14-session average true range as a percentage of close, 20/60-session annualized realized volatility, drawdown, daily volume vs. the preceding 20-session mean | Express typical movement as a range and compare like volume feeds. Use completed sessions for daily relative volume. |
| Business health | Revenue growth year over year, operating margin and its year-over-year change, trailing four-quarter free cash flow, leverage and interest coverage where applicable | Show reported period and filing date. Describe concrete changes such as “revenue grew while margins contracted.” Define free cash flow as operating cash flow less capital expenditure. |
| Valuation and event risk | Trailing P/E when earnings are positive, free-cash-flow yield, next earnings date and confirmation status | Show sector peer median and peer count where comparable. Treat negative earnings as “loss-making.” Use sector-appropriate measures for banks and REITs, or mark the measure inapplicable. Allow an unknown earnings date. |

Compose the stock summary from the strongest observable comparisons. For example, *“The stock beat its sector over 20 sessions. Revenue grew year over year, operating margin fell, and earnings are due next week.”* Every clause should open its chart, table or filing. Keep price-derived indicators in one family so that several transformations of the same close cannot outweigh declining cash flow. ETFs get fund and benchmark comparisons in place of issuer financials.

## 3. Data acquisition and the archive

The research identifies candidate feeds and flags untested endpoints. Before relying on a provider, record what the intended account can retrieve and keep, the actual delay, field completeness, adjustment policy, pagination, request budget, and fallback. A provider's documentation and an observed sample answer different parts of that question.

| Dataset | Acquisition plan | Failure or coverage decision |
| --- | --- | --- |
| Prices, volume, corporate actions | Test Alpaca historical daily bars for SPY, QQQ, sector ETFs, watchlist and breadth universe. Batch symbols. Compare a split, dividend and closing volume against a second permitted source. | Store feed identity. Alpaca Basic's real-time equities cover IEX. Use a consistent price/volume basis for each comparison and label partial-market data. Evaluate another permitted end-of-day feed or a local import for gaps. [Alpaca market data coverage](https://docs.alpaca.markets/us/docs/about-market-data-api) |
| Constituents, sectors and peers | Evaluate a dated S&P constituent list and its usage terms. Store effective dates, sector, share class, additions, removals and symbol changes. A fallback is a permitted import of IVV's dated equity holdings, labeled “IVV holdings breadth,” with cash and derivatives removed. | Start each breadth series at its first verified membership date unless earlier dated membership can be acquired. Today's members can support today's breadth using historical prices. A multi-year breadth series also needs historical members. [S&P index information](https://www.spglobal.com/spdji/en/indices/equity/sp-500/) · [IVV fund holdings](https://www.ishares.com/us/products/239726/ishares-core-sp-500-etf) |
| Volatility, rates and credit | Retrieve VIX and VIX3M from FRED series VIXCLS and VXVCLS. Use Treasury rates for context and test BAMLH0A0HYM2 for high-yield spreads. | Respect series-specific retention and display terms. FRED lists three years of history for this spread. If unavailable, show HYG/IEF return ratio on its own scale as a credit proxy. [FRED high-yield spread notes](https://fred.stlouisfed.org/series/BAMLH0A0HYM2) |
| Filings and earnings | Use SEC EDGAR submissions and Company Facts keyed by CIK. Preserve filing accession, acceptance time, units, fiscal period and amendments. For earnings calendars and consensus, evaluate a permitted vendor against issuer announcements. | Check tag mappings against actual filings. Distinguish quarterly, year-to-date and annual values before building trailing sums. Mark estimated dates and retain the consensus available before each release. [SEC EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) |
| Options quotes, open interest and put/call | Test a documented options chain and contract reference feed. Join quotes, volume and dated open interest (OI) by contract. Verify expiry coverage beyond the provider default, pagination, underlying spot time and multiplier. Seek a permitted data product for market-wide equity and index put/call series. | Cboe expressly prohibits automated extraction of its delayed quote tables. Use a documented feed with the required rights. Label indicative quotes. If OI dates, contract coverage or retention rights are inadequate, release the affected panel later. [Cboe quote dashboard notice](https://www.cboe.com/data/quotes/spy/options) · [Alpaca option chain](https://docs.alpaca.markets/us/reference/optionchain) · [Contract reference](https://docs.alpaca.markets/us/reference/get-options-contracts) |
| Positioning, headlines and revisions | Later, evaluate FINRA short interest, daily short-sale volume and weekly alternative trading system (ATS) volume. Snapshot analyst estimates by publication date. Pilot Alpaca News on the sector sample and check feed-specific rights and coverage. | Keep short interest, daily off-exchange short-sale volume and delayed venue activity separately labeled. ATS volume has no trade side. Suppress days-to-cover or short-interest-to-float if a reliable denominator is missing. [FINRA data catalog](https://developer.finra.org/catalog) · [FINRA guide to short interest](https://syndication.finra.org/content/short-interest-what-it-what-it-not) · [Alpaca historical news](https://docs.alpaca.markets/us/docs/historical-news-data) |

**Collection schedule**

| When | What to capture | How to handle timing |
| --- | --- | --- |
| Before the market opens, initially 8:30 a.m. ET | Watchlist OI and its effective session, latest filings and known events | Retry after the provider's release window if necessary. Compute OI change only between matching contracts with consecutive effective sessions. Repeated effective dates mean “pending update.” |
| After the market closes, initially close plus 30 minutes | Completed bars, benchmark and sector data, chain quotes and underlying spot, available volatility and credit observations | Follow the exchange holiday and early-close calendar. Match spot and chain times. Preserve the latest valid pre-expiry snapshot if the feed provides one. A chain collected after expiry may have already lost that day's contracts. |
| On publication and during reconciliation | Late closes, macro releases, filings, FINRA releases, index changes and estimate revisions | Recheck overdue datasets. Snapshot the universe at least weekly and apply known changes on their effective session. Archive daily consensus if daily revision timing is a requirement. |

Backfill permitted daily prices first. Request at least two years when available to warm up 200-session averages and support year-over-year comparisons. Build option-chain, implied-volatility, OI, and analyst histories forward where historical vintages are unavailable. Track observed, published, and collected times separately. Mark a missed historical snapshot as a gap. A later quote belongs to its actual observation time.

## 4. How to build and operate it

Use one local Python application with a scheduled collector and a read-only dashboard. Streamlit with Plotly is a practical starting point for linked charts, symbol selection and tables. Store permitted raw responses compressed by source and session, normalized observations in date-partitioned Parquet, and use DuckDB to query them. Start scheduling with Windows Task Scheduler. Revisit hosting only if the local machine regularly misses collection windows or remote access becomes a requirement.

| Responsibility | What it owns | Acceptance condition |
| --- | --- | --- |
| Source adapters | Provider-specific field names, units, credentials, rate limits, pagination and retry policy | Each adapter produces the same documented observation fields for its dataset. Changing a bar provider leaves the trend calculation intact. |
| Storage and identity | Security ID, ticker aliases, CIK, dated sector membership, corporate actions, contract terms, raw snapshots, run log and revisions | Rerunning a session introduces no duplicates. Corrections retain their original and revised values. A renamed ticker keeps its history. |
| Analytics | Aligned calendars, indicator definitions, units, sample counts, coverage, freshness rules and versioned wording rules | Given the same inputs, cutoff and formula version, the same numbers and labels can be reproduced offline. |
| Daily publication and UI | Publish one completed dataset version with a manifest of source dates and missing inputs. The UI reads that version throughout a visit. | A failed or overlapping collection leaves the prior published version usable. A missing source affects only dependent measures. |

For price charts and option levels, use the contemporaneous quoted price scale. For trend and volatility history use a consistent split-adjusted series and label it. For relative returns use a common dividend-adjusted basis for stock and ETFs. Keep the raw close and adjustment factors so a split cannot create a false crash or shift a historical option strike. Resolve the historical view as of the selected cutoff, including the filing or membership information available then. Label reconstructed history separately when the original publication vintage is unknown.

Track last successful run, expected next release, oldest overdue input, eligible/expected symbols, rejected contracts and request usage. Mark a source stale against its own publication calendar. Back off on rate limits, retry recoverable failures and keep validation failures for inspection. Keep credentials outside the repository and the UI. Back up permitted snapshots and the manifest, restore a sample session, and use measured bytes per ticker-day to budget storage before expanding the watchlist.

## 5. Options and other research extensions

Promote an extension when its data and interpretation checks pass. The core dashboard can reach daily use before these milestones.

| Extension | Planned output | Release condition |
| --- | --- | --- |
| Implied volatility (IV) and expected move | Show at-the-money IV by expiry, 30-day constant-maturity IV from expiries bracketing 30 days, and 25-delta call IV less 25-delta put IV. For a selected expiry show the at-the-money call mid plus put mid (straddle cost) and the estimated one-standard-deviation move separately. The latter is spot × annualized IV × √(calendar days to expiry / 365), with IV expressed as a decimal. | Reject stale, crossed, zero-bid or excessively wide quotes using a documented, tested spread limit. Display retained contract counts and quote times. If bracketing expiries or matching strikes are missing, withhold the affected estimate. Compare earnings-implied moves with realized moves only after the event window ends. |
| IV history and positioning | Show today's IV against its own history. IV rank measures position between the trailing minimum and maximum. IV percentile measures the share of observations below today's level. Show separate put/call ratios for volume and OI, and separate equity and index series at market level. | Show observation counts. Below 60 valid sessions show collection progress, from 60–251 show a provisional observed-window measure, and use the full-year label only with 252 valid sessions in the stated window. Flat ranges and zero denominators yield an unavailable value. |
| Estimated dealer gamma exposure (GEX) | Show gross call and put exposure, modeled net dollars per 1% spot move, and absolute net divided by gross. Use gamma × OI × contract multiplier × spot squared × 0.01 with an explicit assumed positive-call, negative-put dealer convention. Show VIX and stock IV alongside. | Require dated OI, aligned spot, valid IV, verified contract terms, and quote-quality coverage. Exclude unsupported adjusted deliverables. Flag low net-to-gross or conflicting expiry buckets. Describe possible damping or amplification and make the assumed dealer position visible. |
| Gamma profile and levels | Reprice contract gamma across hypothetical spot levels with IV fixed by strike. Plot net exposure against spot, identify all zero crossings and mark the nearest. Show largest call concentrations above spot and put concentrations below, with separate OI and gamma measures. | Show “no crossing in range” when appropriate. Use contract-specific settlement times, rates and dividend assumptions. Break out 0, 1–7, 8–45 and over 45 calendar days to expiry. For 0-day coverage require a timed pre-expiry capture. Display expiry concentration and the overnight OI date. |
| Sector rotation, market internals and technical detail | Add a relative-strength versus relative-momentum quadrant with weekly trails and disclosed smoothing. Add an advance/decline line and new highs/lows from dated members. Offer swing levels, relative volume and optional volume-at-price drilldowns. | Verify the breadth denominator, pivot confirmation dates, and both ratio windows. Label the rotation chart as the project's approximation. For volume profiles or volume-weighted average price, identify the intraday venue coverage and bar-based approximation. |
| Financial and event detail | Add eight earnings surprises, 30/90-day estimate revisions, five-year valuation context where available, Form 4 open-market purchases/sales, and the lagged FINRA series. | Match fiscal periods and as-published estimates. Separate open-market trades from exercises, gifts and withholding. Expose filing or release lag and the age and size of the peer set. |

Keep secondary price oscillators available for later evaluation when a specific user question justifies them. Treat overlapping price indicators as one evidence family. Candlestick pattern scores, social mention counts, theoretical dealer flows and max-pain levels have lower priority than better coverage of the core measures. A manual level export or watchlist import can serve a later TradingView or brokerage workflow without making an external account a launch dependency.

## 6. Dashboard design and usability

- Keep the market date, coverage and selected benchmark visible during drilldown. Preserve the sector, ticker and time window when navigating back. Opening a watchlist item should take the reader directly to the same stock detail available from the sector table.
- Give the main chart most of the width. Place the explanation and its underlying values beside it on desktop and immediately below on a narrow screen. Align return series on a common base, put breadth and volatility in aligned panels with their own units, and use zero-centered bars for relative performance.
- Use tabular numerals, directly labeled series, aligned decimal places and explicit units for percent, percentage points and basis points. Combine color with signed values, line styles and text. Support keyboard selection, visible focus, a table equivalent for every chart, and text access to values otherwise shown on hover.
- Use concrete data states such as “187 of 200 sessions available,” “OI update pending” and “last successful close, Thursday.” Let the reader inspect the source, formula, observation time, coverage and reason for an unavailable reading from the panel itself.

The local visualization and frontend guides inform chart choice and accessibility. The architecture guide's relevant principle is to keep provider-specific complexity behind a testable interface. [Visualization guide](../Skills/data-visualization.md) · [Frontend design guide](../Skills/frontend-design.md) · [Architecture guide](../Skills/code-base-architecture.md)

## 7. Delivery sequence

**The first usable dashboard ships at the end of Phase 4.** Start Phase 2 collection for each feed as soon as it passes Phase 1. Phase 5 features can ship independently as their data becomes available. The estimates below assume one developer and accessible data. Historical observation windows accumulate on the market calendar.

### Phase 1. Set the scope and verify data access · 2–4 working days

- [x] Select the starting watchlist, benchmark, membership source, budget, and machine for scheduled collection. Define each core measure's unit, time window, cutoff and handling of missing data.
- [ ] Sample SPY, two sector ETFs, a profitable issuer, a loss-making issuer and a recent listing. Check source rights, delay, price adjustments, field completeness, historical depth and request volume. Check whether tomorrow's OI can be tied to a specific session.
- [x] Sketch the three screens using the sample. Walk through a rising index with weak breadth and a rising stock with declining margins. Confirm that the reader can see both facts.

[Phase 1 feasibility record](phase-1-feasibility.md), [test and audit log](../CompletionLog/phase-1.md), and [local preview instructions](../README.md).

**Done when** every core measure has a sampled source or a tested fallback, and each optional feed has a recorded collection decision.

### Phase 2. Start the archive and prove one complete session · 3–5 working days

- [ ] Set up the local data store, stable security identifiers, exchange calendar and source timestamps. Schedule the pre-open and post-close captures in section 3, including additional publication checks for late feeds.
- [ ] Backfill available bars, import dated membership and capture one issuer's filings. Start retaining permitted option chains and estimate snapshots immediately. Record the first usable date for each history.
- [ ] Follow one session from stored inputs through a market breadth value, sector comparison and stock reading. Save reference values. Interrupt and retry a capture, then replay the session offline.

[Phase 2 implementation and replay evidence](../CompletionLog/phase-2.md).

**Done when** both scheduled windows appear in the run log, a retry leaves one published result, and a replay matches the reference values.

### Phase 3. Build the market and sector views · 4–7 working days

- [ ] Expand validated daily prices to the breadth universe and all 11 sector ETFs. Calculate market trend, breadth, volatility and credit using section 2. Display the eligible member count and the date for each source.
- [x] Rank the sectors, show absolute and relative returns, and connect each sector to its member table. Preserve the selected date and window during navigation.
- [x] Independently recalculate one sector rank and one breadth fraction. Inspect a session when the index rose on narrow participation, a sector that led while falling, and a missing membership file.

The market and sector calculations, source dates, and coverage passed the offline acceptance checks. The first item stays open for the verified live universe and stress exports. [Phase 3 implementation and acceptance results](../CompletionLog/phase-3.md)

**Done when** the overview and sector detail explain those cases using the underlying values and identify which breadth or proxy series the reader is seeing.

### Phase 4. Build stock health, test the workflow and launch locally · 5–8 working days

- [x] Connect the watchlist and sector members to stock detail. Add the benchmark comparisons, risk measures, filing-based financials, valuation and earnings status in section 2.
- [x] Reconcile two companies' figures to their filings. Exercise negative earnings, a short trading history, an unknown sector and an amended filing. Check the displayed dates as well as the numbers.
- [ ] Run all five acceptance scenarios in section 8. Check keyboard access, narrow-screen charts, cached load time, an offline optional feed and backup recovery.
- [ ] Install the dashboard and scheduler on the intended machine. After a restart, verify the next capture and open its published session. Record how to start the dashboard, edit the watchlist, inspect a failed run and restore the last good snapshot.

The stock workflow passed offline acceptance. The dashboard runs locally. Browser accessibility and narrow-screen checks, Task Scheduler registration, and a live capture after a machine restart remain open. [Phase 4 implementation and acceptance results](../CompletionLog/phase-4.md)

**Done when** a reader can go from market to sector to stock on one date, trace a claim to its evidence, and reopen the published result after a restart.

### Phase 5. Release deeper analysis as its evidence becomes available

| Track | What needs to be done | Ready to release when |
| --- | --- | --- |
| Headline sentiment | Verify usage rights, map and deduplicate stories, calculate issuer and sector tone, and expose sample counts. | A hand-checked sample reproduces the displayed result, and sparse coverage has an explicit state. |
| Options and positioning | Start with chain quality and expected moves. Add OI changes from consecutive dated captures, volatility history as it matures, then estimated gamma, expiry splits, walls and flips. | Each panel passes its own data and calculation checks in section 5. A chain with no zero crossing and a newly watched stock both display intelligible results. |
| Market and stock detail | Add sector rotation and market internals from dated constituents, financial and ownership history from dated releases, and intraday measures where suitable bars exist. Use section 9 to choose the next indicator. | Independently reproduce one example per added measure and confirm it was available on the historical date shown. |

### Phase 6. Operate the dashboard and decide when to expand · ongoing

- [ ] Review missed captures, stale sources, coverage by sector, storage growth and request usage. Recover available dates and record unrecoverable gaps.
- [ ] Restore an archived session on a clean local setup and reproduce its figures. Repeat the applicable acceptance scenarios after a provider, formula or schema change.
- [ ] Evaluate a broader universe, industry groups, intraday feeds, remote access or exports against a specific user question. Estimate incremental cost and coverage, then pilot the change on a small sample.

**Operating check** — a selected session can be restored and explained, and each proposed expansion has a named use case, data source, cost estimate and success condition.

## 8. Acceptance and handoff

| Scenario | Evidence required before calling the first release ready |
| --- | --- |
| “The index rose. Was it a broad move?” | From the overview, identify trend, eligible-member count, percentage above each average and the change in participation. Reproduce the published numerator and denominator from the dated member list. |
| “Which sectors are leading, and how many stocks are participating?” | Rank all covered sectors on the same date, open one with positive relative performance and inspect absolute performance, breadth and individual member returns. A sector with inadequate coverage keeps its performance history and explains the missing participation label. |
| “Is this company keeping up with its peers, and is the business strengthening?” | Open a ticker, compare both relative-return series, inspect the latest reported margin and cash flow, and reach the source filing. A negative-earnings company, an unmapped stock, and a recent listing each receive an intelligible result. |
| “What did the dashboard know that evening?” | Replay a date before an amended filing, reclassification or later OI update. The earlier view uses only inputs available at its cutoff. A forward-known restatement, a later headline or a newly confirmed swing cannot leak into it. |
| “Can I trust this after a failure?” | Exercise a split, dividend, holiday, half-day, failed source, duplicate run and missing snapshot. Verify last-good dates, affected panels and a backup restore. As pilot targets, cached overview and stock detail should each open within two seconds on the target machine, and five consecutive scheduled sessions should each produce a traceable run outcome. |

For later modules, maintain small hand-worked examples for volatility, straddle versus standard-deviation move, IV rank versus percentile, sector headline aggregation, and GEX with zero, one and multiple crossings. Validate descriptive labels across rising, falling and mixed historical periods. Any future claim of predictive value needs a separately defined target, time-ordered out-of-sample evaluation and comparison against simple baselines such as VIX and at-the-money IV.

## 9. Where each research indicator fits

The identifiers below follow the original indicator catalog. A phase number identifies the earliest planned use. “Optional” means there is a specific question or data dependency to resolve before scheduling the work. [Research indicator catalog](../StockResearch/Stock2.txt)

| Research family | Planned delivery | Optional or excluded items |
| --- | --- | --- |
| Options and dealer positioning (A1–A20) | Phase 2 begins collection. Phase 5 covers net and per-strike gamma, flips and walls (A1–A5), put/call ratios (A10), IV and expected moves (A12–A17), and expiry concentration, OI changes and quote quality (A18–A20). Run the A20 quality checks from the first capture. | Delta, vanna and charm exposures (A6–A8), max pain (A9) and unusual activity (A11) are optional drilldowns. For unusual activity, show volume and subsequent OI separately and leave trade direction unspecified. |
| Price and technicals (B1–B22) | Phase 4 covers moving averages, typical range, realized volatility, relative volume and distance from yearly extremes (B1, B8, B10, B15, B21). Phase 5 adds IV comparisons, trend strength, bandwidth and confirmed swing levels (B10, B6, B9, B19). VWAP and volume profile (B13–B14) depend on suitable intraday data. | Crosses, RSI, MACD, stochastic, rate of change, beta, on-balance volume, accumulation/distribution, Chaikin money flow, up/down volume and gaps (B2–B5, B7, B11–B12, B16–B18, B20) are optional for deeper price analysis. Exclude candlestick pattern scoring (B22) per the research. |
| Market and sectors (C1–C13) | Phase 3 covers index trend, sector leadership, breadth, volatility and credit (C1–C2, C4, C8–C9, C12). Phase 4 completes stock-relative comparisons (C2). Phase 5 adds rotation, advance/decline history, market put/call and rates/dollar context (C3, C5, C10, C13). | McClellan oscillator and Zweig breadth events (C6–C7) require reliable member history. Use the fear-and-greed components (C11) as individually inspectable measures. |
| Fundamentals and ownership (D1–D12) | Phase 4 covers growth, margins, cash flow, leverage, basic valuation and the next earnings date (D1–D3, D5–D6, D8). Phase 5 deepens these histories and adds revisions, earnings surprises, short interest and insider transactions (D7–D10). | Returns on equity and invested capital (D4), quarterly 13F holdings (D11), and dividends/buybacks (D12) are candidates after accounting definitions, reporting lag and split-adjusted share counts are validated. |
| Flow and sentiment (E1–E7) | Phase 5 covers short interest, ATS share, off-exchange short volume and headline tone (E1, E3–E4, E6). Only compute each share when its numerator and denominator cover the stated market and dates. | ETF flows (E2) need dated shares outstanding and NAV. Social mentions (E5) need reliable permitted access and a defensible sample. Borrow fees (E7) need a dated source and an explicit broker-coverage label. |


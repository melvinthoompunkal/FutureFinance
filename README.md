# FutureFinance

A private, end-of-day U.S. market dashboard. It opens the latest published archive session when one is available. The bundled synthetic preview includes SPY and QQQ trend, 50- and 200-session breadth, volatility and credit, all 11 sector ETFs, and stock drilldowns with risk, business health and valuation. Phase 5 adds market internals, sector rotation, headlines, options and deeper issuer research.

## Start on Windows

With Python 3.12, run from the project folder.

```powershell
python -m pip install -r requirements.txt
python -m streamlit run app.py --server.port 8501
```

Open [FutureFinance](http://127.0.0.1:8501). The server listens on the loopback interface. Edit [watchlist.txt](watchlist.txt) to change the stock picker.

On **Market**, the August 8, 2025 sample shows SPY up 0.84% with only 38 of 100 members above their 50-session average. To see a sector outperform during a decline, pick August 1, 2025 and open **Financials (XLF)** from the market view. The selected session and chart window stay in place as you navigate. Expand **Session sources and coverage** to inspect dates and available inputs.

On August 8, open **Technology (XLK)** and select **AAPL**, or choose AAPL directly in **Stock**. The synthetic example shows a rising close and lower operating margin. Choose **RIVN** to see loss-making trailing earnings or **CRCL** to see how the dashboard handles a recent listing and an unknown sector. Expand **Dividend-adjusted index chart data** to see the plotted returns as a table.

For Phase 5, open **Sector rotation** and **Seven-day headline tone** under Sector. Under AAPL Stock, open **Options, implied moves and positioning** to compare the straddle with the IV-based move and inspect the chain and dated open interest. CRCL shows the state for a symbol with no chain history.

## Try a local price export

Create a `data` folder and add these files from an export whose terms permit your use. Dates must be completed trading sessions in New York.

- `source.json` identifies the provider and feed, for example `{"prices": "Broker export, consolidated daily bars"}`.
- `bars.csv` has header `session,symbol,close,split_close,total_return_close,volume`. Use ISO dates, quoted USD closes, split-adjusted closes, dividend- and split-adjusted closes, and share volume. Leave unavailable fields blank and use a row with blank price fields to mark a known session with missing bars.
- Optional `bars.csv` columns `split_high,split_low,market_cap,split_volume` add split-adjusted intraday highs and lows, same-session company market capitalization in USD, and share volume adjusted to a common split basis. The dashboard can use quoted share volume when the price adjustments show a consistent share basis throughout the comparison.
- Optional `membership.csv` has header `session,symbol,sector_etf`. Add a `membership` string to `source.json` such as `"IVV holdings breadth"`. Keep only the intended equity share classes, use one row per symbol per verified session, and leave unknown sector ETFs blank.
- Optional `stock_sectors.csv` uses the same header for dated stock-sector mappings outside the breadth universe. A dated sector from `membership.csv` takes precedence. Include a row for each session you want to map. These rows provide the stock's comparison ETF and leave the breadth counts based on dated membership.
- Optional `stress.csv` has header `session,series,value,available_at`. Use NYSE observation dates and the series keys `VIX`, `VIX3M` and `OAS`. Enter volatility in quoted index points and the high-yield option-adjusted spread in percentage units (`3.50` means 350 bp). `available_at` is when that value became available, with an ISO 8601 offset or `Z`. For example, `2025-08-07,VIX,18.4,2025-08-08T10:00:00-04:00` is a sample row. Add a `stress_sources` object to `source.json` with a provider label for each series present, such as `{"VIX":"Permitted volatility export"}`. [Cboe volatility index horizons](https://www.cboe.com/tradable-products/vix/term-structure/) · [High-yield spread units](https://fred.stlouisfed.org/series/BAMLH0A0HYM2)

The preview requires at least one quoted SPY close and keeps missing NYSE sessions between supplied dates as gaps. It carries no membership forward. With missing membership, the market view can show RSP/SPY as a concentration proxy. With no published OAS, it can show dividend-adjusted HYG/IEF as a credit proxy.

Stress readings use the latest observations available by the selected NYSE close plus 30 minutes. Revisions use another row with the same observation date and a later `available_at`. VIX/VIX3M uses a common observation date. The spread change requires a reading exactly 20 NYSE sessions before the latest eligible spread. The VIX percentile uses available closes in the trailing 252 NYSE sessions through its observation date.

### Add issuer filings and earnings dates

Put the optional exports alongside `bars.csv` for local preview or in `data/inbox` for publication. The dashboard reads normalized local exports. The [SEC API probe](#check-data-access) checks data access and tag coverage separately.

- `filings.csv` requires `symbol,cik,accession,form,period,available_at,basis`. Use the ticker active when the report was published, the SEC CIK and accession, the form (`10-Q`, `10-K`, `10-Q/A` or `10-K/A`), fiscal period end, and the EDGAR acceptance timestamp with its offset. Use `operating`, `financial` or `reit` for `basis`. The source label defaults to `SEC EDGAR` and can be set through `filings` in `source.json`.
- Optional filing values are `revenue,prior_revenue,operating_income,prior_operating_income,ttm_cfo,ttm_capex,ttm_eps,gross_debt,ttm_ebitda,ttm_ebit,ttm_interest,eps_basis_session`. Use full USD amounts, except diluted EPS in USD per share and the basis session in `YYYY-MM-DD`. Enter comparable standalone current and prior-year quarters for revenue and operating income. Use four quarters for trailing amounts. For cumulative cash flow, the prior fiscal year plus current year-to-date less comparable prior year-to-date yields a four-quarter value. Enter capex and interest expense as positive costs. Leave unverified amounts blank.
- `eps_basis_session` is required with `ttm_eps`. Supply an exchange session whose quoted share basis matches all four EPS inputs, including quoted and split-adjusted closes for that day. Retain those bars when replacing the export. The dashboard uses both closes to put EPS on the selected session’s quoted share basis if a split intervenes.
- Keep original filing rows when adding an amendment. Add a new row for the same fiscal period with the amendment's accession, acceptance time, and the full known snapshot after the amendment. The latest reported fiscal period takes precedence. If an amendment to an older period changes the latest trailing figures, include a revised snapshot for the affected latest period with the amendment's accession and availability time. [Hand-checked sample](tests/fixtures/phase4-filings.csv) · [SEC filing and Company Facts documentation](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)
- `earnings.csv` uses `symbol,event_date,status,available_at,source_url`. Supply the next date known as of each announcement or estimate, with `confirmed` or `estimated`. Confirmed dates require an HTTPS source URL. Use `unknown` and a blank event date to withdraw an earlier schedule. Set an `earnings` label in `source.json` to identify the feed. Keep dated rows when the announced date changes.

The selected NYSE close plus 30 minutes controls which filings and earnings announcements appear. Business measures with incomplete inputs stay unavailable, and sector valuations use comparable dated members with the same reporting basis and one share class per eligible issuer. The stock page links to each filing or announcement when available. An invalid optional filing or earnings export is recorded in the session source metadata while prices remain usable.

## Archive and replay a session

Put a complete export in `data/inbox` using the files above. Include the price history for each session you want to publish. Two years is the initial backfill target. The archive uses the NYSE calendar to preserve missing sessions and requires a quoted SPY close for the selected date. Membership applies only to its supplied dates.

```powershell
python -m future_finance.collect capture --session 2026-11-20
python -m future_finance.collect runs
python -m future_finance.collect replay --session 2026-11-20
```

The archives under `data/archive` contain the compressed source files, month-partitioned Parquet, and a SQLite catalog of capture attempts and immutable publications. DuckDB reads the Parquet for replay. Use `replay --version <run-id>` to read a specific published version, including an earlier revision. An unchanged export records another run without publishing another version. Reopen the dashboard to pick up new publications during an existing visit.

- Optional `prices_published_at` and `membership_published_at` values in `source.json` record known source publication times. Use ISO 8601 timestamps with offsets. Imported history is labeled reconstructed.
- Optional `security_aliases.csv` has header `symbol,security_id,start,end`. Dates are ISO calendar dates. Start is inclusive, end is exclusive, and a blank end is open-ended. Give both ticker ranges the same ID for a rename and distinct IDs when a ticker is reused. Undeclared tickers use a ticker-derived ID.
- Keep a whole bundle together when updating the inbox. A capture reads the supplied history as a bundle for that publication, so include the warmup history in each replacement.

### Add Phase 5 research exports

Put any of the following optional CSVs beside the bars. Use `data/inbox` for capture or `data` for a local preview. Add a corresponding entry under `research_sources` in `source.json` with a provider and coverage label and `"permitted": true` after verifying storage and display rights. For example, `"research_sources": {"options": {"label": "Provider, indicative options feed", "permitted": true}}`. An unconfigured or invalid export affects its own panel. Include ISO dates, explicit UTC or local offsets on timestamps, and blank cells for unavailable optional values.

| File | Required columns | Optional columns and input definitions |
| --- | --- | --- |
| `options.csv` | `symbol,observed_at,contract,available_at,spot_at,spot,expiry,settlement_at,side,strike,deliverable,multiplier,quote_at,bid,ask` | `iv,delta,volume,oi,oi_session,rate,dividend_yield`. Provide decimal annualized IV, rate and dividend yield, signed delta, per-share USD quotes, and contract counts. Use `call` or `put`, and `standard`, `adjusted` or `unknown` deliverables. Keep the same underlying spot and times within a snapshot. Quote fields can be blank for a pre-open OI export and settlement or multiplier can be blank when unverified. OI needs its paired earlier effective session. |
| `headlines.csv` | `symbol,story_id,source,available_at,issuer_id,published_at,title` | Use a stable issuer ID across share classes and a stable story ID across syndicated copies. Provide `headline_dictionary.csv` with `term,tone` and one `positive` or `negative` word per row. The headlines source entry also needs a `dictionary_label` identifying its version. |
| `market_context.csv` | `session,series,available_at` | Supply `value` for `DGS10` in percent, `T10Y2Y` in percentage points or `DTWEXBGS` in index points. Supply matched `puts,calls` for `equity_volume`, `index_volume`, `equity_oi` or `index_oi`. |
| `estimates.csv` | `symbol,period,kind,available_at,eps` | `target,analysts,released_at`. Use `consensus` or `actual`, the fiscal period end and USD EPS on the same per-share and accounting basis. Use `released_at` on actuals if the release predates the vendor timestamp, otherwise `available_at` must be the first release time. |
| `insiders.csv` | `symbol,transaction_id,available_at,accession,cik,session,code,venue,shares,price` | Use the SEC acceptance time, transaction date, stable transaction ID across amendments, and USD price or a blank price. Use `open_market`, `private`, `other` or `unknown` after checking filing notes. SEC codes P and S also cover private transactions. [SEC Form 4 instructions](https://www.sec.gov/files/form4.pdf) |
| `positioning.csv` | `symbol,session,metric,available_at,start,numerator,scope` | `denominator,denominator_scope,denominator_source`. Use end and start dates for the measured window and identify the numerator's market or facilities in `scope`. Use `short_float` with same-date `float`, `days_to_cover` with `consolidated_daily_average`, `ats_share` with same-week `consolidated_weekly`, and `off_exchange_short_share` with volume from the `same_facilities_daily`. [FINRA catalog](https://developer.finra.org/catalog) |
| `intraday.csv` | `symbol,start_at,available_at,end_at,high,low,close,volume` | Use contiguous bars from the regular session, quoted USD bars and reported share volume. Identify the venue coverage in the source label. |

Archive captures keep prior options and estimate observations under the same permitted source label. Include cumulative history in the other exports when earlier readings are needed. The application filters observations at the selected session's close-plus-30-minute cutoff. A snapshot that first becomes available later remains absent from that evening's replay. Keep pre-expiry chains timestamped before actual contract settlement for 0-day analysis. The one-standard-deviation move uses calendar days and remaining fractional days for same-day expirations.

Use a documented endpoint and verify pagination, quote delays, contract terms and effective OI dates on the intended account before relying on live chains. Confirm terms for both the headline feed and dictionary before importing. [Alpaca option chain](https://docs.alpaca.markets/us/reference/optionchain) · [OCC open interest](https://www.theocc.com/market-data/market-data-reports/volume-and-open-interest/open-interest) · [Loughran–McDonald dictionary terms](https://sraf.nd.edu/loughranmcdonald-master-dictionary/)

```powershell
python -m future_finance.collect replay --version <run-id> --research --sector XLK --stock AAPL
```

### Windows capture schedule

Preview registration with `./scripts/Register-ArchiveTask.ps1 -WhatIf`. Run the script without `-WhatIf` to register it once the permitted exports are ready. Use `-Python` with the full path to the interpreter that has the project requirements installed. The task uses the current Windows user and needs that user to be signed in.

The task checks for an 8:30 a.m. pre-open window, a window 30 minutes after the NYSE close, and a 6:30 p.m. late check, all in New York time. It logs an attempt only in a due window. The post-close and late windows ingest the local bundle, including issuer exports. The pre-open window preserves permitted options snapshots with dated OI and records a waiting status when the export is missing. An abrupt stop can leave a run marked `started` in the log. Use `runs` to inspect the failed run and its `detail`, correct the source export, and use a manual `capture` to retry. After signing back in following a restart, check `runs` after the next due window, then use `replay` to verify its session and open that session in the dashboard.

### Back up and recover a session

With captures paused and idle, copy the entire `data/archive` directory to a dated backup. Keep `catalog.sqlite3`, `raw`, and `normalized` together. Verify the copy with `python -m future_finance.collect --archive <backup-path> replay --version <run-id>` using a good version from `runs`.

To recover, close the dashboard, keep captures paused, rename the current archive aside, and copy the verified backup to `data/archive`. Reopen the dashboard and confirm the expected date and version. Re-enable scheduled capture after verification.

See the [Phase 2 completion log](CompletionLog/phase-2.md) for archive verification, [Phase 3](CompletionLog/phase-3.md) for market and sector acceptance, [Phase 4](CompletionLog/phase-4.md) for local launch status, and [Phase 5](CompletionLog/phase-5.md) for research validation and live release checks.

## Check data access

Set `APCA_API_KEY_ID` and `APCA_API_SECRET_KEY` in your environment for Alpaca. For SEC API checks, set `SEC_USER_AGENT` to the application name and your contact email. Run with a completed New York trading date.

```powershell
python -m future_finance.probe --session 2026-11-20
python -m future_finance.probe --session 2026-11-20 --options
python -m unittest discover -s tests -v
```

`--options` samples the chain and OI available when the command runs. It defaults to Alpaca paper-account credentials. Add `--live-keys` for live-account credentials. The probe prints request counts, field coverage, and adjustment or OI date evidence as JSON.

See the [Phase 1 feasibility record](Plans/phase-1-feasibility.md) for verified sources, pending checks, and calculation definitions.

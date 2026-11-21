# FutureFinance

A private, end-of-day U.S. market dashboard. It opens the latest published archive session when one is available. The bundled preview uses a synthetic session with a rising SPY, weak breadth, sector rankings, and stock drilldowns.

## Start on Windows

With Python 3.12, run from the project folder.

```powershell
python -m pip install -r requirements.txt
python -m streamlit run app.py --server.port 8501
```

Open [FutureFinance](http://127.0.0.1:8501). The server listens on the loopback interface. Edit [watchlist.txt](watchlist.txt) to change the stock picker.

Select **Sector**, open **AAPL**, and compare the daily gain with the year-over-year margin decline. **RIVN** illustrates negative earnings. **CRCL** illustrates short history and an unavailable sector comparison. The selected session and chart window stay in place as you navigate.

## Try a local price export

Create a `data` folder and add these files from an export whose terms permit your use. Dates must be completed trading sessions in New York.

- `source.json` identifies the provider and feed, for example `{"prices": "Broker export, consolidated daily bars"}`.
- `bars.csv` has header `session,symbol,close,split_close,total_return_close,volume`. Use ISO dates, quoted USD closes, split-adjusted closes, dividend- and split-adjusted closes, and share volume. Leave unavailable fields blank and use a row with blank price fields to mark a known session with missing bars.
- Optional `membership.csv` has header `session,symbol,sector_etf`. Add a `membership` string to `source.json` such as `"IVV holdings breadth"`. Keep only the intended equity share classes, use one row per symbol per verified session, and leave unknown sector ETFs blank.

The preview uses price-file session rows as its calendar and requires at least one quoted SPY close. Supply a row for every expected session to preserve trading-session windows during outages. The import does not carry a membership list across sessions. A local import displays its own prices and membership with missing financial and volatility data clearly marked.

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

### Windows capture schedule

Preview registration with `./scripts/Register-ArchiveTask.ps1 -WhatIf`. Run the script without `-WhatIf` to register it once the permitted exports are ready. Use `-Python` with the full path to the interpreter that has the project requirements installed. The task uses the current Windows user and needs that user to be signed in.

The task checks for an 8:30 a.m. pre-open window, a window 30 minutes after the NYSE close, and a 6:30 p.m. late check, all in New York time. It logs an attempt only in a due window. The post-close and late windows ingest local price and membership exports. The pre-open window records that it is waiting for a verified source. An abrupt stop can leave a run marked `started` in the log. Use a manual `capture` to retry and `runs` to inspect the outcome.

See the [Phase 2 completion log](CompletionLog/phase-2.md) for the offline walkthrough and live collection work still open.

## Check data access

Set `APCA_API_KEY_ID` and `APCA_API_SECRET_KEY` in your environment for Alpaca. For SEC API checks, set `SEC_USER_AGENT` to the application name and your contact email. Run with a completed New York trading date.

```powershell
python -m future_finance.probe --session 2026-11-20
python -m future_finance.probe --session 2026-11-20 --options
python -m unittest discover -s tests -v
```

`--options` samples the chain and OI available when the command runs. It defaults to Alpaca paper-account credentials. Add `--live-keys` for live-account credentials. The probe prints request counts, field coverage, and adjustment or OI date evidence as JSON.

See the [Phase 1 feasibility record](Plans/phase-1-feasibility.md) for verified sources, pending checks, and calculation definitions.

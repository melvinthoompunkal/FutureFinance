# Phase 2 progress log

**Started November 21, 2026.** The local archive and offline replay are working. Live collection and Task Scheduler registration are pending.

## Delivered

- Added a collector for permitted local price and dated membership exports. It stores source files as gzip, writes monthly Parquet partitions, and records capture runs and immutable publications in SQLite. A manifest records per-source status, dates, first usable sessions, and the archive publication time. Replays read the normalized Parquet through DuckDB.
- Added dated ticker aliases for stable security IDs, exchange-session alignment, and explicit gaps for missing trading sessions. Imported history is marked reconstructed unless it is labeled synthetic.
- Added pre-open, post-close, and late capture windows and prepared the Windows registration script. The capture calendar accounts for NYSE holidays and early closes. The script was checked with `-WhatIf` and the 15-minute Windows trigger was constructed successfully. [NYSE trading hours and holidays](https://www.nyse.com/trade/hours-calendars)
- Connected the dashboard to archived sessions. A dashboard visit keeps its selected publication version while new or revised sessions are published.

## Offline reference

The synthetic August 8, 2025 session was tested with simulated New York window times. The pre-open attempt was logged as waiting. The post-close attempt was interrupted after staging, the late retry published archive version **3**, and a duplicate capture recorded `unchanged`. Exactly one publication was visible.

| Reading | Replay value |
| --- | ---: |
| SPY session change | +0.840044% |
| 50-session breadth | 38 of 100 eligible, 38.0% |
| Five-session change in 50-session breadth | −7.0 pp |
| 200-session breadth | 45 of 100 eligible, 45.0% |
| XLK absolute return over 20 sessions | +5.096125% |
| XLK relative return vs. SPY over 20 sessions | +4.573927% |
| AAPL session change | +1.298111% |
| AAPL relative return vs. SPY over 20 sessions | +11.012489% |

The synthetic price and membership histories both begin September 3, 2024. The first published synthetic session is August 8, 2025. The archive is under `data/phase2-replay/archive` on this workstation. Formula version 1 reuses the Phase 1 analytics.

```powershell
& ./.venv/Scripts/python.exe -m future_finance.collect --archive data/phase2-replay/archive runs
& ./.venv/Scripts/python.exe -m future_finance.collect --archive data/phase2-replay/archive replay --version 3
& ./.venv/Scripts/python.exe -m unittest discover -s tests -v
```

The test suite also recreates the archive in a temporary directory and replays after removing the input exports. All 15 tests passed, along with Ruff and Python compilation.

## Remaining

- Backfill a permitted real price export and verify an actual dated membership import. Record first usable real dates and complete the Phase 1 source checks.
- Collect the first issuer filing snapshot after the SEC contact and source check. Options, open interest, consensus estimates, and volatility remain pending their respective feed checks.
- Register the Windows task when inputs are ready and verify real pre-open, post-close, and late run outcomes. The present pre-open path logs that it is waiting for a verified source.

from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
import gzip
import json
from pathlib import Path
from shutil import copytree
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import pandas as pd
from streamlit.testing.v1 import AppTest

from future_finance.archive import Archive
from future_finance.collect import replay
from future_finance.demo import make_demo
from future_finance.market_calendar import capture_cutoff, scheduled_window
from future_finance.scope import NEW_YORK
from future_finance.stock import filings_as_of
from future_finance.stress import stress_history, vix_percentile

ROOT = Path(__file__).resolve().parents[1]
DAY = date(2025, 8, 8)
HEADER = "session,symbol,close,split_close,total_return_close,volume\n"


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(TemporaryDirectory()))
        self.inbox = self.root / "inbox"
        self.inbox.mkdir()
        self.archive = Archive(self.root / "data" / "archive")

    def _source(self, **metadata):
        (self.inbox / "source.json").write_text(
            json.dumps({"prices": "Synthetic bars", "synthetic": True, **metadata}),
            encoding="utf-8",
        )

    def _bars(self, rows):
        (self.inbox / "bars.csv").write_text(HEADER + rows, encoding="utf-8")

    def _capture(self, day=DAY, window="post-close", hour=16, minute=30, scheduled=False):
        stamp = datetime.combine(day, datetime.min.time(), NEW_YORK).replace(hour=hour, minute=minute)
        return self.archive.capture(self.inbox, day, window, now=stamp, scheduled=scheduled)

    def test_interrupt_retry_and_replay_stored_walkthrough(self):
        demo = make_demo()
        self._source(membership=demo.membership_source)
        demo.bars.to_csv(self.inbox / "bars.csv", index=False)
        demo.members.to_csv(self.inbox / "membership.csv", index=False)
        preopen = self._capture(window="pre-open", hour=8, scheduled=True)
        self.assertEqual(preopen["status"], "waiting")
        self.assertIsNone(self._capture(window="pre-open", hour=8, scheduled=True))

        with patch.object(self.archive, "_publish", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self._capture(scheduled=True)
        self.assertFalse(self.archive.published_sessions())
        publication = self._capture(window="late", hour=18)
        self.assertEqual(publication["status"], "published")
        self.assertEqual(self._capture()["status"], "unchanged")
        self.assertEqual(self.archive.published_sessions(), {DAY: publication["id"]})
        self.assertEqual([run["status"] for run in self.archive.runs()],
                         ["waiting", "interrupted", "published", "unchanged"])

        manifest = self.archive.publication(publication["id"])
        raw_bars = self.archive.root / manifest["raw"]["bars.csv"]
        self.assertEqual(gzip.decompress(raw_bars.read_bytes()), (self.inbox / "bars.csv").read_bytes())
        (self.inbox / "bars.csv").unlink()
        (self.inbox / "membership.csv").unlink()
        result = replay(self.archive, publication["id"])
        self.assertEqual(result["market"]["breadth"][50], {
            "above": 38, "eligible": 100, "expected": 100, "percent": 38.0, "label": "Narrow",
        })
        self.assertEqual(result["market"]["breadth_50_change_pp"], -7.0)
        self.assertAlmostEqual(result["market"]["spy_change_pct"], 0.84, places=2)
        self.assertAlmostEqual(result["stock"]["change_pct"], 1.30, places=2)
        prices = demo.prices("total_return_close")
        old, end = prices.iloc[-21], prices.iloc[-1]
        expected = (end.XLK * old.SPY / (old.XLK * end.SPY) - 1) * 100
        self.assertAlmostEqual(result["sector"]["vs_spy_20_pct"], expected, places=5)

    def test_gap_rename_revision_and_failed_replacement(self):
        self._source(prices_published_at="2025-08-08T20:25:00Z")
        rows = ("2025-08-06,SPY,100,100,100,1000\n"
                "2025-08-06,OLD,20,20,20,100\n"
                "2025-08-08,NEW,22,22,22,100\n"
                "2025-08-08,SPY,101,101,101,1000\n"
                "2025-08-11,SPY,102,102,102,1000\n")
        self._bars(rows)
        (self.inbox / "security_aliases.csv").write_text(
            "symbol,security_id,start,end\nOLD,asset-01,2025-08-01,2025-08-08\n"
            "NEW,asset-01,2025-08-08,\n", encoding="utf-8",
        )
        first = self._capture()["id"]
        inputs, manifest = self.archive.load(first)
        prices = inputs.prices("close")
        self.assertEqual(list(prices), ["NEW", "SPY"])
        self.assertEqual(prices.loc["2025-08-06", "NEW"], 20)
        self.assertTrue(pd.isna(prices.loc["2025-08-07", "SPY"]))
        self.assertEqual(prices.index[-1], pd.Timestamp(DAY))
        self.assertEqual(manifest["sources"]["prices"]["observed_at"], "2025-08-08T16:00:00-04:00")
        self.assertEqual(manifest["sources"]["prices"]["published_at"], "2025-08-08T16:25:00-04:00")

        self._bars(rows.replace("102,102,102", "103,103,103"))
        self.assertEqual(self._capture()["status"], "unchanged")
        self._bars(rows.replace("101,101,101", "103,103,103"))
        revised = self._capture()["id"]
        self.assertEqual(self.archive.published_sessions(), {DAY: revised})
        self.assertEqual(self.archive.load(first)[0].prices("close").SPY.iloc[-1], 101)
        self.assertEqual(self.archive.load(revised)[0].prices("close").SPY.iloc[-1], 103)
        self._bars(rows.replace("2025-08-08,SPY", "2025-08-09,SPY"))
        self.assertEqual(self._capture()["status"], "failed")
        self.assertEqual(self.archive.published_sessions(), {DAY: revised})

    def test_stress_replay_uses_release_cutoff_and_matching_observation_dates(self):
        sources = {"VIX": "Example daily volatility", "VIX3M": "Example term data", "OAS": "Example spread"}
        self._source(stress_sources=sources)
        self._bars("2025-08-08,SPY,101,101,101,1000\n")
        stress_file = self.inbox / "stress.csv"
        stress_file.write_text(
            "session,series,value,available_at\n"
            "2025-07-11,OAS,3.50,2025-07-14T10:00:00-04:00\n"
            "2025-08-06,VIX,18,2025-08-06T16:20:00-04:00\n"
            "2025-08-06,VIX3M,20,2025-08-06T16:20:00-04:00\n"
            "2025-08-07,VIX,24,2025-08-08T10:00:00-04:00\n"
            "2025-08-07,VIX3M,21,2025-08-08T18:05:00-04:00\n"
            "2025-08-08,VIX,26,2025-08-08T19:00:00-04:00\n"
            "2025-08-08,OAS,4.25,2025-08-08T16:25:00-04:00\n"
            "2025-08-06,VIX,30,2025-08-08T18:10:00-04:00\n",
            encoding="utf-8",
        )
        capture = self._capture(window="late", hour=18, minute=30)
        self.assertEqual(capture["status"], "published", capture["detail"])
        stress_file.unlink()
        inputs, manifest = self.archive.load(capture["id"])
        self.assertEqual(inputs.stress_sources, sources)
        self.assertNotIn(26, inputs.stress["value"].tolist())
        self.assertEqual(manifest["sources"]["stress"]["VIX3M"]["observed_session"], "2025-08-06")
        day = pd.Timestamp(DAY)
        values = stress_history(inputs.stress, day)
        self.assertEqual(values["VIX"].dropna().tolist(), [18, 24])
        self.assertEqual(values["VIX / VIX3M"].dropna().to_dict(), {pd.Timestamp("2025-08-06"): 0.9})
        self.assertEqual(values.at[day, "High-yield spread"], 425)
        self.assertEqual(values.at[day, "Spread change"], 75)
        self.assertEqual(vix_percentile(values["VIX"], pd.Timestamp("2025-08-07")), (75.0, 2))

        app_path = self.root / "app.py"
        app_path.write_bytes((ROOT / "app.py").read_bytes())
        (self.root / "watchlist.txt").write_text("AAPL\n", encoding="utf-8")
        app = AppTest.from_file(str(app_path)).run()
        self.assertFalse(app.exception)
        metrics = {metric.label: metric.value for metric in app.metric}
        self.assertEqual(metrics["VIX close"], "24.00")
        self.assertEqual(metrics["VIX / VIX3M"], "0.90:gray[×]")
        self.assertEqual(metrics["High-yield spread"], "425 :gray[bp]")
        self.assertTrue(any("widening" in item.value and "+75.00 bp" in item.value for item in app.caption))

    def test_concurrent_retries_leave_one_publication(self):
        self._source()
        self._bars("2025-08-08,SPY,101,101,101,1000\n")
        with ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(self._capture)
            second = executor.submit(self._capture)
            statuses = {first.result()["status"], second.result()["status"]}
        self.assertIn("published", statuses)
        self.assertTrue(statuses & {"unchanged", "superseded"})
        self.assertEqual(len(self.archive.published_sessions()), 1)
        with self.assertRaisesRegex(ValueError, "does not exist"):
            duplicate_id = next(run["id"] for run in self.archive.runs() if run["status"] != "published")
            self.archive.publication(duplicate_id)

    def test_filing_reconciliation_revision_and_backup_replay(self):
        self._source(filings="SEC EDGAR (hand-checked)")
        self._bars("2025-07-31,SPY,99,99,99,1000\n2025-07-31,AAPL,100,100,100,1000\n"
                   "2025-08-01,SPY,100,100,100,1000\n2025-08-01,AAPL,103,103,103,1000\n"
                   "2025-08-05,SPY,100,100,100,1000\n2025-08-05,RIVN,16,16,16,1000\n"
                   "2025-08-08,SPY,101,101,101,1000\n2025-08-08,AAPL,101,101,101,1000\n"
                   "2025-08-08,RIVN,15,15,15,1000\n")
        original = (ROOT / "tests/fixtures/phase4-filings.csv").read_text(encoding="utf-8")
        export = self.inbox / "filings.csv"
        export.write_text(original, encoding="utf-8")
        (self.inbox / "earnings.csv").write_text(
            "symbol,event_date,status,available_at,source_url\n"
            "AAPL,2025-10-30,estimated,2025-08-08T15:00:00-04:00,\n", encoding="utf-8",
        )
        (self.inbox / "stock_sectors.csv").write_text(
            "session,symbol,sector_etf\n2025-08-08,RIVN,XLY\n", encoding="utf-8",
        )
        before = self._capture(day=date(2025, 8, 5), window="late", hour=19)
        self.assertEqual(before["status"], "published", before["detail"])
        self.assertIsNone(replay(self.archive, before["id"], stock="RIVN")["stock"]["filing"])
        first = self._capture()
        self.assertEqual(first["status"], "published", first["detail"])
        apple_stock = replay(self.archive, first["id"])["stock"]
        apple = apple_stock["filing"]
        self.assertEqual(apple_stock["next_earnings"]["date"], "2025-10-30")
        self.assertEqual(apple["available_at"], "2025-08-01T06:00:42-04:00")
        self.assertAlmostEqual(apple["revenue_yoy_pct"], (94036 / 85777 - 1) * 100, places=5)
        self.assertAlmostEqual(apple["operating_margin_pct"], 28202 / 94036 * 100, places=5)
        self.assertEqual(apple["trailing_fcf_usd"], (118254 + 81754 - 91443 - (9447 + 9473 - 6539)) * 1e6)
        self.assertAlmostEqual(apple["trailing_pe"], 101 / (0.97 + 2.40 + 1.65 + 1.57), places=5)
        self.assertIn("0000320193-25-000073-index.htm", apple["url"])
        rivian_stock = replay(self.archive, first["id"], stock="RIVN")["stock"]
        self.assertEqual(rivian_stock["sector_etf"], "XLY")
        rivian = rivian_stock["filing"]
        self.assertEqual(rivian["available_at"], "2025-08-05T17:00:52-04:00")
        self.assertAlmostEqual(rivian["operating_margin_pct"], -1114 / 1303 * 100, places=5)
        self.assertEqual(rivian["trailing_fcf_usd"], (-1716 - 124 + 2023 - (1141 + 800 - 537)) * 1e6)
        self.assertIsNone(rivian["gross_debt_ebitda"])
        self.assertTrue(rivian["loss_making"])
        self.assertIsNone(rivian["trailing_pe"])

        app_path = self.root / "app.py"
        app_path.write_bytes((ROOT / "app.py").read_bytes())
        (self.root / "watchlist.txt").write_text("AAPL\n", encoding="utf-8")
        app = AppTest.from_file(str(app_path)).run()
        app.radio(key="view").set_value("Stock").run()
        self.assertFalse(app.exception)
        self.assertIn(":gray[$]96.18:gray[B]", [metric.value for metric in app.metric])
        self.assertTrue(any("Jun 28, 2025" in note.value and "06:00:42 AM ET" in note.value for note in app.caption))
        self.assertEqual(app.get("link_button")[0].proto.url, apple["url"])

        # A controlled amendment is available before the Aug 8 cutoff, but after the earlier session.
        amendment = original.splitlines()[1].replace("000073,10-Q", "999999,10-Q/A").replace(
            "2025-08-01T06:00:42", "2025-08-08T16:25:00").replace("28202000000", "27000000000")
        export.write_text(original + amendment + "\n", encoding="utf-8")
        amended = self._capture()
        self.assertEqual(amended["status"], "published", amended["detail"])
        revised = replay(self.archive, amended["id"])["stock"]["filing"]
        self.assertEqual(revised["form"], "10-Q/A")
        self.assertEqual(revised["period"], apple["period"])
        self.assertAlmostEqual(revised["operating_margin_pct"], 27000 / 94036 * 100, places=5)
        restored = Archive(Path(copytree(self.archive.root, self.root / "restored")))
        export.unlink()
        self.assertEqual(replay(restored, amended["id"]), replay(self.archive, amended["id"]))
        self.assertEqual(replay(restored, first["id"])["stock"]["filing"], apple)
        historic, _ = restored.load(amended["id"])
        report = filings_as_of(historic.filings, pd.Timestamp("2025-08-05")).loc["AAPL"]
        self.assertEqual(report.form, "10-Q")

    def test_bad_optional_filing_does_not_block_price_publication(self):
        self._source()
        self._bars("2025-08-08,SPY,101,101,101,1000\n")
        (self.inbox / "filings.csv").write_text("broken,export\n1,2\n", encoding="utf-8")
        run = self._capture()
        self.assertEqual(run["status"], "published", run["detail"])
        inputs, manifest = self.archive.load(run["id"])
        self.assertEqual(manifest["sources"]["filings"]["status"], "invalid export")
        self.assertTrue(inputs.filings.empty)
        self.assertEqual(inputs.prices("close").iloc[-1].SPY, 101)

    def test_dashboard_uses_published_version_and_existing_visit_stays_pinned(self):
        self._source()
        self._bars("2025-08-08,SPY,101,101,101,1000\n")
        version = self._capture()["id"]
        app_path = self.root / "app.py"
        app_path.write_bytes((ROOT / "app.py").read_bytes())
        (self.root / "watchlist.txt").write_text("AAPL\n", encoding="utf-8")
        app = AppTest.from_file(str(app_path)).run()
        self.assertFalse(app.exception)
        self.assertTrue(any(f"Version {version} · Synthetic" in message.value for message in app.info))
        self._bars("2025-08-08,SPY,103,103,103,1000\n")
        revised = self._capture()["id"]
        app.run()
        self.assertTrue(any(f"Version {version} · Synthetic" in message.value for message in app.info))
        new_visit = AppTest.from_file(str(app_path)).run()
        self.assertTrue(any(f"Version {revised} · Synthetic" in message.value for message in new_visit.info))

    def test_nyse_holiday_early_close_and_dst(self):
        half_day = date(2026, 11, 27)
        self.assertEqual(capture_cutoff(half_day).isoformat(), "2026-11-27T13:30:00-05:00")
        self.assertIsNone(scheduled_window(datetime(2026, 11, 26, 16, 30, tzinfo=NEW_YORK)))
        self.assertIsNone(scheduled_window(datetime(2026, 11, 27, 13, 29, tzinfo=NEW_YORK)))
        self.assertEqual(scheduled_window(capture_cutoff(half_day)), "post-close")
        self.assertEqual(scheduled_window(datetime(2026, 11, 27, 18, 30, tzinfo=NEW_YORK)), "late")
        self.assertEqual(scheduled_window(datetime(2026, 7, 1, 8, 30, tzinfo=NEW_YORK)), "pre-open")
        self.assertEqual(capture_cutoff(date(2026, 7, 1)).isoformat(), "2026-07-01T16:30:00-04:00")

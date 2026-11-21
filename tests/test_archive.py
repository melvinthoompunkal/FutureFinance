from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
import gzip
import json
from pathlib import Path
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

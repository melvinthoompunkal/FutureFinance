from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import pandas as pd
from streamlit.testing.v1 import AppTest

from future_finance.analytics import change
from future_finance.inputs import import_bundle

ROOT = Path(__file__).resolve().parents[1]
BAR_HEADER = "session,symbol,close,split_close,total_return_close,volume\n"


class PreviewTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(TemporaryDirectory()))
        self.data = self.root / "data"
        self.data.mkdir()

    def _app(self):
        app = self.root / "app.py"
        app.write_text((ROOT / "app.py").read_text(encoding="utf-8"), encoding="utf-8")
        (self.root / "watchlist.txt").write_text("AAPL\nRIVN\nCRCL\n", encoding="utf-8")
        preview = AppTest.from_file(str(app)).run()
        self.assertFalse(preview.exception)
        return preview

    def _bars(self, rows):
        (self.data / "source.json").write_text(
            '{"prices":"Controlled test bars","membership":"Test members"}', encoding="utf-8"
        )
        (self.data / "bars.csv").write_text(BAR_HEADER + rows, encoding="utf-8")

    def test_drilldown_preserves_context_and_shows_filing_cutoff(self):
        app = self._app()
        self.assertIn("38% · Narrow", [metric.value for metric in app.metric])
        app.selectbox[1].set_value(120).run()
        app.radio(key="view").set_value("Sector").run()
        self.assertEqual(app.title[0].value, "Sector leadership")
        self.assertTrue(any("pp in 5 sessions" in item.value for item in app.caption))
        app.selectbox(key="member_XLK").select("AAPL").run()
        app.button[0].click().run()
        self.assertEqual(app.title[0].value, "AAPL stock detail")
        self.assertEqual(app.selectbox[0].value, pd.Timestamp("2025-08-08"))
        self.assertEqual(app.selectbox[1].value, 120)
        self.assertIn("+1.30%", [metric.value for metric in app.metric])
        self.assertTrue(any("operating margin was lower" in item.value for item in app.markdown))
        self.assertEqual(next(metric.delta for metric in app.metric if metric.label == "Operating margin"),
                         "-2.00 pp YoY")

        app.selectbox(key="stock_choice_selector").select("RIVN").run()
        self.assertIn("Loss-making", [metric.value for metric in app.metric])
        app.selectbox[0].set_value(pd.Timestamp("2025-08-05")).run()
        self.assertTrue(any("selected cutoff" in item.value for item in app.info))
        app.selectbox(key="stock_choice_selector").select("CRCL").run()
        self.assertTrue(any("of 200 split-adjusted closes" in item.value for item in app.caption))
        self.assertTrue(any("Sector mapping is unavailable" in item.value for item in app.caption))
        self.assertFalse(app.exception)

    def test_zero_earnings_leave_pe_unavailable(self):
        app = AppTest.from_string("""
from future_finance.demo import make_demo
from future_finance.views import Session, stock

inputs = make_demo()
inputs.filings.loc[inputs.filings["symbol"].eq("AAPL"), "ttm_eps"] = 0.0
split = inputs.prices("split_close")
stock(Session(inputs, split, inputs.prices("total_return_close"), inputs.prices("close"),
              split.index[-60:]), "AAPL")
""").run()
        self.assertEqual(next(metric.value for metric in app.metric if metric.label == "Trailing P/E"),
                         "Unavailable")
        self.assertFalse(app.exception)

    def test_csv_preserves_adjustment_basis_and_dated_missing_data(self):
        self._bars("2025-12-04,SPY,100,100,100,1000\n"
                   "2025-12-05,SPY,50,100,100,2000\n"
                   "2025-12-08,SPY,,,,\n"
                   "2025-12-04,NA,10,10,10,0\n")
        (self.data / "membership.csv").write_text(
            "session,symbol,sector_etf\n2025-12-04,NA,XLK\n", encoding="utf-8"
        )
        inputs = import_bundle(self.data)
        split = inputs.prices("split_close")
        self.assertIn("NA", split)
        self.assertEqual(len(split.index), 3)
        self.assertEqual(inputs.prices("close")["SPY"].iloc[1], 50)
        self.assertEqual(change(split["SPY"], 1).iloc[1], 0)
        self.assertTrue(pd.isna(change(split["SPY"], 1).iloc[2]))
        self.assertEqual(inputs.members_on(split.index[0])["symbol"].tolist(), ["NA"])
        self.assertTrue(inputs.members_on(split.index[-1]).empty)

    def test_csv_rejects_extra_fields_and_duplicate_keys(self):
        valid = "2025-12-04,SPY,100,100,100,1000\n"
        for rows, message in [("extra," + valid, "more fields"), (valid * 2, "duplicate session")]:
            with self.subTest(message=message):
                self._bars(rows)
                with self.assertRaisesRegex(ValueError, message):
                    import_bundle(self.data)

    def test_import_labels_missing_series_and_shows_concentration_proxy(self):
        self._bars("2025-12-04,SPY,100,100,100,1000\n"
                   "2025-12-05,SPY,101,101,101,1200\n"
                   "2025-12-04,RSP,60,60,60,300\n"
                   "2025-12-05,RSP,61,61,61,330\n"
                   "2025-12-05,AAPL,75,75,,100\n")
        app = self._app()
        self.assertIn("Membership unavailable", [metric.value for metric in app.metric])
        self.assertTrue(any("QQQ" in note.value and "No dividend-adjusted" in note.value for note in app.caption))
        self.assertTrue(any("Concentration proxy index" in item.label for item in app.expander))
        app.radio(key="view").set_value("Stock").run()
        self.assertTrue(any("AAPL" in note.value and "No dividend-adjusted" in note.value for note in app.caption))
        self.assertFalse(app.exception)

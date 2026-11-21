from datetime import date
from unittest import TestCase
from unittest.mock import patch

from future_finance.probe import Client, ProbeError, bars_sample


class ProbeTests(TestCase):
    def test_bar_sample_follows_pages_and_reports_missing_symbol(self):
        client = Client({})
        bar = {"t": "2025-12-05T05:00:00Z", "o": 49, "h": 51, "l": 48, "c": 50, "v": 2000}
        payloads = iter([
            {"bars": {"SPY": [bar]}, "next_page_token": "second"},
            {"bars": {"XLK": [bar]}},
        ])

        def get_page(endpoint, **params):
            client.requests += 1
            return next(payloads)

        with patch.object(client, "get", side_effect=get_page) as get:
            report = bars_sample(client, date(2025, 12, 4), date(2025, 12, 5), "raw")
        self.assertEqual(get.call_args.kwargs["page_token"], "second")
        self.assertEqual(report["requests"], 2)
        self.assertEqual(report["symbols"]["SPY"]["adjustment_checkpoints"]["2025-12-05"]["close"], 50)
        self.assertTrue(report["symbols"]["XLK"]["requested_session_present"])
        self.assertFalse(report["symbols"]["CRCL"]["requested_session_present"])

    def test_pages_reject_repeated_token(self):
        client = Client({})
        with patch.object(client, "get", return_value={"next_page_token": "repeated"}):
            with self.assertRaisesRegex(ProbeError, "usable next-page token"):
                list(client.pages("https://test.invalid"))

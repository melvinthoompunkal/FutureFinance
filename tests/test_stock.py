import unittest

import numpy as np
import pandas as pd

from future_finance.analytics import change, relative
from future_finance.inputs import BAR_FIELDS, MEMBER_FIELDS, Inputs, parse_bundle
from future_finance.stock import next_earnings, price_risk, valuation


class StockTests(unittest.TestCase):
    def test_split_safe_risk_and_valuation(self):
        dates = pd.bdate_range(end="2025-08-08", periods=252)
        close = pd.Series(50.0, index=dates)
        close.iloc[0] = 54
        quoted = close.copy()
        quoted.iloc[:-1] *= 2
        volume = np.full(len(dates), 100)
        volume[-1] = 200
        bars = pd.DataFrame({
            "session": dates, "symbol": "AAPL", "close": quoted.to_numpy(), "split_close": close.to_numpy(),
            "total_return_close": close.to_numpy(), "volume": volume, "split_high": close.to_numpy() + 1,
            "split_low": close.to_numpy() - 1, "market_cap": 5000,
        }).reindex(columns=BAR_FIELDS)
        inputs = Inputs(bars, pd.DataFrame(columns=MEMBER_FIELDS), "Test bars", "")
        dates_in_chart = dates[-60:]
        risk = price_risk(inputs, "AAPL", close, dates_in_chart)
        self.assertEqual(risk["ATR (14), % of close"], 4)
        self.assertEqual(risk["Realized volatility (60)"], 0)
        self.assertAlmostEqual(risk["Distance from 52-week high"], (50 / 55 - 1) * 100)
        self.assertTrue(pd.isna(risk["Relative volume (20)"]))
        bars["split_volume"] = 200
        self.assertEqual(price_risk(inputs, "AAPL", close, dates_in_chart)["Relative volume (20)"], 1)

        filing = pd.Series({"basis": "operating", "ttm_eps": 4, "eps_basis_session": dates[-2],
                            "ttm_cfo": 250, "ttm_capex": 150})
        value = valuation(filing, inputs.bars_for("AAPL"), dates[-1])
        self.assertEqual(value.pe, 25)
        self.assertEqual(value.fcf_yield, 2)

        dividend_example = pd.DataFrame({"AAPL": [49, 50], "SPY": [100, 100]}, index=dates[-2:])
        self.assertAlmostEqual(change(relative(dividend_example, "AAPL"), 1).iloc[-1], (50 / 49 - 1) * 100)
        bars.loc[bars.index[-5], "split_high"] = np.nan
        self.assertTrue(pd.isna(price_risk(inputs, "AAPL", close, dates_in_chart)["ATR (14), % of close"]))

    def test_earnings_history_uses_early_close_cutoff_and_keeps_unknown(self):
        inputs = parse_bundle({
            "source.json": b'{"prices":"Test bars", "earnings":"Test announcements"}',
            "bars.csv": b"session,symbol,close,split_close,total_return_close,volume\n2026-11-27,SPY,101,101,101,1000\n",
            "earnings.csv": b"symbol,event_date,status,available_at,source_url\n"
                            b"AAPL,2026-12-15,estimated,2026-11-25T15:00:00-05:00,\n"
                            b"AAPL,2026-12-16,confirmed,2026-11-27T13:45:00-05:00,https://example.com/earnings\n"
                            b"AAPL,,unknown,2026-12-01T12:00:00-05:00,\n",
        })
        first = next_earnings(inputs.earnings, "AAPL", pd.Timestamp("2026-11-27"))
        self.assertEqual((first.event_date, first.status), (pd.Timestamp("2026-12-15"), "estimated"))
        confirmed = next_earnings(inputs.earnings, "AAPL", pd.Timestamp("2026-11-30"))
        self.assertEqual((confirmed.event_date, confirmed.status), (pd.Timestamp("2026-12-16"), "confirmed"))
        self.assertIsNone(next_earnings(inputs.earnings, "AAPL", pd.Timestamp("2026-12-01")))

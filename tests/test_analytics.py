from dataclasses import replace
import unittest

import pandas as pd

from future_finance.analytics import breadth_history, change, sector_ranking, trend, moving_average_gaps
from future_finance.demo import make_demo


class PhaseOneScenarios(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs = make_demo()
        cls.split = cls.inputs.prices("split_close")
        cls.total = cls.inputs.prices("total_return_close")

    def test_rising_benchmark_with_weak_breadth(self):
        dates = self.split.index[-6:]
        readings = breadth_history(self.inputs, self.split, dates)[50]
        latest = readings[dates[-1]]
        self.assertEqual((latest.above, latest.eligible, latest.expected), (38, 100, 100))
        self.assertEqual(latest.label, "Narrow")
        self.assertEqual(latest.percent - readings[dates[0]].percent, -7)
        self.assertAlmostEqual(change(self.split["SPY"], 1).iloc[-1], 0.84, places=2)
        self.assertEqual(trend(moving_average_gaps(self.split["SPY"])), "Uptrend")

    def test_partial_coverage_and_missing_membership(self):
        day = self.split.index[-1:]
        absent = self.inputs.members_on(day[0])["symbol"].head(11)
        prices = self.split.drop(columns=absent)
        latest = breadth_history(self.inputs, prices, day)[200][day[0]]
        self.assertEqual((latest.eligible, latest.expected), (89, 100))
        self.assertEqual(latest.label, "Insufficient coverage")

        missing = self.inputs.members_on(day[0]).iloc[:0]
        no_members = replace(self.inputs, members=missing)
        self.assertEqual(breadth_history(no_members, prices, day)[50][day[0]].label, "Membership unavailable")

    def test_sector_rank_uses_ratio_and_recent_listing_stays_incomplete(self):
        sector = sector_ranking(self.total)
        self.assertEqual(sector.index[0], "XLK")
        start, end = self.total.iloc[[-21, -1]].itertuples(index=False, name=None)
        xlk, spy = (self.total.columns.get_loc(ticker) for ticker in ("XLK", "SPY"))
        expected = ((end[xlk] / end[spy]) / (start[xlk] / start[spy]) - 1) * 100
        self.assertAlmostEqual(sector.loc["XLK", "20 sessions"], expected)
        gaps = moving_average_gaps(self.split["CRCL"])
        self.assertTrue(pd.isna(gaps[200]))
        self.assertEqual(trend(gaps), "Incomplete history")

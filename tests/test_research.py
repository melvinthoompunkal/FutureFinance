from datetime import date, datetime
from math import exp, pi, sqrt
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

import numpy as np
import pandas as pd
from streamlit.testing.v1 import AppTest

from future_finance import issuer_research, market_research, options, technical
from future_finance.archive import Archive
from future_finance.collect import replay
from future_finance.demo import make_demo
from future_finance.market_calendar import capture_cutoff, exchange, sessions_between
from future_finance.research_inputs import EXPORTS, parse_research
from future_finance.scope import NEW_YORK

DAY = pd.Timestamp("2025-08-08")


def option_pair(day, *, preopen=False, oi=100):
    close = exchange().session_close(day)
    observed = exchange().session_open(day) - pd.Timedelta(hours=1) if preopen else close
    expiry = "2026-08-08"
    return [
        dict(symbol="AAPL", observed_at=observed.isoformat(), available_at=observed.isoformat(),
             contract=side, spot_at=observed.isoformat(), spot=100, expiry=expiry,
             settlement_at=f"{expiry}T16:00:00-04:00", side=side, strike=100, deliverable="standard",
             multiplier=100, quote_at=observed.isoformat(), bid=3, ask=3.4, iv=.2,
             delta=.25 if side == "call" else -.25, volume=12,
             oi=oi if side == "call" else oi / 2, oi_session=exchange().previous_session(day).date().isoformat(),
             rate=0, dividend_yield=0)
        for side in ("call", "put")
    ]


def csv_bytes(name, rows):
    return pd.DataFrame(rows, columns=EXPORTS[name].columns).to_csv(index=False).encode()


def config(*names):
    return {"research_sources": {name: {"label": f"Fixture {name}", "permitted": True} for name in names}}


class ResearchTests(unittest.TestCase):
    def test_chain_quality_straddle_variance_skew_and_gamma(self):
        rows = option_pair(DAY)
        for label, changes in (
            ("wide", {"ask": 7}), ("zero", {"bid": 0}), ("crossed", {"bid": 4}),
            ("adjusted", {"deliverable": "adjusted"}), ("stale", {"quote_at": "2025-08-08T14:00:00-04:00"}),
        ):
            rows.append({**rows[0], "contract": label, "strike": 110 + len(rows), **changes})
        research = parse_research({"options.csv": csv_bytes("options", rows)}, config("options"))
        history = options.visible_history(research, "AAPL", DAY)
        checked = options.assess_quotes(options.latest_chain(history, DAY), DAY)
        self.assertEqual(checked["quality"].value_counts()["Retained"], 2)
        self.assertEqual(checked["quality"].nunique(), 6)
        term = options.term_structure(checked, DAY)
        self.assertAlmostEqual(term.at[0, "Straddle ($)"], 6.40)
        self.assertAlmostEqual(term.at[0, "One standard deviation ($)"], 20)
        self.assertEqual(term.at[0, "25-delta risk reversal (pp)"], 0)
        self.assertTrue(np.isnan(options.iv_at_30(term)))
        iv_term = pd.DataFrame({"Days": [20, 40], "ATM IV (%)": [20, 30], "Retained contracts": [2, 2]})
        self.assertAlmostEqual(options.iv_at_30(iv_term), sqrt(2.2 / 30) * 100)
        interest, effective = options.open_interest(history, DAY)
        self.assertEqual(effective, pd.Timestamp("2025-08-07"))
        self.assertTrue(interest["change"].isna().all())
        self.assertTrue(options.gamma_profile(checked, interest, DAY).by_strike.empty)
        retained = checked.loc[checked["quality"].eq("Retained")]
        gamma = options.gamma_profile(retained, interest, DAY)
        phi = exp(-.1 ** 2 / 2) / sqrt(2 * pi)
        self.assertAlmostEqual(gamma.by_strike["exposure"].sum(), (phi / (100 * .2)) * 50 * 100 * 100,
                               places=6)
        self.assertEqual(gamma.crossings, [])

    def test_iv_history_counts_ties_and_crossings(self):
        sample = pd.Series([10] + [15] * 57 + [40, 20])
        count, rank, percentile = options.iv_reading(sample)
        self.assertEqual(count, 60)
        self.assertAlmostEqual(rank, 33.3333333333)
        self.assertAlmostEqual(percentile, 58 / 60 * 100)
        self.assertTrue(np.isnan(options.iv_reading(sample.tail(59))[1]))
        self.assertTrue(np.isnan(options.iv_reading(pd.Series([10] * 252))[1]))
        spots = np.array([80, 90, 100, 110, 120])
        self.assertEqual(options.zero_crossings(spots, np.array([1, 0, -1, 0, 1])), [90, 110])
        self.assertEqual(options.zero_crossings(spots, np.array([1, 1, 1, -1, -1])), [105])
        self.assertEqual(options.zero_crossings(spots, np.array([1, 1, 0, 1, 1])), [])

    def test_historical_option_versions_keep_the_pre_expiry_snapshot(self):
        initial = option_pair(DAY)
        pre = "2025-08-08T15:55:00-04:00"
        same_day = {**initial[0], "contract": "same-day", "observed_at": pre,
                    "available_at": pre, "quote_at": pre, "spot_at": pre,
                    "expiry": "2025-08-08", "settlement_at": "2025-08-08T16:00:00-04:00"}
        research = parse_research({"options.csv": csv_bytes("options", [same_day, *initial])}, config("options"))
        history = options.visible_history(research, "AAPL", DAY)
        self.assertNotIn("same-day", options.latest_chain(history, DAY)["contract"].tolist())
        self.assertEqual(options.pre_expiry_chain(history, DAY)["contract"].tolist(), ["same-day"])

    def test_headline_deduplication_and_equal_issuer_weight(self):
        inputs = make_demo()
        research = inputs.research
        headlines = research.tables["headlines"]
        aapl = headlines.loc[headlines["symbol"].eq("AAPL")].iloc[0]
        duplicate = aapl.copy()
        duplicate["source"] = "Syndicated wire"
        rewritten = duplicate.copy()
        rewritten["story_id"] = "unmatched-wire-id"
        rewritten["title"] = aapl.title.upper() + "!"
        future = duplicate.copy()
        future["story_id"] = "after cutoff"
        future["available_at"] = pd.Timestamp("2025-08-08T16:31:00-04:00")
        future["title"] = "Strong earnings"
        research.tables["headlines"] = pd.concat([headlines, pd.DataFrame([duplicate, rewritten, future])],
                                                ignore_index=True)
        tone, details = market_research.headline_tone(research, inputs.members_on(DAY), DAY)
        self.assertEqual(tone.at["XLK", "scored"], 10)
        self.assertAlmostEqual(tone.at["XLK", "Tone"], (0.5 + 1 - 1) / 3)
        self.assertEqual(tone.at["XLY", "Coverage"], "Limited news coverage")
        self.assertNotIn("after cutoff", details["story_id"].tolist())

    def test_market_internals_and_rotation_use_the_selected_day(self):
        dates = sessions_between(date(2024, 6, 3), DAY.date())
        prices = pd.DataFrame({"A": np.arange(len(dates)) + 100, "B": 100.0,
                               "SPY": 100.0, "XLK": (np.arange(len(dates)) ** 2 + 100)}, index=dates)
        members = pd.DataFrame({"session": [dates[1], dates[3], dates[3], DAY, DAY],
                                "symbol": ["A", "A", "B", "A", "B"]})
        activity = market_research.internals(members, prices, dates[:4].append(dates[-1:]))
        self.assertEqual(activity.loc[dates[1], "Advance/decline line"], 1)
        self.assertTrue(pd.isna(activity.loc[dates[2], "Advance/decline line"]))
        self.assertEqual(activity.loc[dates[3], "Advance/decline line"], 1)
        self.assertEqual(activity.loc[DAY, ["New highs", "New lows", "Eligible yearly extremes"]].tolist(), [1, 0, 2])
        rotation = market_research.rotation(prices, DAY)
        ratio = prices["XLK"] / prices["SPY"]
        expected = (100 * ratio / ratio.rolling(20).mean()).rolling(5).mean()
        self.assertAlmostEqual(rotation.iloc[-1]["Relative strength"], expected.iloc[-1])
        self.assertAlmostEqual(rotation.iloc[-1]["Relative momentum"], 100 * expected.iloc[-1] / expected.tail(10).mean())
        self.assertEqual(rotation.iloc[-1]["Session"], DAY)

    def test_estimates_form4_and_positioning_use_matching_vintages(self):
        inputs = make_demo()
        cutoff = capture_cutoff(DAY.date())
        known = inputs.research.known("estimates", cutoff, "AAPL")
        surprises = issuer_research.earnings_surprises(known)
        self.assertAlmostEqual(surprises.at[0, "Surprise (%)"], (1.48 / 1.40 - 1) * 100)
        revisions = issuer_research.estimate_revisions(known, cutoff)
        self.assertAlmostEqual(revisions.at[0, "EPS change ($)"], .03)
        self.assertAlmostEqual(revisions.at[1, "EPS change ($)"], .06)
        positioning = issuer_research.positioning(inputs.research.known("positioning", cutoff, "AAPL"))
        self.assertEqual(positioning.set_index("metric").at["off_exchange_short_share", "Value"], 37.5)
        self.assertEqual(positioning.set_index("metric").at["days_to_cover", "Value"], 2)
        insiders = [
            dict(symbol="AAPL", accession="0000320193-25-000093", transaction_id=str(i), cik="320193",
                 session="2025-08-05", available_at="2025-08-07T12:00:00-04:00", code=code,
                 venue=venue, shares=5, price=2)
            for i, (code, venue) in enumerate([("P", "open_market"), ("S", "private"), ("M", "open_market")])
        ]
        research = parse_research({"insiders.csv": csv_bytes("insiders", insiders)}, config("insiders"))
        trades = issuer_research.insider_trades(research.known("insiders", cutoff))
        self.assertEqual(trades["Side"].tolist(), ["Purchase"])
        self.assertEqual(trades["Value ($)"].tolist(), [10])
        history = options.visible_history(inputs.research, "AAPL", DAY)
        close = inputs.prices("split_close")["AAPL"]
        releases = issuer_research.earning_releases(known)
        self.assertTrue(options.event_moves(history, releases, close.loc[:"2025-07-31"]).empty)
        self.assertEqual(options.event_moves(history, releases, close).iloc[0]["Post-release close"],
                         pd.Timestamp("2025-08-01"))

    def test_price_pivots_and_intraday_require_complete_windows(self):
        intervals = exchange()
        opening, closing = intervals.session_open(DAY), intervals.session_close(DAY)
        middle = opening + (closing - opening) / 2
        bars = pd.DataFrame({"start_at": [opening, middle], "end_at": [middle, closing],
                             "available_at": [middle, closing], "high": [101, 102], "low": [99, 100],
                             "close": [100, 101], "volume": [1, 3]})
        used, profile = technical.intraday_profile(bars, DAY)
        self.assertEqual(used["VWAP proxy"].iloc[-1], 100.75)
        self.assertEqual(profile.loc[profile["70% value area"], "Shares"].sum(), 3)
        self.assertTrue(technical.intraday_profile(bars.tail(1), DAY)[1].empty)
        prices = pd.Series([1, 2, 3, 10, 4, 3, 2], index=pd.date_range("2025-08-01", periods=7))
        pivots = pd.DataFrame({"split_high": prices, "split_low": prices})
        self.assertTrue(technical.swings(pivots.iloc[:-1]).empty)
        self.assertEqual(technical.swings(pivots).iloc[0]["Confirmed session"], prices.index[-1])
        up = pd.Series(range(100, 141), dtype=float)
        measures = technical.technical(pd.DataFrame({"split_high": up + 1, "split_low": up - 1, "split_close": up}))
        self.assertEqual(measures["ADX (14)"].iloc[-1], 100)
        self.assertAlmostEqual(measures["Bandwidth (%)"].iloc[-1], 400 * sqrt((20 ** 2 - 1) / 12) / 130.5)

    def test_archive_retains_permitted_observations_and_blocks_future_data(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            inbox = root / "inbox"
            inbox.mkdir()
            archive = Archive(root / "archive")
            source = {"prices": "Fixture", **config("options", "estimates")}
            (inbox / "source.json").write_text(json.dumps(source), encoding="utf-8")
            (inbox / "bars.csv").write_text("session,symbol,close,split_close,total_return_close,volume\n"
                                           "2025-08-07,SPY,100,100,100,10\n2025-08-08,SPY,101,101,101,10\n",
                                           encoding="utf-8")
            prior = pd.Timestamp("2025-08-07")
            path = inbox / "options.csv"
            path.write_bytes(csv_bytes("options", option_pair(prior, oi=90)))
            stamp = datetime(2025, 8, 7, 17, tzinfo=NEW_YORK)
            first = archive.capture(inbox, prior.date(), "post-close", now=stamp)
            self.assertEqual(first["status"], "published", first)
            path.write_bytes(csv_bytes("options", option_pair(DAY, preopen=True)))
            preopen = archive.capture(inbox, DAY.date(), "pre-open", now=datetime(2025, 8, 8, 8, 30, tzinfo=NEW_YORK))
            self.assertEqual(preopen["status"], "captured", preopen)
            path.unlink()
            (inbox / "estimates.csv").write_bytes(csv_bytes("estimates", [
                {"symbol": "AAPL", "period": "2025-06-28", "kind": "actual", "eps": 1.1,
                 "available_at": "2025-08-08T16:31:00-04:00"},
            ]))
            (inbox / "headlines.csv").write_text("never store a source without rights", encoding="utf-8")
            stamp = datetime(2025, 8, 8, 18, 30, tzinfo=NEW_YORK)
            today = archive.capture(inbox, DAY.date(), "late", now=stamp)
            self.assertEqual(today["status"], "published", today)
            inputs, manifest = archive.load(today["id"])
            self.assertEqual(manifest["sources"]["estimates"]["status"], "missing at cutoff")
            self.assertEqual(manifest["sources"]["headlines"]["status"], "invalid export")
            self.assertNotIn("headlines.csv", manifest["raw"])
            self.assertFalse((archive.root / "raw" / "headlines.csv").exists())
            known = options.visible_history(inputs.research, "AAPL", DAY)
            rows, _ = options.open_interest(known, DAY)
            self.assertEqual(rows.set_index("contract")["change"].to_dict(), {"call": 10, "put": 5})
            retry = archive.capture(inbox, DAY.date(), "late", now=stamp)
            self.assertEqual(retry["status"], "unchanged", retry)
            original = archive.load(first["id"])[0]
            self.assertEqual(len(original.research.tables["options"]), 2)
            readings = replay(archive, today["id"], include_research=True)["research"]
            self.assertEqual(readings["stock"]["options"]["open_interest"][0]["change"], 10)
            self.assertFalse(readings["stock"]["earnings_surprises"])
            (inbox / "estimates.csv").unlink()
            with (inbox / "bars.csv").open("a", encoding="utf-8") as bars:
                bars.write("2025-08-11,SPY,102,102,102,10\n")
            next_day = date(2025, 8, 11)
            stamp = datetime(2025, 8, 11, 17, tzinfo=NEW_YORK)
            later = archive.capture(inbox, next_day, "post-close", now=stamp)
            self.assertEqual(later["status"], "published", later)
            earnings = replay(archive, later["id"], include_research=True)["research"]["stock"]["earnings_surprises"]
            self.assertEqual(earnings[0]["Reported EPS"], 1.1)

    def test_dashboard_shows_populated_and_unavailable_research(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            app_file = root / "app.py"
            app_file.write_bytes((Path(__file__).resolve().parents[1] / "app.py").read_bytes())
            (root / "watchlist.txt").write_text("AAPL\nCRCL\n", encoding="utf-8")
            app = AppTest.from_file(str(app_file)).run()
            self.assertFalse(app.exception)
            app.radio(key="view").set_value("Sector").run()
            self.assertIn("Seven-day headline tone", [item.label for item in app.expander])
            app.radio(key="view").set_value("Stock").run()
            app.selectbox(key="stock_choice_selector").select("AAPL").run()
            self.assertIn("30-day ATM IV", [item.label for item in app.metric])
            app.selectbox(key="stock_choice_selector").select("CRCL").run()
            self.assertTrue(any("No permitted chain snapshots" in item.value for item in app.caption))
            self.assertFalse(app.exception)

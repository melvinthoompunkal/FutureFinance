"""Small synthetic exports that exercise the Phase 5 workflow without a provider."""

import pandas as pd

from .market_calendar import exchange
from .research_inputs import EXPORTS, ResearchInputs, parse_research
from .scope import NEW_YORK


def make_research_demo(prices: pd.Series) -> ResearchInputs:
    day = prices.index[-1]
    calendar = exchange()
    rows = {name: [] for name in EXPORTS}

    def add(name, **values):
        rows[name].append(values)

    expiries = [str(value.date()) for value in (day + pd.Timedelta(days=21), day + pd.Timedelta(days=42))]
    center = round(prices.iloc[-1] / 5) * 5
    chain_days = [pd.Timestamp("2025-07-31"), *prices.index[-2:]]
    for number, session in enumerate(chain_days):
        close = calendar.session_close(session)
        previous = calendar.previous_session(session).date().isoformat()
        for expiry_index, expiry in enumerate(expiries):
            # Provide the same contract identifiers across daily snapshots for the OI example.
            for offset in (-10, 0, 10):
                strike = center + offset
                for side in ("call", "put"):
                    delta = 0.50 - offset / 40 if side == "call" else -0.50 - offset / 40
                    add("options", symbol="AAPL", observed_at=close.isoformat(),
                        available_at=(close + pd.Timedelta(minutes=2)).isoformat(),
                        contract=f"SIM-{expiry}-{side}-{strike}", spot_at=close.isoformat(),
                        spot=prices.loc[session], expiry=expiry, settlement_at=f"{expiry}T16:00:00-04:00",
                        side=side, strike=strike, deliverable="standard", multiplier=100, quote_at=close.isoformat(),
                        bid=3.10 + expiry_index + abs(offset) / 10, ask=3.30 + expiry_index + abs(offset) / 10,
                        iv=.24 + .018 * expiry_index + .01 * number + (.02 if side == "put" else 0),
                        delta=delta, volume=15 + abs(offset),
                        oi=(120 if side == "call" else 140) + (3 * offset if side == "call" else -4 * offset) + number * 5,
                        oi_session=previous, rate=.04, dividend_yield=.006)
    for symbol, issuer, titles in (
        ("AAPL", "320193", ["Growth in services", "Services growth accelerates", "Strong hardware demand",
                           "Supplier weakness remains"]),
        ("MSFT", "789019", ["Strong cloud demand", "Cloud growth continues", "Revenue growth improves"]),
        ("NVDA", "1045810", ["Export weakness weighs", "Weakness in orders", "Weakness restrains sales"]),
        ("AMZN", "1018724", ["Delivery growth"]),
    ):
        for index, title in enumerate(titles):
            stamp = (day - pd.Timedelta(days=5 - index) + pd.Timedelta(hours=12)).tz_localize(NEW_YORK).isoformat()
            add("headlines", symbol=symbol, story_id=f"{issuer}-{index}", source="Synthetic wire",
                issuer_id=issuer, published_at=stamp, available_at=stamp, title=title)
    for index, session in enumerate(prices.index[-100:]):
        stamp = (session + pd.Timedelta(hours=16)).tz_localize(NEW_YORK).isoformat()
        for series, value in (("DGS10", 4.2 - index * .003), ("T10Y2Y", .22 + index * .002),
                              ("DTWEXBGS", 122 - index * .04)):
            add("market_context", session=session.date().isoformat(), available_at=stamp, series=series, value=value)
        for series, calls, puts in (("equity_volume", 1000, 500 + 2 * index), ("index_volume", 1100, 900 + 3 * index)):
            add("market_context", session=session.date().isoformat(), available_at=stamp, series=series,
                puts=puts, calls=calls)
    for stamp, period, kind, eps, target in (
        ("2025-04-30T15:00:00-04:00", "2025-09-27", "consensus", 1.49, 273),
        ("2025-07-01T15:00:00-04:00", "2025-09-27", "consensus", 1.52, 288),
        ("2025-07-30T15:00:00-04:00", "2025-06-28", "consensus", 1.40, 285),
        ("2025-07-31T16:10:00-04:00", "2025-06-28", "actual", 1.48, None),
        ("2025-08-08T12:00:00-04:00", "2025-09-27", "consensus", 1.55, 292),
    ):
        add("estimates", symbol="AAPL", period=period, kind=kind, available_at=stamp, eps=eps,
            target=target, analysts=15 if kind == "consensus" else None)
    for metric, start, end, numerator, divisor, scope, denominator_scope in (
        ("short_float", "2025-07-31", "2025-07-31", 80e6, 14e9, "exchange-listed", "float"),
        ("days_to_cover", "2025-07-03", "2025-07-31", 80e6, 40e6, "exchange-listed", "consolidated_daily_average"),
        ("ats_share", "2025-07-21", "2025-07-25", 20e6, 170e6, "ATS weekly", "consolidated_weekly"),
        ("off_exchange_short_share", "2025-08-07", "2025-08-07", 3e6, 8e6, "Sample off-exchange facilities",
         "same_facilities_daily"),
    ):
        add("positioning", symbol="AAPL", session=end, metric=metric, start=start, numerator=numerator,
            scope=scope, denominator=divisor, denominator_scope=denominator_scope,
            denominator_source="Synthetic share counts", available_at="2025-08-08T11:00:00-04:00")
    opening, close = calendar.session_open(day), calendar.session_close(day)
    times = pd.date_range(opening, close, freq="30min")
    for index, (start, end) in enumerate(zip(times, times[1:])):
        price = prices.iloc[-1] - 2 + index / 6
        add("intraday", symbol="AAPL", start_at=start.isoformat(), end_at=end.isoformat(), high=price + .25,
            low=price - .35, close=price, volume=500 + index * 20, available_at=end.isoformat())

    files = {f"{name}.csv": pd.DataFrame(data, columns=EXPORTS[name].columns).to_csv(index=False).encode()
             for name, data in rows.items() if data}
    files["headline_dictionary.csv"] = b"term,tone\ngrowth,positive\nstrong,positive\nweakness,negative\n"
    sources = {name: {"label": f"Synthetic {name.replace('_', ' ')}", "permitted": True} for name in rows}
    sources["headlines"]["dictionary_label"] = "Synthetic three-word dictionary"
    return parse_research(files, {"research_sources": sources})

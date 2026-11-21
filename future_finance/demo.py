from datetime import datetime

import numpy as np
import pandas as pd

from .inputs import BAR_FIELDS, MEMBER_FIELDS, Inputs
from .issuer_inputs import EARNINGS_FIELDS, FILING_FIELDS
from .market_calendar import sessions_between
from .research_demo import make_research_demo
from .scope import NEW_YORK, SECTORS

DEMO_SECTOR = {
    "AAPL": "XLK", "MSFT": "XLK", "NVDA": "XLK",
    "GOOGL": "XLC", "META": "XLC",
    "AMZN": "XLY", "TSLA": "XLY",
    "JPM": "XLF", "BAC": "XLF", "XOM": "XLE", "CVX": "XLE",
    "UNH": "XLV", "LLY": "XLV", "COST": "XLP", "WMT": "XLP",
    "CAT": "XLI", "LIN": "XLB", "NEE": "XLU",
}
DEMO_SHARES = {"AAPL": 14.8e9, "MSFT": 7.4e9, "NVDA": 24.4e9}


def _sessions() -> pd.DatetimeIndex:
    return sessions_between(pd.Timestamp("2024-09-03").date(), pd.Timestamp("2025-08-08").date())


def make_demo() -> Inputs:
    dates = _sessions()
    x = np.arange(len(dates))
    rng = np.random.default_rng(701)
    bars = []

    def add(symbol: str, close: np.ndarray, start: str = "2024-09-03") -> None:
        for date, value in zip(dates, close, strict=True):
            if date >= pd.Timestamp(start):
                price = round(float(value), 2)
                volume = int(rng.integers(500_000, 6_000_000))
                market_cap = price * DEMO_SHARES.get(symbol, np.nan)
                bars.append((date, symbol, price, price, price, volume, price * 1.012, price * 0.989,
                             market_cap, volume))

    market = 515 + x * 0.4 + 6 * np.sin(x / 10) + 3 * np.cos(x / 3.1)
    market[-1] = market[-2] * 1.0084
    add("SPY", market)
    add("QQQ", 447 + x * 0.54 + 9 * np.sin(x / 8.2))
    add("RSP", market * (0.32 - 0.00019 * x))
    add("HYG", 83 + 0.5 * np.sin(x / 12))
    add("IEF", 94 + 0.4 * np.cos(x / 7))
    for index, sector in enumerate(SECTORS):
        slope = {"XLK": 0.0022, "XLE": -0.0019}.get(sector, 0.00025 * (index - 4))
        ratio = (0.12 + index * 0.015) * np.exp(slope * (x - x[-1]))
        add(sector, market * ratio * (1 + 0.005 * np.sin(x / 3.3 + index)))

    members = dict(DEMO_SECTOR)
    for index in range(100 - len(members)):
        members[f"SIM{index + 1:02d}"] = tuple(SECTORS)[index % len(SECTORS)]
    for index, symbol in enumerate(members):
        base = 90 + index * 1.2 + 1.5 * np.sin(x / 6 + index)
        slope = 0.22 if index < 38 or index >= 93 else -0.19
        close = base + slope * x
        if index >= 93:
            close -= 3.8 * np.maximum(x - x[-6], 0)
        if symbol == "AAPL":
            close = 174 + 0.32 * x + 3 * np.sin(x / 5)
            close += 0.7 * np.maximum(x - x[-22], 0)
            close[-1] = close[-2] * 1.013
        add(symbol, close)
    add("RIVN", 17.3 - 0.023 * x + 0.55 * np.cos(x / 7))
    add("CRCL", 60 + (x - x[-1] + 45) * 2.8 + 9 * np.sin(x / 2.8), "2025-06-05")

    membership = pd.DataFrame(
        [(date, ticker, sector) for date in dates for ticker, sector in members.items()],
        columns=MEMBER_FIELDS,
    )
    stock_sectors = pd.DataFrame({"session": dates, "symbol": "RIVN", "sector_etf": "XLY"})
    filings = pd.DataFrame([
        ("AAPL", "320193", None, "10-Q", "2025-06-28", datetime(2025, 7, 31, 16, 10, tzinfo=NEW_YORK),
         "operating", 94e9, 86e9, 26.32e9, 25.8e9, 105e9, 12e9, 6.5, 99e9, 137e9, 115e9, 3e9, "2025-07-31"),
        ("MSFT", "789019", None, "10-K", "2025-06-30", datetime(2025, 7, 30, 16, 10, tzinfo=NEW_YORK),
         "operating", 76e9, 66e9, 34e9, 29e9, 130e9, 66e9, 12, 48e9, 145e9, 128e9, 2e9, "2025-07-30"),
        ("NVDA", "1045810", None, "10-Q", "2025-04-27", datetime(2025, 5, 28, 16, 10, tzinfo=NEW_YORK),
         "operating", 44e9, 26e9, 22e9, 17e9, 72e9, 4e9, 3.2, 9e9, 81e9, 77e9, 0.25e9, "2025-05-28"),
        ("RIVN", "1874178", None, "10-Q", "2025-06-30", datetime(2025, 8, 5, 17, tzinfo=NEW_YORK),
         "operating", 1.3e9, 1.16e9, -1.105e9, -1.369e9, -2.6e9, 1.7e9, -4.5, 4.4e9, -3e9,
         -3.6e9, 0.24e9, "2025-08-05"),
    ], columns=FILING_FIELDS)
    filings["period"] = pd.to_datetime(filings["period"])
    filings["eps_basis_session"] = pd.to_datetime(filings["eps_basis_session"])
    earnings = pd.DataFrame([
        ("AAPL", pd.Timestamp("2025-10-30"), "estimated", datetime(2025, 7, 31, 16, 15, tzinfo=NEW_YORK), None),
    ], columns=EARNINGS_FIELDS)
    stress = pd.DataFrame({
        "session": dates[:-1],
        "available_at": (dates[1:] + pd.Timedelta(hours=10)).tz_localize(NEW_YORK).tz_convert("UTC"),
        "VIX": 20 + 3 * np.sin(x[:-1] / 16),
        "VIX3M": 22 + 2 * np.sin(x[:-1] / 19),
        "OAS": 3.4 + 0.26 * np.cos(x[:-1] / 11),
    }).melt(id_vars=["session", "available_at"], var_name="series", value_name="value")
    bar_frame = pd.DataFrame(bars, columns=BAR_FIELDS)
    apple = bar_frame.loc[bar_frame["symbol"].eq("AAPL")].set_index("session")["close"]
    return Inputs(bar_frame, membership,
                  "Synthetic daily bars", "Synthetic 100-stock universe", demo=True, filings=filings,
                  stress=stress, stress_sources={"VIX": "Synthetic volatility", "VIX3M": "Synthetic volatility",
                                                 "OAS": "Synthetic credit spread"}, earnings=earnings,
                  stock_sectors=stock_sectors, research=make_research_demo(apple))

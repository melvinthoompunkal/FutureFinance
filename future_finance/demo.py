from datetime import datetime

import numpy as np
import pandas as pd

from .inputs import BAR_FIELDS, Inputs
from .scope import NEW_YORK, SECTORS

DEMO_SECTOR = {
    "AAPL": "XLK", "MSFT": "XLK", "NVDA": "XLK",
    "GOOGL": "XLC", "META": "XLC",
    "AMZN": "XLY", "TSLA": "XLY",
    "JPM": "XLF", "BAC": "XLF", "XOM": "XLE", "CVX": "XLE",
    "UNH": "XLV", "LLY": "XLV", "COST": "XLP", "WMT": "XLP",
    "CAT": "XLI", "LIN": "XLB", "NEE": "XLU",
}


def _sessions() -> pd.DatetimeIndex:
    closed = pd.to_datetime([
        "2024-11-28", "2024-12-25", "2025-01-01", "2025-01-09", "2025-01-20",
        "2025-02-17", "2025-04-18", "2025-05-26", "2025-06-19", "2025-07-04",
    ])
    sessions = pd.bdate_range("2024-09-03", "2025-08-08")
    return sessions.difference(closed)


def make_demo() -> Inputs:
    dates = _sessions()
    x = np.arange(len(dates))
    rng = np.random.default_rng(701)
    bars = []

    def add(symbol: str, close: np.ndarray, start: str = "2024-09-03") -> None:
        for date, value in zip(dates, close, strict=True):
            if date >= pd.Timestamp(start):
                price = round(float(value), 2)
                bars.append((date, symbol, price, price, price, int(rng.integers(500_000, 6_000_000))))

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
        columns=["session", "symbol", "sector_etf"],
    )
    filings = pd.DataFrame([
        ("AAPL", "2025-06-28", datetime(2025, 7, 31, 16, 10, tzinfo=NEW_YORK),
         94000, 86000, 26320, 25800, 105_000, 12_000, 6.5),
        ("RIVN", "2025-06-30", datetime(2025, 8, 5, 17, tzinfo=NEW_YORK),
         1300, 1160, -1105, -1369, -2600, 1700, -4.5),
    ], columns=[
        "symbol", "period", "available_at", "revenue", "prior_revenue",
        "operating_income", "prior_operating_income", "ttm_cfo", "ttm_capex", "ttm_eps",
    ])
    stress = pd.DataFrame({
        "session": dates[:-1],
        "available_on": dates[1:],
        "VIX": 20 + 3 * np.sin(x[:-1] / 16),
        "VIX3M": 22 + 2 * np.sin(x[:-1] / 19),
        "OAS": 3.4 + 0.26 * np.cos(x[:-1] / 11),
    }).set_index("session")
    return Inputs(pd.DataFrame(bars, columns=BAR_FIELDS), membership,
                  "Synthetic daily bars", "Synthetic 100-stock universe", True, filings, stress)

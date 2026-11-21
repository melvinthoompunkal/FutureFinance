from pathlib import Path
import re
from zoneinfo import ZoneInfo

NEW_YORK = ZoneInfo("America/New_York")
BENCHMARK = "SPY"
COMPARISON = "QQQ"
SECTORS = {
    "XLC": "Communication services",
    "XLY": "Consumer discretionary",
    "XLP": "Consumer staples",
    "XLE": "Energy",
    "XLF": "Financials",
    "XLV": "Health care",
    "XLI": "Industrials",
    "XLK": "Information technology",
    "XLB": "Materials",
    "XLRE": "Real estate",
    "XLU": "Utilities",
}
SAMPLE_ISSUERS = {"AAPL": 320193, "RIVN": 1874178, "CRCL": 1876042}
SAMPLE_SYMBOLS = (BENCHMARK, COMPARISON, "XLK", "XLE", *SAMPLE_ISSUERS)
SYMBOL_PATTERN = r"[A-Z0-9][A-Z0-9./-]{0,14}"


def read_watchlist(path: Path) -> list[str]:
    symbols = {}
    for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        symbol = line.partition("#")[0].strip().upper()
        if not symbol:
            continue
        if not re.fullmatch(SYMBOL_PATTERN, symbol):
            raise ValueError(f"Invalid ticker on watchlist line {number}.")
        symbols[symbol] = None
    return list(symbols)

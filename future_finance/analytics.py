from dataclasses import dataclass

import pandas as pd

from .inputs import Inputs
from .scope import BENCHMARK, SECTORS

BREADTH_WINDOWS = (50, 200)


def change(values: pd.Series | pd.DataFrame, window: int):
    return (values / values.shift(window) - 1) * 100


def relative(prices: pd.DataFrame, ticker: str, benchmark: str = BENCHMARK) -> pd.Series:
    empty = pd.Series(index=prices.index, dtype=float)
    return prices.get(ticker, empty) / prices.get(benchmark, empty)


def rebase(prices: pd.DataFrame, tickers: list[str]) -> pd.DataFrame:
    selected = prices.reindex(columns=list(dict.fromkeys(tickers))).dropna(axis=1, how="all")
    common = selected.dropna()
    if common.empty:
        return common
    return selected.loc[common.index[0]:].div(common.iloc[0]).mul(100)


def moving_average_gaps(prices: pd.Series) -> dict[int, float]:
    return {window: (prices / prices.rolling(window).mean() - 1).iloc[-1] * 100
            for window in (20, *BREADTH_WINDOWS)}


def trend(gaps: dict[int, float]) -> str:
    short, long = (gaps[window] for window in BREADTH_WINDOWS)
    if pd.isna(short) or pd.isna(long):
        return "Incomplete history"
    if short > 0 and long > 0:
        return "Uptrend"
    if short < 0 and long < 0:
        return "Downtrend"
    return "Mixed trend"


@dataclass(frozen=True)
class Breadth:
    above: int
    eligible: int
    expected: int

    @property
    def percent(self) -> float | None:
        return 100 * self.above / self.eligible if self.eligible else None

    @property
    def label(self) -> str:
        percent = self.percent
        if not self.expected:
            return "Membership unavailable"
        if self.eligible / self.expected < 0.9 or percent is None:
            return "Insufficient coverage"
        if percent >= 60:
            return "Broad"
        if percent <= 40:
            return "Narrow"
        return "Mixed"


def breadth_history(inputs: Inputs, prices: pd.DataFrame, dates: pd.DatetimeIndex,
                    sector: str | None = None) -> dict[int, dict[pd.Timestamp, Breadth]]:
    members = inputs.members[inputs.members["session"].isin(dates)]
    if sector:
        members = members[members["sector_etf"].eq(sector)]
    by_date = members.groupby("session")["symbol"].agg(list).to_dict()
    result = {}
    for window in BREADTH_WINDOWS:
        average = prices.rolling(window).mean()
        readings = {}
        for date in dates:
            symbols = by_date.get(date, [])
            closes = prices.loc[date].reindex(symbols)
            averages = average.loc[date].reindex(symbols)
            readings[date] = Breadth(int(closes.gt(averages).sum()), int(averages.count()), len(symbols))
        result[window] = readings
    return result


def sector_ranking(prices: pd.DataFrame) -> pd.DataFrame:
    sector_prices = prices.reindex(columns=list(SECTORS))
    ratios = sector_prices.div(prices[BENCHMARK], axis="index")
    return pd.DataFrame({
        "Sector": SECTORS,
        "5 sessions": change(ratios, 5).iloc[-1],
        "20 sessions": change(ratios, 20).iloc[-1],
        "60 sessions": change(ratios, 60).iloc[-1],
        "Absolute, 20 sessions": change(sector_prices, 20).iloc[-1],
    }).rename_axis("ETF").sort_values("20 sessions", ascending=False)

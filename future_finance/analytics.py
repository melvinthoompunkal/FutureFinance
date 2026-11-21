from dataclasses import dataclass

import pandas as pd

from .inputs import Inputs
from .scope import BENCHMARK, SECTORS

BREADTH_WINDOWS = (50, 200)
SECTOR_WINDOW = 20


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


def breadth_members(inputs: Inputs, prices: pd.DataFrame, dates: pd.DatetimeIndex) -> pd.DataFrame:
    members = inputs.members.loc[inputs.members["session"].isin(dates)].copy()
    keys = pd.MultiIndex.from_frame(members[["session", "symbol"]])
    members["close"] = prices.loc[dates].stack(future_stack=True).reindex(keys).to_numpy()
    for window in BREADTH_WINDOWS:
        averages = prices.rolling(window).mean().loc[dates].stack(future_stack=True)
        members[window] = averages.reindex(keys).to_numpy()
    return members


def breadth_count(members: pd.DataFrame, window: int) -> Breadth:
    return Breadth(int(members["close"].gt(members[window]).sum()), int(members[window].count()), len(members))


def breadth_readings(members: pd.DataFrame, dates: pd.DatetimeIndex,
                     sector: str | None = None) -> dict[int, dict[pd.Timestamp, Breadth]]:
    if sector:
        members = members.loc[members["sector_etf"].eq(sector)]
    by_date = {day: rows for day, rows in members.groupby("session", sort=False)}
    empty = Breadth(0, 0, 0)
    return {window: {day: breadth_count(by_date[day], window) if day in by_date else empty for day in dates}
            for window in BREADTH_WINDOWS}


def breadth_history(inputs: Inputs, prices: pd.DataFrame, dates: pd.DatetimeIndex,
                    sector: str | None = None) -> dict[int, dict[pd.Timestamp, Breadth]]:
    return breadth_readings(breadth_members(inputs, prices, dates), dates, sector)


def member_returns(prices: pd.DataFrame, symbols: pd.Series) -> pd.Series:
    ratios = prices.reindex(columns=symbols).div(prices[BENCHMARK], axis="index")
    return change(ratios, SECTOR_WINDOW).iloc[-1].sort_values(ascending=False, kind="stable")


def sector_ranking(prices: pd.DataFrame) -> pd.DataFrame:
    sector_prices = prices.reindex(columns=list(SECTORS))
    ratios = sector_prices.div(prices[BENCHMARK], axis="index")
    ranking = pd.DataFrame({
        "Sector": SECTORS,
        "5 sessions": change(ratios, 5).iloc[-1],
        "20 sessions": change(ratios, SECTOR_WINDOW).iloc[-1],
        "60 sessions": change(ratios, 60).iloc[-1],
        "Absolute, 20 sessions": change(sector_prices, SECTOR_WINDOW).iloc[-1],
    }).rename_axis("ETF").sort_values("20 sessions", ascending=False, kind="stable")
    ranking.insert(0, "Rank", ranking["20 sessions"].rank(ascending=False, method="min").astype("Int64"))
    return ranking

"""Calculate stock readings from bars and issuer releases available at the selected close."""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .inputs import Inputs
from .market_calendar import capture_cutoff
from .scope import BENCHMARK, COMPARISON, SECTORS

FUNDS = {BENCHMARK, COMPARISON, "DIA", "IWM", "RSP", "HYG", "IEF", *SECTORS}


def _divide(numerator: float, denominator: float) -> float:
    return numerator / denominator if pd.notna(denominator) and denominator > 0 else np.nan


def price_risk(inputs: Inputs, ticker: str, close: pd.Series, dates: pd.DatetimeIndex) -> dict[str, float]:
    bars = inputs.bars_for(ticker).reindex(close.index)
    high, low = bars["split_high"], bars["split_low"]
    previous = close.shift()
    true_range = pd.concat([high - low, (high - previous).abs(), (low - previous).abs()], axis=1).max(
        axis=1, skipna=False
    )
    returns = np.log(close / previous)
    window = close.loc[dates]
    first = window.first_valid_index()
    drawdown = np.nan
    if first is not None and window.loc[first:].notna().all():
        drawdown = (close.iloc[-1] / window.max() - 1) * 100
    high_252 = high.rolling(252).max().iloc[-1]
    volume = bars["split_volume"].tail(21)
    if volume.isna().all():
        recent = bars.tail(21)
        factor = recent["split_close"] / recent["close"]
        if factor.notna().all() and np.allclose(factor, factor.iloc[-1], rtol=0.0005, atol=0):
            volume = recent["volume"]
    return {
        "ATR (14), % of close": _divide(true_range.rolling(14).mean().iloc[-1] * 100, close.iloc[-1]),
        "Realized volatility (20)": returns.rolling(20).std().iloc[-1] * np.sqrt(252) * 100,
        "Realized volatility (60)": returns.rolling(60).std().iloc[-1] * np.sqrt(252) * 100,
        "Drawdown in chart window": drawdown,
        "Distance from 52-week high": (_divide(close.iloc[-1], high_252) - 1) * 100,
        "Relative volume (20)": _divide(volume.iloc[-1], volume.shift().rolling(20).mean().iloc[-1]),
    }


def filings_as_of(filings: pd.DataFrame, day: pd.Timestamp) -> pd.DataFrame:
    if filings.empty:
        return filings.set_index("symbol")
    known = filings.loc[filings["available_at"].le(capture_cutoff(day.date()))]
    return known.sort_values(["period", "available_at"]).drop_duplicates("symbol", keep="last").set_index("symbol")


def next_earnings(earnings: pd.DataFrame, ticker: str, day: pd.Timestamp) -> pd.Series | None:
    if earnings.empty:
        return None
    known = earnings.loc[earnings["symbol"].eq(ticker) & earnings["available_at"].le(capture_cutoff(day.date()))]
    if known.empty:
        return None
    event = known.sort_values("available_at").iloc[-1]
    return event if event.event_date >= day else None


def filing_url(filing: pd.Series) -> str | None:
    if pd.isna(filing.cik) or pd.isna(filing.accession):
        return None
    return (f"https://www.sec.gov/Archives/edgar/data/{int(filing.cik)}/"
            f"{filing.accession.replace('-', '')}/{filing.accession}-index.htm")


@dataclass(frozen=True)
class BusinessHealth:
    growth: float
    margin: float
    margin_change: float
    fcf: float
    debt_to_ebitda: float
    coverage: float


def business_health(filing: pd.Series) -> BusinessHealth:
    growth = (_divide(filing.revenue, filing.prior_revenue) - 1) * 100
    margin = _divide(filing.operating_income, filing.revenue) * 100
    prior_margin = _divide(filing.prior_operating_income, filing.prior_revenue) * 100
    return BusinessHealth(
        growth, margin, margin - prior_margin, filing.ttm_cfo - filing.ttm_capex,
        _divide(filing.gross_debt, filing.ttm_ebitda), _divide(filing.ttm_ebit, filing.ttm_interest),
    )


@dataclass(frozen=True)
class Valuation:
    pe: float
    fcf_yield: float
    loss_making: bool


def valuation(filing: pd.Series, bars: pd.DataFrame, day: pd.Timestamp) -> Valuation:
    today = bars.loc[day] if day in bars.index else None
    loss_making = pd.notna(filing.ttm_eps) and filing.ttm_eps < 0
    if today is None:
        return Valuation(np.nan, np.nan, loss_making)
    pe = np.nan
    if filing.ttm_eps > 0 and filing.basis != "reit" and filing.eps_basis_session in bars.index:
        basis = bars.loc[filing.eps_basis_session]
        factor_then = _divide(basis.split_close, basis.close)
        factor_now = _divide(today.split_close, today.close)
        eps_at_close = filing.ttm_eps * _divide(factor_then, factor_now)
        pe = _divide(today.close, eps_at_close)
    fcf_yield = np.nan
    if filing.basis == "operating":
        fcf_yield = _divide((filing.ttm_cfo - filing.ttm_capex) * 100, today.market_cap)
    return Valuation(pe, fcf_yield, loss_making)


def peer_valuations(inputs: Inputs, members: pd.DataFrame, filings: pd.DataFrame, ticker: str,
                    filing: pd.Series, sector: str, day: pd.Timestamp) -> pd.DataFrame:
    peers = members.loc[members["sector_etf"].eq(sector)].index.difference([ticker])
    reports = filings.reindex(filings.index.intersection(peers))
    reports = reports.loc[reports["basis"].eq(filing.basis) & reports["cik"].ne(filing.cik)]
    prices = inputs.bars.loc[inputs.bars["symbol"].isin(reports.index)].set_index("session")
    values = []
    for peer, bars in prices.groupby("symbol", sort=True):
        report = reports.loc[peer]
        value = valuation(report, bars, day)
        values.append((peer, report.cik, value.pe, value.fcf_yield, report.period,
                       (day - report.period).days))
    # Pick one priced share class per issuer. The first ticker is deterministic.
    return (pd.DataFrame(values, columns=["Symbol", "CIK", "Trailing P/E", "FCF yield (%)",
                                          "Fiscal period", "Period age (calendar days)"])
            .dropna(subset=["Trailing P/E", "FCF yield (%)"], how="all").drop_duplicates("CIK").set_index("Symbol"))

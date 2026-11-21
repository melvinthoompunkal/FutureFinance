from dataclasses import dataclass

import pandas as pd
import streamlit as st

from . import analytics as calc, charts
from .inputs import Inputs
from .issuer_inputs import FINANCIAL_FIELDS
from .scope import BENCHMARK, NEW_YORK
from .stock import FUNDS, business_health, filing_url, filings_as_of, next_earnings, peer_valuations, price_risk, valuation


def signed(value: float | None, suffix: str = "%") -> str:
    return "Unavailable" if pd.isna(value) else f"{value:+.2f}{suffix}"


@dataclass
class Session:
    inputs: Inputs
    split: pd.DataFrame
    total: pd.DataFrame
    close: pd.DataFrame
    dates: pd.DatetimeIndex
    manifest: dict | None = None

    @property
    def day(self) -> pd.Timestamp:
        return self.dates[-1]


def return_chart(session: Session, tickers: list[str]) -> None:
    prices = session.total.loc[session.dates]
    available = prices.dropna(axis=1, how="all").columns
    missing = list(dict.fromkeys(ticker for ticker in tickers if ticker not in available))
    if missing:
        st.caption(f"No dividend-adjusted closes in this window for {', '.join(missing)}.")
    indexed = calc.rebase(prices, tickers)
    if indexed.empty and indexed.shape[1]:
        st.info("The available price series have no overlapping session in this window.")
        return
    charts.lines(indexed.reindex(session.dates), "Dividend-adjusted index", index_baseline=True)


def stock(session: Session, ticker: str) -> None:
    fund = ticker in FUNDS
    st.title(f"{ticker} {'fund' if fund else 'stock'} detail")
    members = session.inputs.members_on(session.day).set_index("symbol")
    sector_etf = session.inputs.sector_on(ticker, session.day)
    tickers = [ticker, sector_etf, BENCHMARK] if sector_etf else [ticker, BENCHMARK]
    split = session.split.get(ticker, pd.Series(index=session.split.index, dtype=float))
    last_close = session.close[ticker].iloc[-1] if ticker in session.close else float("nan")
    move = calc.change(split, 1).iloc[-1]
    event = next_earnings(session.inputs.earnings, ticker, session.day) if not fund else None
    main, evidence = st.columns([3, 1.45], gap="large")
    with main:
        st.subheader("Relative performance", anchor="relative-performance")
        return_chart(session, tickers)
        if sector_etf is None and not fund:
            st.caption("Sector mapping is unavailable for this stock on the selected session.")
        if sector_etf:
            _relative_reading(session, ticker, sector_etf)
            _relative_reading(session, sector_etf, BENCHMARK)
        if ticker != BENCHMARK:
            _relative_reading(session, ticker, BENCHMARK)
    with evidence:
        st.subheader("Price at the close")
        st.metric("Quoted close", f"${last_close:,.2f}" if pd.notna(last_close) else "Unavailable")
        if pd.isna(last_close) and ticker in session.close:
            latest = session.close[ticker].last_valid_index()
            if latest is not None:
                st.caption(f"Last available quoted close was {latest:%b %d, %Y}.")
        st.metric("Session change", signed(move))
        gaps = calc.moving_average_gaps(split)
        st.metric("Price trend", calc.trend(gaps))
        st.caption("Distance from moving averages · " + " · ".join(
            f"{window} sessions {signed(value)}" for window, value in gaps.items()
        ))
        if split.tail(200).count() < 200:
            st.caption(f"{split.tail(200).count()} of 200 split-adjusted closes available.")
        if not fund:
            label = event.event_date.strftime("%b %d, %Y") if event is not None else "Unknown"
            st.metric("Next earnings", label)
            if event is not None:
                source = session.inputs.issuer_sources.get("earnings", {}).get("label", "Synthetic calendar")
                st.caption(f"{event.status.capitalize()} · {source} · {_publication_label(event.available_at)}")
                if pd.notna(event.source_url):
                    st.link_button("Open earnings announcement", event.source_url)
            else:
                _issuer_export_status(session, "earnings")
    _risk(session, ticker, split)
    if fund:
        return

    _business(session, ticker, members, sector_etf, move)


def _relative_reading(session: Session, ticker: str, benchmark: str) -> None:
    relative = calc.change(calc.relative(session.total, ticker, benchmark), calc.SECTOR_WINDOW).iloc[-1]
    if pd.isna(relative):
        st.caption(f"{ticker} vs. {benchmark} needs common adjusted closes 20 sessions apart.")
    else:
        action = "outperformed" if relative > 0 else "trailed" if relative < 0 else "matched"
        st.write(f"{ticker} {action} {benchmark} over 20 sessions ({signed(relative)} relative).")


def _risk(session: Session, ticker: str, split: pd.Series) -> None:
    st.subheader("Risk and trading activity")
    values = price_risk(session.inputs, ticker, split, session.dates)
    columns = st.columns(3)
    for index, (label, value) in enumerate(values.items()):
        if label == "Relative volume (20)":
            formatted = f"{value:.2f}×" if pd.notna(value) else "Unavailable"
        elif label.startswith("Drawdown") or label.startswith("Distance"):
            formatted = signed(value)
        else:
            formatted = f"{value:.2f}%" if pd.notna(value) else "Unavailable"
        columns[index % len(columns)].metric(label, formatted)
    with st.expander("Price sources and calculation windows"):
        st.write(f"Daily prices from {session.inputs.source} through {session.day:%b %d, %Y}.")
        st.write("The 14-session average true range uses split-adjusted highs, lows and previous closes. "
                 "Realized volatility annualizes the standard deviation of daily log returns. Drawdown uses "
                 "the highest split-adjusted close within the selected window.")
        st.write("The 52-week high requires 252 split-adjusted intraday highs. Relative volume compares the "
                 "selected session with the preceding 20 sessions on a consistent share basis.")


def _publication_label(stamp: pd.Timestamp) -> str:
    return f"Available {stamp.tz_convert(NEW_YORK):%b %d, %Y at %I:%M:%S %p ET}"


def _issuer_export_status(session: Session, dataset: str) -> None:
    source = session.inputs.issuer_sources.get(dataset, {})
    if source.get("status") == "invalid export":
        st.caption(source["detail"])


def _business(session: Session, ticker: str, members: pd.DataFrame, sector_etf: str | None, move: float) -> None:
    st.subheader("Business health", anchor="business-health")
    filings = filings_as_of(session.inputs.filings, session.day)
    if ticker not in filings.index:
        st.info("No financial statement is available in this dataset by the selected cutoff.")
        _issuer_export_status(session, "filings")
        return
    filing = filings.loc[ticker]
    health = business_health(filing)
    if filing.basis == "operating" and move > 0 and health.margin_change < 0:
        st.write("The stock rose on the session while operating margin was lower year over year.")
    elif filing.basis == "operating" and pd.notna(health.growth) and pd.notna(health.margin_change):
        revenue = "grew" if health.growth > 0 else "fell" if health.growth < 0 else "was unchanged"
        margin = "rose" if health.margin_change > 0 else "fell" if health.margin_change < 0 else "was unchanged"
        st.write(f"Revenue {revenue} and operating margin {margin} year over year.")

    def ratio(value: float) -> str:
        return f"{value:.2f}×" if pd.notna(value) else "Unavailable"

    price_bars = session.inputs.bars_for(ticker)
    value = valuation(filing, price_bars, session.day)
    revenue_col, margin_col, cash_col = st.columns(3)
    revenue_col.metric("Quarterly revenue YoY", signed(health.growth))
    if filing.basis == "operating":
        margin_col.metric("Operating margin", f"{health.margin:.1f}%" if pd.notna(health.margin) else "Unavailable",
                          signed(health.margin_change, " pp YoY") if pd.notna(health.margin_change) else None,
                          delta_color="off")
        fcf = f"{'−' if health.fcf < 0 else ''}${abs(health.fcf) / 1e9:,.2f}B" if pd.notna(health.fcf) else "Unavailable"
        cash_col.metric("Trailing free cash flow", fcf)
        revenue_col.metric("Gross debt / EBITDA", ratio(health.debt_to_ebitda))
        margin_col.metric("Interest coverage", ratio(health.coverage))
    else:
        margin_col.caption("Operating margin, cash flow and leverage comparisons are inapplicable for this "
                           "reporting basis.")

    source = session.inputs.issuer_sources.get("filings", {}).get("label", "Synthetic filing" if session.inputs.demo
                                                                 else "SEC EDGAR")
    st.caption(f"{source} · {filing.form} · Period ended {filing.period:%b %d, %Y}. "
               f"{_publication_label(filing.available_at)}.")
    url = filing_url(filing)
    if url:
        st.link_button("Open source filing", url)
    with st.expander("Reported values and definitions"):
        labels = ["Quarterly revenue (USD)", "Prior-year quarterly revenue (USD)", "Operating income (USD)",
                  "Prior-year operating income (USD)", "Trailing operating cash flow (USD)",
                  "Trailing capital expenditure (USD)", "Trailing diluted EPS (USD per share)",
                  "Gross interest-bearing debt (USD)", "Trailing EBITDA (USD)", "Trailing EBIT (USD)",
                  "Trailing interest expense (USD)"]
        reported = filing[FINANCIAL_FIELDS].set_axis(labels).rename("Reported value").to_frame()
        reported["Reported value"] = reported["Reported value"].astype(float)
        st.dataframe(reported, width="stretch", column_config={"Reported value": st.column_config.NumberColumn(
            format="localized")})
        st.caption("Free cash flow subtracts capital expenditure from operating cash flow. Leverage divides "
                   "gross debt by positive trailing EBITDA. Interest coverage divides trailing EBIT by interest expense.")

    st.subheader("Valuation")
    pe, cash = st.columns(2)
    pe.metric("Trailing P/E", "Inapplicable" if filing.basis == "reit" else
              "Loss-making" if value.loss_making else ratio(value.pe))
    cash.metric("Free cash flow yield", signed(value.fcf_yield) if filing.basis == "operating" else "Inapplicable")
    if sector_etf:
        peers = peer_valuations(session.inputs, members, filings, ticker, filing, sector_etf, session.day)
        for column, measure, formatter in ((pe, "Trailing P/E", ratio), (cash, "FCF yield (%)", signed)):
            series = peers[measure].dropna()
            median = formatter(series.median()) if len(series) else "Unavailable"
            column.caption(f"{sector_etf} peer median {median} · {len(series)} eligible")
        if len(peers):
            with st.expander("Comparable sector valuations"):
                st.dataframe(peers.drop(columns="CIK").round(2), width="stretch")
    st.caption("P/E uses positive trailing diluted EPS on the quoted share basis. Free cash flow yield uses "
               "trailing free cash flow and same-session market capitalization.")

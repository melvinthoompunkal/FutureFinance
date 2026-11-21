from dataclasses import dataclass
from datetime import time

import pandas as pd
import streamlit as st

from . import analytics as calc, charts
from .inputs import Inputs
from .scope import BENCHMARK, COMPARISON, NEW_YORK, SECTORS


def signed(value: float | None, suffix: str = "%") -> str:
    return "Unavailable" if pd.isna(value) else f"{value:+.2f}{suffix}"


@dataclass
class Session:
    inputs: Inputs
    split: pd.DataFrame
    total: pd.DataFrame
    close: pd.DataFrame
    dates: pd.DatetimeIndex

    @property
    def day(self) -> pd.Timestamp:
        return self.dates[-1]

    def metric(self, name: str, series: pd.Series, window: int) -> None:
        st.metric(name, signed(calc.change(series, window).iloc[-1]))


def _breadth_chart(history: dict, dates: pd.DatetimeIndex) -> None:
    values = pd.DataFrame({
        f"{window}-session average": {day: reading.percent for day, reading in series.items()}
        for window, series in history.items()
    }).reindex(dates)
    charts.lines(values, "Members above average (%)", height=155, domain=[0, 100])


def _return_chart(session: Session, tickers: list[str]) -> None:
    prices = session.total.loc[session.dates]
    available = prices.dropna(axis=1, how="all").columns
    missing = list(dict.fromkeys(ticker for ticker in tickers if ticker not in available))
    if missing:
        st.caption(f"No dividend-adjusted closes in this window for {', '.join(missing)}.")
    indexed = calc.rebase(prices, tickers)
    if indexed.empty and indexed.shape[1]:
        st.info("The available price series have no overlapping session in this window.")
        return
    charts.lines(indexed, "Dividend-adjusted index", index_baseline=True)


def _breadth_evidence(history: dict, day: pd.Timestamp, earlier: pd.Timestamp | None) -> None:
    for window, readings in history.items():
        reading = readings[day]
        previous = readings.get(earlier)
        percent = reading.percent
        text = f"{percent:.0f}% · {reading.label}" if percent is not None else reading.label
        st.metric(f"Above {window}-session average", text)
        if reading.expected:
            details = f"{reading.above} above · {reading.eligible} of {reading.expected} eligible"
            if previous is not None and previous.percent is not None and percent is not None:
                details += f" · {percent - previous.percent:+.0f} pp in 5 sessions"
            st.caption(details)


def _stress(session: Session) -> None:
    st.subheader("Volatility and credit")
    if session.inputs.stress.empty:
        st.caption("VIX, VIX3M and high-yield spreads are unavailable in this import.")
        proxy = calc.relative(session.total, "HYG", "IEF")
        if proxy.notna().any():
            session.metric("HYG / IEF credit proxy · 20 sessions", proxy, 20)
        return
    available = session.inputs.stress.loc[session.inputs.stress["available_on"].le(session.day)]
    if available.empty:
        st.caption("No stress readings published by this session.")
        return
    latest = available.iloc[-1]
    left, middle, right = st.columns(3)
    left.metric("VIX close", f"{latest['VIX']:.2f}")
    middle.metric("VIX / VIX3M", f"{latest['VIX'] / latest['VIX3M']:.2f}×")
    shift = available["OAS"].diff(20).iloc[-1] * 100
    right.metric("High-yield spread", f"{latest['OAS'] * 100:.0f} bp", signed(shift, " bp over 20 sessions"),
                 delta_color="off")
    st.caption(f"Observation dated {latest.name:%b %d, %Y}.")


def market(session: Session) -> None:
    st.title("U.S. market")
    history = calc.breadth_history(session.inputs, session.split, session.split.index[-max(6, len(session.dates)):])
    gaps = calc.moving_average_gaps(session.split[BENCHMARK])
    move = calc.change(session.split[BENCHMARK], 1).iloc[-1]
    reading = history[50][session.day]
    lead = f"SPY moved {signed(move)} on the session." if pd.notna(move) else "SPY session change is unavailable."
    if reading.label == "Narrow":
        lead += f" Only {reading.percent:.0f}% of eligible members are above their 50-session average."
    elif reading.percent is not None:
        lead += f" {reading.percent:.0f}% of eligible members are above their 50-session average."
    st.write(lead)

    main, evidence = st.columns([3, 1.45], gap="large")
    with main:
        st.subheader("Benchmark performance")
        _return_chart(session, [BENCHMARK, COMPARISON])
        st.subheader("Market participation")
        if reading.expected:
            _breadth_chart(history, session.dates)
        else:
            st.caption("A dated membership snapshot is unavailable for this session.")
            ratio = calc.relative(session.total, "RSP").loc[session.dates]
            if ratio.notna().any():
                charts.lines((ratio / ratio.dropna().iloc[0] * 100).to_frame("RSP / SPY"),
                             "Concentration proxy index", height=155, index_baseline=True)
                st.caption("RSP compares equal-weight performance with cap-weight SPY.")
    with evidence:
        st.subheader("Evidence at the close")
        st.metric("SPY trend", calc.trend(gaps))
        st.caption(f"50-session gap {signed(gaps[50])} · 200-session gap {signed(gaps[200])}")
        sma = session.split[BENCHMARK].rolling(200).mean()
        st.caption(f"200-session average · {signed(calc.change(sma, 20).iloc[-1])} in 20 sessions")
        if COMPARISON in session.split:
            qqq_trend = calc.trend(calc.moving_average_gaps(session.split[COMPARISON]))
            st.caption(f"QQQ trend · {qqq_trend}")
        earlier = session.split.index[-6] if len(session.split) > 5 else None
        _breadth_evidence(history, session.day, earlier)
    _stress(session)


def sector(session: Session, chosen: str, open_stock) -> None:
    st.title("Sector leadership")
    ranking = calc.sector_ranking(session.total)
    left, right = st.columns([1, 1.5], gap="large")
    with left:
        st.subheader("20 sessions vs. SPY")
        charts.sector_bars(ranking)
    with right:
        st.subheader("Relative and absolute returns")
        st.dataframe(ranking, width="stretch", column_config={
            column: st.column_config.NumberColumn(format="%+.2f%%")
            for column in ranking.columns if column != "Sector"
        })
    st.subheader(f"{SECTORS[chosen]} ({chosen})")
    latest = ranking.loc[chosen, "20 sessions"]
    absolute = ranking.loc[chosen, "Absolute, 20 sessions"]
    st.write(f"Over 20 sessions, {chosen} returned {signed(absolute)} and moved {signed(latest)} relative to SPY."
             if pd.notna(latest) else f"{chosen} needs aligned dividend-adjusted closes 20 sessions apart.")
    historic = calc.breadth_history(session.inputs, session.split, session.dates, chosen)
    main, evidence = st.columns([3, 1.45], gap="large")
    with main:
        ratio = calc.relative(session.total, chosen).loc[session.dates].dropna()
        if not ratio.empty:
            charts.lines((ratio / ratio.iloc[0] * 100).reindex(session.dates).to_frame(f"{chosen} / SPY"),
                         "Relative performance index", index_baseline=True)
        if historic[50][session.day].expected:
            _breadth_chart(historic, session.dates)
    with evidence:
        earlier = session.dates[-6] if len(session.dates) > 5 else None
        _breadth_evidence(historic, session.day, earlier)

    members = session.inputs.members_on(session.day)
    symbols = members.loc[members["sector_etf"].eq(chosen), "symbol"].tolist()
    if not symbols:
        return
    ratios = session.total.reindex(columns=symbols).div(session.total[BENCHMARK], axis="index")
    moves = calc.change(ratios, 20).iloc[-1].sort_values(ascending=False)
    count = int(moves.count())
    if count:
        st.caption(f"{int(moves.gt(0).sum())} of {count} eligible members outperformed SPY over 20 sessions. "
                   f"{count} of {len(symbols)} members had comparable prices.")
    with st.expander("Member returns"):
        st.dataframe(moves.round(2).to_frame("20-session return vs. SPY (%)"), width="stretch")
    member = st.selectbox("Sector member", moves.index, key=f"member_{chosen}")
    st.button(f"Open {member} stock detail", on_click=open_stock, args=(member,))


def stock(session: Session, ticker: str) -> None:
    st.title(f"{ticker} stock detail")
    if ticker not in session.close:
        st.info(f"No bars for {ticker} in this dataset.")
        return
    members = session.inputs.members_on(session.day).set_index("symbol")
    sector_etf = members["sector_etf"].get(ticker)
    if ticker == "RIVN" and session.inputs.demo:
        sector_etf = "XLY"
    tickers = [ticker, sector_etf, BENCHMARK] if pd.notna(sector_etf) else [ticker, BENCHMARK]
    history = session.close[ticker]
    last_close = history.iloc[-1]
    move = calc.change(session.split[ticker], 1).iloc[-1]
    main, evidence = st.columns([3, 1.45], gap="large")
    with main:
        st.subheader("Performance against peers")
        _return_chart(session, tickers)
        if pd.isna(sector_etf):
            st.caption("Sector mapping is unavailable for this stock on the selected session.")
        else:
            sector_move = calc.change(calc.relative(session.total, ticker, sector_etf), 20).iloc[-1]
            st.caption(f"20 sessions vs. {sector_etf} · {signed(sector_move)}")
    with evidence:
        st.subheader("Price at the close")
        st.metric("Quoted close", f"${last_close:,.2f}" if pd.notna(last_close) else "Unavailable")
        st.metric("Session change", signed(move))
        split = session.split[ticker]
        gaps = calc.moving_average_gaps(split)
        st.metric("Price trend", calc.trend(gaps))
        st.caption("Distance from moving averages · " + " · ".join(
            f"{window} sessions {signed(value)}" for window, value in gaps.items()
        ))
        if split.tail(200).count() < 200:
            st.caption(f"{split.tail(200).count()} of 200 split-adjusted closes available.")
        session.metric("20 sessions vs. SPY", calc.relative(session.total, ticker), 20)

    st.subheader("Business health")
    filings = session.inputs.filings
    if not filings.empty:
        cutoff = pd.Timestamp.combine(session.day.date(), time(16, 30)).tz_localize(NEW_YORK)
        filings = filings.loc[filings["symbol"].eq(ticker) & filings["available_at"].le(cutoff)]
    if filings.empty:
        st.info("No verified financial statement is available in this dataset by the selected cutoff.")
        return
    filing = filings.sort_values(["period", "available_at"]).iloc[-1]
    margin = filing.operating_income / filing.revenue * 100
    prior_margin = filing.prior_operating_income / filing.prior_revenue * 100
    growth = (filing.revenue / filing.prior_revenue - 1) * 100
    if move > 0 and margin < prior_margin:
        st.write("The stock rose on the session while operating margin was lower year over year.")
    revenue_col, margin_col, cash_col, pe_col = st.columns(4)
    revenue_col.metric("Quarterly revenue YoY", signed(growth))
    margin_col.metric("Operating margin", f"{margin:.1f}%", signed(margin - prior_margin, " pp YoY"),
                      delta_color="off")
    cash_col.metric("Trailing free cash flow", f"${(filing.ttm_cfo - filing.ttm_capex) / 1000:,.1f}B")
    pe = "Unavailable"
    if filing.ttm_eps < 0:
        pe = "Loss-making"
    elif filing.ttm_eps > 0 and pd.notna(last_close):
        pe = f"{last_close / filing.ttm_eps:.1f}×"
    pe_col.metric("Trailing P/E", pe)
    st.caption(f"Demo period ended {filing.period}. Available {filing.available_at:%b %d, %Y at %I:%M %p ET}.")

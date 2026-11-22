import pandas as pd
import streamlit as st

from . import analytics as calc, charts
from . import research_views
from .presentation import quantity_markdown
from .scope import BENCHMARK, COMPARISON, SECTORS
from .stress_view import market_stress
from .views import Session, price_and_volume, price_heading, return_chart, signed


def _breadth_chart(history: dict, dates: pd.DatetimeIndex) -> None:
    values = pd.DataFrame({
        f"{window}-session average": {day: reading.percent for day, reading in series.items()}
        for window, series in history.items()
    }).reindex(dates)
    if values.notna().any().any():
        charts.lines(values, "Members above average (%)", height=265, domain=[0, 100])


def _breadth_evidence(history: dict, day: pd.Timestamp, earlier: pd.Timestamp | None) -> None:
    for window, readings in history.items():
        reading = readings[day]
        previous = readings.get(earlier)
        percent = reading.percent
        text = f"{percent:.0f}% · {reading.label}" if percent is not None else reading.label
        st.metric(f"Above {window}-session average", quantity_markdown(text))
        if reading.expected:
            details = f"{reading.above} above · {reading.eligible} of {reading.expected} eligible"
            if previous is not None and previous.percent is not None and percent is not None:
                details += f" · {percent - previous.percent:+.0f} pp in 5 sessions"
            st.caption(details)


def _breadth_data(members: pd.DataFrame) -> pd.DataFrame:
    return members.set_index("symbol")[["sector_etf", "close", *calc.BREADTH_WINDOWS]].rename(columns={
        "sector_etf": "Sector ETF", "close": "Split-adjusted close",
        50: "50-session average", 200: "200-session average",
    }).rename_axis("Symbol")


def _sources(session: Session) -> None:
    inputs = session.inputs
    metadata = session.manifest["sources"] if session.manifest else {}
    recent_members = inputs.members.loc[inputs.members["session"].le(session.day), "session"].max()
    on_date = inputs.members_on(session.day)
    with st.expander("Session sources and coverage"):
        st.write(f"Daily bars: {inputs.source}. Selected session {session.day:%b %d, %Y} (New York).")
        for ticker in (BENCHMARK, COMPARISON):
            prices = session.split.get(ticker)
            latest = prices.last_valid_index() if prices is not None else None
            stamp = f"{latest:%b %d, %Y}" if latest is not None else "unavailable"
            st.caption(f"{ticker} latest split-adjusted close: {stamp}.")
        coverage = session.total.reindex(columns=list(SECTORS)).loc[session.day].notna()
        st.caption(f"{coverage.sum()} of {len(SECTORS)} sector ETFs have a dividend-adjusted close on this session.")
        if not coverage.all():
            st.caption(f"Missing ETF closes: {', '.join(coverage[~coverage].index)}.")
        if pd.notna(recent_members):
            st.write(f"Membership: {inputs.membership_source}. Latest dated list: {recent_members:%b %d, %Y}.")
        if on_date.empty:
            st.caption("No membership list applies on this date. Earlier lists remain on their own dates.")
        else:
            st.caption(f"{len(on_date)} share classes on this date, with one vote per share class. "
                       "Breadth requires a split-adjusted close for every session in the moving average. "
                       "Labels require 90% coverage. Broad starts at 60%; narrow is 40% or less.")
        for name in ("prices", "membership"):
            published = metadata.get(name, {}).get("published_at")
            if published:
                stamp = pd.Timestamp(published)
                st.caption(f"{name.capitalize()} export published {stamp:%b %d, %Y at %I:%M %p %Z}.")


def _concentration_proxy(session: Session) -> None:
    st.caption("Member breadth is unavailable for this session without a dated membership snapshot.")
    ratio = calc.relative(session.total, "RSP").loc[session.dates]
    available = ratio.dropna()
    if available.empty:
        st.caption("The concentration proxy needs dividend-adjusted RSP and SPY closes on a common session.")
        return
    charts.lines(ratio.div(available.iloc[0]).mul(100).to_frame("RSP / SPY"),
                 "Concentration proxy index", height=155, index_baseline=True)
    st.caption(f"RSP compares equal-weight performance with cap-weight SPY. "
               f"Latest common close in this window: {available.index[-1]:%b %d, %Y}.")


def _market_leadership(session: Session, open_sector) -> None:
    st.subheader("Sector drilldown")
    ranking = calc.sector_ranking(session.total)
    moves = ranking["20 sessions"]
    leaders = ranking.loc[moves.gt(0)].head(3)
    laggards = ranking.loc[moves.lt(0)].tail(3)
    selected = pd.concat([leaders, laggards])
    if not selected.empty:
        extremes = pd.concat([leaders.head(1), laggards.tail(1)])
        snapshot = " / ".join(f"{ticker} {signed(value)}" for ticker, value in extremes["20 sessions"].items())
        st.caption(f"{snapshot} vs. SPY over 20 sessions.")
    options = list(ranking.index)
    prior = st.session_state.get("sector_choice", options[0])
    ticker = st.selectbox("Sector to inspect", options, index=options.index(prior),
                          format_func=lambda value: f"{SECTORS[value]} ({value})", key="market_sector")
    st.button("Open sector detail", on_click=open_sector, args=(ticker,))
    if selected.empty:
        st.caption("No sectors have a positive or negative 20-session relative return for this date.")
    else:
        with st.expander("Sector leaders and laggards"):
            _ranking_table(selected[["Rank", "Sector", "20 sessions", "Absolute, 20 sessions"]])


def market(session: Session, open_sector, details) -> None:
    dates = session.split.index[-max(6, len(session.dates)):]
    earlier = dates[-6] if len(dates) >= 6 else None
    members = calc.breadth_members(session.inputs, session.split, dates)
    history = calc.breadth_readings(members, dates)
    gaps = calc.moving_average_gaps(session.split[BENCHMARK])
    move = calc.change(session.split[BENCHMARK], 1).iloc[-1]
    price_heading("U.S. market", "SPY benchmark", session.close[BENCHMARK].iloc[-1], move)
    reading = history[50][session.day]
    lead = f"SPY moved {signed(move)} on the session." if pd.notna(move) else "SPY session change is unavailable."
    if reading.percent is not None:
        qualifier = "Only " if reading.label == "Narrow" else ""
        lead += f" {qualifier}{reading.percent:.0f}% of eligible members are above their 50-session average."
    st.write(lead)

    price_chart, performance, participation, stress, internals = st.tabs(
        ["Price & volume", "Performance", "Participation", "Volatility & credit", "Internals"]
    )
    with price_chart:
        price_and_volume(session, BENCHMARK)
    with performance:
        return_chart(session, [BENCHMARK, COMPARISON])
    with participation:
        if session.inputs.membership_source:
            st.caption(session.inputs.membership_source)
        _breadth_chart(history, session.dates)
        if not reading.expected:
            _concentration_proxy(session)
        else:
            with st.expander("Member closes and moving averages"):
                st.dataframe(_breadth_data(members.loc[members["session"].eq(session.day)]), width="stretch")
    with stress:
        market_stress(session)
    with internals:
        research_views.market(session)

    with details:
        with st.container(key="trend-evidence"):
            _market_trend(session, gaps)
        with st.container(key="breadth-evidence"):
            st.subheader("Breadth over time")
            _breadth_evidence(history, session.day, earlier)
        with st.container(key="sector-evidence"):
            _market_leadership(session, open_sector)
            _sources(session)


def _market_trend(session: Session, gaps: dict[int, float]) -> None:
    st.subheader("Trend at the close")
    spy_trend = calc.trend(gaps)
    st.metric("SPY trend", spy_trend)
    st.caption(f"50-session gap {signed(gaps[50])} · 200-session gap {signed(gaps[200])}")
    sma = session.split[BENCHMARK].rolling(200).mean()
    st.caption(f"200-session average · {signed(calc.change(sma, 20).iloc[-1])} in 20 sessions. "
               "Trend uses split-adjusted closes.")
    if COMPARISON in session.split:
        qqq_gaps = calc.moving_average_gaps(session.split[COMPARISON])
        qqq_trend = calc.trend(qqq_gaps)
        st.caption(f"QQQ trend · {qqq_trend}. 50-session gap {signed(qqq_gaps[50])} · "
                   f"200-session gap {signed(qqq_gaps[200])}.")
        if spy_trend != qqq_trend and "Incomplete history" not in (spy_trend, qqq_trend):
            st.caption("QQQ and SPY have different trend readings.")


def _ranking_table(ranking: pd.DataFrame) -> None:
    st.dataframe(ranking, width="stretch", column_config={
        column: st.column_config.NumberColumn(label=f"{column} (%)", format="%+.2f")
        for column in ranking.columns if "sessions" in column
    } | {"Breadth (50)": st.column_config.NumberColumn(label="Breadth (50) (%)", format="%.1f"),
         "Eligible members": {"alignment": "right"}})


def _sector_summary(chosen: str, relative: float, absolute: float) -> None:
    if pd.notna(relative):
        comparison = "outperformed" if relative > 0 else "trailed" if relative < 0 else "matched"
        action = "fell" if absolute < 0 else "rose" if absolute > 0 else "was flat"
        st.write(f"{chosen} {action} ({signed(absolute)}) over 20 sessions and {comparison} SPY "
                 f"({signed(relative)} relative).")
    elif pd.notna(absolute):
        st.write(f"{chosen} returned {signed(absolute)} over 20 sessions. The comparison needs SPY closes "
                 "on both sessions.")
    else:
        st.write(f"{chosen} needs dividend-adjusted closes 20 sessions apart.")


def sector(session: Session, chosen: str, open_stock, details) -> None:
    st.title("Sector leadership")
    dates = session.split.index[-max(6, len(session.dates)):]
    earlier = dates[-6] if len(dates) >= 6 else None
    members = calc.breadth_members(session.inputs, session.split, dates)
    today = members.loc[members["session"].eq(session.day)]
    by_sector = {ticker: calc.breadth_count(rows, 50) for ticker, rows in today.groupby("sector_etf")}
    ranking = calc.sector_ranking(session.total)
    ranking["Breadth (50)"] = {ticker: count.percent for ticker, count in by_sector.items()}
    ranking["Eligible members"] = {ticker: f"{count.eligible} / {count.expected}"
                                   for ticker, count in by_sector.items()}
    _sector_summary(chosen, ranking.at[chosen, "20 sessions"], ranking.at[chosen, "Absolute, 20 sessions"])
    historic = calc.breadth_readings(members, dates, chosen)
    ranks, performance, participation, research = st.tabs(
        ["Rankings", "Performance", "Participation", "Rotation & news"]
    )
    with ranks:
        st.caption(f"{ranking['Rank'].count()} of {len(SECTORS)} sectors ranked by 20-session return vs. SPY.")
        charts.sector_bars(ranking)
        with st.expander("Relative and absolute returns"):
            _ranking_table(ranking)
            st.caption("Relative returns measure changes in the dividend-adjusted ETF / SPY ratio. "
                       "Breadth uses dated members.")
    with performance:
        ratio = calc.relative(session.total, chosen).loc[session.dates]
        valid = ratio.dropna()
        if not valid.empty:
            charts.lines(ratio.div(valid.iloc[0]).mul(100).to_frame(f"{chosen} / SPY"),
                         "Relative performance index", height=325, index_baseline=True)
        else:
            st.caption(f"No common dividend-adjusted closes for {chosen} and SPY in this window.")
    with participation:
        if session.inputs.membership_source:
            st.caption(session.inputs.membership_source)
        _breadth_chart(historic, session.dates)
        if not historic[50][session.day].expected:
            st.caption(f"No dated members are mapped to {chosen} on the selected session.")
    with research:
        research_views.sector(session, chosen)

    with details:
        _sector_members(session, today, chosen, open_stock)
        st.subheader("Sector breadth")
        _breadth_evidence(historic, session.day, earlier)
        _sources(session)


def _sector_members(session: Session, today: pd.DataFrame, chosen: str, open_stock) -> None:
    selected = today.loc[today["sector_etf"].eq(chosen)]
    if selected.empty:
        st.caption(f"No members are mapped to {chosen} on the selected session.")
        return
    moves = calc.member_returns(session.total, selected["symbol"])
    count = int(moves.count())
    st.subheader("Sector members")
    member = st.selectbox("Sector member", moves.index, key=f"member_{chosen}")
    st.button(f"Open {member} stock detail", on_click=open_stock, args=(member,))
    if count:
        leaders = int(moves.gt(0).sum())
        st.caption(f"{leaders} of {count} eligible members ({leaders / count:.0%}) outperformed SPY over "
                   f"20 sessions. Comparable prices were available for {count} of {len(selected)} members.")
    else:
        st.caption(f"0 of {len(selected)} members have comparable closes 20 sessions apart.")
    with st.expander("Member returns and moving averages"):
        data = _breadth_data(selected).reindex(moves.index).drop(columns="Sector ETF")
        data.insert(0, "20-session return vs. SPY (%)", moves)
        st.dataframe(data, width="stretch")

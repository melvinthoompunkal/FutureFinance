import pandas as pd
import streamlit as st

from . import analytics as calc, charts
from .presentation import quantity_markdown
from .stress import CREDIT_LOOKBACK, VIX_LOOKBACK, stress_history, vix_percentile
from .views import Session, signed


def _observation(session: Session, series: str, day: pd.Timestamp | None) -> str:
    source = session.inputs.stress_sources.get(series, "Source unavailable")
    return f"{day:%b %d, %Y} · {source}" if day is not None else f"{source} · No reading by the cutoff."


def _credit_proxy(session: Session) -> None:
    proxy = calc.relative(session.total, "HYG", "IEF")
    latest = proxy.last_valid_index()
    if latest is None:
        st.caption("The credit proxy needs dividend-adjusted HYG and IEF closes on a common session.")
        return
    move = calc.change(proxy, CREDIT_LOOKBACK).loc[latest]
    st.metric("HYG / IEF credit proxy", quantity_markdown(signed(move)))
    st.caption(f"20-session change in the dividend-adjusted ETF ratio through {latest:%b %d, %Y}. "
               f"Price source: {session.inputs.source}.")
    visible = proxy.loc[session.dates]
    if visible.notna().any():
        indexed = visible.div(visible.dropna().iloc[0]).mul(100)
        charts.lines(indexed.to_frame("HYG / IEF"), "Credit proxy index", height=155, index_baseline=True)


def market_stress(session: Session) -> None:
    st.subheader("Volatility and credit")
    values = stress_history(session.inputs.stress, session.day)
    vix_day = values["VIX"].last_valid_index()
    three_month_day = values["VIX3M"].last_valid_index()
    pair_day = values["VIX / VIX3M"].last_valid_index()
    spread_day = values["OAS"].last_valid_index()
    left, middle, right = st.columns(3)
    with left:
        vix = values.at[vix_day, "VIX"] if vix_day is not None else None
        st.metric("VIX close", f"{vix:.2f}" if vix is not None else "Unavailable")
        st.caption(_observation(session, "VIX", vix_day))
        if vix_day is not None:
            percentile, count = vix_percentile(values["VIX"], vix_day)
            text = f"Percentile rank {percentile:.0f}" if percentile is not None else "Percentile unavailable"
            st.caption(f"{text} across {count} of the trailing {VIX_LOOKBACK} sessions with a VIX close. "
                       "Ties count as half an observation.")
    with middle:
        ratio = values.at[pair_day, "VIX / VIX3M"] if pair_day is not None else None
        st.metric("VIX / VIX3M", quantity_markdown(f"{ratio:.2f}×" if ratio is not None else "Unavailable"))
        if three_month_day is not None:
            st.caption(f"VIX3M close {values.at[three_month_day, 'VIX3M']:.2f}. "
                       f"{_observation(session, 'VIX3M', three_month_day)}")
        else:
            st.caption(_observation(session, "VIX3M", None))
        if pair_day is not None:
            interpretation = " Near-term implied volatility is higher." if ratio > 1 else ""
            st.caption(f"Matched on {pair_day:%b %d, %Y} using {values.at[pair_day, 'VIX']:.2f} "
                       f"÷ {values.at[pair_day, 'VIX3M']:.2f}.{interpretation}")
        else:
            st.caption("The ratio needs VIX and VIX3M closes from the same session.")
    with right:
        spread = values.at[spread_day, "High-yield spread"] if spread_day is not None else None
        st.metric("High-yield spread", quantity_markdown(f"{spread:.0f} bp" if spread is not None else "Unavailable"))
        st.caption(_observation(session, "OAS", spread_day))
        if spread_day is not None:
            shift = values.at[spread_day, "Spread change"]
            if pd.notna(shift):
                prior = values.loc[:spread_day].index[-CREDIT_LOOKBACK - 1]
                direction = "widening" if shift > 0 else "narrowing" if shift < 0 else "steady"
                st.caption(f"Credit spreads {direction}. {signed(shift, ' bp')} vs. {prior:%b %d, %Y} "
                           f"({CREDIT_LOOKBACK} sessions earlier).")
            else:
                st.caption(f"Change needs a spread reading exactly {CREDIT_LOOKBACK} sessions earlier.")
    if spread_day is None:
        _credit_proxy(session)

    panels = [
        ("VIX and VIX3M", ["VIX", "VIX3M"], "Implied volatility (index points)"),
        ("Term structure", ["VIX / VIX3M"], "VIX / VIX3M (ratio)"),
        ("High-yield spread", ["High-yield spread"], "High-yield spread (bp)"),
    ]
    visible = values.reindex(session.dates)
    available = [panel for panel in panels if visible[panel[1]].notna().any().any()]
    if available:
        tabs = st.tabs([name for name, _, _ in available])
        for tab, (_, columns, unit) in zip(tabs, available, strict=True):
            with tab:
                charts.lines(visible[columns], unit, height=155)

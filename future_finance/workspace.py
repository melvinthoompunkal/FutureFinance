from base64 import b64encode
from html import escape
from pathlib import Path

import pandas as pd
import streamlit as st

from . import analytics as calc
from .charts import REFERENCE
from .presentation import quantity_html
from .scope import BENCHMARK, COMPARISON, SECTORS
from .views import Session, format_volume, signed

STYLE = Path(__file__).with_name("workspace.css")
MARKET_PROXIES = {BENCHMARK: "S&P 500", COMPARISON: "Nasdaq-100", "DIA": "Dow 30", "IWM": "Russell 2000"}


def session_status(mode: str, source: str, membership: str) -> None:
    with st.container(key="sourcebar"):
        info, coverage = st.columns([2, 1], vertical_alignment="center")
        info.info(f"**{mode}** · {source}" if source else f"**{mode}**")
        coverage.caption(membership or "Membership unavailable")


def _tone(move: float) -> str:
    if pd.isna(move) or move == 0:
        return "flat"
    return "gain" if move > 0 else "loss"


def _sparkline(series: pd.Series) -> str:
    valid = series.dropna()
    if len(valid) < 2:
        return ""
    low = valid.min()
    span = valid.max() - low
    points = pd.Series({index: f"{2 + index * 84 / (len(series) - 1):.1f},"
                               f"{30 - 26 * (price - low) / span if span else 17:.1f}"
                        for index, price in enumerate(series) if pd.notna(price)})
    lines = []
    for _, segment in points.groupby(points.index.to_series().diff().ne(1).cumsum()):
        if len(segment) >= 2:
            lines.append(f'<polyline points="{" ".join(segment)}" />')
    if not lines:
        return ""
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 88 34" fill="none" stroke="{REFERENCE}" '
           f'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">{"".join(lines)}</svg>')
    encoded = b64encode(svg.encode("ascii")).decode("ascii")
    return f'<img class="ff-sparkline" src="data:image/svg+xml;base64,{encoded}" alt="">'


def _breadth_summary(session: Session) -> str:
    members = calc.breadth_members(session.inputs, session.split.tail(200), session.dates[-1:])
    heading = '<div class="ff-breadth-heading"><h2>Market breadth</h2><span>End of day</span></div>'
    if members.empty:
        content = '<p class="ff-breadth-note">No dated membership for this session.</p>'
    else:
        changes = calc.change(session.split.reindex(columns=members["symbol"]).tail(2), 1).iloc[-1].dropna()
        coverage = f'{len(changes):,} of {len(members):,} members with comparable closes'
        if changes.empty:
            content = '<p class="ff-breadth-note">No members have comparable session closes.</p>'
        else:
            up, down = int(changes.gt(0).sum()), int(changes.lt(0).sum())
            flat = len(changes) - up - down
            content = (f'<div class="ff-breadth-counts"><span>Advancers <strong class="ff-gain">{up:,}</strong></span>'
                       f'<span>Decliners <strong class="ff-loss">{down:,}</strong></span></div>'
                       '<div class="ff-breadth-track" aria-hidden="true">'
                       f'<span style="width:{up / len(changes):.3%}"></span>'
                       f'<span style="width:{down / len(changes):.3%}"></span></div>'
                       f'<p class="ff-breadth-note">{coverage}{f" · {flat:,} unchanged" if flat else ""}</p>')
    averages = []
    for window in calc.BREADTH_WINDOWS:
        reading = calc.breadth_count(members, window)
        value = reading.percent
        display = f"{value:.0f}%" if value is not None else "—"
        note = f"{reading.eligible:,} of {reading.expected:,} members eligible"
        averages.append(f'<div><dt>Above {window}D avg.</dt><dd title="{note}">{quantity_html(display)}</dd></div>')
    return f'<article class="ff-breadth">{heading}{content}<dl>{"".join(averages)}</dl></article>'


def market_snapshot(session: Session) -> None:
    closes = session.close.reindex(columns=MARKET_PROXIES).iloc[-1]
    prices = session.split.reindex(columns=MARKET_PROXIES).tail(20)
    changes = calc.change(prices, 1).iloc[-1]
    quotes = []
    for symbol, label in MARKET_PROXIES.items():
        close, move = closes[symbol], changes[symbol]
        tone = _tone(move)
        price = f"${close:,.2f}" if pd.notna(close) else "—"
        delta = signed(move) if pd.notna(move) else "—"
        quotes.append(f'<article class="ff-market-quote" aria-label="{escape(label)} ETF proxy ({symbol})">'
                      f'<div class="ff-market-label"><h2>{symbol}</h2><span>{escape(label)}</span></div>'
                      f'<div><div class="ff-market-price" aria-label="Quoted close {price}">{quantity_html(price)}</div>'
                      f'<div class="ff-market-delta ff-{tone}" aria-label="Session change {delta}">'
                      f'{quantity_html(delta)}</div></div>'
                      f'{_sparkline(prices[symbol])}</article>')
    st.html('<section class="ff-snapshot" aria-label="Market snapshot">'
            '<div class="ff-market-strip" role="group" aria-label="Benchmark ETF quotes">'
            f'{"".join(quotes)}</div>{_breadth_summary(session)}</section>')


def sector_leadership(session: Session) -> None:
    moves = calc.change(session.split.reindex(columns=SECTORS).tail(2), 1).iloc[-1].dropna()
    with st.container(key="sector-leadership"):
        st.subheader("Sector leadership")
        if moves.empty:
            st.caption("Sector ETFs need closes on consecutive sessions.")
            return
        ranked = moves.sort_values(ascending=False, kind="stable")
        extremes = pd.concat([ranked.head(3), ranked.iloc[3:].tail(2)])
        scale = extremes.abs().max()
        rows = []
        for symbol, move in extremes.items():
            width = abs(move) / scale if scale else 0
            rows.append(f'<li><span>{SECTORS[symbol]}</span>'
                        f'<span class="ff-sector-track" aria-hidden="true">'
                        f'<span class="ff-{_tone(move)}" style="width:{width:.3%}"></span></span>'
                        f'<strong class="ff-{_tone(move)}">{quantity_html(signed(move))}</strong></li>')
        st.html('<p class="ff-sector-period">Daily ETF returns</p>'
                f'<ul class="ff-sector-moves" aria-label="Sector ETF session returns">{"".join(rows)}</ul>')


def watchlist_quotes(session: Session, symbols: list[str], selected: str | None) -> None:
    quotes = session.inputs.bars.loc[session.inputs.bars["session"].eq(session.day)].set_index("symbol")
    quotes = quotes.reindex(symbols)
    changes = calc.change(session.split.reindex(columns=symbols).tail(2), 1).iloc[-1]
    rows = []
    for symbol in symbols:
        close, volume = quotes.loc[symbol, ["close", "volume"]]
        move = changes[symbol]
        price = f"${close:,.2f}" if pd.notna(close) else "—"
        change = signed(move) if pd.notna(move) else "—"
        active = ' class="ff-selected-quote"' if symbol == selected else ""
        rows.append(f'<tr{active}><th scope="row">{escape(symbol)}</th>'
                    f'<td>{quantity_html(price)}</td><td class="ff-{_tone(move)}">{quantity_html(change)}</td>'
                    f'<td>{quantity_html(format_volume(volume))}</td></tr>')
    st.html('<div class="ff-watchlist-scroll" tabindex="0" role="region" aria-label="Watchlist quote table">'
            '<table class="ff-quotes">'
            '<thead><tr><th scope="col">Symbol</th><th scope="col">Close</th>'
            '<th scope="col">Day</th><th scope="col">Volume</th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div>')

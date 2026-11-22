from html import escape
from pathlib import Path

import pandas as pd
import streamlit as st

from . import analytics as calc
from .views import Session, signed

STYLE = Path(__file__).with_name("workspace.css")


def watchlist_quotes(session: Session, symbols: list[str], selected: str | None) -> None:
    closes = session.close.reindex(columns=symbols).iloc[-1]
    changes = calc.change(session.split.reindex(columns=symbols), 1).iloc[-1]
    rows = []
    for symbol in symbols:
        close, move = closes[symbol], changes[symbol]
        price = f"${close:,.2f}" if pd.notna(close) else "—"
        change = signed(move) if pd.notna(move) else "—"
        tone = "gain" if move > 0 else "loss" if move < 0 else "flat"
        active = ' class="ff-selected-quote"' if symbol == selected else ""
        rows.append(f'<tr{active}><th scope="row">{escape(symbol)}</th>'
                    f'<td>{price}</td><td class="ff-{tone}">{change}</td></tr>')
    st.html('<table class="ff-quotes" aria-label="Watchlist closes and session changes">'
            '<thead><tr><th scope="col">Symbol</th><th scope="col">Close</th>'
            '<th scope="col">Day</th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table>')

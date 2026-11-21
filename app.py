from pathlib import Path
import sqlite3

import duckdb
import pandas as pd
import streamlit as st

from future_finance.archive import Archive
from future_finance.demo import make_demo
from future_finance.inputs import import_bundle
from future_finance.scope import SECTORS, read_watchlist
from future_finance import views

ROOT = Path(__file__).resolve().parent
LOCAL_DATA = ROOT / "data"


@st.cache_data(show_spinner=False)
def demo_data():
    return make_demo()


@st.cache_data(show_spinner=False)
def local_data(folder: Path, modified: tuple[int, ...]):
    return import_bundle(folder)


@st.cache_data(show_spinner=False)
def archived_data(folder: Path, version: int):
    return Archive(folder).load(version)


def open_stock(ticker: str) -> None:
    st.session_state["stock_choice"] = ticker
    st.session_state["view"] = "Stock"


def remember(widget_key: str, state_key: str) -> None:
    st.session_state[state_key] = st.session_state[widget_key]


def choose(label: str, options, key: str, default: str, format_func=str) -> str:
    selected = st.session_state.get(key, default)
    return st.selectbox(
        label, options, index=options.index(selected) if selected in options else 0,
        format_func=format_func, key=f"{key}_selector", on_change=remember,
        args=(f"{key}_selector", key),
    )


st.set_page_config(page_title="FutureFinance", page_icon="📈", layout="wide")
st.markdown("""
<style>
[data-testid="stMainBlockContainer"] { max-width: 1260px; padding-top: 2rem; }
[data-testid="stHeader"] { background: transparent; }
h1, h2, h3 { letter-spacing: -.035em; }
[data-testid="stMetricValue"], [data-testid="stMetricDelta"] { font-variant-numeric: tabular-nums; }
[data-testid="stMetricValue"] { font-size: clamp(1.2rem, 2.3vw, 1.85rem); white-space: normal; }
[data-testid="stMetricLabel"] { min-height: auto; margin-bottom: .15rem; }
[data-testid="stMetric"] { padding: .4rem 0; }
[data-testid="stCaptionContainer"] { color: #455771; }
.masthead { font-size: 1.12rem; font-weight: 750; letter-spacing: -.025em; color: #142746; }
</style>
<div class="masthead">FutureFinance</div>
""", unsafe_allow_html=True)

try:
    watchlist = read_watchlist(ROOT / "watchlist.txt")
    archive = Archive(LOCAL_DATA / "archive")
    publications = st.session_state.get("archive_versions") or archive.published_sessions()
    if publications:
        st.session_state["archive_versions"] = publications
        published = [pd.Timestamp(day) for day in publications]
    else:
        files = [LOCAL_DATA / name for name in ("source.json", "bars.csv", "membership.csv")]
        if any(path.is_file() for path in files):
            updated = tuple(path.stat().st_mtime_ns if path.is_file() else 0 for path in files)
            inputs = local_data(LOCAL_DATA, updated)
        else:
            inputs = demo_data()
        dates = inputs.prices("close").index
        published = dates[-30:][::-1] if inputs.demo else dates[::-1]
except (OSError, ValueError, sqlite3.Error) as error:
    st.error(f"Could not load dashboard inputs. {error}")
    st.stop()

nav, day_control, window_control = st.columns([2.2, 1.45, 1])
with nav:
    view = st.radio("View", ["Market", "Sector", "Stock"], horizontal=True, key="view")
with day_control:
    day = st.selectbox("Session (New York)", published, format_func=lambda value: value.strftime("%b %d, %Y"))
with window_control:
    window = st.selectbox("Chart window", [20, 60, 120, 252], index=1,
                          format_func=lambda value: f"{value} sessions")

if publications:
    try:
        inputs, manifest = archived_data(archive.root, publications[day.date()])
    except (OSError, ValueError, duckdb.Error, sqlite3.Error) as error:
        st.error(f"Could not read the published session. {error}")
        st.stop()
    st.info(f"Archived session from {inputs.source}. Version {manifest['version']} · {manifest['vintage'].capitalize()}.")
elif inputs.demo:
    st.info("Phase 1 preview with synthetic prices, constituents and financial statements.")
else:
    st.info(f"Local price import from {inputs.source}.")
universe = inputs.membership_source or "Membership unavailable"
st.caption(f"SPY benchmark and QQQ comparison · {universe}")

split = inputs.prices("split_close").loc[:day]
total = inputs.prices("total_return_close").loc[:day]
session = views.Session(inputs, split, total, inputs.prices("close").loc[:day],
                        pd.DatetimeIndex(split.index[-window:]))

if view == "Market":
    views.market(session)
elif view == "Sector":
    sector = choose("Sector", list(SECTORS), "sector_choice", "XLK",
                    lambda ticker: f"{SECTORS[ticker]} ({ticker})")
    views.sector(session, sector, open_stock)
else:
    stock_choice = st.session_state.get("stock_choice")
    options = list(dict.fromkeys(watchlist + ([stock_choice] if stock_choice else [])))
    if options:
        views.stock(session, choose("Watchlist symbol", options, "stock_choice", options[0]))
    else:
        st.info("Add a symbol to watchlist.txt or open a stock from a sector.")

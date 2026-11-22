from pathlib import Path
import sqlite3

import duckdb
import pandas as pd
import streamlit as st

from future_finance.archive import Archive
from future_finance.demo import make_demo
from future_finance.inputs import BUNDLE_FILES, import_bundle
from future_finance.scope import SECTORS, read_watchlist
from future_finance import market_views, views, workspace

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


def open_watchlist_stock() -> None:
    ticker = st.session_state["watchlist_lookup"]
    if ticker is not None:
        open_stock(ticker)


def open_sector(ticker: str) -> None:
    st.session_state["sector_choice"] = ticker
    st.session_state["view"] = "Sector"


def remember(widget_key: str, state_key: str) -> None:
    st.session_state[state_key] = st.session_state[widget_key]


def choose(label: str, options, key: str, default: str, format_func=str) -> str:
    selected = st.session_state.get(key, default)
    return st.selectbox(
        label, options, index=options.index(selected) if selected in options else 0,
        format_func=format_func, key=f"{key}_selector", on_change=remember,
        args=(f"{key}_selector", key),
    )


st.set_page_config(page_title="FutureFinance", layout="wide")
st.html(workspace.STYLE)

try:
    watchlist = read_watchlist(ROOT / "watchlist.txt")
    archive = Archive(LOCAL_DATA / "archive")
    publications = st.session_state.get("archive_versions") or archive.published_sessions()
    if publications:
        st.session_state["archive_versions"] = publications
        published = [pd.Timestamp(day) for day in publications]
    else:
        files = [LOCAL_DATA / name for name in BUNDLE_FILES]
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

with st.container(key="toolbar"):
    brand, nav, day_control, window_control = st.columns([1, 2, 1, .85], vertical_alignment="center")
    brand.html('<div class="ff-brand">FutureFinance</div>')
    with nav:
        view = st.radio("View", ["Market", "Sector", "Stock"], horizontal=True, key="view",
                        format_func={"Market": "Market", "Sector": "Sectors", "Stock": "Stocks"}.get,
                        label_visibility="collapsed")
    with day_control:
        day = st.selectbox("Archived session (ET)" if publications else "Session (ET)", published,
                           format_func=lambda value: value.strftime("%b %d, %Y"), key="session_day")
    with window_control:
        window = st.selectbox("Chart window", [20, 60, 120, 252], index=1,
                              format_func=lambda value: f"{value} sessions")

manifest = None
if publications:
    try:
        inputs, manifest = archived_data(archive.root, publications[day.date()])
    except (OSError, ValueError, duckdb.Error, sqlite3.Error) as error:
        st.error(f"Could not read the published session. {error}")
        st.stop()
    mode = "Archive replay"
    source = f"{inputs.source} · Version {manifest['version']} · {manifest['vintage'].capitalize()}"
elif inputs.demo:
    mode, source = "Synthetic preview", ""
else:
    mode, source = "Local price import", inputs.source

split = inputs.prices("split_close").loc[:day]
total = inputs.prices("total_return_close").loc[:day]
session = views.Session(inputs, split, total, inputs.prices("close").loc[:day],
                        pd.DatetimeIndex(split.index[-window:]), manifest)
workspace.session_status(mode, source, inputs.membership_source)
workspace.market_snapshot(session)

with st.container(key="workspace"):
    main = st.container(key="chart-panel")
    rail = st.container(key="left-rail")
    details = st.container(key="evidence-panel")
    ticker = None
    with rail:
        with st.container(key="watchlist-panel"):
            st.subheader("Watchlist")
            if view == "Stock":
                stock_choice = st.session_state.get("stock_choice")
                options = list(dict.fromkeys(watchlist + ([stock_choice] if stock_choice else [])))
                if options:
                    ticker = choose("Watchlist symbol", options, "stock_choice", options[0])
            elif watchlist:
                st.selectbox("Watchlist symbol", watchlist, index=None, placeholder="Find a symbol",
                             label_visibility="collapsed",
                             key="watchlist_lookup", on_change=open_watchlist_stock)
            if watchlist:
                workspace.watchlist_quotes(session, watchlist, ticker)
            else:
                st.caption("Add symbols to watchlist.txt.")
        workspace.sector_leadership(session)

    with main:
        if view == "Market":
            market_views.market(session, open_sector, details)
        elif view == "Sector":
            with details:
                st.subheader("Sector detail")
                sector = choose("Sector", list(SECTORS), "sector_choice", "XLK",
                                lambda ticker: f"{SECTORS[ticker]} ({ticker})")
            market_views.sector(session, sector, open_stock, details)
        elif ticker:
            views.stock(session, ticker, details)
        else:
            st.title("Stock detail")
            st.info("Add a symbol to watchlist.txt or open a stock from a sector.")

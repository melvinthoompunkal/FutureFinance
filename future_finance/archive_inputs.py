"""Normalize dated price exports for publication and preserve ticker identity."""

from collections import Counter
from datetime import date, datetime, timedelta
from io import BytesIO
import re

import pandas as pd

from .inputs import BAR_FIELDS, Inputs, parse_bundle, source_metadata
from .market_calendar import capture_cutoff, sessions_between
from .scope import BENCHMARK, NEW_YORK, SYMBOL_PATTERN

ALIAS_FILE = "security_aliases.csv"
ALIAS_FIELDS = ["symbol", "security_id", "start", "end"]


def _aliases(files: dict[str, bytes]) -> pd.DataFrame:
    if ALIAS_FILE not in files:
        return pd.DataFrame(columns=ALIAS_FIELDS)
    aliases = pd.read_csv(BytesIO(files[ALIAS_FILE]), dtype=str, keep_default_na=False)
    if list(aliases.columns) != ALIAS_FIELDS or not isinstance(aliases.index, pd.RangeIndex):
        raise ValueError(f"{ALIAS_FILE} needs columns {', '.join(ALIAS_FIELDS)}.")
    aliases["symbol"] = aliases["symbol"].str.strip().str.upper()
    for row in aliases.itertuples(index=False):
        if (not re.fullmatch(SYMBOL_PATTERN, row.symbol)
                or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", row.security_id)):
            raise ValueError(f"{ALIAS_FILE} contains an invalid symbol or security ID.")
        for value in (row.start, row.end) if row.end else (row.start,):
            if date.fromisoformat(value).isoformat() != value:
                raise ValueError(f"{ALIAS_FILE} dates must use YYYY-MM-DD.")
        if row.end and row.end <= row.start:
            raise ValueError(f"{ALIAS_FILE} contains an empty or inverted date range.")
    aliases = aliases.sort_values("start")
    for field in ("symbol", "security_id"):
        for _, spans in aliases.groupby(field):
            previous_end = ""
            for start, end in spans[["start", "end"]].itertuples(index=False, name=None):
                if start < previous_end:
                    raise ValueError(f"{ALIAS_FILE} contains overlapping {field} ranges.")
                previous_end = end or "9999-12-31"
    return aliases


def _identify(frame: pd.DataFrame, aliases: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    frame["security_id"] = "ticker:" + frame["symbol"]
    if frame.empty:
        return frame
    by_symbol = frame.groupby("symbol").groups
    for symbol, spans in aliases.groupby("symbol"):
        dates = frame.loc[by_symbol.get(symbol, []), "session"].dt.strftime("%Y-%m-%d")
        for row in spans.itertuples(index=False):
            mask = dates.ge(row.start)
            if row.end:
                mask &= dates.lt(row.end)
            frame.loc[dates[mask].index, "security_id"] = row.security_id
    if frame.duplicated(["session", "security_id"]).any():
        raise ValueError("More than one row resolves to the same security on a session.")
    return frame


def _display_symbols(inputs: Inputs, aliases: pd.DataFrame, session: date) -> dict[str, str]:
    fields = ["session", "symbol", "security_id"]
    rows = inputs.bars[fields]
    if not inputs.members.empty:
        rows = pd.concat([rows, inputs.members[fields]], ignore_index=True)
    newest = rows.sort_values("session").drop_duplicates("security_id", keep="last")
    names = dict(zip(newest["security_id"], newest["symbol"]))
    day = session.isoformat()
    active = aliases.loc[aliases["start"].le(day) & (aliases["end"].eq("") | aliases["end"].gt(day))]
    current = dict(zip(active["symbol"], active["security_id"]))
    for symbol, identifier in current.items():
        if identifier in names:
            names[identifier] = symbol
    counts = Counter(names.values())
    return {
        identifier: f"{symbol} ({identifier})"
        if counts[symbol] > 1 and identifier != current.get(symbol, f"ticker:{symbol}") else symbol
        for identifier, symbol in names.items()
    }


def _published(metadata: dict, dataset: str, now: datetime) -> str | None:
    value = metadata.get(f"{dataset}_published_at")
    if value is None:
        return None
    if isinstance(value, str):
        stamp = datetime.fromisoformat(value)
        if stamp.tzinfo is not None and stamp <= now:
            return stamp.astimezone(NEW_YORK).isoformat()
    raise ValueError(f"{dataset}_published_at must be an offset timestamp at or before collection.")


def prepare_export(files: dict[str, bytes], session: date, now: datetime) -> tuple[Inputs, dict]:
    inputs = parse_bundle(files)
    metadata = source_metadata(files)
    synthetic = metadata.get("synthetic", False)
    if not isinstance(synthetic, bool):
        raise ValueError("synthetic in source.json must be true or false.")
    day = pd.Timestamp(session)
    inputs.bars = inputs.bars.loc[inputs.bars["session"].le(day)].copy()
    inputs.members = inputs.members.loc[inputs.members["session"].le(day)].copy()
    actual = inputs.bars.loc[inputs.bars["close"].notna()]
    if not (actual["session"].eq(day) & actual["symbol"].eq(BENCHMARK)).any():
        raise ValueError(f"Price export has no quoted {BENCHMARK} close for {session}.")
    first_price_day = inputs.bars["session"].min()
    first_day = first_price_day
    if not inputs.members.empty:
        first_day = min(first_day, inputs.members["session"].min())
    calendar = sessions_between(first_day.date(), session)
    for name, dates in (("bars", inputs.bars["session"]), ("membership", inputs.members["session"])):
        invalid = dates.loc[~dates.isin(calendar)]
        if not invalid.empty:
            raise ValueError(f"{name} contains a non-session date, {invalid.iloc[0]:%Y-%m-%d}.")
    benchmark_dates = inputs.bars.loc[inputs.bars["symbol"].eq(BENCHMARK), "session"]
    gaps = calendar[calendar >= first_price_day].difference(benchmark_dates)
    if len(gaps):
        rows = [[stamp, BENCHMARK, float("nan"), float("nan"), float("nan"), float("nan")] for stamp in gaps]
        inputs.bars = pd.concat([inputs.bars, pd.DataFrame(rows, columns=BAR_FIELDS)], ignore_index=True)
    aliases = _aliases(files)
    inputs.bars = _identify(inputs.bars, aliases).sort_values(["session", "symbol"])
    inputs.members = _identify(inputs.members, aliases).sort_values(["session", "symbol"])
    present = inputs.members["session"].eq(day)
    first_bar = actual.loc[actual["symbol"].eq(BENCHMARK), "session"].min()
    sources = {
        "prices": {
            "status": "available", "label": inputs.source,
            "observed_at": (capture_cutoff(session) - timedelta(minutes=30)).isoformat(),
            "published_at": _published(metadata, "prices", now),
            "first_session": first_bar.date().isoformat(),
        },
        "membership": {
            "status": "available" if present.any() else "missing",
            "label": inputs.membership_source,
            "effective_session": inputs.members["session"].max().date().isoformat() if len(inputs.members) else None,
            "published_at": _published(metadata, "membership", now),
            "first_session": inputs.members["session"].min().date().isoformat() if len(inputs.members) else None,
        },
    }
    return inputs, {
        "synthetic": synthetic,
        "vintage": "synthetic" if synthetic else "reconstructed export",
        "sources": sources,
        "display_symbols": _display_symbols(inputs, aliases, session),
    }

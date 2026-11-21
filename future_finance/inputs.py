from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
import json

import numpy as np
import pandas as pd

from .issuer_inputs import (
    EARNINGS_FIELDS, EARNINGS_FILE, FILING_FIELDS, FILING_KEYS, FILINGS_FILE,
    iso_date, parse_earnings, parse_filings, publication_time,
)
from .market_calendar import sessions_between
from .scope import BENCHMARK, NEW_YORK, SECTORS, SYMBOL_PATTERN

PRICE_FIELDS = ["close", "split_close", "total_return_close"]
REQUIRED_BAR_FIELDS = ["session", "symbol", *PRICE_FIELDS, "volume"]
EXTRA_BAR_FIELDS = ["split_high", "split_low", "market_cap", "split_volume"]
BAR_FIELDS = [*REQUIRED_BAR_FIELDS, *EXTRA_BAR_FIELDS]
MEMBER_FIELDS = ["session", "symbol", "sector_etf"]
STOCK_SECTORS_FILE = "stock_sectors.csv"
STRESS_FILE = "stress.csv"
STRESS_SERIES = ("VIX", "VIX3M", "OAS")
STRESS_FIELDS = ["session", "series", "value", "available_at"]
BUNDLE_FILES = ("source.json", "bars.csv", "membership.csv", STOCK_SECTORS_FILE, STRESS_FILE,
                FILINGS_FILE, EARNINGS_FILE)


@dataclass
class Inputs:
    bars: pd.DataFrame
    members: pd.DataFrame
    source: str
    membership_source: str
    demo: bool = False
    filings: pd.DataFrame = field(default_factory=lambda: pd.DataFrame(columns=FILING_FIELDS))
    stress: pd.DataFrame = field(default_factory=lambda: pd.DataFrame(columns=STRESS_FIELDS))
    stress_sources: dict[str, str] = field(default_factory=dict)
    earnings: pd.DataFrame = field(default_factory=lambda: pd.DataFrame(columns=EARNINGS_FIELDS))
    issuer_sources: dict[str, dict[str, str]] = field(default_factory=dict)
    stock_sectors: pd.DataFrame = field(default_factory=lambda: pd.DataFrame(columns=MEMBER_FIELDS))

    def prices(self, field: str) -> pd.DataFrame:
        return self.bars.pivot(index="session", columns="symbol", values=field).sort_index()

    def members_on(self, session: pd.Timestamp) -> pd.DataFrame:
        return self.members[self.members["session"].eq(session)]

    def bars_for(self, ticker: str) -> pd.DataFrame:
        return self.bars.loc[self.bars["symbol"].eq(ticker)].set_index("session")

    def sector_on(self, ticker: str, session: pd.Timestamp) -> str | None:
        for frame in (self.members, self.stock_sectors):
            row = frame.loc[frame["session"].eq(session) & frame["symbol"].eq(ticker), "sector_etf"].dropna()
            if not row.empty:
                return row.iloc[0]
        return None


def _csv(name: str, content: bytes, fields: list[str], optional=()) -> pd.DataFrame:
    frame = pd.read_csv(BytesIO(content), dtype=str, keep_default_na=False, na_values=[""])
    if not isinstance(frame.index, pd.RangeIndex):
        raise ValueError(f"{name} has rows with more fields than its header.")
    missing = set(fields) - set(frame.columns)
    if missing:
        raise ValueError(f"{name} is missing {', '.join(sorted(missing))}.")
    return frame.reindex(columns=[*fields, *optional])


def _symbols(name: str, content: bytes, fields: list[str], optional=()) -> pd.DataFrame:
    frame = _csv(name, content, fields, optional)
    frame["session"] = iso_date(frame["session"])
    frame["symbol"] = frame["symbol"].str.strip().str.upper()
    if frame["session"].isna().any() or not frame["symbol"].str.fullmatch(SYMBOL_PATTERN, na=False).all():
        raise ValueError(f"{name} contains an invalid date or ticker.")
    keys = ["session", "symbol"]
    if frame.duplicated(keys).any():
        raise ValueError(f"{name} contains a duplicate session and ticker.")
    return frame.sort_values(keys)


def _sector_rows(name: str, content: bytes) -> pd.DataFrame:
    frame = _symbols(name, content, MEMBER_FIELDS)
    frame["sector_etf"] = frame["sector_etf"].str.strip().str.upper()
    if not frame["sector_etf"].dropna().isin(SECTORS).all():
        raise ValueError(f"{name} has an unknown sector ETF. Leave unmapped sectors blank.")
    return frame


def _stress(content: bytes, labels: object) -> tuple[pd.DataFrame, dict[str, str]]:
    frame = _csv(STRESS_FILE, content, STRESS_FIELDS)
    frame["session"] = iso_date(frame["session"])
    frame["series"] = frame["series"].str.strip().str.upper()
    if frame["session"].isna().any() or not frame["series"].isin(STRESS_SERIES).all():
        raise ValueError(f"{STRESS_FILE} needs ISO session dates and a series of {', '.join(STRESS_SERIES)}.")
    stamps = publication_time(frame["available_at"])
    local_days = stamps.dt.tz_convert(NEW_YORK).dt.tz_localize(None).dt.normalize()
    if stamps.isna().any() or local_days.lt(frame["session"]).any():
        raise ValueError(f"{STRESS_FILE} needs offset publication timestamps on or after the observation date.")
    frame["available_at"] = stamps
    frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
    volatility = frame["series"].isin(("VIX", "VIX3M"))
    if not np.isfinite(frame["value"]).all() or frame.loc[volatility, "value"].le(0).any():
        raise ValueError(f"{STRESS_FILE} needs finite values and positive volatility closes.")
    keys = ["session", "series", "available_at"]
    if frame.duplicated(keys).any():
        raise ValueError(f"{STRESS_FILE} contains a duplicate session, series and publication timestamp.")
    series = sorted(frame["series"].unique())
    if not isinstance(labels, dict) or any(
        not isinstance(labels.get(name), str) or not labels[name].strip() for name in series
    ):
        raise ValueError(f"source.json requires a stress_sources label for each series in {STRESS_FILE}.")
    return frame.sort_values(keys), {name: labels[name].strip() for name in series}


def import_bundle(folder: Path) -> Inputs:
    inputs = parse_bundle(read_files(folder, BUNDLE_FILES))
    # Insert missing exchange sessions for local previews, just as the archive does.
    dates = inputs.bars["session"]
    calendar = sessions_between(dates.min().date(), dates.max().date())
    invalid = dates.loc[~dates.isin(calendar)]
    if not invalid.empty:
        raise ValueError(f"bars.csv contains a non-session date, {invalid.iloc[0]:%Y-%m-%d}.")
    gaps = calendar.difference(dates)
    if len(gaps):
        missing = pd.DataFrame({"session": gaps, "symbol": BENCHMARK})
        inputs.bars = pd.concat([inputs.bars, missing], ignore_index=True)
    return inputs


def read_files(folder: Path, names: tuple[str, ...]) -> dict[str, bytes]:
    return {name: (folder / name).read_bytes() for name in names if (folder / name).is_file()}


def source_metadata(files: dict[str, bytes]) -> dict:
    if "source.json" not in files:
        raise ValueError("The price export needs source.json.")
    metadata = json.loads(files["source.json"].decode("utf-8-sig"))
    if not isinstance(metadata, dict):
        raise ValueError("source.json must contain a JSON object.")
    return metadata


def parse_bundle(files: dict[str, bytes]) -> Inputs:
    metadata = source_metadata(files)
    source = metadata.get("prices")
    if not isinstance(source, str) or not source.strip():
        raise ValueError("source.json requires a prices label with the provider and feed.")
    if "bars.csv" not in files:
        raise ValueError("The price export needs bars.csv.")
    bars = _symbols("bars.csv", files["bars.csv"], REQUIRED_BAR_FIELDS, EXTRA_BAR_FIELDS)
    numeric = [*PRICE_FIELDS, "volume", *EXTRA_BAR_FIELDS]
    supplied = bars[numeric].notna()
    bars[numeric] = bars[numeric].apply(pd.to_numeric, errors="coerce")
    if (supplied & ~np.isfinite(bars[numeric])).any().any():
        raise ValueError("bars.csv contains a nonnumeric or infinite price or volume.")
    positive = [*PRICE_FIELDS, "split_high", "split_low", "market_cap"]
    if bars[positive].le(0).any().any() or bars[["volume", "split_volume"]].lt(0).any().any():
        raise ValueError("Prices must be positive and volume must be nonnegative.")
    if (bars["split_high"].lt(bars["split_low"]) | bars["split_high"].lt(bars["split_close"])
            | bars["split_low"].gt(bars["split_close"])).any():
        raise ValueError("Split-adjusted highs and lows must bracket the split-adjusted close.")
    if not bars.loc[bars["symbol"].eq(BENCHMARK), "close"].notna().any():
        raise ValueError(f"bars.csv needs at least one quoted {BENCHMARK} close.")
    members = pd.DataFrame(columns=MEMBER_FIELDS)
    membership_source = ""
    if "membership.csv" in files:
        membership_source = metadata.get("membership")
        if not isinstance(membership_source, str) or not membership_source.strip():
            raise ValueError("source.json requires a membership label for membership.csv.")
        members = _sector_rows("membership.csv", files["membership.csv"])
    inputs = Inputs(bars, members, source, membership_source)
    if STOCK_SECTORS_FILE in files:
        inputs.stock_sectors = _sector_rows(STOCK_SECTORS_FILE, files[STOCK_SECTORS_FILE])
    if STRESS_FILE in files:
        inputs.stress, inputs.stress_sources = _stress(files[STRESS_FILE], metadata.get("stress_sources"))
    for dataset, filename, required, optional, parser in (
        ("filings", FILINGS_FILE, FILING_KEYS, FILING_FIELDS[len(FILING_KEYS):], parse_filings),
        ("earnings", EARNINGS_FILE, EARNINGS_FIELDS[:-1], EARNINGS_FIELDS[-1:], parse_earnings),
    ):
        if filename not in files:
            continue
        try:
            frame = parser(_csv(filename, files[filename], required, optional))
            label = metadata.get(dataset, "SEC EDGAR" if dataset == "filings" else "Earnings date export")
            if not isinstance(label, str) or not label.strip():
                raise ValueError(f"source.json needs a nonempty {dataset} label.")
        except ValueError as error:
            inputs.issuer_sources[dataset] = {"status": "invalid export", "detail": str(error)}
        else:
            setattr(inputs, dataset, frame)
            inputs.issuer_sources[dataset] = {"status": "loaded", "label": label.strip()}
    return inputs

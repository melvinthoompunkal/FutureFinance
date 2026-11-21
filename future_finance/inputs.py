from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
import json

import numpy as np
import pandas as pd

from .scope import BENCHMARK, SECTORS, SYMBOL_PATTERN

PRICE_FIELDS = ["close", "split_close", "total_return_close"]
BAR_FIELDS = ["session", "symbol", *PRICE_FIELDS, "volume"]
MEMBER_FIELDS = ["session", "symbol", "sector_etf"]
BUNDLE_FILES = ("source.json", "bars.csv", "membership.csv")


@dataclass
class Inputs:
    bars: pd.DataFrame
    members: pd.DataFrame
    source: str
    membership_source: str
    demo: bool = False
    filings: pd.DataFrame = field(default_factory=pd.DataFrame)
    stress: pd.DataFrame = field(default_factory=pd.DataFrame)

    def prices(self, field: str) -> pd.DataFrame:
        return self.bars.pivot(index="session", columns="symbol", values=field).sort_index()

    def members_on(self, session: pd.Timestamp) -> pd.DataFrame:
        return self.members[self.members["session"].eq(session)]


def _csv(name: str, content: bytes, fields: list[str], unique: list[str]) -> pd.DataFrame:
    frame = pd.read_csv(BytesIO(content), dtype=str, keep_default_na=False, na_values=[""])
    if not isinstance(frame.index, pd.RangeIndex):
        raise ValueError(f"{name} has rows with more fields than its header.")
    missing = set(fields) - set(frame.columns)
    if missing:
        raise ValueError(f"{name} is missing {', '.join(sorted(missing))}.")
    frame = frame[fields].copy()
    valid_dates = frame["session"].str.fullmatch(r"\d{4}-\d{2}-\d{2}", na=False)
    frame["session"] = pd.to_datetime(frame["session"].where(valid_dates), errors="coerce")
    frame["symbol"] = frame["symbol"].str.strip().str.upper()
    if frame["session"].isna().any() or not frame["symbol"].str.fullmatch(SYMBOL_PATTERN, na=False).all():
        raise ValueError(f"{name} contains an invalid date or ticker.")
    if frame.duplicated(unique).any():
        raise ValueError(f"{name} contains a duplicate session and ticker.")
    return frame.sort_values(unique)


def import_bundle(folder: Path) -> Inputs:
    return parse_bundle(read_files(folder, BUNDLE_FILES))


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
    bars = _csv("bars.csv", files["bars.csv"], BAR_FIELDS, ["session", "symbol"])
    numeric = [*PRICE_FIELDS, "volume"]
    supplied = bars[numeric].notna()
    bars[numeric] = bars[numeric].apply(pd.to_numeric, errors="coerce")
    if (supplied & ~np.isfinite(bars[numeric])).any().any():
        raise ValueError("bars.csv contains a nonnumeric or infinite price or volume.")
    if bars[PRICE_FIELDS].le(0).any().any() or bars["volume"].lt(0).any():
        raise ValueError("Prices must be positive and volume must be nonnegative.")
    if not bars.loc[bars["symbol"].eq(BENCHMARK), "close"].notna().any():
        raise ValueError(f"bars.csv needs at least one quoted {BENCHMARK} close.")
    members = pd.DataFrame(columns=MEMBER_FIELDS)
    membership_source = ""
    if "membership.csv" in files:
        membership_source = metadata.get("membership")
        if not isinstance(membership_source, str) or not membership_source.strip():
            raise ValueError("source.json requires a membership label for membership.csv.")
        members = _csv("membership.csv", files["membership.csv"], MEMBER_FIELDS, ["session", "symbol"])
        members["sector_etf"] = members["sector_etf"].str.strip().str.upper()
        if not members["sector_etf"].dropna().isin(SECTORS).all():
            raise ValueError("membership.csv has an unknown sector ETF. Leave unmapped sectors blank.")
    return Inputs(bars, members, source, membership_source)

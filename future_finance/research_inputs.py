"""Validate optional Phase 5 exports before they enter the archive."""

from dataclasses import dataclass, field
from io import BytesIO

import numpy as np
import pandas as pd

from .issuer_inputs import iso_date, publication_time
from .scope import NEW_YORK, SYMBOL_PATTERN

MARKET_SERIES = {
    "DGS10": ("10-year Treasury yield", "%"),
    "T10Y2Y": ("10-year minus 2-year Treasury yield", "pp"),
    "DTWEXBGS": ("Broad U.S. dollar index", "index"),
    "equity_volume": ("Equity options volume put/call", "ratio"),
    "index_volume": ("Index options volume put/call", "ratio"),
    "equity_oi": ("Equity options open interest put/call", "ratio"),
    "index_oi": ("Index options open interest put/call", "ratio"),
}
DENOMINATORS = {
    "short_float": "float",
    "days_to_cover": "consolidated_daily_average",
    "ats_share": "consolidated_weekly",
    "off_exchange_short_share": "same_facilities_daily",
}


@dataclass(frozen=True)
class Export:
    keys: tuple[str, ...]
    fields: tuple[str, ...]
    optional: tuple[str, ...] = ()

    @property
    def columns(self) -> list[str]:
        return [*self.keys, "available_at", *self.fields, *self.optional]


EXPORTS = {
    "options": Export(
        ("symbol", "observed_at", "contract"),
        ("spot_at", "spot", "expiry", "settlement_at", "side", "strike", "deliverable",
         "multiplier", "quote_at", "bid", "ask"),
        ("iv", "delta", "volume", "oi", "oi_session", "rate", "dividend_yield"),
    ),
    "headlines": Export(("symbol", "story_id", "source"),
                        ("issuer_id", "published_at", "title")),
    "market_context": Export(("session", "series"), (), ("value", "puts", "calls")),
    "estimates": Export(("symbol", "period", "kind"), ("eps",), ("target", "analysts", "released_at")),
    "insiders": Export(("symbol", "transaction_id"),
                       ("accession", "cik", "session", "code", "venue", "shares", "price")),
    "positioning": Export(("symbol", "session", "metric"), ("start", "numerator", "scope"),
                          ("denominator", "denominator_scope", "denominator_source")),
    "intraday": Export(("symbol", "start_at"), ("end_at", "high", "low", "close", "volume")),
}
RESEARCH_FILES = (*[f"{name}.csv" for name in EXPORTS], "headline_dictionary.csv")


@dataclass
class ResearchInputs:
    tables: dict[str, pd.DataFrame] = field(default_factory=dict)
    sources: dict[str, dict] = field(default_factory=dict)
    dictionary: dict[str, int] = field(default_factory=dict)

    def known(self, name: str, cutoff, symbol: str | None = None) -> pd.DataFrame:
        columns = EXPORTS[name].columns
        frame = self.tables.get(name)
        if frame is None:
            return pd.DataFrame(columns=columns)
        visible = frame["available_at"].le(cutoff)
        if symbol is not None:
            visible &= frame["symbol"].eq(symbol)
        return frame.loc[visible]


def _read(payload: bytes, columns: list[str], optional=()) -> pd.DataFrame:
    frame = pd.read_csv(BytesIO(payload), dtype=str, keep_default_na=False, na_values=[""])
    missing = set(columns) - set(optional) - set(frame.columns)
    if missing or not isinstance(frame.index, pd.RangeIndex):
        raise ValueError(f"Expected CSV columns {', '.join(columns)}.")
    return frame.reindex(columns=columns)


def _dates(frame, required=(), optional=()):
    for column in (*required, *optional):
        raw = frame[column].astype("string")
        dates = iso_date(raw)
        if (dates.isna() & (raw.notna() if column in optional else True)).any():
            raise ValueError(f"{column} requires ISO dates.")
        frame[column] = dates


def _times(frame, required=(), optional=()):
    for column in (*required, *optional):
        raw = frame[column].astype("string")
        stamps = publication_time(raw)
        if (stamps.isna() & (raw.notna() if column in optional else True)).any():
            raise ValueError(f"{column} requires offset timestamps.")
        # DuckDB stores timezone-aware Parquet timestamps at microsecond precision.
        frame[column] = stamps.dt.ceil("us")


def _numbers(frame, required=(), optional=(), nonnegative=(), integral=()):
    for column in (*required, *optional):
        raw = frame[column]
        values = pd.to_numeric(raw, errors="coerce")
        invalid = ~np.isfinite(values) & (raw.notna() if column in optional else True)
        if column in nonnegative:
            invalid |= values.lt(0)
        if column in integral:
            invalid |= values.notna() & values.mod(1).ne(0)
        if invalid.any():
            raise ValueError(f"{column} contains an invalid numeric value.")
        frame[column] = values.astype(float)


def _text(frame, *columns):
    for column in columns:
        frame[column] = frame[column].str.strip()
        if (frame[column].isna() | frame[column].eq("")).any():
            raise ValueError(f"{column} needs a nonempty value.")


def _require(condition, message):
    if not condition.all():
        raise ValueError(message)


def local_date(stamps: pd.Series) -> pd.Series:
    return stamps.dt.tz_convert(NEW_YORK).dt.tz_localize(None).dt.normalize()


def _options(frame):
    _text(frame, "contract")
    _dates(frame, ("expiry",), ("oi_session",))
    _times(frame, ("observed_at", "spot_at"), ("quote_at", "settlement_at"))
    _numbers(frame, ("spot", "strike"), ("bid", "ask", "multiplier", "iv", "delta", "volume", "oi",
                                        "rate", "dividend_yield"),
             ("volume", "oi", "dividend_yield"), ("volume", "oi", "multiplier"))
    day = local_date(frame["observed_at"])
    _require(frame["side"].isin(("call", "put")) & frame["deliverable"].isin(
        ("standard", "adjusted", "unknown")), "Specify call/put and standard/adjusted/unknown deliverables.")
    _require(frame["spot"].gt(0) & frame["strike"].gt(0)
             & (frame["multiplier"].isna() | frame["multiplier"].gt(0)), "Spot, strike and multiplier must be positive.")
    _require(frame["observed_at"].le(frame["available_at"]) & frame["spot_at"].le(frame["observed_at"])
             & (frame["quote_at"].isna() | frame["quote_at"].le(frame["observed_at"])),
             "Spot and quote timestamps must precede the snapshot and its availability.")
    _require(frame["expiry"].ge(day) & (frame["settlement_at"].isna()
             | local_date(frame["settlement_at"]).eq(frame["expiry"])), "Settlement must match the expiration date.")
    _require(frame["oi"].isna().eq(frame["oi_session"].isna())
             & (frame["oi_session"].isna() | frame["oi_session"].lt(day)),
             "Open interest requires an effective session before the snapshot's local date.")
    _require(frame["delta"].isna() | (frame["side"].eq("call") & frame["delta"].between(0, 1))
             | (frame["side"].eq("put") & frame["delta"].between(-1, 0)), "Delta has the wrong sign or magnitude.")
    for _, chain in frame.groupby(["symbol", "observed_at", "available_at"], sort=False):
        if len(chain[["spot", "spot_at"]].drop_duplicates()) != 1:
            raise ValueError("Spot and its timestamp must agree across a snapshot.")
        standard = chain.loc[chain["deliverable"].eq("standard")]
        if standard.duplicated(["expiry", "strike", "side"], keep=False).any():
            # Distinct settlement series are allowed. Analytics keeps them apart.
            if standard.duplicated(["expiry", "settlement_at", "strike", "side"]).any():
                raise ValueError("Duplicate standard contracts within an expiration and settlement series.")


def _headlines(frame):
    _text(frame, "story_id", "source", "issuer_id", "title")
    _times(frame, ("published_at",))
    _require(frame["published_at"].le(frame["available_at"]), "Headlines cannot be known before publication.")


def _market_context(frame):
    _dates(frame, ("session",))
    _numbers(frame, optional=("value", "puts", "calls"), nonnegative=("puts", "calls"), integral=("puts", "calls"))
    counts = frame["series"].str.endswith(("_volume", "_oi"), na=False)
    _require(frame["series"].isin(MARKET_SERIES)
             & np.where(counts, frame["value"].isna() & frame["puts"].notna() & frame["calls"].notna(),
                        frame["value"].notna() & frame["puts"].isna() & frame["calls"].isna())
             & (~frame["series"].eq("DTWEXBGS") | frame["value"].gt(0)),
             "Provide macro values or matched put and call counts for a supported series.")


def _estimates(frame):
    _dates(frame, ("period",))
    _times(frame, optional=("released_at",))
    _numbers(frame, ("eps",), ("target", "analysts"), ("target", "analysts"), ("analysts",))
    actual = frame["kind"].eq("actual")
    release = frame["released_at"].fillna(frame["available_at"])
    _require(frame["kind"].isin(("actual", "consensus"))
             & (~actual | (frame["target"].isna() & frame["analysts"].isna()
                           & frame["period"].le(local_date(release))))
             & (frame["released_at"].isna() | (actual & release.le(frame["available_at"]))),
             "Provide consensus snapshots or results released on or after the fiscal period end.")


def _insiders(frame):
    _dates(frame, ("session",))
    _text(frame, "transaction_id")
    _numbers(frame, ("shares",), ("price",), ("shares", "price"))
    _require(frame["shares"].gt(0) & frame["cik"].str.fullmatch(r"\d{1,10}", na=False)
             & ~frame["cik"].str.fullmatch(r"0+", na=False)
             & frame["accession"].str.fullmatch(r"\d{10}-\d{2}-\d{6}", na=False)
             & frame["code"].str.fullmatch(r"[A-Z]", na=False)
             & frame["venue"].isin(("open_market", "private", "other", "unknown")),
             "Form 4 rows need a CIK, accession, transaction code and positive shares.")


def _positioning(frame):
    _dates(frame, ("session", "start"))
    _text(frame, "scope")
    _numbers(frame, ("numerator",), ("denominator",), ("numerator", "denominator"), ("numerator",))
    _require(frame["metric"].isin(DENOMINATORS) & frame["start"].le(frame["session"]),
             "Positioning requires a supported metric and matching date window.")
    present = frame["denominator"].notna()
    scopes = frame["metric"].map(DENOMINATORS)
    _require(~present | (frame["denominator_scope"].eq(scopes)
                         & frame["denominator_source"].fillna("").str.strip().ne("")),
             "A denominator requires the specified matching coverage and its source.")
    is_share = frame["metric"].isin(("short_float", "ats_share", "off_exchange_short_share"))
    same_day = frame["metric"].isin(("off_exchange_short_share", "short_float"))
    weekly = frame["metric"].eq("ats_share")
    _require((~same_day | frame["start"].eq(frame["session"]))
             & (~weekly | frame["session"].sub(frame["start"]).dt.days.between(0, 6))
             & (~present | ~is_share | frame["metric"].eq("short_float")
                | frame["numerator"].le(frame["denominator"])),
             "Use one-day or one-week windows as applicable and matching share counts.")


def _intraday(frame):
    _times(frame, ("start_at", "end_at"))
    _numbers(frame, ("high", "low", "close", "volume"), nonnegative=("volume",), integral=("volume",))
    _require(frame["start_at"].lt(frame["end_at"]) & frame["end_at"].le(frame["available_at"])
             & frame["low"].gt(0) & frame["high"].ge(frame["close"]) & frame["close"].ge(frame["low"]),
             "Intraday bars require ordered timestamps and prices.")


PARSERS = {
    "options": _options, "headlines": _headlines, "market_context": _market_context,
    "estimates": _estimates, "insiders": _insiders, "positioning": _positioning, "intraday": _intraday,
}


def _dictionary(payload: bytes) -> dict[str, int]:
    frame = _read(payload, ["term", "tone"])
    frame["term"] = frame["term"].str.casefold()
    _require(frame["term"].str.fullmatch(r"[a-z]+", na=False) & frame["tone"].isin(("positive", "negative")),
             "Dictionary entries need one word and positive or negative tone.")
    if frame.empty or frame["term"].duplicated().any():
        raise ValueError("The dictionary requires unique words.")
    return dict(zip(frame["term"], frame["tone"].map({"positive": 1, "negative": -1})))


def parse_research(files: dict[str, bytes], metadata: dict) -> ResearchInputs:
    research = ResearchInputs()
    config = metadata.get("research_sources")
    config = config if isinstance(config, dict) else {}
    for name, export in EXPORTS.items():
        filename = f"{name}.csv"
        if filename not in files:
            continue
        try:
            source = config.get(name)
            labels = ("label", "dictionary_label") if name == "headlines" else ("label",)
            if (not isinstance(source, dict) or source.get("permitted") is not True
                    or any(not isinstance(source.get(key), str) or not source[key].strip() for key in labels)):
                raise ValueError("Confirm retention and display rights in source.json and identify the source.")
            frame = _read(files[filename], export.columns, export.optional)
            _times(frame, ("available_at",))
            if "symbol" in frame:
                frame["symbol"] = frame["symbol"].str.strip().str.upper()
                _require(frame["symbol"].str.fullmatch(SYMBOL_PATTERN, na=False), "Invalid ticker.")
            PARSERS[name](frame)
            if "session" in frame:
                _require(frame["session"].le(local_date(frame["available_at"])),
                         "The observation date must precede or equal publication.")
            keys = [*export.keys, "available_at"]
            if frame.duplicated(keys).any():
                raise ValueError("Duplicate observations with the same publication timestamp.")
            if name == "headlines":
                if "headline_dictionary.csv" not in files:
                    raise ValueError("Supply the permitted headline_dictionary.csv.")
                research.dictionary = _dictionary(files["headline_dictionary.csv"])
            research.tables[name] = frame.sort_values(keys).reset_index(drop=True)
            research.sources[name] = {"status": "loaded", **{key: source[key].strip() for key in labels}}
        except (ValueError, UnicodeError) as error:
            research.sources[name] = {"status": "invalid export", "detail": str(error)}
    return research

"""Validate normalized, point-in-time filing and earnings exports."""

import numpy as np
import pandas as pd

from .scope import NEW_YORK, SYMBOL_PATTERN

FILINGS_FILE = "filings.csv"
EARNINGS_FILE = "earnings.csv"
FILING_KEYS = ["symbol", "cik", "accession", "form", "period", "available_at", "basis"]
FINANCIAL_FIELDS = [
    "revenue", "prior_revenue", "operating_income", "prior_operating_income",
    "ttm_cfo", "ttm_capex", "ttm_eps", "gross_debt", "ttm_ebitda", "ttm_ebit", "ttm_interest",
]
FILING_FIELDS = [*FILING_KEYS, *FINANCIAL_FIELDS, "eps_basis_session"]
EARNINGS_FIELDS = ["symbol", "event_date", "status", "available_at", "source_url"]


def iso_date(values: pd.Series) -> pd.Series:
    return pd.to_datetime(values.where(values.str.fullmatch(r"\d{4}-\d{2}-\d{2}", na=False)),
                          errors="coerce")


def publication_time(values: pd.Series) -> pd.Series:
    offset = values.str.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:\d{2})", na=False
    )
    return pd.to_datetime(values.where(offset), format="ISO8601", utc=True, errors="coerce")


def _identity(frame: pd.DataFrame, name: str) -> pd.Series:
    frame["symbol"] = frame["symbol"].str.strip().str.upper()
    frame["available_at"] = publication_time(frame["available_at"])
    if frame["available_at"].isna().any() or not frame["symbol"].str.fullmatch(SYMBOL_PATTERN, na=False).all():
        raise ValueError(f"{name} requires valid symbols and offset publication timestamps.")
    return frame["available_at"].dt.tz_convert(NEW_YORK).dt.tz_localize(None).dt.normalize()


def parse_filings(frame: pd.DataFrame) -> pd.DataFrame:
    available_days = _identity(frame, FILINGS_FILE)
    frame["period"] = iso_date(frame["period"])
    if frame["period"].isna().any() or frame["period"].gt(available_days).any():
        raise ValueError("filings.csv requires fiscal period ends on or before publication.")
    if (not frame["cik"].str.fullmatch(r"\d{1,10}", na=False).all()
            or frame["cik"].str.fullmatch(r"0+", na=False).any()
            or not frame["accession"].str.fullmatch(r"\d{10}-\d{2}-\d{6}", na=False).all()
            or not frame["form"].isin(["10-K", "10-Q", "10-K/A", "10-Q/A"]).all()
            or not frame["basis"].isin(["operating", "financial", "reit"]).all()):
        raise ValueError("filings.csv requires a CIK, SEC accession, 10-K or 10-Q form, and reporting basis.")
    frame["cik"] = frame["cik"].str.zfill(10)
    numbers = frame[FINANCIAL_FIELDS].apply(pd.to_numeric, errors="coerce")
    if (frame[FINANCIAL_FIELDS].notna() & ~np.isfinite(numbers)).any().any():
        raise ValueError("filings.csv contains a nonnumeric or infinite financial value.")
    if numbers[["revenue", "prior_revenue", "ttm_capex", "gross_debt", "ttm_interest"]].lt(0).any().any():
        raise ValueError("filings.csv requires nonnegative revenue, capex, debt, and interest expense.")
    eps_dates = iso_date(frame["eps_basis_session"].astype("string"))
    if ((frame["eps_basis_session"].notna() | numbers["ttm_eps"].notna()) & eps_dates.isna()).any() or (
        eps_dates.gt(available_days).any()
    ):
        raise ValueError("filings.csv requires a quoted-share basis session for EPS on or before publication.")
    frame[FINANCIAL_FIELDS] = numbers
    frame["eps_basis_session"] = eps_dates
    keys = ["symbol", "period", "available_at"]
    if frame.duplicated(keys).any():
        raise ValueError("filings.csv contains duplicate issuer, period and publication time values.")
    return frame.sort_values(keys)


def parse_earnings(frame: pd.DataFrame) -> pd.DataFrame:
    available_days = _identity(frame, EARNINGS_FILE)
    dates = iso_date(frame["event_date"])
    scheduled = frame["status"].isin(["confirmed", "estimated"])
    unknown = frame["status"].eq("unknown") & frame["event_date"].isna()
    if not ((scheduled & dates.ge(available_days)) | unknown).all():
        raise ValueError("earnings.csv requires a confirmed or estimated future date, or a blank date with unknown status.")
    if not (frame["source_url"].isna() | frame["source_url"].str.fullmatch(
        r"https://[A-Za-z0-9.-]+(?::[0-9]+)?(?:[/?#][^\s<>\\]*)?", na=False
    )).all() or (frame["status"].eq("confirmed") & frame["source_url"].isna()).any():
        raise ValueError("earnings.csv requires an HTTPS source URL for a confirmed date.")
    frame["event_date"] = dates
    keys = ["symbol", "available_at"]
    if frame.duplicated(keys).any():
        raise ValueError("earnings.csv contains duplicate ticker and publication time values.")
    return frame.sort_values(keys)

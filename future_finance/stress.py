"""Point-in-time volatility and credit calculations for dated observations."""

from datetime import datetime

import pandas as pd

from .inputs import STRESS_SERIES
from .market_calendar import capture_cutoff, sessions_between

VIX_LOOKBACK = 252
CREDIT_LOOKBACK = 20


def observations_as_of(observations: pd.DataFrame, day: pd.Timestamp, cutoff: datetime) -> pd.DataFrame:
    if observations.empty:
        return observations
    known = observations.loc[observations["session"].le(day) & observations["available_at"].le(cutoff)]
    return known.sort_values(["session", "available_at"]).drop_duplicates(["session", "series"], keep="last")


def stress_history(observations: pd.DataFrame, day: pd.Timestamp) -> pd.DataFrame:
    known = observations_as_of(observations, day, capture_cutoff(day.date()))
    if known.empty:
        values = pd.DataFrame(index=pd.DatetimeIndex([], name="session"), columns=STRESS_SERIES, dtype=float)
    else:
        dates = sessions_between(known["session"].min().date(), day.date())
        values = known.pivot(index="session", columns="series", values="value").reindex(
            index=dates, columns=STRESS_SERIES
        )
    values["VIX / VIX3M"] = values["VIX"] / values["VIX3M"]
    values["High-yield spread"] = values["OAS"] * 100
    values["Spread change"] = values["High-yield spread"].diff(CREDIT_LOOKBACK)
    return values


def vix_percentile(vix: pd.Series, day: pd.Timestamp) -> tuple[float | None, int]:
    sample = vix.loc[:day].tail(VIX_LOOKBACK).dropna()
    if len(sample) < 2:
        return None, len(sample)
    latest = sample.iloc[-1]
    midrank = sample.lt(latest).sum() + sample.eq(latest).sum() / 2
    return float(100 * midrank / len(sample)), len(sample)

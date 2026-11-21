"""Market internals, relative rotation and headline evidence."""

import re

import numpy as np
import pandas as pd

from .market_calendar import capture_cutoff
from .research_inputs import MARKET_SERIES, ResearchInputs
from .scope import BENCHMARK, SECTORS
from .stress import observations_as_of


def internals(members: pd.DataFrame, prices: pd.DataFrame, dates: pd.DatetimeIndex) -> pd.DataFrame:
    expected = members.loc[members["session"].isin(dates), ["session", "symbol"]].set_index(["session", "symbol"])
    moves = prices.diff()
    prior = prices.shift()
    high, low = prior.rolling(252).max(), prior.rolling(252).min()
    daily = pd.concat({
        "Eligible moves": moves.notna().stack(),
        "Advances": moves.gt(0).stack(),
        "Declines": moves.lt(0).stack(),
        "Eligible yearly extremes": high.notna().where(prices.notna(), False).stack(),
        "New highs": prices.gt(high).stack(),
        "New lows": prices.lt(low).stack(),
    }, axis=1).reindex(expected.index)
    counts = daily.fillna(False).groupby(level="session").sum().reindex(dates)
    counts["Dated members"] = expected.groupby(level="session").size().reindex(dates)
    enough = counts["Eligible moves"].ge(.9 * counts["Dated members"])
    yearly = counts["Eligible yearly extremes"].ge(.9 * counts["Dated members"])
    net = (counts["Advances"] - counts["Declines"]).where(enough)
    counts["Advance/decline line"] = net.groupby(net.isna().cumsum()).cumsum()
    counts[["New highs", "New lows"]] = counts[["New highs", "New lows"]].where(yearly, axis=0)
    return counts


def rotation(prices: pd.DataFrame, day: pd.Timestamp, weeks: int = 10) -> pd.DataFrame:
    ratios = prices.loc[:day].reindex(columns=[*SECTORS, BENCHMARK])
    ratios = ratios[list(SECTORS)].div(ratios[BENCHMARK], axis=0)
    strength = ratios.div(ratios.rolling(20).mean()).mul(100).rolling(5).mean()
    momentum = strength.div(strength.rolling(10).mean()).mul(100)
    dates = strength.index.to_series().groupby(strength.index.to_period("W-FRI")).last().tail(weeks)
    values = pd.concat({"Relative strength": strength.loc[dates].stack(),
                        "Relative momentum": momentum.loc[dates].stack()}, axis=1).dropna()
    values.index.names = ["Session", "ETF"]
    values = values.reset_index()
    strength, momentum = values["Relative strength"], values["Relative momentum"]
    values["Quadrant"] = np.select(
        [strength.gt(100) & momentum.gt(100), strength.gt(100) & momentum.lt(100),
         strength.lt(100) & momentum.lt(100), strength.lt(100) & momentum.gt(100)],
        ["Leading", "Weakening", "Lagging", "Improving"], default="On boundary",
    )
    return values


def market_context(research: ResearchInputs, day: pd.Timestamp) -> pd.DataFrame:
    cutoff = capture_cutoff(day.date())
    known = observations_as_of(research.known("market_context", cutoff), day, cutoff).copy()
    if known.empty:
        return known
    ratio = known["puts"].div(known["calls"].where(known["calls"].gt(0)))
    known["reading"] = known["value"].fillna(ratio)
    known["unit"] = known["series"].map(lambda name: MARKET_SERIES[name][1])
    return known


def context_summary(history: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for series, frame in history.groupby("series", sort=False):
        row = frame.iloc[-1]
        label, unit = MARKET_SERIES[series]
        result = {"Series": label, "Value": row.reading, "Unit": unit, "Observation": row.session,
                  "Available (UTC)": row.available_at}
        if unit == "ratio":
            sample = frame.loc[frame["session"].ge(row.session - pd.Timedelta(days=365)), "reading"].dropna()
            result["Valid observations in trailing year"] = len(sample)
            if len(sample) >= 60 and pd.notna(row.reading):
                result["Percentile"] = sample.lt(row.reading).mean() * 100
        else:
            for days in (30, 90):
                anchor = row.session - pd.Timedelta(days=days)
                earlier = frame.loc[frame["session"].between(anchor - pd.Timedelta(days=7), anchor)]
                if not earlier.empty:
                    baseline = earlier["reading"].iloc[-1]
                    result[f"{days}-day change"] = ((row.reading / baseline - 1) * 100 if unit == "index"
                                                    else (row.reading - baseline) * 100)
            result["Change unit"] = "%" if unit == "index" else "bp"
        rows.append(result)
    return pd.DataFrame(rows)


def headline_tone(research: ResearchInputs, membership: pd.DataFrame, day: pd.Timestamp) -> tuple:
    cutoff = capture_cutoff(day.date())
    rows = research.known("headlines", cutoff)
    if rows.empty or membership.empty:
        return pd.DataFrame(), pd.DataFrame()
    rows = rows.loc[rows["published_at"].gt(cutoff - pd.Timedelta(days=7))]
    rows = rows.merge(membership[["symbol", "sector_etf"]].dropna(), on="symbol", validate="many_to_one")
    if rows.empty:
        return pd.DataFrame(), pd.DataFrame()
    keys = ["sector_etf", "issuer_id"]
    rows["normalized"] = rows["title"].map(lambda title: " ".join(re.findall("[a-z0-9]+", title.casefold())))
    rows = (rows.sort_values(["published_at", "available_at", "source", "story_id"])
            .drop_duplicates([*keys, "story_id", "source"], keep="last")
            .drop_duplicates([*keys, "story_id"])
            .drop_duplicates([*keys, "normalized"]).copy())

    def word_score(title: str) -> float:
        scores = [research.dictionary.get(word, 0) for word in re.findall("[a-z]+", title.casefold())]
        count = sum(abs(score) for score in scores)
        return sum(scores) / count if count else np.nan

    rows["tone"] = rows["title"].map(word_score)
    grouped = rows.groupby("sector_etf")
    summary = grouped.agg(total=("story_id", "size"), scored=("tone", "count"),
                          issuers_with_headlines=("issuer_id", "nunique"))
    issuers = rows.dropna(subset="tone").groupby(keys)["tone"].mean()
    summary["Scored issuers"] = issuers.groupby(level=0).size().reindex(summary.index, fill_value=0)
    adequate = summary["scored"].ge(10) & summary["Scored issuers"].ge(3)
    summary["Tone"] = issuers.groupby(level=0).mean().where(adequate)
    summary["Coverage"] = np.where(adequate, "Available", "Limited news coverage")
    summary["Sources after deduplication"] = grouped["source"].agg(
        lambda sources: ", ".join(f"{name} ({count})" for name, count in sources.value_counts().items())
    )
    return summary, rows.drop(columns="normalized")

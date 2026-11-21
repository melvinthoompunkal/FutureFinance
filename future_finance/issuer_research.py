"""Point-in-time issuer histories built from filing and event vintages."""

import numpy as np
import pandas as pd

from .market_calendar import capture_cutoff
from .scope import NEW_YORK
from .stock import business_health, filing_url, valuation


def issuer_history(filings: pd.DataFrame, ticker: str, day: pd.Timestamp) -> tuple[pd.DataFrame, pd.DataFrame]:
    known = filings.loc[filings["symbol"].eq(ticker) & filings["available_at"].le(capture_cutoff(day.date()))]
    history = known.sort_values(["period", "available_at"]).drop_duplicates("period", keep="last")
    rows = []
    for row in history.itertuples(index=False):
        health = business_health(row)
        operating = row.basis == "operating"
        rows.append({
            "Period": row.period, "Available (UTC)": row.available_at, "Form": row.form,
            "Revenue growth (%)": health.growth, "Operating margin (%)": health.margin if operating else np.nan,
            "Margin change (pp)": health.margin_change if operating else np.nan,
            "Trailing FCF ($B)": health.fcf / 1e9 if operating else np.nan,
            "Gross debt / EBITDA": health.debt_to_ebitda if operating else np.nan,
            "Interest coverage": health.coverage if operating else np.nan,
            "Filing": filing_url(row),
        })
    return pd.DataFrame(rows), known


def valuation_history(filings: pd.DataFrame, bars: pd.DataFrame, day: pd.Timestamp) -> pd.DataFrame:
    if filings.empty or bars.empty:
        return pd.DataFrame()
    days = bars.loc[day - pd.DateOffset(years=5):day].index
    if days.empty:
        return pd.DataFrame()
    cutoffs = pd.DatetimeIndex([capture_cutoff(date.date()) for date in days])
    chronology = filings.sort_values("available_at")
    reports = chronology.itertuples(index=False)
    pending = next(reports, None)
    latest = None
    values = []
    for session, cutoff in zip(days, cutoffs):
        while pending is not None and pending.available_at <= cutoff:
            if latest is None or pending.period >= latest.period:
                latest = pending
            pending = next(reports, None)
        if latest is not None:
            reading = valuation(latest, bars, session)
            values.append((session, reading.pe, reading.fcf_yield))
    return pd.DataFrame(values, columns=["Session", "Trailing P/E", "FCF yield (%)"]).set_index("Session")


def earning_releases(known: pd.DataFrame) -> pd.DataFrame:
    rows = known.loc[known["kind"].eq("actual")].copy()
    rows["release"] = rows["released_at"].fillna(rows["available_at"])
    return rows.sort_values(["release", "available_at"]).drop_duplicates("period")


def earnings_surprises(known: pd.DataFrame) -> pd.DataFrame:
    consensus = known.loc[known["kind"].eq("consensus")].sort_values("available_at")
    rows = []
    for result in earning_releases(known).sort_values("period", ascending=False).head(8).itertuples(index=False):
        earlier = consensus.loc[consensus["period"].eq(result.period)
                                & consensus["available_at"].lt(result.release)]
        estimate = earlier.iloc[-1].eps if not earlier.empty else np.nan
        surprise = (result.eps - estimate) / abs(estimate) * 100 if pd.notna(estimate) and estimate else np.nan
        rows.append({"Fiscal period": result.period, "Reported (UTC)": result.release, "Reported EPS": result.eps,
                     "Consensus EPS": estimate, "Surprise (%)": surprise,
                     "Consensus as of (UTC)": earlier.iloc[-1].available_at if not earlier.empty else pd.NaT,
                     "Analysts": earlier.iloc[-1].analysts if not earlier.empty else np.nan})
    return pd.DataFrame(rows)


def estimate_revisions(known: pd.DataFrame, cutoff) -> pd.DataFrame:
    actual = earning_releases(known)
    fiscal_period = actual["period"].max()
    consensus = known.loc[known["kind"].eq("consensus")].sort_values("available_at")
    consensus = consensus.loc[consensus["period"].gt(fiscal_period) if pd.notna(fiscal_period)
                              else consensus["period"].ge(pd.Timestamp(cutoff.date()))]
    if consensus.empty:
        return pd.DataFrame()
    forward = consensus.loc[consensus["period"].eq(consensus["period"].min())]
    latest = forward.iloc[-1]
    rows = []
    for days in (30, 90):
        anchor = cutoff - pd.Timedelta(days=days)
        earlier = forward.loc[forward["available_at"].le(anchor)]
        baseline = earlier.iloc[-1] if not earlier.empty else None
        rows.append({
            "Lookback (days)": days, "Fiscal period": latest.period, "Consensus EPS": latest.eps,
            "EPS change ($)": latest.eps - baseline.eps if baseline is not None else np.nan,
            "Price target ($)": latest.target,
            "Target change ($)": latest.target - baseline.target if baseline is not None else np.nan,
            "Analysts": latest.analysts, "Latest snapshot (UTC)": latest.available_at,
            "Baseline snapshot (UTC)": baseline.available_at if baseline is not None else pd.NaT,
        })
    return pd.DataFrame(rows)


def insider_trades(known: pd.DataFrame) -> pd.DataFrame:
    trades = known.sort_values("available_at").drop_duplicates(["symbol", "transaction_id"], keep="last")
    trades = trades.loc[trades["venue"].eq("open_market") & trades["code"].isin(("P", "S"))].copy()
    if trades.empty:
        return trades
    trades["Side"] = trades["code"].map({"P": "Purchase", "S": "Sale"})
    trades["Value ($)"] = trades["shares"] * trades["price"]
    trades["Filing"] = [filing_url(row) for row in trades.itertuples(index=False)]
    return trades.sort_values("session", ascending=False)


def positioning(known: pd.DataFrame) -> pd.DataFrame:
    rows = (known.sort_values(["session", "available_at"])
            .drop_duplicates(["session", "metric"], keep="last").copy())
    if rows.empty:
        return rows
    rows["Value"] = rows["numerator"].div(rows["denominator"].where(rows["denominator"].gt(0)))
    percent = rows["metric"].ne("days_to_cover")
    rows.loc[percent, "Value"] *= 100
    rows["Unit"] = np.where(percent, "%", "days")
    released = rows["available_at"].dt.tz_convert(NEW_YORK).dt.tz_localize(None).dt.normalize()
    rows["Publication lag (calendar days)"] = released.sub(rows["session"]).dt.days
    return rows

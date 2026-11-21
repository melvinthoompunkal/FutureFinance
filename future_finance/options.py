"""Options analytics for observed, time-aligned chain snapshots."""

from dataclasses import dataclass
from math import sqrt

import numpy as np
import pandas as pd

from .market_calendar import capture_cutoff, exchange
from .research_inputs import ResearchInputs, local_date

MAX_SPREAD = 0.35
MAX_AGE = pd.Timedelta(minutes=30)
MAX_SPOT_GAP = pd.Timedelta(minutes=20)
MIN_GAMMA_COVERAGE = 0.70
BUCKETS = ["0 days", "1–7 days", "8–45 days", "Over 45 days"]
TERM_COLUMNS = ["Expiry", "Settlement (UTC)", "Days", "ATM strike", "ATM IV (%)", "Straddle ($)",
                "One standard deviation ($)", "25-delta risk reversal (pp)", "Retained contracts"]


def visible_history(inputs: ResearchInputs, symbol: str, day: pd.Timestamp) -> pd.DataFrame:
    known = inputs.known("options", capture_cutoff(day.date()), symbol)
    if known.empty:
        return known.assign(day=pd.Series(dtype="datetime64[ns]"))
    return known.assign(day=local_date(known["observed_at"]))


def latest_chain(history: pd.DataFrame, day: pd.Timestamp) -> pd.DataFrame:
    rows = history.loc[history["day"].eq(day) & history["available_at"].le(capture_cutoff(day.date()))]
    if rows.empty:
        return rows
    latest = rows.sort_values(["observed_at", "available_at"]).iloc[-1]
    return rows.loc[rows["observed_at"].eq(latest.observed_at) & rows["available_at"].eq(latest.available_at)]


def pre_expiry_chain(history: pd.DataFrame, day: pd.Timestamp) -> pd.DataFrame:
    rows = history.loc[history["day"].eq(day) & history["available_at"].le(capture_cutoff(day.date()))]
    timely = rows.loc[rows["expiry"].eq(day) & rows["settlement_at"].gt(rows["observed_at"])]
    if timely.empty:
        return timely
    retained = assess_quotes(timely, day)
    eligible = retained.loc[retained["quality"].eq("Retained")]
    if eligible.empty:
        return eligible
    latest = eligible.sort_values(["observed_at", "available_at"]).iloc[-1]
    return rows.loc[rows["observed_at"].eq(latest.observed_at) & rows["available_at"].eq(latest.available_at)]


def assess_quotes(chain: pd.DataFrame, day: pd.Timestamp) -> pd.DataFrame:
    if chain.empty:
        return chain.assign(quality=pd.Series(dtype=str), mid=pd.Series(dtype=float))
    opening = exchange().session_open(day)
    mid = (chain["bid"] + chain["ask"]) / 2
    spread = (chain["ask"] - chain["bid"]) / mid.where(mid.gt(0))
    too_old = (
        chain["quote_at"].isna() | chain["quote_at"].lt(opening) | chain["spot_at"].lt(opening)
        | chain["observed_at"].sub(chain["quote_at"]).gt(MAX_AGE)
        | chain["observed_at"].sub(chain["spot_at"]).gt(MAX_AGE)
        | chain["quote_at"].sub(chain["spot_at"]).abs().gt(MAX_SPOT_GAP)
    )
    expired = (chain["settlement_at"].le(chain["observed_at"])
               | (chain["expiry"].eq(day) & chain["settlement_at"].isna()))
    quality = np.select(
        [chain["deliverable"].ne("standard") | chain["multiplier"].isna(), expired, too_old,
         chain["bid"].isna() | chain["ask"].isna() | chain["bid"].le(0),
         chain["ask"].lt(chain["bid"]), spread.gt(MAX_SPREAD)],
        ["Unverified or adjusted terms", "Expired or unverified 0-day settlement", "Stale or unaligned",
         "Missing quote or zero bid", "Crossed quote", "Wide spread"],
        default="Retained",
    )
    return chain.assign(quality=quality, mid=mid)


def _delta_iv(rows: pd.DataFrame) -> float:
    values = (rows.loc[rows["iv"].gt(0) & rows["delta"].notna()]
              .assign(abs_delta=lambda x: x["delta"].abs()).groupby("abs_delta")["iv"].mean())
    if values.empty or not values.index.min() <= 0.25 <= values.index.max():
        return np.nan
    return float(np.interp(0.25, values.index, values))


def term_structure(checked: pd.DataFrame, day: pd.Timestamp) -> pd.DataFrame:
    valid = checked.loc[checked["quality"].eq("Retained")]
    term = []
    for (expiry, settlement), rows in valid.groupby(["expiry", "settlement_at"], dropna=False):
        calls = rows.loc[rows["side"].eq("call")].set_index("strike")
        puts = rows.loc[rows["side"].eq("put")].set_index("strike")
        both = calls.index.intersection(puts.index)
        spot = rows["spot"].iloc[0]
        strike = min(both, key=lambda value: (abs(value - spot), value), default=np.nan)
        iv = straddle = np.nan
        if pd.notna(strike) and calls.at[strike, "multiplier"] == puts.at[strike, "multiplier"]:
            pair = [calls.at[strike, "iv"], puts.at[strike, "iv"]]
            iv = np.mean(pair) if min(pair) > 0 and all(pd.notna(pair)) else np.nan
            straddle = calls.at[strike, "mid"] + puts.at[strike, "mid"]
        days = (expiry - day).days
        remaining = days or (settlement - rows["observed_at"].iloc[0]).total_seconds() / 86400
        term.append((expiry, settlement, days, strike, iv * 100, straddle,
                     spot * iv * sqrt(remaining / 365),
                     (_delta_iv(calls) - _delta_iv(puts)) * 100, len(rows)))
    return pd.DataFrame(term, columns=TERM_COLUMNS)


def iv_at_30(term: pd.DataFrame) -> float:
    pairs = (term.dropna(subset=["ATM IV (%)"]).loc[lambda x: x["Days"].gt(0)]
             .sort_values(["Days", "Retained contracts"], ascending=[True, False])
             .drop_duplicates("Days").set_index("Days")["ATM IV (%)"].div(100))
    if pairs.empty or not pairs.index.min() <= 30 <= pairs.index.max():
        return np.nan
    total_variance = np.interp(30, pairs.index, pairs.pow(2).mul(pairs.index))
    return sqrt(total_variance / 30) * 100


def iv_history(history: pd.DataFrame, dates: pd.DatetimeIndex) -> pd.Series:
    sample = pd.Series(index=dates[-252:], dtype=float, name="30-day ATM IV")
    for day, rows in history.loc[history["day"].isin(sample.index)].groupby("day"):
        sample.loc[day] = iv_at_30(term_structure(assess_quotes(latest_chain(rows, day), day), day))
    return sample


def iv_reading(sample: pd.Series) -> tuple[int, float, float]:
    valid = sample.dropna()
    count = len(valid)
    if count < 60 or pd.isna(sample.iloc[-1]) or valid.min() == valid.max():
        return count, np.nan, np.nan
    latest = sample.iloc[-1]
    return count, (latest - valid.min()) / (valid.max() - valid.min()) * 100, valid.lt(latest).mean() * 100


def event_moves(history: pd.DataFrame, releases: pd.DataFrame, close: pd.Series) -> pd.DataFrame:
    if history.empty or releases.empty or close.empty:
        return pd.DataFrame()
    cal = exchange()
    closes = pd.DatetimeIndex([cal.session_close(day) for day in close.index])
    values = []
    for event in releases.sort_values("period", ascending=False).head(8).itertuples(index=False):
        index = closes.searchsorted(event.release, side="right")
        if index == 0 or index == len(close) or close.iloc[index - 1:index + 1].isna().any():
            continue
        before = close.index[index - 1]
        chain = latest_chain(history.loc[history["available_at"].lt(event.release)], before)
        if chain.empty:
            continue
        term = term_structure(assess_quotes(chain, before), before)
        eligible = term.loc[term["Settlement (UTC)"].ge(closes[index])].dropna(subset=["Straddle ($)"])
        if eligible.empty:
            continue
        first = eligible.sort_values("Settlement (UTC)").iloc[0]
        spots = chain["spot"].iloc[0]
        realized = abs(close.iloc[index] / close.iloc[index - 1] - 1) * 100
        values.append((event.period, before, close.index[index], first["Expiry"], first["Straddle ($)"] / spots * 100,
                       first["One standard deviation ($)"] / spots * 100, realized))
    return pd.DataFrame(values, columns=["Fiscal period", "Pre-release close", "Post-release close", "Option expiry",
                                         "Straddle (% of spot)", "IV move to expiry (% of spot)",
                                         "Absolute realized close move (%)"])


def open_interest(history: pd.DataFrame, day: pd.Timestamp) -> tuple[pd.DataFrame, pd.Timestamp]:
    previous = exchange().previous_session(day)
    earlier = exchange().previous_session(previous)
    rows = history.loc[history["oi_session"].isin([earlier, previous])
                       & history["deliverable"].eq("standard") & history["multiplier"].notna()]
    if rows.empty:
        return pd.DataFrame(columns=["contract", "side", "strike", "expiry", "oi", "change"]), previous
    keys = ["contract", "side", "strike", "expiry", "settlement_at", "multiplier"]
    dated = (rows.sort_values(["observed_at", "available_at"])
             .drop_duplicates([*keys, "oi_session"], keep="last"))
    current = dated.loc[dated["oi_session"].eq(previous) & dated["expiry"].ge(day)]
    before = dated.loc[dated["oi_session"].eq(earlier), [*keys, "oi"]].rename(columns={"oi": "previous_oi"})
    joined = current.merge(before, on=keys, how="left", validate="one_to_one")
    return joined.assign(change=joined["oi"] - joined["previous_oi"]), previous


def put_call(rows: pd.DataFrame, field: str) -> tuple[float, int]:
    if rows.empty:
        return np.nan, 0
    usable = rows.loc[rows[field].notna()]
    sides = usable.groupby("side")[field].sum()
    value = sides["put"] / sides["call"] if {"put", "call"} <= set(sides.index) and sides["call"] > 0 else np.nan
    return value, len(usable)


def _gamma_dollars(rows: pd.DataFrame, grid: np.ndarray) -> np.ndarray:
    spot = grid[:, None]
    strikes = rows["strike"].to_numpy()
    rate, dividend = rows[["rate", "dividend_yield"]].to_numpy().T
    years, iv = rows[["years", "iv"]].to_numpy().T
    width = iv * np.sqrt(years)
    d1 = (np.log(spot / strikes) + (rate - dividend + iv ** 2 / 2) * years) / width
    gamma = np.exp(-dividend * years - d1 ** 2 / 2) / (sqrt(2 * np.pi) * spot * width)
    return gamma * rows["oi"].to_numpy() * rows["multiplier"].to_numpy() * spot ** 2 * .01


def zero_crossings(spots: np.ndarray, exposure: np.ndarray) -> list[float]:
    # An exact zero counts only when opposite signs bound it.
    valid = np.flatnonzero(exposure != 0)
    crossings = []
    for i, j in zip(valid, valid[1:]):
        if np.sign(exposure[i]) != np.sign(exposure[j]):
            if j > i + 1:
                crossings.append(float((spots[i + 1] + spots[j - 1]) / 2))
            else:
                crossings.append(float(spots[i] - exposure[i] * (spots[j] - spots[i]) / (exposure[j] - exposure[i])))
    return crossings


@dataclass
class GammaProfile:
    modelled: int
    contracts: int
    by_strike: pd.DataFrame
    curve: pd.DataFrame
    crossings: list[float]


def gamma_profile(checked: pd.DataFrame, interest: pd.DataFrame, day: pd.Timestamp) -> GammaProfile:
    if checked.empty or interest.empty:
        return GammaProfile(0, len(checked), pd.DataFrame(), pd.DataFrame(), [])
    matched = ["contract", "side", "strike", "expiry", "settlement_at", "multiplier"]
    dated = checked.drop(columns="oi").merge(interest[[*matched, "oi"]], on=matched, how="left",
                                             validate="one_to_one")
    years = dated["settlement_at"].sub(dated["observed_at"]).dt.total_seconds() / (365 * 86400)
    eligible = dated["quality"].eq("Retained") & years.gt(0) & dated["iv"].gt(0)
    eligible &= dated[["oi", "rate", "dividend_yield"]].notna().all(axis=1)
    rows = dated.loc[eligible].assign(years=years)
    if len(rows) / len(checked) < MIN_GAMMA_COVERAGE or set(rows["side"]) != {"put", "call"}:
        return GammaProfile(len(rows), len(checked), pd.DataFrame(), pd.DataFrame(), [])
    spot = rows["spot"].iloc[0]
    grid = spot * np.linspace(.8, 1.2, 161)
    sign = np.where(rows["side"].eq("call"), 1, -1)
    # Accumulate in batches so a large option universe does not require a full grid × chain matrix.
    exposure = np.zeros(len(grid))
    for start in range(0, len(rows), 5000):
        stop = start + 5000
        exposure += _gamma_dollars(rows.iloc[start:stop], grid) @ sign[start:stop]
    days = rows["expiry"].sub(day).dt.days
    by_strike = rows.assign(exposure=_gamma_dollars(rows, np.array([spot]))[0] * sign,
                            bucket=pd.cut(days, [-1, 0, 7, 45, np.inf], labels=BUCKETS))
    by_strike = (by_strike.groupby(["bucket", "strike", "side"], observed=True)
                 .agg(exposure=("exposure", "sum"), oi=("oi", "sum")).reset_index())
    return GammaProfile(len(rows), len(checked), by_strike, pd.DataFrame({"Spot ($)": grid, "Net gamma": exposure}),
                        zero_crossings(grid, exposure))

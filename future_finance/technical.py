"""Price structure and intraday indicators."""

import numpy as np
import pandas as pd

from .market_calendar import exchange


def _wilder(values: pd.Series, window: int = 14) -> pd.Series:
    result = pd.Series(index=values.index, dtype=float)
    blocks = values.isna().cumsum()
    for _, block in values.dropna().groupby(blocks):
        if len(block) >= window:
            seeded = block.iloc[window - 1:].copy()
            seeded.iloc[0] = block.iloc[:window].mean()
            result.loc[seeded.index] = seeded.ewm(alpha=1 / window, adjust=False).mean()
    return result


def technical(bars: pd.DataFrame) -> pd.DataFrame:
    high, low, close = bars["split_high"], bars["split_low"], bars["split_close"]
    up, down = high.diff(), -low.diff()
    usable = up.notna() & down.notna() & close.notna()
    plus = up.where(up.gt(down) & up.gt(0), 0).where(usable)
    minus = down.where(down.gt(up) & down.gt(0), 0).where(usable)
    prior = close.shift()
    ranges = pd.concat([high - low, (high - prior).abs(), (low - prior).abs()], axis=1).max(axis=1, skipna=False)
    average = _wilder(ranges).where(lambda x: x.gt(0))
    pos = _wilder(plus).div(average).mul(100)
    neg = _wilder(minus).div(average).mul(100)
    total = pos + neg
    dx = (pos - neg).abs().div(total.where(total.gt(0))).mul(100).mask(total.eq(0), 0)
    width = close.rolling(20).std(ddof=0).mul(400).div(close.rolling(20).mean())
    return pd.DataFrame({"ADX (14)": _wilder(dx), "+DI": pos, "−DI": neg, "Bandwidth (%)": width})


def swings(bars: pd.DataFrame, radius: int = 3) -> pd.DataFrame:
    rows = []
    for kind, field in (("Swing high", "split_high"), ("Swing low", "split_low")):
        values = bars[field] if kind == "Swing high" else -bars[field]
        left = values.shift().rolling(radius).max()
        right = values.iloc[::-1].shift().rolling(radius).max().iloc[::-1]
        for day in values.loc[values.gt(left) & values.gt(right)].index:
            confirmed = values.index[values.index.get_loc(day) + radius]
            rows.append((day, confirmed, kind, bars.at[day, field]))
    return pd.DataFrame(rows, columns=["Pivot session", "Confirmed session", "Level", "Split-adjusted price"]
                        ).sort_values("Confirmed session", ascending=False)


def intraday_profile(known: pd.DataFrame, day: pd.Timestamp) -> tuple[pd.DataFrame, pd.DataFrame]:
    if known.empty:
        return pd.DataFrame(), pd.DataFrame()
    calendar = exchange()
    opening, close = calendar.session_open(day), calendar.session_close(day)
    rows = (known.loc[known["start_at"].ge(opening) & known["end_at"].le(close)]
            .sort_values("available_at").drop_duplicates("start_at", keep="last").sort_values("start_at").copy())
    if (rows.empty or rows["start_at"].iloc[0] != opening or rows["end_at"].iloc[-1] != close
            or not rows["start_at"].iloc[1:].reset_index(drop=True).eq(
                rows["end_at"].iloc[:-1].reset_index(drop=True)).all() or rows["volume"].sum() <= 0):
        return rows, pd.DataFrame()
    price = rows[["high", "low", "close"]].mean(axis=1)
    volume = rows["volume"]
    rows["VWAP proxy"] = price.mul(volume).cumsum().div(volume.cumsum().where(volume.cumsum().gt(0)))
    minimum, maximum = rows["low"].min(), rows["high"].max()
    edges = np.linspace(minimum - .005, maximum + .005, 21)
    shares, _ = np.histogram(price, bins=edges, weights=volume)
    peak = shares.argmax()
    left = right = peak
    while shares[left:right + 1].sum() < .7 * shares.sum():
        previous = shares[left - 1] if left else -1
        following = shares[right + 1] if right + 1 < len(shares) else -1
        if previous >= following:
            left -= 1
        else:
            right += 1
    positions = np.arange(len(shares))
    profile = pd.DataFrame({"Bin low ($)": edges[:-1], "Bin high ($)": edges[1:], "Shares": shares,
                            "Point of control": positions == peak, "70% value area": (positions >= left)
                            & (positions <= right)})
    return rows, profile

"""NYSE session dates and local capture windows."""

from datetime import date, datetime, time, timedelta
from functools import cache

import exchange_calendars as xcals
import pandas as pd

from .scope import NEW_YORK

WINDOWS = ("pre-open", "post-close", "late")


@cache
def exchange():
    return xcals.get_calendar("XNYS")


def capture_cutoff(session: date) -> datetime:
    return exchange().session_close(session).to_pydatetime().astimezone(NEW_YORK) + timedelta(minutes=30)


def sessions_between(first: date, last: date) -> pd.DatetimeIndex:
    return exchange().sessions_in_range(first, last)


def scheduled_window(now: datetime) -> str | None:
    local = now.astimezone(NEW_YORK)
    day = local.date()
    calendar = exchange()
    if not calendar.is_session(day):
        return None
    opening = calendar.session_open(day).to_pydatetime().astimezone(NEW_YORK)
    if datetime.combine(day, time(8, 30), NEW_YORK) <= local < opening:
        return "pre-open"
    if local >= datetime.combine(day, time(18, 30), NEW_YORK):
        return "late"
    if local >= capture_cutoff(day):
        return "post-close"
    return None

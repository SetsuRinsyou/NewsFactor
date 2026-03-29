from __future__ import annotations

from datetime import date, datetime
from typing import Union

import pandas as pd

DateLike = Union[str, date, datetime, pd.Timestamp]


def to_date(d: DateLike) -> pd.Timestamp:
    return pd.Timestamp(d).normalize()


def get_trading_dates(
    market: str,
    start: DateLike,
    end: DateLike,
) -> pd.DatetimeIndex:
    """Return trading dates for the given market between start and end (inclusive).

    Uses pandas_market_calendars when available; falls back to simple business days.

    Args:
        market: "cn" for A-share (XSHG) or "us" for NYSE.
        start: Start date.
        end: End date.

    Returns:
        pd.DatetimeIndex of trading dates (UTC-normalized timestamps).
    """
    start_ts = to_date(start)
    end_ts = to_date(end)

    calendar_map = {"cn": "XSHG", "us": "NYSE"}
    cal_name = calendar_map.get(market.lower(), "NYSE")

    try:
        import pandas_market_calendars as mcal

        cal = mcal.get_calendar(cal_name)
        schedule = cal.schedule(
            start_date=start_ts.strftime("%Y-%m-%d"),
            end_date=end_ts.strftime("%Y-%m-%d"),
        )
        return mcal.date_range(schedule, frequency="1D").normalize().unique()
    except Exception:
        # Fallback: business days
        return pd.bdate_range(start=start_ts, end=end_ts)


def align_to_trading_dates(
    df: pd.DataFrame,
    market: str,
    start: DateLike,
    end: DateLike,
    date_col: str = "date",
) -> pd.DataFrame:
    """Keep only rows whose date falls on a trading day."""
    td = get_trading_dates(market, start, end)
    # Strip timezone (pandas_market_calendars returns UTC-aware timestamps)
    if td.tz is not None:
        td = td.tz_localize(None)
    trading = set(td.normalize())
    mask = pd.to_datetime(df[date_col]).dt.tz_localize(None).dt.normalize().isin(trading)
    return df[mask].copy()

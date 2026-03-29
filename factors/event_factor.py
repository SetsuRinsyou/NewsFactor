from __future__ import annotations

from typing import Optional

import pandas as pd

from factors.base import BaseFactorCalculator, FactorRegistry, FactorResult
from utils.logger import get_logger

logger = get_logger(__name__)


def _daily_event_intensity(nlp_df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate event_intensity to one value per (date, ticker) by summing."""
    if "event_intensity" not in nlp_df.columns:
        raise ValueError("nlp_df must contain an 'event_intensity' column.")
    agg = (
        nlp_df.groupby(["date", "ticker"])["event_intensity"]
        .sum()
        .reset_index()
    )
    agg["date"] = pd.to_datetime(agg["date"]).dt.normalize()
    return agg


@FactorRegistry.register("event_intensity")
class EventIntensityFactor(BaseFactorCalculator):
    """Rolling-decayed event intensity factor.

    Sums keyword-match counts on each day, then applies exponential decay
    so that events further in the past have less weight.

    Factor value = ewm(daily_event_intensity, halflife=decay_days).

    Args:
        decay_days: EWM half-life in trading days (default 3).
    """

    def __init__(self, decay_days: int = 3):
        self.decay_days = decay_days

    def compute(
        self,
        nlp_df: pd.DataFrame,
        market_df: pd.DataFrame,
        **kwargs,
    ) -> FactorResult:
        decay = kwargs.get("decay_days", self.decay_days)
        agg = _daily_event_intensity(nlp_df)
        wide = agg.pivot(index="date", columns="ticker", values="event_intensity")
        wide = wide.reindex(market_df.index).fillna(0.0)
        ewm = wide.ewm(halflife=decay, min_periods=1).mean()

        series = (
            ewm.stack(future_stack=True)
            .dropna()
            .rename("event_intensity")
        )
        series.index.names = ["date", "ticker"]
        return FactorResult(
            name="event_intensity",
            values=series,
            meta={"decay_days": decay},
        )


@FactorRegistry.register("event_type_dummy")
class EventTypeFactor(BaseFactorCalculator):
    """Binary dummy factor: 1 if a given event type was mentioned on that day, else 0.

    Useful for isolating the impact of a specific event category (e.g. earnings
    announcements) without conflating other event types.

    Args:
        event_type: One of "earnings", "merger", "litigation", "dividend", "leadership".
        decay_days: EWM half-life for the binary signal (default 3).
    """

    def __init__(self, event_type: str = "earnings", decay_days: int = 3):
        self.event_type = event_type
        self.decay_days = decay_days

    def compute(
        self,
        nlp_df: pd.DataFrame,
        market_df: pd.DataFrame,
        **kwargs,
    ) -> FactorResult:
        etype = kwargs.get("event_type", self.event_type)
        decay = kwargs.get("decay_days", self.decay_days)

        if "event_type" not in nlp_df.columns:
            raise ValueError("nlp_df must contain an 'event_type' column.")

        subset = nlp_df.copy()
        subset["_match"] = (subset["event_type"] == etype).astype(float)
        agg = (
            subset.groupby(["date", "ticker"])["_match"]
            .max()
            .reset_index()
        )
        agg["date"] = pd.to_datetime(agg["date"]).dt.normalize()

        wide = agg.pivot(index="date", columns="ticker", values="_match")
        wide = wide.reindex(market_df.index).fillna(0.0)
        ewm = wide.ewm(halflife=decay, min_periods=1).mean()

        series = (
            ewm.stack(future_stack=True)
            .dropna()
            .rename(f"event_type_{etype}")
        )
        series.index.names = ["date", "ticker"]
        return FactorResult(
            name="event_type_dummy",
            values=series,
            meta={"event_type": etype, "decay_days": decay},
        )

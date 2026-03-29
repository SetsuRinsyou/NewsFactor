from __future__ import annotations

import pandas as pd

from factors.base import BaseFactorCalculator, FactorRegistry, FactorResult
from utils.logger import get_logger

logger = get_logger(__name__)


def _daily_compound(nlp_df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate compound sentiment scores to one value per (date, ticker).

    Uses mean compound across all articles for that day.
    """
    if "compound" not in nlp_df.columns:
        raise ValueError("nlp_df must contain a 'compound' column.")
    agg = (
        nlp_df.groupby(["date", "ticker"])["compound"]
        .mean()
        .reset_index()
        .rename(columns={"compound": "compound_daily"})
    )
    agg["date"] = pd.to_datetime(agg["date"]).dt.normalize()
    return agg


def _pivot_and_fill(agg: pd.DataFrame, prices: pd.DataFrame) -> pd.DataFrame:
    """Pivot to wide [date × ticker], reindex to price dates, forward-fill short gaps."""
    wide = agg.pivot(index="date", columns="ticker", values="compound_daily")
    wide = wide.reindex(prices.index)
    wide = wide.ffill(limit=3)  # fill at most 3 consecutive missing days
    return wide


@FactorRegistry.register("sentiment_ma")
class SentimentMAFactor(BaseFactorCalculator):
    """Rolling mean of daily compound sentiment score.

    Factor value on date t = mean(compound_daily[t-window+1 : t]).

    Args:
        window: Look-back window in trading days (default 5).
    """

    def __init__(self, window: int = 5):
        self.window = window

    def compute(
        self,
        nlp_df: pd.DataFrame,
        market_df: pd.DataFrame,
        **kwargs,
    ) -> FactorResult:
        window = kwargs.get("window", self.window)
        agg = _daily_compound(nlp_df)
        wide = _pivot_and_fill(agg, market_df)
        rolled = wide.rolling(window=window, min_periods=1).mean()

        series = (
            rolled.stack(future_stack=True)
            .dropna()
            .rename("sentiment_ma")
        )
        series.index.names = ["date", "ticker"]
        return FactorResult(
            name="sentiment_ma",
            values=series,
            meta={"window": window},
        )


@FactorRegistry.register("sentiment_ewm")
class SentimentEWMFactor(BaseFactorCalculator):
    """Exponentially-weighted mean of daily compound sentiment score.

    Gives more weight to recent articles. Useful for capturing sentiment momentum.

    Args:
        halflife: Half-life in trading days (default 3).
    """

    def __init__(self, halflife: float = 3.0):
        self.halflife = halflife

    def compute(
        self,
        nlp_df: pd.DataFrame,
        market_df: pd.DataFrame,
        **kwargs,
    ) -> FactorResult:
        halflife = kwargs.get("halflife", self.halflife)
        agg = _daily_compound(nlp_df)
        wide = _pivot_and_fill(agg, market_df)
        ewm = wide.ewm(halflife=halflife, min_periods=1).mean()

        series = (
            ewm.stack(future_stack=True)
            .dropna()
            .rename("sentiment_ewm")
        )
        series.index.names = ["date", "ticker"]
        return FactorResult(
            name="sentiment_ewm",
            values=series,
            meta={"halflife": halflife},
        )

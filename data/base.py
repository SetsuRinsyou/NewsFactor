from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

import pandas as pd

from utils.date_utils import DateLike


class BaseDataLoader(ABC):
    """Abstract base class for all data loaders.

    Subclasses must implement `fetch`, which returns a DataFrame with
    at least the columns: date, ticker, text, source.
    """

    # Canonical schema columns for text loaders
    TEXT_COLS = ["date", "ticker", "text", "source"]

    @abstractmethod
    def fetch(
        self,
        tickers: List[str],
        start: DateLike,
        end: DateLike,
    ) -> pd.DataFrame:
        """Fetch data for the given tickers and date range.

        Returns:
            DataFrame with columns [date, ticker, text, source] for text loaders,
            or a prices DataFrame [date × ticker] for market loaders.
        """

    @staticmethod
    def _ensure_schema(df: pd.DataFrame, required: List[str]) -> pd.DataFrame:
        for col in required:
            if col not in df.columns:
                raise ValueError(
                    f"Loader output missing required column '{col}'. "
                    f"Got: {list(df.columns)}"
                )
        df["date"] = pd.to_datetime(df["date"]).dt.normalize()
        return df

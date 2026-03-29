from __future__ import annotations

from typing import List, Optional, Tuple

import pandas as pd

from factors.base import FactorResult
from utils.logger import get_logger

logger = get_logger(__name__)


class FactorSignalGenerator:
    """Convert a FactorResult into alphalens-compatible inputs.

    alphalens requires:
    - factor:  pd.Series with MultiIndex (date, ticker) → float
    - prices:  pd.DataFrame with DatetimeIndex rows and ticker columns

    Usage:
        gen = FactorSignalGenerator(periods=(1, 5, 20), quantiles=5)
        factor_data = gen.build(result, prices)
    """

    def __init__(
        self,
        periods: Tuple[int, ...] = (1, 5, 20),
        quantiles: int = 5,
        filter_zscore: int = 20,
        max_loss: float = 0.35,
    ):
        self.periods = periods
        self.quantiles = quantiles
        self.filter_zscore = filter_zscore
        self.max_loss = max_loss

    def build(
        self,
        result: FactorResult,
        prices: pd.DataFrame,
    ) -> pd.DataFrame:
        """Call alphalens.utils.get_clean_factor_and_forward_returns().

        Args:
            result: FactorResult from a BaseFactorCalculator.
            prices: prices DataFrame [date × ticker].

        Returns:
            alphalens factor_data DataFrame with MultiIndex (date, ticker).
        """
        try:
            from alphalens.utils import get_clean_factor_and_forward_returns
        except ImportError as e:
            raise ImportError(
                "alphalens-reloaded is required. "
                "Install with: pip install alphalens-reloaded"
            ) from e

        factor = self._prepare_factor(result, prices)
        prices_clean = self._prepare_prices(prices, factor)

        logger.info(
            f"FactorSignalGenerator: building factor_data for '{result.name}' "
            f"periods={self.periods}"
        )
        factor_data = get_clean_factor_and_forward_returns(
            factor=factor,
            prices=prices_clean,
            quantiles=self.quantiles,
            periods=self.periods,
            filter_zscore=self.filter_zscore,
            max_loss=self.max_loss,
        )
        return factor_data

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _prepare_factor(
        result: FactorResult, prices: pd.DataFrame
    ) -> pd.Series:
        """Align factor values to tickers present in prices."""
        factor = result.values.copy()
        # Rebuild the MultiIndex with normalised datetime dates
        dates = pd.to_datetime(factor.index.get_level_values("date")).normalize()
        tickers = factor.index.get_level_values("ticker")
        factor.index = pd.MultiIndex.from_arrays(
            [dates, tickers], names=["date", "ticker"]
        )
        # Keep only tickers present in prices
        valid_tickers = set(prices.columns)
        mask = tickers.isin(valid_tickers)
        factor = factor[mask]
        return factor.sort_index()

    @staticmethod
    def _prepare_prices(
        prices: pd.DataFrame, factor: pd.Series
    ) -> pd.DataFrame:
        """Keep only dates/tickers needed by the factor."""
        prices = prices.copy()
        prices.index = pd.to_datetime(prices.index).normalize()
        tickers = factor.index.get_level_values("ticker").unique()
        cols = [t for t in tickers if t in prices.columns]
        return prices[cols].sort_index()

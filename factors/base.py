from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Type

import pandas as pd


@dataclass
class FactorResult:
    """Holds the output of a factor computation.

    Attributes:
        name:   Registered factor name (e.g. "sentiment_ma").
        values: pd.Series with MultiIndex (date, ticker) → float factor value.
        meta:   Optional dict for extra info (params used, coverage stats, etc.).
    """

    name: str
    values: pd.Series
    meta: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not isinstance(self.values.index, pd.MultiIndex):
            raise ValueError(
                "FactorResult.values must have a MultiIndex with levels (date, ticker)."
            )
        self.values.index.names = ["date", "ticker"]


class BaseFactorCalculator(ABC):
    """Abstract base class for all factor calculators.

    Subclasses must implement ``compute`` and should be registered via
    ``@FactorRegistry.register("factor_name")``.
    """

    @abstractmethod
    def compute(
        self,
        nlp_df: pd.DataFrame,
        market_df: pd.DataFrame,
        **kwargs,
    ) -> FactorResult:
        """Compute factor values.

        Args:
            nlp_df: DataFrame output from SentimentAnalyzer.analyze_df() and/or
                    EventDetector.tag_df().  Columns include at minimum:
                    [date, ticker, text, source, positive, negative, neutral, compound,
                     event_type, event_intensity].
            market_df: Prices DataFrame [date × ticker] of adjusted close prices.
            **kwargs: Additional compute-time overrides.

        Returns:
            FactorResult with a MultiIndex(date, ticker) Series.
        """


class FactorRegistry:
    """Central registry for factor calculators.

    Usage:
        @FactorRegistry.register("my_factor")
        class MyFactor(BaseFactorCalculator):
            def compute(self, nlp_df, market_df, **kwargs) -> FactorResult:
                ...

        FactorRegistry.list_factors()        # -> ['my_factor', ...]
        factor = FactorRegistry.build("my_factor", window=5)
        result = factor.compute(nlp_df, market_df)
    """

    _registry: Dict[str, Type[BaseFactorCalculator]] = {}

    @classmethod
    def register(cls, name: str) -> Callable[[Type[BaseFactorCalculator]], Type[BaseFactorCalculator]]:
        """Class decorator to register a factor under a given name."""
        def decorator(klass: Type[BaseFactorCalculator]) -> Type[BaseFactorCalculator]:
            if name in cls._registry:
                raise ValueError(
                    f"Factor '{name}' is already registered by "
                    f"{cls._registry[name].__qualname__}."
                )
            cls._registry[name] = klass
            return klass
        return decorator

    @classmethod
    def list_factors(cls) -> List[str]:
        """Return a sorted list of all registered factor names."""
        return sorted(cls._registry.keys())

    @classmethod
    def build(cls, name: str, **kwargs) -> BaseFactorCalculator:
        """Instantiate a registered factor by name, passing kwargs to __init__."""
        if name not in cls._registry:
            raise KeyError(
                f"Factor '{name}' is not registered. "
                f"Available: {cls.list_factors()}"
            )
        return cls._registry[name](**kwargs)

    @classmethod
    def get_class(cls, name: str) -> Type[BaseFactorCalculator]:
        if name not in cls._registry:
            raise KeyError(f"Factor '{name}' not found. Available: {cls.list_factors()}")
        return cls._registry[name]

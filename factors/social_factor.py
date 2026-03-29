from __future__ import annotations

import pandas as pd

from factors.base import BaseFactorCalculator, FactorRegistry, FactorResult
from utils.logger import get_logger

logger = get_logger(__name__)


@FactorRegistry.register("social_buzz")
class SocialBuzzFactor(BaseFactorCalculator):
    """Normalised mention-volume factor from social media sources.

    Counts unique article/post mentions per (date, ticker) from social sources
    (twitter, stocktwits, weibo), then z-scores across tickers on each day.

    Args:
        window: Rolling window for z-score normalisation (default 5 trading days).
        sources: Social source labels to include. Defaults to all social sources.
    """

    _SOCIAL_SOURCES = {"twitter", "stocktwits", "weibo"}

    def __init__(self, window: int = 5, sources: set | None = None):
        self.window = window
        self.sources = sources or self._SOCIAL_SOURCES

    def compute(
        self,
        nlp_df: pd.DataFrame,
        market_df: pd.DataFrame,
        **kwargs,
    ) -> FactorResult:
        window = kwargs.get("window", self.window)
        social = nlp_df[nlp_df["source"].isin(self.sources)].copy()

        if social.empty:
            logger.warning("SocialBuzzFactor: no social-source rows found in nlp_df.")
            empty = pd.Series(
                [], dtype=float, name="social_buzz",
                index=pd.MultiIndex.from_tuples([], names=["date", "ticker"]),
            )
            return FactorResult(name="social_buzz", values=empty)

        social["date"] = pd.to_datetime(social["date"]).dt.normalize()
        counts = (
            social.groupby(["date", "ticker"])
            .size()
            .reset_index(name="mention_count")
        )
        wide = counts.pivot(index="date", columns="ticker", values="mention_count")
        wide = wide.reindex(market_df.index).fillna(0.0)

        # Rolling z-score: (x - rolling_mean) / rolling_std
        mu = wide.rolling(window=window, min_periods=2).mean()
        sigma = wide.rolling(window=window, min_periods=2).std()
        zscore = (wide - mu) / sigma.replace(0, float("nan"))
        zscore = zscore.fillna(0.0)

        series = (
            zscore.stack(future_stack=True)
            .dropna()
            .rename("social_buzz")
        )
        series.index.names = ["date", "ticker"]
        return FactorResult(
            name="social_buzz",
            values=series,
            meta={"window": window, "sources": list(self.sources)},
        )


@FactorRegistry.register("sentiment_divergence")
class SentimentDivergenceFactor(BaseFactorCalculator):
    """Sentiment divergence between news and social media sources.

    Measures whether news sentiment and social sentiment disagree, which can
    signal contrarian opportunities or information asymmetry.

    Factor value = compound_news - compound_social (daily averages).
    Positive = news is more bullish than social; Negative = social more bullish.

    Args:
        news_sources: Source labels treated as news (default: em_news, newsapi, rss).
        social_sources: Source labels treated as social.
    """

    _DEFAULT_NEWS = {"em_news", "newsapi", "rss"}
    _DEFAULT_SOCIAL = {"twitter", "stocktwits", "weibo"}

    def __init__(
        self,
        news_sources: set | None = None,
        social_sources: set | None = None,
    ):
        self.news_sources = news_sources or self._DEFAULT_NEWS
        self.social_sources = social_sources or self._DEFAULT_SOCIAL

    def compute(
        self,
        nlp_df: pd.DataFrame,
        market_df: pd.DataFrame,
        **kwargs,
    ) -> FactorResult:
        if "compound" not in nlp_df.columns or "source" not in nlp_df.columns:
            raise ValueError("nlp_df must contain 'compound' and 'source' columns.")

        def _agg(subset: pd.DataFrame, label: str) -> pd.DataFrame:
            if subset.empty:
                return pd.DataFrame(columns=["date", "ticker", label])
            g = (
                subset.groupby(["date", "ticker"])["compound"]
                .mean()
                .reset_index()
                .rename(columns={"compound": label})
            )
            g["date"] = pd.to_datetime(g["date"]).dt.normalize()
            return g

        news_df = nlp_df[nlp_df["source"].isin(self.news_sources)]
        social_df = nlp_df[nlp_df["source"].isin(self.social_sources)]

        news_agg = _agg(news_df, "news_compound")
        social_agg = _agg(social_df, "social_compound")

        merged = pd.merge(news_agg, social_agg, on=["date", "ticker"], how="inner")
        if merged.empty:
            logger.warning(
                "SentimentDivergenceFactor: no overlapping (date, ticker) between "
                "news and social sources."
            )
            empty = pd.Series(
                [], dtype=float, name="sentiment_divergence",
                index=pd.MultiIndex.from_tuples([], names=["date", "ticker"]),
            )
            return FactorResult(name="sentiment_divergence", values=empty)

        merged["divergence"] = merged["news_compound"] - merged["social_compound"]
        wide = merged.pivot(index="date", columns="ticker", values="divergence")
        wide = wide.reindex(market_df.index)
        wide = wide.ffill(limit=3)

        series = (
            wide.stack(future_stack=True)
            .dropna()
            .rename("sentiment_divergence")
        )
        series.index.names = ["date", "ticker"]
        return FactorResult(
            name="sentiment_divergence",
            values=series,
            meta={
                "news_sources": list(self.news_sources),
                "social_sources": list(self.social_sources),
            },
        )

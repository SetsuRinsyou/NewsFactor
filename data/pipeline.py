from __future__ import annotations

from typing import Dict, List, Optional

import pandas as pd
import yaml

from data.base import BaseDataLoader
from data.loaders.market_loader import MarketLoader
from utils.cache import disk_cache
from utils.date_utils import DateLike, align_to_trading_dates
from utils.logger import get_logger

logger = get_logger(__name__)


class DataPipeline:
    """Orchestrate multiple text loaders and one market loader.

    Usage:
        pipeline = DataPipeline.from_config("config/config.yaml", market="cn")
        pipeline.add_loader(EMNewsLoader())
        text_df, prices = pipeline.run(["600519"], "2024-01-01", "2024-06-01")
    """

    def __init__(
        self,
        market: str = "cn",
        cache_dir: str = ".cache",
        cache_ttl_hours: int = 24,
    ):
        self.market = market
        self._cache_dir = cache_dir
        self._cache_ttl = cache_ttl_hours * 3600
        self._text_loaders: List[BaseDataLoader] = []
        self._market_loader = MarketLoader(market=market)

    # ------------------------------------------------------------------
    # Builder helpers
    # ------------------------------------------------------------------

    @classmethod
    def from_config(cls, config_path: str, market: Optional[str] = None) -> "DataPipeline":
        """Instantiate and auto-configure enabled loaders from config.yaml."""
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)

        m = market or cfg.get("market", {}).get("default", "cn")
        data_cfg = cfg.get("data", {})
        news_cfg = cfg.get("news", {})

        pipeline = cls(
            market=m,
            cache_dir=data_cfg.get("cache_dir", ".cache"),
            cache_ttl_hours=data_cfg.get("cache_ttl_hours", 24),
        )

        if news_cfg.get("em_news", {}).get("enabled", False):
            from data.loaders.em_news import EMNewsLoader

            pipeline.add_loader(
                EMNewsLoader(delay=news_cfg["em_news"].get("delay_seconds", 0.5))
            )

        if news_cfg.get("newsapi", {}).get("enabled", False):
            import os
            from data.loaders.newsapi_loader import NewsAPILoader

            pipeline.add_loader(
                NewsAPILoader(
                    api_key=os.path.expandvars(news_cfg["newsapi"].get("api_key", "")),
                    page_size=news_cfg["newsapi"].get("page_size", 100),
                )
            )

        if news_cfg.get("rss", {}).get("enabled", False):
            from data.loaders.newsapi_loader import RSSLoader

            pipeline.add_loader(RSSLoader(feeds=news_cfg["rss"].get("feeds", [])))

        if news_cfg.get("twitter", {}).get("enabled", False):
            import os
            from data.loaders.social_loader import TwitterLoader

            pipeline.add_loader(
                TwitterLoader(
                    bearer_token=os.path.expandvars(
                        news_cfg["twitter"].get("bearer_token", "")
                    ),
                    max_results=news_cfg["twitter"].get("max_results", 100),
                )
            )

        if news_cfg.get("stocktwits", {}).get("enabled", False):
            from data.loaders.social_loader import StockTwitsLoader

            pipeline.add_loader(StockTwitsLoader())

        if news_cfg.get("weibo", {}).get("enabled", False):
            from data.loaders.social_loader import WeiboLoader

            pipeline.add_loader(WeiboLoader())

        if news_cfg.get("gdelt", {}).get("enabled", False):
            from data.loaders.gdelt_loader import GDELTLoader

            gdelt_cfg = news_cfg["gdelt"]
            pipeline.add_loader(
                GDELTLoader(
                    language=gdelt_cfg.get("language"),
                    num_records=gdelt_cfg.get("num_records", 250),
                    delay=gdelt_cfg.get("delay_seconds", 1.0),
                )
            )

        return pipeline

    def add_loader(self, loader: BaseDataLoader) -> "DataPipeline":
        self._text_loaders.append(loader)
        return self

    # ------------------------------------------------------------------
    # Main execution
    # ------------------------------------------------------------------

    def run(
        self,
        tickers: List[str],
        start: DateLike,
        end: DateLike,
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Fetch text data + market prices.

        Returns:
            text_df: DataFrame with columns [date, ticker, text, source], aligned to
                     trading days, deduplicated.
            prices:  DataFrame [date × ticker] of adjusted close prices.
        """
        text_df = self._fetch_text(tickers, start, end)
        prices = self._fetch_prices(tickers, start, end)
        return text_df, prices

    # ------------------------------------------------------------------
    # Internal helpers (cached)
    # ------------------------------------------------------------------

    def _fetch_text(
        self, tickers: List[str], start: DateLike, end: DateLike
    ) -> pd.DataFrame:
        frames = []
        for loader in self._text_loaders:
            name = type(loader).__name__
            logger.info(f"DataPipeline: running {name}")
            try:
                df = self._cached_loader(loader, tickers, start, end)
                frames.append(df)
            except Exception as exc:
                logger.error(f"DataPipeline: {name} error: {exc}")

        if not frames:
            return pd.DataFrame(columns=["date", "ticker", "text", "source"])

        combined = pd.concat(frames, ignore_index=True)
        combined = combined.drop_duplicates(subset=["date", "ticker", "text"])
        combined = align_to_trading_dates(combined, self.market, start, end)
        combined = combined.sort_values(["date", "ticker"]).reset_index(drop=True)
        return combined

    def _fetch_prices(
        self, tickers: List[str], start: DateLike, end: DateLike
    ) -> pd.DataFrame:
        logger.info("DataPipeline: fetching market prices")
        key = f"prices_{self.market}_{'_'.join(sorted(tickers))}_{start}_{end}"
        cache_fn = disk_cache(ttl=self._cache_ttl, cache_dir=self._cache_dir)

        @cache_fn
        def _load(k):  # noqa: ARG001  (k used only as cache key)
            return self._market_loader.fetch(tickers, start, end)

        return _load(key)

    def _cached_loader(
        self,
        loader: BaseDataLoader,
        tickers: List[str],
        start: DateLike,
        end: DateLike,
    ) -> pd.DataFrame:
        """Wrap loader.fetch with disk cache."""
        key = (
            f"{type(loader).__name__}_"
            f"{'_'.join(sorted(tickers))}_"
            f"{pd.Timestamp(start).date()}_{pd.Timestamp(end).date()}"
        )
        cache_fn = disk_cache(ttl=self._cache_ttl, cache_dir=self._cache_dir)

        @cache_fn
        def _load(k):  # noqa: ARG001
            return loader.fetch(tickers, start, end)

        return _load(key)

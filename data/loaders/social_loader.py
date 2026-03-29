from __future__ import annotations

import os
import time
from typing import List, Optional

import pandas as pd

from data.base import BaseDataLoader
from utils.date_utils import DateLike
from utils.logger import get_logger

logger = get_logger(__name__)


class TwitterLoader(BaseDataLoader):
    """Fetch tweets mentioning $TICKER cashtags via Twitter API v2 (tweepy).

    Requires TWITTER_BEARER_TOKEN environment variable.
    """

    def __init__(self, bearer_token: Optional[str] = None, max_results: int = 100):
        self._token = bearer_token or os.environ.get("TWITTER_BEARER_TOKEN", "")
        if not self._token:
            raise ValueError(
                "Twitter bearer token not provided. Set TWITTER_BEARER_TOKEN env var."
            )
        self._max_results = min(max(10, max_results), 100)

    def fetch(
        self,
        tickers: List[str],
        start: DateLike,
        end: DateLike,
    ) -> pd.DataFrame:
        try:
            import tweepy
        except ImportError as e:
            raise ImportError("tweepy is required for TwitterLoader") from e

        client = tweepy.Client(bearer_token=self._token, wait_on_rate_limit=True)
        start_ts = pd.Timestamp(start).tz_localize("UTC") if pd.Timestamp(start).tzinfo is None else pd.Timestamp(start)
        end_ts = pd.Timestamp(end).tz_localize("UTC") if pd.Timestamp(end).tzinfo is None else pd.Timestamp(end)
        records = []

        for ticker in tickers:
            query = f"${ticker} lang:en -is:retweet"
            logger.info(f"TwitterLoader: querying '{query}'")
            try:
                for tweet in tweepy.Paginator(
                    client.search_recent_tweets,
                    query=query,
                    tweet_fields=["created_at", "text"],
                    start_time=start_ts.isoformat(),
                    end_time=end_ts.isoformat(),
                    max_results=self._max_results,
                ).flatten(limit=500):
                    d = pd.Timestamp(tweet.created_at).normalize().tz_localize(None)
                    records.append(
                        {"date": d, "ticker": ticker, "text": tweet.text, "source": "twitter"}
                    )
            except Exception as exc:
                logger.warning(f"TwitterLoader: failed for {ticker}: {exc}")
            time.sleep(0.5)

        if not records:
            return pd.DataFrame(columns=self.TEXT_COLS)
        return self._ensure_schema(pd.DataFrame(records), self.TEXT_COLS)


class StockTwitsLoader(BaseDataLoader):
    """Fetch messages from StockTwits public API (no auth required)."""

    BASE_URL = "https://api.stocktwits.com/api/2/streams/symbol/{ticker}.json"

    def fetch(
        self,
        tickers: List[str],
        start: DateLike,
        end: DateLike,
    ) -> pd.DataFrame:
        import requests

        start_ts = pd.Timestamp(start).normalize()
        end_ts = pd.Timestamp(end).normalize()
        records = []

        for ticker in tickers:
            logger.info(f"StockTwitsLoader: fetching {ticker}")
            url = self.BASE_URL.format(ticker=ticker)
            cursor = None
            for _ in range(10):  # max 10 pages
                params: dict = {"limit": 30}
                if cursor:
                    params["max"] = cursor
                try:
                    resp = requests.get(url, params=params, timeout=15)
                    resp.raise_for_status()
                    data = resp.json()
                except Exception as exc:
                    logger.warning(f"StockTwitsLoader: {ticker}: {exc}")
                    break

                messages = data.get("messages", [])
                if not messages:
                    break

                for msg in messages:
                    created = msg.get("created_at", "")
                    try:
                        d = pd.Timestamp(created).normalize().tz_localize(None)
                    except Exception:
                        continue
                    if d < start_ts:
                        # older than window, stop paging
                        messages = []
                        break
                    if d > end_ts:
                        continue
                    body = msg.get("body", "").strip()
                    if body:
                        records.append(
                            {"date": d, "ticker": ticker, "text": body, "source": "stocktwits"}
                        )

                if not messages:
                    break
                cursor = messages[-1]["id"]
                time.sleep(0.3)

        if not records:
            return pd.DataFrame(columns=self.TEXT_COLS)
        return self._ensure_schema(pd.DataFrame(records), self.TEXT_COLS)


class WeiboLoader(BaseDataLoader):
    """Stub loader for Weibo. Official API requires enterprise approval.

    Returns an empty DataFrame. Replace with real implementation when credentials
    are available.
    """

    def fetch(
        self,
        tickers: List[str],
        start: DateLike,
        end: DateLike,
    ) -> pd.DataFrame:
        logger.warning(
            "WeiboLoader is a stub. Weibo official API requires enterprise approval. "
            "Returning empty DataFrame."
        )
        return pd.DataFrame(columns=self.TEXT_COLS)

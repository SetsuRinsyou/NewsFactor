from __future__ import annotations

import time
from typing import List, Optional

import pandas as pd

from data.base import BaseDataLoader
from utils.date_utils import DateLike
from utils.logger import get_logger

logger = get_logger(__name__)


class NewsAPILoader(BaseDataLoader):
    """Fetch English news articles via the NewsAPI.org REST API.

    Requires NEWSAPI_KEY environment variable or explicit api_key.
    """

    BASE_URL = "https://newsapi.org/v2/everything"

    def __init__(self, api_key: Optional[str] = None, page_size: int = 100):
        import os

        self._api_key = api_key or os.environ.get("NEWSAPI_KEY", "")
        if not self._api_key:
            raise ValueError(
                "NewsAPI key not provided. Set NEWSAPI_KEY env var or pass api_key."
            )
        self._page_size = page_size

    def fetch(
        self,
        tickers: List[str],
        start: DateLike,
        end: DateLike,
    ) -> pd.DataFrame:
        import requests

        start_iso = pd.Timestamp(start).strftime("%Y-%m-%dT00:00:00")
        end_iso = pd.Timestamp(end).strftime("%Y-%m-%dT23:59:59")
        records = []

        for ticker in tickers:
            logger.info(f"NewsAPILoader: fetching '{ticker}'")
            page = 1
            while True:
                try:
                    resp = requests.get(
                        self.BASE_URL,
                        params={
                            "q": ticker,
                            "from": start_iso,
                            "to": end_iso,
                            "language": "en",
                            "pageSize": self._page_size,
                            "page": page,
                            "sortBy": "publishedAt",
                            "apiKey": self._api_key,
                        },
                        timeout=15,
                    )
                    resp.raise_for_status()
                    data = resp.json()
                except Exception as exc:
                    logger.warning(f"NewsAPILoader: failed for {ticker} page {page}: {exc}")
                    break

                articles = data.get("articles", [])
                if not articles:
                    break

                for art in articles:
                    pub = art.get("publishedAt", "")
                    title = art.get("title") or ""
                    desc = art.get("description") or ""
                    text = f"{title} {desc}".strip()
                    if not text:
                        continue
                    try:
                        d = pd.Timestamp(pub).normalize()
                    except Exception:
                        continue
                    records.append(
                        {"date": d, "ticker": ticker, "text": text, "source": "newsapi"}
                    )

                if len(articles) < self._page_size:
                    break
                page += 1
                time.sleep(0.2)

        if not records:
            return pd.DataFrame(columns=self.TEXT_COLS)
        df = pd.DataFrame(records)
        df = df[
            (df["date"] >= pd.Timestamp(start).normalize())
            & (df["date"] <= pd.Timestamp(end).normalize())
        ]
        return self._ensure_schema(df, self.TEXT_COLS)


class RSSLoader(BaseDataLoader):
    """Fetch articles from a list of RSS feed URLs using feedparser."""

    def __init__(self, feeds: List[str], ticker_map: Optional[dict] = None):
        """
        Args:
            feeds: List of RSS feed URLs.
            ticker_map: Optional dict mapping keywords → ticker symbol for tagging.
        """
        self._feeds = feeds
        self._ticker_map = ticker_map or {}

    def fetch(
        self,
        tickers: List[str],
        start: DateLike,
        end: DateLike,
    ) -> pd.DataFrame:
        try:
            import feedparser
        except ImportError as e:
            raise ImportError("feedparser is required for RSSLoader") from e

        start_ts = pd.Timestamp(start).normalize()
        end_ts = pd.Timestamp(end).normalize()
        records = []

        for url in self._feeds:
            logger.info(f"RSSLoader: parsing {url}")
            try:
                feed = feedparser.parse(url)
            except Exception as exc:
                logger.warning(f"RSSLoader: failed {url}: {exc}")
                continue

            for entry in feed.entries:
                published = entry.get("published", "") or entry.get("updated", "")
                try:
                    d = pd.Timestamp(published).normalize()
                except Exception:
                    continue
                if d < start_ts or d > end_ts:
                    continue

                title = entry.get("title", "")
                summary = entry.get("summary", "")
                text = f"{title} {summary}".strip()
                if not text:
                    continue

                # Try to map text to a ticker
                matched_ticker = None
                text_lower = text.lower()
                for keyword, tk in self._ticker_map.items():
                    if keyword.lower() in text_lower:
                        matched_ticker = tk
                        break

                # If no mapping, try to match against requested tickers directly
                if matched_ticker is None:
                    for tk in tickers:
                        if tk.lower() in text_lower:
                            matched_ticker = tk
                            break

                if matched_ticker is None:
                    continue

                records.append(
                    {"date": d, "ticker": matched_ticker, "text": text, "source": "rss"}
                )

        if not records:
            return pd.DataFrame(columns=self.TEXT_COLS)
        return self._ensure_schema(pd.DataFrame(records), self.TEXT_COLS)

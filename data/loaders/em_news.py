from __future__ import annotations

import time
from typing import List

import pandas as pd

from data.base import BaseDataLoader
from utils.date_utils import DateLike
from utils.logger import get_logger

logger = get_logger(__name__)


class EMNewsLoader(BaseDataLoader):
    """Fetch news from 东方财富 via akshare.stock_news_em().

    Returns one row per article with columns: date, ticker, text, source.
    """

    def __init__(self, delay: float = 0.5):
        self._delay = delay

    def fetch(
        self,
        tickers: List[str],
        start: DateLike,
        end: DateLike,
    ) -> pd.DataFrame:
        try:
            import akshare as ak
        except ImportError as e:
            raise ImportError("akshare is required for EMNewsLoader") from e

        start_ts = pd.Timestamp(start).normalize()
        end_ts = pd.Timestamp(end).normalize()
        records = []

        for ticker in tickers:
            logger.info(f"EMNewsLoader: fetching news for {ticker}")
            try:
                df = ak.stock_news_em(symbol=ticker)
            except Exception as exc:
                logger.warning(f"EMNewsLoader: failed for {ticker}: {exc}")
                time.sleep(self._delay)
                continue

            if df is None or df.empty:
                time.sleep(self._delay)
                continue

            # akshare returns columns like: 关键词, 新闻标题, 新闻内容, 发布时间, 文章来源, 新闻链接
            title_col = next(
                (c for c in df.columns if "标题" in c or "title" in c.lower()), None
            )
            content_col = next(
                (c for c in df.columns if "内容" in c or "content" in c.lower()), None
            )
            time_col = next(
                (c for c in df.columns if "时间" in c or "time" in c.lower() or "date" in c.lower()), None
            )

            if time_col is None:
                logger.warning(f"EMNewsLoader: no date column found for {ticker}, skipping")
                time.sleep(self._delay)
                continue

            df["_date"] = pd.to_datetime(df[time_col], errors="coerce").dt.normalize()
            df = df[(df["_date"] >= start_ts) & (df["_date"] <= end_ts)]

            for _, row in df.iterrows():
                parts = []
                if title_col and pd.notna(row.get(title_col)):
                    parts.append(str(row[title_col]))
                if content_col and pd.notna(row.get(content_col)):
                    parts.append(str(row[content_col]))
                text = " ".join(parts).strip()
                if not text:
                    continue
                records.append(
                    {
                        "date": row["_date"],
                        "ticker": ticker,
                        "text": text,
                        "source": "em_news",
                    }
                )

            time.sleep(self._delay)

        if not records:
            return pd.DataFrame(columns=self.TEXT_COLS)

        result = pd.DataFrame(records)
        return self._ensure_schema(result, self.TEXT_COLS)

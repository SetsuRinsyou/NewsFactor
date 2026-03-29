from __future__ import annotations

import time
from typing import List, Optional, Union

import pandas as pd

from data.base import BaseDataLoader
from utils.date_utils import DateLike
from utils.logger import get_logger

logger = get_logger(__name__)


class GDELTLoader(BaseDataLoader):
    """Fetch news articles from GDELT Project via gdeltdoc.

    GDELT (Global Database of Events, Language, and Tone) indexes news from
    thousands of outlets worldwide, with coverage from 2015 onwards via this API.
    No API key required; free to use.

    Company names are resolved automatically via utils.ticker_names (populated
    when a .txt file with 'code,name' format is passed to --tickers, or via
    akshare/yfinance fallback for tickers without cached names).

    Args:
        language: GDELT language filter. E.g. "Chinese" or "English".
            None means no language filter.
        num_records: Max articles per query (default 250, GDELT API max is 250).
        delay: Seconds to wait between ticker requests to be polite.
    """

    def __init__(
        self,
        language: Optional[Union[str, List[str]]] = None,
        num_records: int = 250,
        delay: float = 1.0,
    ):
        try:
            from gdeltdoc import GdeltDoc, Filters  # noqa: F401
        except ImportError as e:
            raise ImportError(
                "gdeltdoc is required for GDELTLoader. "
                "Install with: pip install gdeltdoc"
            ) from e

        self._language = language
        self._num_records = min(num_records, 250)
        self._delay = delay

    def fetch(
        self,
        tickers: List[str],
        start: DateLike,
        end: DateLike,
    ) -> pd.DataFrame:
        from gdeltdoc import GdeltDoc, Filters
        from gdeltdoc.errors import RateLimitError

        start_dt = pd.Timestamp(start).to_pydatetime()
        end_dt = pd.Timestamp(end).to_pydatetime()
        start_ts = pd.Timestamp(start).normalize()
        end_ts = pd.Timestamp(end).normalize()

        gd = GdeltDoc()
        records = []

        # Resolve company names for all tickers via ticker_names cache
        # (populated from .txt file names, or akshare/yfinance on first miss)
        from utils.ticker_names import resolve_names
        keyword_map = resolve_names(tickers)
        logger.info(
            "GDELTLoader: resolved keywords: "
            + ", ".join(f"{k}={v!r}" for k, v in keyword_map.items())
        )

        for ticker in tickers:
            keyword = keyword_map.get(ticker, ticker)
            logger.info(f"GDELTLoader: querying '{keyword}' for {ticker}")

            df = None
            for attempt in range(2):
                try:
                    f = Filters(
                        keyword=keyword,
                        start_date=start_dt,
                        end_date=end_dt,
                        num_records=self._num_records,
                        language=self._language,
                    )
                    df = gd.article_search(f)
                    break
                except RateLimitError:
                    if attempt == 0:
                        wait = 120
                        logger.warning(
                            f"GDELTLoader: rate limited for {ticker}, "
                            f"waiting {wait}s before retry"
                        )
                        time.sleep(wait)
                    else:
                        logger.warning(
                            f"GDELTLoader: rate limited again for {ticker}, skipping"
                        )
                except Exception as exc:
                    exc_msg = repr(exc) if str(exc) == "" else str(exc)
                    logger.warning(
                        f"GDELTLoader: failed for {ticker} "
                        f"(keyword={keyword!r}): {exc_msg}"
                    )
                    break

            if df is None or df.empty:
                logger.info(f"GDELTLoader: no results for {ticker}")
                time.sleep(self._delay)
                continue

            # GDELT article_search returns columns including:
            # url, url_mobile, title, seendate, socialimage, domain, language, sourcecountry
            date_col = next(
                (c for c in df.columns if c.lower() in ("seendate", "date", "publishdate")),
                None,
            )
            title_col = next(
                (c for c in df.columns if c.lower() == "title"), None
            )

            if date_col is None:
                logger.warning(f"GDELTLoader: no date column in response for {ticker}. Columns: {df.columns.tolist()}")
                time.sleep(self._delay)
                continue

            for _, row in df.iterrows():
                try:
                    raw = pd.Timestamp(row[date_col])
                    d = (raw.tz_convert(None) if raw.tzinfo is not None else raw).normalize()
                except Exception:
                    continue

                if d < start_ts or d > end_ts:
                    continue

                text = str(row[title_col]).strip() if title_col and pd.notna(row.get(title_col)) else ""
                if not text:
                    continue

                records.append({
                    "date": d,
                    "ticker": ticker,
                    "text": text,
                    "source": "gdelt",
                })

            time.sleep(self._delay)

        if not records:
            return pd.DataFrame(columns=self.TEXT_COLS)

        return self._ensure_schema(pd.DataFrame(records), self.TEXT_COLS)

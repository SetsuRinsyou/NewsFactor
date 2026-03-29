from __future__ import annotations

from typing import List

import pandas as pd

from data.base import BaseDataLoader
from utils.date_utils import DateLike
from utils.logger import get_logger

logger = get_logger(__name__)


class MarketLoader(BaseDataLoader):
    """Load OHLCV price data for CN (akshare) or US (yfinance) markets.

    Returns a prices DataFrame: index=date (DatetimeIndex), columns=ticker symbols.
    The prices are adjusted closing prices.
    """

    def __init__(self, market: str = "cn"):
        assert market in ("cn", "us"), "market must be 'cn' or 'us'"
        self.market = market

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch(
        self,
        tickers: List[str],
        start: DateLike,
        end: DateLike,
    ) -> pd.DataFrame:
        """Return a prices DataFrame [date × ticker] of adjusted close prices."""
        start_str = pd.Timestamp(start).strftime("%Y-%m-%d")
        end_str = pd.Timestamp(end).strftime("%Y-%m-%d")

        if self.market == "cn":
            return self._fetch_cn(tickers, start_str, end_str)
        return self._fetch_us(tickers, start_str, end_str)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _fetch_cn(self, tickers: List[str], start: str, end: str) -> pd.DataFrame:
        try:
            import akshare as ak
        except ImportError as e:
            raise ImportError("akshare is required for CN market data") from e

        frames = {}
        for ticker in tickers:
            logger.info(f"MarketLoader(cn): fetching {ticker}")
            try:
                df = ak.stock_zh_a_hist(
                    symbol=ticker,
                    period="daily",
                    start_date=start.replace("-", ""),
                    end_date=end.replace("-", ""),
                    adjust="qfq",  # 前复权
                )
                if df is None or df.empty:
                    logger.warning(f"MarketLoader: no data for {ticker}")
                    continue
                date_col = next(
                    (c for c in df.columns if "日期" in c or "date" in c.lower()), None
                )
                close_col = next(
                    (c for c in df.columns if "收盘" in c or "close" in c.lower()), None
                )
                if date_col is None or close_col is None:
                    logger.warning(f"MarketLoader: unexpected columns for {ticker}: {df.columns.tolist()}")
                    continue
                s = df.set_index(pd.to_datetime(df[date_col]))[close_col].rename(ticker)
                s.index = s.index.normalize()
                frames[ticker] = s
            except Exception as exc:
                logger.warning(f"MarketLoader: failed for {ticker}: {exc}")

        if not frames:
            return pd.DataFrame()
        return pd.DataFrame(frames).sort_index()

    def _fetch_us(self, tickers: List[str], start: str, end: str) -> pd.DataFrame:
        try:
            import yfinance as yf
        except ImportError as e:
            raise ImportError("yfinance is required for US market data") from e

        logger.info(f"MarketLoader(us): fetching {tickers}")
        raw = yf.download(
            tickers,
            start=start,
            end=end,
            auto_adjust=True,
            progress=False,
        )
        if raw.empty:
            return pd.DataFrame()

        if isinstance(raw.columns, pd.MultiIndex):
            prices = raw["Close"]
        else:
            prices = raw[["Close"]].rename(columns={"Close": tickers[0]})

        prices.index = pd.to_datetime(prices.index).normalize()
        return prices.sort_index()

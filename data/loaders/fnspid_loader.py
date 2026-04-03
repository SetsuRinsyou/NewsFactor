from __future__ import annotations

from pathlib import Path
from typing import Iterable, List, Optional

import pandas as pd

from data.base import BaseDataLoader
from utils.date_utils import DateLike
from utils.logger import get_logger

logger = get_logger(__name__)


def _find_column(columns: Iterable[str], candidates: List[str]) -> str | None:
    """Return the first column whose lowercase name contains any candidate."""
    for col in columns:
        col_str = str(col)
        col_lower = col_str.lower()
        if any(token in col_lower for token in candidates):
            return col_str
    return None


def _build_text(row: pd.Series, text_columns: List[str]) -> str:
    """Join available text fields into one article string."""
    parts: list[str] = []
    for col in text_columns:
        value = row.get(col)
        if pd.notna(value):
            text = str(value).strip()
            if text:
                parts.append(text)
    return " ".join(parts).strip()


def normalize_fnspid_chunk(
    chunk: pd.DataFrame,
    tickers: Optional[set[str]] = None,
    start_ts: Optional[pd.Timestamp] = None,
    end_ts: Optional[pd.Timestamp] = None,
    source_name: str = "fnspid",
) -> pd.DataFrame:
    """Convert a raw FNSPID chunk into the canonical text-loader schema."""
    if chunk is None or chunk.empty:
        return pd.DataFrame(columns=BaseDataLoader.TEXT_COLS)

    chunk = chunk.copy()
    chunk.columns = [str(col).strip() for col in chunk.columns]
    columns = list(chunk.columns)

    # FNSPID columns are typically named like:
    # Date, Stock_symbol, Article_title, Article, Lsa_summary, Luhn_summary.
    date_col = _find_column(columns, ["date", "time"])
    ticker_col = _find_column(columns, ["stock_symbol", "ticker", "symbol"])
    title_col = _find_column(columns, ["article_title", "headline", "title"])
    content_col = _find_column(columns, ["article", "content", "body", "news"])

    fallback_cols = [
        col
        for col in columns
        if col.lower() in {
            "lsa_summary",
            "luhn_summary",
            "textrank_summary",
            "lexrank_summary",
        }
    ]

    if date_col is None or ticker_col is None:
        logger.warning(
            "FNSPIDNewsLoader: missing required columns. Got: %s",
            columns,
        )
        return pd.DataFrame(columns=BaseDataLoader.TEXT_COLS)

    # Normalize raw columns into canonical intermediate fields.
    chunk["_date"] = pd.to_datetime(chunk[date_col], errors="coerce", utc=True)
    chunk["_date"] = chunk["_date"].dt.tz_convert(None).dt.normalize()
    chunk["_ticker"] = chunk[ticker_col].astype(str).str.strip()
    chunk = chunk[chunk["_date"].notna() & chunk["_ticker"].ne("")]

    if tickers:
        chunk = chunk[chunk["_ticker"].isin(tickers)]
    if start_ts is not None:
        chunk = chunk[chunk["_date"] >= start_ts]
    if end_ts is not None:
        chunk = chunk[chunk["_date"] <= end_ts]
    if chunk.empty:
        return pd.DataFrame(columns=BaseDataLoader.TEXT_COLS)

    # Prefer title + full article; fall back to summary fields when needed.
    text_columns = [col for col in [title_col, content_col] if col]
    if not text_columns:
        text_columns = fallback_cols
    elif fallback_cols:
        text_columns.extend(fallback_cols)

    chunk["text"] = chunk.apply(lambda row: _build_text(row, text_columns), axis=1)
    chunk = chunk[chunk["text"].ne("")]
    if chunk.empty:
        return pd.DataFrame(columns=BaseDataLoader.TEXT_COLS)

    result = pd.DataFrame(
        {
            "date": chunk["_date"],
            "ticker": chunk["_ticker"],
            "text": chunk["text"],
            "source": source_name,
        }
    )
    return BaseDataLoader._ensure_schema(result, BaseDataLoader.TEXT_COLS)


class FNSPIDNewsLoader(BaseDataLoader):
    """Load FNSPID news data in EMNewsLoader-compatible schema.

    Returns one row per article with columns: date, ticker, text, source.
    """

    def __init__(
        self,
        processed_path: str = ".cache/fnspid/processed/news_em_schema.csv.gz",
        raw_path: str = ".cache/fnspid/raw/nasdaq_exteral_data.csv",
        chunksize: int = 200_000,
    ):
        self._processed_path = Path(processed_path)
        self._raw_path = Path(raw_path)
        self._chunksize = chunksize

    def fetch(
        self,
        tickers: List[str],
        start: DateLike,
        end: DateLike,
    ) -> pd.DataFrame:
        start_ts = pd.Timestamp(start).normalize()
        end_ts = pd.Timestamp(end).normalize()
        ticker_set = {str(ticker).strip() for ticker in tickers}

        if self._processed_path.exists():
            logger.info(
                "FNSPIDNewsLoader: reading processed dataset from %s",
                self._processed_path,
            )
            df = pd.read_csv(
                self._processed_path,
                usecols=self.TEXT_COLS,
                parse_dates=["date"],
                compression="infer",
            )
            df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.normalize()
            df["ticker"] = df["ticker"].astype(str).str.strip()
            df = df[
                df["ticker"].isin(ticker_set)
                & (df["date"] >= start_ts)
                & (df["date"] <= end_ts)
            ]
            if df.empty:
                return pd.DataFrame(columns=self.TEXT_COLS)
            return self._ensure_schema(df.reset_index(drop=True), self.TEXT_COLS)

        if not self._raw_path.exists():
            raise FileNotFoundError(
                "FNSPID raw dataset not found. Expected one of:\n"
                f"  processed: {self._processed_path}\n"
                f"  raw: {self._raw_path}"
            )

        logger.info(
            "FNSPIDNewsLoader: processed dataset not found, scanning raw CSV from %s",
            self._raw_path,
        )
        frames: list[pd.DataFrame] = []
        # Stream the raw CSV chunk by chunk so the full dataset is never loaded at once.
        for chunk in pd.read_csv(
            self._raw_path,
            chunksize=self._chunksize,
            low_memory=False,
        ):
            normalized = normalize_fnspid_chunk(
                chunk,
                tickers=ticker_set,
                start_ts=start_ts,
                end_ts=end_ts,
            )
            if not normalized.empty:
                frames.append(normalized)

        if not frames:
            return pd.DataFrame(columns=self.TEXT_COLS)

        result = pd.concat(frames, ignore_index=True)
        result = result.drop_duplicates(subset=["date", "ticker", "text"])
        result = result.sort_values(["date", "ticker"]).reset_index(drop=True)
        return self._ensure_schema(result, self.TEXT_COLS)

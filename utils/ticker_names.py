from __future__ import annotations

"""Lightweight ticker → company name resolver.

Maintains a module-level cache that is populated in two ways:
1. Automatically when `utils.universe` fetches index constituents (preferred,
   covers all universe-mode runs with zero extra network calls).
2. On-demand via `resolve_names()` for tickers not already in cache:
   - CN 6-digit codes: one-shot bulk fetch via akshare stock_zh_a_spot_em(),
     result cached for the entire process lifetime.
   - US tickers: per-ticker yfinance fast_info lookup, falls back to ticker
     symbol itself if unavailable.

All lookups are best-effort; if a name cannot be determined the ticker symbol
is returned unchanged (GDELT will still run — it simply searches for the
bare code/symbol).
"""

from utils.logger import get_logger

logger = get_logger(__name__)

# Module-level cache: ticker code (str) → company short name (str)
_name_cache: dict[str, str] = {}
_cn_bulk_fetched: bool = False   # guard: fetch all A-share names at most once


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def update_cache(mapping: dict[str, str]) -> None:
    """Bulk-insert ticker→name pairs (called by universe.py after index fetch)."""
    _name_cache.update(mapping)


def resolve_names(tickers: list[str]) -> dict[str, str]:
    """Return a {ticker: name} dict for the given tickers.

    Hits cache first; for misses, resolves CN and US tickers separately.
    Always returns an entry for every ticker (fallback = ticker itself).
    """
    result: dict[str, str] = {}
    cn_missing: list[str] = []
    us_missing: list[str] = []

    for t in tickers:
        if t in _name_cache:
            result[t] = _name_cache[t]
        elif _is_cn(t):
            cn_missing.append(t)
        else:
            us_missing.append(t)

    if cn_missing:
        _resolve_cn_bulk(cn_missing)
        for t in cn_missing:
            result[t] = _name_cache.get(t, t)

    if us_missing:
        _resolve_us(us_missing)
        for t in us_missing:
            result[t] = _name_cache.get(t, t)

    return result


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _is_cn(ticker: str) -> bool:
    return ticker.isdigit() and len(ticker) == 6


def _resolve_cn_bulk(tickers: list[str]) -> None:
    """One-shot bulk fetch all A-share names via akshare, populate cache."""
    global _cn_bulk_fetched
    if _cn_bulk_fetched:
        # already fetched; any remaining misses just fall back to ticker
        return
    _cn_bulk_fetched = True
    try:
        import akshare as ak
        df = ak.stock_zh_a_spot_em()
        code_col = next((c for c in df.columns if "代码" in c), None)
        name_col = next((c for c in df.columns if "名称" in c), None)
        if code_col and name_col:
            mapping = dict(
                zip(
                    df[code_col].astype(str).str.zfill(6),
                    df[name_col].astype(str),
                )
            )
            _name_cache.update(mapping)
            logger.info(f"ticker_names: cached {len(mapping)} CN stock names")
        else:
            logger.warning("ticker_names: could not find code/name columns in spot data")
    except Exception as exc:
        logger.warning(f"ticker_names: CN bulk name fetch failed: {exc}. "
                       "Using ticker codes as GDELT keywords.")


def _resolve_us(tickers: list[str]) -> None:
    """Per-ticker yfinance name lookup for US symbols."""
    try:
        import yfinance as yf
    except ImportError:
        logger.warning("ticker_names: yfinance not available for US name lookup")
        return

    for ticker in tickers:
        try:
            info = yf.Ticker(ticker).fast_info
            name = getattr(info, "display_name", None) or ticker
            _name_cache[ticker] = str(name)
        except Exception as exc:
            logger.debug(f"ticker_names: yfinance lookup failed for {ticker}: {exc}")
            _name_cache[ticker] = ticker

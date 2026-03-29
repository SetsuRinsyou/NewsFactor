#!/usr/bin/env python3
"""Generate universe txt files for common stock indices.

Run once to populate the universes/ directory:
    python scripts/build_universes.py

Output format (one entry per line):
    code,company_name     e.g.  600519,贵州茅台  or  AAPL,Apple Inc.
    (name is used by GDELTLoader for auto keyword resolution)

Re-run periodically to update constituent lists.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

OUT_DIR = Path(__file__).parent.parent / "universes"
OUT_DIR.mkdir(exist_ok=True)


def write_file(name: str, entries: list[tuple[str, str]]) -> None:
    path = OUT_DIR / f"{name}.txt"
    lines: list[str] = []
    for code, cname in entries:
        lines.append(f"{code},{cname}" if cname else code)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"  ✓ {name}: {len(lines)} tickers → {path}")


# ---------------------------------------------------------------------------
# CN indices via akshare
# ---------------------------------------------------------------------------

CN_INDEX_MAP = {
    "sz50":    "000016",
    "hs300":   "000300",
    "zz500":   "000905",
    "zz1000":  "000852",
}


def build_cn() -> None:
    try:
        import akshare as ak
    except ImportError:
        print("akshare not installed, skipping CN indices")
        return

    for name, symbol in CN_INDEX_MAP.items():
        print(f"Fetching {name} ({symbol}) ...")
        try:
            df = ak.index_stock_cons_weight_csindex(symbol=symbol)
            code_col = next(c for c in df.columns if "成分" in c and "代码" in c)
            name_col = next((c for c in df.columns if "成分" in c and "名称" in c), None)

            seen: set[str] = set()
            entries: list[tuple[str, str]] = []
            for _, row in df.iterrows():
                code = str(row[code_col]).zfill(6)
                if code in seen:
                    continue
                seen.add(code)
                cname = str(row[name_col]).strip() if name_col else ""
                entries.append((code, cname))
            entries.sort()
            write_file(name, entries)
        except Exception as exc:
            print(f"  ✗ {name}: {exc}")
        time.sleep(1)


# ---------------------------------------------------------------------------
# US indices via Wikipedia
# ---------------------------------------------------------------------------

def _wiki_df(url: str, **read_html_kwargs) -> "pd.DataFrame":
    """Fetch a Wikipedia page with a browser-like User-Agent and parse HTML tables."""
    import io
    import requests
    import pandas as pd
    headers = {"User-Agent": "Mozilla/5.0 (compatible; research/index-builder)"}
    r = requests.get(url, headers=headers, timeout=40)
    r.raise_for_status()
    tables = pd.read_html(io.StringIO(r.text), **read_html_kwargs)
    return tables[0]


def _fetch_sp500() -> list[tuple[str, str]]:
    df = _wiki_df(
        "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
        attrs={"id": "constituents"},
    )
    sym_col = next(c for c in df.columns if "symbol" in c.lower() or "ticker" in c.lower())
    name_col = next((c for c in df.columns if "security" in c.lower() or "company" in c.lower()), None)
    entries = []
    for _, row in df.iterrows():
        sym = str(row[sym_col]).strip().replace(".", "-")
        name = str(row[name_col]).strip() if name_col else ""
        if sym and sym.lower() != "nan":
            entries.append((sym, name))
    return sorted(set(entries))


def _fetch_nasdaq100() -> list[tuple[str, str]]:
    df = _wiki_df(
        "https://en.wikipedia.org/wiki/Nasdaq-100",
        attrs={"id": "constituents"},
    )
    sym_col = next(c for c in df.columns if "ticker" in c.lower() or "symbol" in c.lower())
    name_col = next((c for c in df.columns if "company" in c.lower() or "name" in c.lower()), None)
    entries = []
    for _, row in df.iterrows():
        sym = str(row[sym_col]).strip()
        name = str(row[name_col]).strip() if name_col else ""
        if sym and sym.lower() != "nan":
            entries.append((sym, name))
    return sorted(set(entries))


def _fetch_dow30() -> list[tuple[str, str]]:
    df = _wiki_df(
        "https://en.wikipedia.org/wiki/Dow_Jones_Industrial_Average",
        match="Symbol",
    )
    sym_col = next(c for c in df.columns if "symbol" in c.lower())
    name_col = next((c for c in df.columns if "company" in c.lower() or "name" in c.lower()), None)
    entries = []
    for _, row in df.iterrows():
        sym = str(row[sym_col]).strip()
        name = str(row[name_col]).strip() if name_col else ""
        if sym and sym.lower() != "nan":
            entries.append((sym, name))
    return sorted(set(entries))


def build_us() -> None:
    for name, fn in [
        ("sp500",     _fetch_sp500),
        ("nasdaq100", _fetch_nasdaq100),
        ("dow30",     _fetch_dow30),
    ]:
        print(f"Fetching {name} ...")
        try:
            entries = fn()
            write_file(name, entries)
        except Exception as exc:
            print(f"  ✗ {name}: {exc}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    targets = sys.argv[1:] or ["cn", "us"]

    if "cn" in targets or "all" in targets:
        print("\n=== CN indices ===")
        build_cn()

    if "us" in targets or "all" in targets:
        print("\n=== US indices ===")
        build_us()

    print("\nDone. Universe files written to:", OUT_DIR)

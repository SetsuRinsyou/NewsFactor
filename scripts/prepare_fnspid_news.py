#!/usr/bin/env python3
"""Normalize the raw FNSPID CSV into the canonical news loader schema.

Usage:
   python scripts/prepare_fnspid_news.py

Optional CLI arguments:
    --input     Path to the raw FNSPID CSV file.
    --output    Path to the normalized gzip-compressed CSV.
    --chunksize Rows to read per chunk while streaming the raw CSV.
    --tickers   Optional ticker subset filter.
    --start     Optional start date filter.
    --end       Optional end date filter.

Input:
    A raw FNSPID CSV file, typically stored under:
        .cache/fnspid/raw/nasdaq_exteral_data.csv

Output:
    A gzip-compressed CSV stored by default at:
        .cache/fnspid/processed/news_em_schema.csv.gz

Output schema:
    date, ticker, text, source

The output format is compatible with EMNewsLoader-style text data and is
intended to be consumed by FNSPIDNewsLoader or the wider data pipeline.
"""

from __future__ import annotations

import argparse
import gzip
import sys
from pathlib import Path

import pandas as pd

# Allow running the script directly from the project root, e.g.
# `python scripts/prepare_fnspid_news.py ...`.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from data.loaders.fnspid_loader import normalize_fnspid_chunk


def _resolve_input_path(input_arg: str | None) -> Path:
    """Resolve the raw CSV path from CLI input or the default raw directory."""
    if input_arg:
        # If --input is provided, use it directly.
        return Path(input_arg)

    raw_dir = PROJECT_ROOT / ".cache" / "fnspid" / "raw"
    preferred = raw_dir / "nasdaq_exteral_data.csv"
    if preferred.exists():
        # Prefer the expected default filename when it exists.
        return preferred

    candidates = sorted(raw_dir.glob("*.csv"))
    if len(candidates) == 1:
        # If there is only one CSV in the raw directory, use it automatically.
        return candidates[0]
    if not candidates:
        raise FileNotFoundError(f"No CSV file found in {raw_dir}")
    # When multiple raw CSVs exist, force the caller to disambiguate via --input.
    raise FileNotFoundError(
        f"Multiple CSV files found in {raw_dir}. Please pass --input explicitly."
    )


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for the one-time FNSPID normalization job."""
    parser = argparse.ArgumentParser(
        description="Convert raw FNSPID CSV into the canonical news loader schema."
    )
    parser.add_argument(
        "--input",
        default=None,
        help="Path to the raw FNSPID CSV file. Defaults to auto-detect in .cache/fnspid/raw.",
    )
    parser.add_argument(
        "--output",
        default=".cache/fnspid/processed/news_em_schema.csv.gz",
        help="Path to the normalized output file.",
    )
    parser.add_argument(
        "--chunksize",
        type=int,
        default=20_000,
        help="Rows per chunk while streaming the input CSV.",
    )
    parser.add_argument(
        "--tickers",
        nargs="*",
        default=None,
        help="Optional subset of ticker symbols to keep.",
    )
    parser.add_argument(
        "--start",
        default=None,
        help="Optional start date filter, e.g. 2020-01-01.",
    )
    parser.add_argument(
        "--end",
        default=None,
        help="Optional end date filter, e.g. 2020-12-31.",
    )
    return parser.parse_args()


def main() -> None:
    """Stream the raw CSV and write a normalized gzip-compressed CSV."""
    args = parse_args()
    input_path = _resolve_input_path(args.input)
    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = PROJECT_ROOT / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)

    ticker_set = {ticker.strip() for ticker in args.tickers} if args.tickers else None
    start_ts = pd.Timestamp(args.start).normalize() if args.start else None
    end_ts = pd.Timestamp(args.end).normalize() if args.end else None

    if not input_path.exists():
        raise FileNotFoundError(f"Input CSV not found: {input_path}")

    print(f"input={input_path}")
    print(f"output={output_path}")
    print(f"chunksize={args.chunksize}")

    rows_written = 0
    chunks_seen = 0

    with gzip.open(output_path, "wt", encoding="utf-8", newline="") as handle:
        header_written = False
        # Processing strategy:
        # 1. Read the raw CSV in chunks so the full dataset is never loaded at once.
        # 2. Normalize each chunk into the canonical columns: date, ticker, text, source.
        # 3. Deduplicate within the current chunk before writing.
        # 4. Append each normalized chunk directly to a gzip-compressed CSV on disk.
        #
        # This keeps memory usage manageable for very large source files while still
        # producing one final EMNewsLoader-compatible dataset.
        for chunk in pd.read_csv(input_path, chunksize=args.chunksize, low_memory=False):
            chunks_seen += 1
            normalized = normalize_fnspid_chunk(
                chunk,
                tickers=ticker_set,
                start_ts=start_ts,
                end_ts=end_ts,
            )
            if normalized.empty:
                continue

            normalized = normalized.drop_duplicates(subset=["date", "ticker", "text"])
            normalized.to_csv(handle, index=False, header=not header_written)
            header_written = True
            rows_written += len(normalized)

            print(
                f"chunk={chunks_seen} kept_rows={len(normalized)} total_rows={rows_written}"
            )

    print(f"done: wrote {rows_written} rows to {output_path}")


if __name__ == "__main__":
    main()

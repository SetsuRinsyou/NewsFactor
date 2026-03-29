#!/usr/bin/env python3
"""NewsFactor — News/Social-media driven quantitative factor analysis CLI.

Usage examples:
    # A-share, VADER sentiment, sentiment_ma factor
    python main.py --factor sentiment_ma --tickers 600519 000858 \
        --start 2024-01-01 --end 2024-06-01 --market cn

    # US stocks, sentiment_ewm factor
    python main.py --factor sentiment_ewm --tickers AAPL MSFT \
        --start 2024-01-01 --end 2024-06-01 --market us \
        --nlp-backend finbert-en

    # List all registered factors
    python main.py --list-factors
"""
from __future__ import annotations

import argparse
import os
import sys

# Make sure project root is on the path when run directly
sys.path.insert(0, os.path.dirname(__file__))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="NewsFactor",
        description="News/social-media quantitative factor extraction and backtesting.",
    )
    parser.add_argument(
        "--factor", "-f",
        type=str,
        default="sentiment_ma",
        help="Factor name to compute (see --list-factors).",
    )
    parser.add_argument(
        "--tickers", "-t",
        nargs="+",
        default=[],
        help=(
            "Ticker symbols (A-share 6-digit codes or US tickers), "
            "or a single path to a .txt file (one ticker per line, 'code,name' format supported)."
        ),
    )
    parser.add_argument(
        "--start", "-s",
        type=str,
        default="2024-01-01",
        help="Start date (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--end", "-e",
        type=str,
        default="2024-06-01",
        help="End date (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--market", "-m",
        type=str,
        choices=["cn", "us"],
        default="cn",
        help="Target market: cn (A-share) or us (NYSE/NASDAQ).",
    )
    parser.add_argument(
        "--config", "-c",
        type=str,
        default="config/config.yaml",
        help="Path to config.yaml.",
    )
    parser.add_argument(
        "--nlp-backend",
        type=str,
        choices=["vader", "finbert-en", "finbert-zh"],
        default=None,
        help="Override NLP backend from config.",
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default="reports",
        help="Directory for output reports and plots.",
    )
    parser.add_argument(
        "--list-factors",
        action="store_true",
        help="Print all registered factor names and exit.",
    )
    parser.add_argument(
        "--factor-kwargs",
        nargs="*",
        metavar="KEY=VALUE",
        default=[],
        help="Extra kwargs passed to the factor, e.g. window=10 halflife=3",
    )
    return parser.parse_args()


def _parse_kwargs(raw: list[str]) -> dict:
    kwargs = {}
    for item in raw:
        if "=" not in item:
            continue
        k, v = item.split("=", 1)
        try:
            kwargs[k] = int(v)
        except ValueError:
            try:
                kwargs[k] = float(v)
            except ValueError:
                kwargs[k] = v
    return kwargs


def main() -> None:
    args = _parse_args()

    # Import factors package so all @FactorRegistry.register decorators run
    import factors  # noqa: F401
    from factors import FactorRegistry

    if args.list_factors:
        print("Registered factors:")
        for name in FactorRegistry.list_factors():
            print(f"  {name}")
        return

    # Resolve tickers: single .txt path → read file; otherwise use values directly
    tickers = args.tickers
    if len(tickers) == 1 and tickers[0].endswith(".txt"):
        from pathlib import Path
        txt_path = Path(tickers[0])
        if not txt_path.exists():
            print(f"ERROR: ticker file not found: {txt_path}", file=sys.stderr)
            sys.exit(1)
        parsed: list[str] = []
        name_map: dict[str, str] = {}
        for raw in txt_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            code, _, rest = line.partition(",")
            code = code.strip()
            if code:
                parsed.append(code)
                name = rest.strip()
                if name:
                    name_map[code] = name
        if name_map:
            from utils.ticker_names import update_cache
            update_cache(name_map)
        tickers = parsed

    if not tickers:
        print("ERROR: provide --tickers (symbols or a .txt file path)", file=sys.stderr)
        sys.exit(1)
    args.tickers = tickers

    import yaml
    from utils.logger import get_logger

    log = get_logger("main")

    # ------------------------------------------------------------------
    # Load config
    # ------------------------------------------------------------------
    with open(args.config, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    nlp_cfg = cfg.get("nlp", {})
    backtest_cfg = cfg.get("backtest", {})
    backend = args.nlp_backend or nlp_cfg.get("backend", "vader")

    # ------------------------------------------------------------------
    # Step 1: Data
    # ------------------------------------------------------------------
    log.info(f"Step 1 — Fetching data for {args.tickers} [{args.start} → {args.end}]")
    from data.pipeline import DataPipeline

    pipeline = DataPipeline.from_config(args.config, market=args.market)

    # Always enable EM news for CN, skip if US (no CN news source for US tickers logic)
    if args.market == "cn":
        from data.loaders.em_news import EMNewsLoader
        if not any(isinstance(l, EMNewsLoader) for l in pipeline._text_loaders):
            pipeline.add_loader(EMNewsLoader())

    text_df, prices = pipeline.run(args.tickers, args.start, args.end)

    if prices.empty:
        log.error("No price data retrieved. Check tickers and date range.")
        sys.exit(1)

    log.info(f"Prices shape: {prices.shape} | Text rows: {len(text_df)}")

    # ------------------------------------------------------------------
    # Step 2: NLP
    # ------------------------------------------------------------------
    log.info(f"Step 2 — Running NLP (backend={backend})")
    from nlp.sentiment import SentimentAnalyzer
    from nlp.event_detector import EventDetector

    lang = "zh" if args.market == "cn" else "en"
    analyzer = SentimentAnalyzer(
        backend=backend,
        batch_size=nlp_cfg.get("batch_size", 32),
        device=nlp_cfg.get("device", "cpu"),
        finbert_en_model=nlp_cfg.get("finbert_en_model"),
        finbert_zh_model=nlp_cfg.get("finbert_zh_model"),
    )
    detector = EventDetector.from_config(args.config)

    if text_df.empty:
        log.warning("No text data available. Generating synthetic neutral scores.")
        import pandas as pd
        import numpy as np
        # Build a minimal nlp_df with zero sentiment so factor computation doesn't crash
        rows = []
        for date in prices.index:
            for ticker in prices.columns:
                rows.append({
                    "date": date, "ticker": ticker,
                    "text": "", "source": "synthetic",
                    "positive": 0.0, "negative": 0.0, "neutral": 1.0, "compound": 0.0,
                    "event_type": None, "event_intensity": 0.0,
                })
        nlp_df = pd.DataFrame(rows)
    else:
        nlp_df = analyzer.analyze_df(text_df, text_col="text", lang=lang)
        nlp_df = detector.tag_df(nlp_df, text_col="text")

    log.info(f"NLP complete. nlp_df shape: {nlp_df.shape}")

    # ------------------------------------------------------------------
    # Step 3: Factor computation
    # ------------------------------------------------------------------
    log.info(f"Step 3 — Computing factor '{args.factor}'")
    factor_kwargs = _parse_kwargs(args.factor_kwargs)
    factor_calc = FactorRegistry.build(args.factor, **factor_kwargs)
    result = factor_calc.compute(nlp_df, prices, **factor_kwargs)
    log.info(f"Factor '{result.name}': {len(result.values)} values, meta={result.meta}")

    if result.values.empty:
        log.error("Factor returned no values. Cannot run backtest.")
        sys.exit(1)

    # ------------------------------------------------------------------
    # Step 4: Signal generation (alphalens format)
    # ------------------------------------------------------------------
    log.info("Step 4 — Building alphalens factor_data")
    from backtest.signal_generator import FactorSignalGenerator

    gen = FactorSignalGenerator(
        periods=tuple(backtest_cfg.get("periods", [1, 5, 20])),
        quantiles=backtest_cfg.get("quantiles", 5),
        filter_zscore=backtest_cfg.get("filter_zscore", 20),
        max_loss=backtest_cfg.get("max_loss", 0.35),
    )
    try:
        factor_data = gen.build(result, prices)
    except Exception as exc:
        log.error(f"Failed to build factor_data: {exc}")
        sys.exit(1)

    log.info(f"factor_data shape: {factor_data.shape}")

    # ------------------------------------------------------------------
    # Step 5: Analysis / report
    # ------------------------------------------------------------------
    log.info(f"Step 5 — Generating report in '{args.output}/'")
    from backtest.analyzer import FactorAnalyzer

    analyzer_bt = FactorAnalyzer(output_dir=args.output, long_short=True)
    analyzer_bt.create_full_report(factor_data, factor_name=result.name)

    log.info("Done. Check the reports/ directory for output files.")


if __name__ == "__main__":
    main()

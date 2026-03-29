# Plan: News/Social Media Driven Quantitative Factor Framework

## Goals
- 数据处理（新闻+社媒+行情）→ NLP处理 → 因子计算 → alphalens因子有效性验证
- 支持A股（akshare）和美股（yfinance）
- 新闻源：东方财富/同花顺爬虫、NewsAPI/RSS、Weibo/Twitter、StockTwits
- 因子计算模块化，通过 FactorRegistry 装饰器扩展
- NLP：FinBERT-EN（yiyanghkust/finbert-tone）、FinBERT-ZH（hw2942/bert-base-chinese...）、VADER fallback
- 回测：alphalens-reloaded IC/ICIR + 分层回测

## File Structure
```
NewsFactor/
├── config/
│   └── config.yaml
├── data/
│   ├── __init__.py
│   ├── base.py              # BaseDataLoader ABC
│   ├── loaders/
│   │   ├── __init__.py
│   │   ├── em_news.py       # 东方财富/同花顺 akshare.stock_news_em()
│   │   ├── newsapi_loader.py # NewsAPI + feedparser RSS
│   │   ├── social_loader.py  # tweepy Twitter, StockTwits API, Weibo
│   │   └── market_loader.py  # akshare + yfinance
│   └── pipeline.py          # DataPipeline：merge, align, cache
├── nlp/
│   ├── __init__.py
│   ├── preprocessor.py      # clean_text(text, lang), extract_ticker_mentions()
│   ├── sentiment.py         # SentimentAnalyzer class, batched inference
│   └── event_detector.py    # keyword-based EventDetector
├── factors/
│   ├── __init__.py
│   ├── base.py              # BaseFactorCalculator ABC + FactorRegistry
│   ├── sentiment_factor.py  # SentimentMAFactor, SentimentEWMFactor
│   ├── event_factor.py      # EventIntensityFactor, EventTypeFactor
│   └── social_factor.py     # SocialBuzzFactor, SentimentDivergenceFactor
├── backtest/
│   ├── __init__.py
│   ├── signal_generator.py  # factor → alphalens MultiIndex alignment
│   └── analyzer.py          # alphalens wrapper: IC, quantile, tear sheet
├── utils/
│   ├── __init__.py
│   ├── cache.py             # @disk_cache decorator (diskcache/pickle)
│   ├── logger.py            # logging config
│   └── date_utils.py        # trading date helpers
├── main.py                  # CLI entry point
└── requirements.txt
```

## Step-by-step plan

### Phase 1: Foundation (no dependencies)
1. `requirements.txt` - pin all deps
2. `config/config.yaml` - credentials via env vars, factor/backtest params
3. `utils/logger.py` - logging setup
4. `utils/cache.py` - @disk_cache(key_fn) decorator using diskcache
5. `utils/date_utils.py` - get_trading_dates(market, start, end) via akshare/pandas_market_calendars

### Phase 2: Data Layer (depends on Phase 1)
6. `data/base.py` - BaseDataLoader ABC with fetch(tickers, start, end) -> pd.DataFrame
7. `data/loaders/market_loader.py` - MarketLoader: akshare for CN, yfinance for US; returns prices DataFrame [date × ticker]
8. `data/loaders/em_news.py` - EMNewsLoader: akshare.stock_news_em(symbol) per ticker
9. `data/loaders/newsapi_loader.py` - NewsAPILoader + RSSLoader using feedparser
10. `data/loaders/social_loader.py` - TwitterLoader (tweepy), StockTwitsLoader, WeiboLoader stub
11. `data/pipeline.py` - DataPipeline: compose loaders, unify schema to (date, ticker, text, source), cache, align to trading days

### Phase 3: NLP Layer (depends on Phase 2)
12. `nlp/preprocessor.py` - clean_text(text, lang), strip HTML, extract_ticker_mentions()
13. `nlp/sentiment.py` - SentimentAnalyzer(backend, batch_size, device); backends: finbert-en, finbert-zh, vader; analyze(texts) -> DataFrame[positive, negative, neutral, compound]
14. `nlp/event_detector.py` - EventDetector(keyword_dict); tag(text) -> {event_type, intensity}

### Phase 4: Factor Layer (depends on Phase 3)
15. `factors/base.py` - FactorResult dataclass, BaseFactorCalculator ABC (compute(nlp_df, market_df) -> FactorResult), FactorRegistry with @register decorator + list_factors() + build()
16. `factors/sentiment_factor.py` - SentimentMAFactor(window), SentimentEWMFactor(halflife) registered as "sentiment_ma", "sentiment_ewm"
17. `factors/event_factor.py` - EventIntensityFactor, EventTypeFactor(event_type) registered as "event_intensity", "event_type_dummy"
18. `factors/social_factor.py` - SocialBuzzFactor(window), SentimentDivergenceFactor registered as "social_buzz", "sentiment_divergence"

### Phase 5: Backtest Layer (depends on Phase 4)
19. `backtest/signal_generator.py` - FactorSignalGenerator: takes FactorResult + prices DataFrame, builds alphalens-compatible MultiIndex Series + prices, calls get_clean_factor_and_forward_returns()
20. `backtest/analyzer.py` - FactorAnalyzer: run_ic_analysis(), run_quantile_returns(), create_full_report() → save plots to reports/

### Phase 6: CLI (depends on all)
21. `main.py` - argparse CLI: --factor, --tickers, --start, --end, --market (cn/us), --output

## Key Design Patterns

### FactorRegistry (factors/base.py)
```python
@FactorRegistry.register("sentiment_ma")
class SentimentMAFactor(BaseFactorCalculator):
    def compute(self, nlp_df, market_df, **kwargs) -> FactorResult:
        ...
```

### alphalens input contract (backtest/signal_generator.py)
- factor: pd.Series with MultiIndex (date, ticker) → float
- prices: pd.DataFrame indexed by date, columns = tickers

### NLP output schema (nlp/sentiment.py)
- DataFrame columns: [date, ticker, text, source, positive, negative, neutral, compound]
- compound = positive - negative (range [-1, 1])

## Verification
1. `python main.py --factor sentiment_ma --tickers 600519 --start 2024-01-01 --end 2024-06-01 --market cn` runs without error
2. alphalens IC plot generated in reports/
3. Add a second factor via @FactorRegistry.register without modifying existing code
4. Run `python -c "from factors import FactorRegistry; print(FactorRegistry.list_factors())"` → lists all registered factors
5. VADER fallback works without GPU/model downloads

## Decisions
- Scope: factor validity (IC/ICIR + quantile returns), NOT full portfolio simulation
- Weibo loader: stub implementation (official API requires corp approval)
- FinNLP: used via transformers directly (finbert-tone for EN, hw2942 model for ZH)
- alphalens-reloaded (maintained fork of Quantopian alphalens)
- Credentials via environment variables, referenced in config.yaml as ${VAR_NAME}
- Disk cache in .cache/ dir for NLP results (expensive to recompute)

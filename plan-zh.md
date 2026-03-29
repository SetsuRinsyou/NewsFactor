# 计划：新闻/社媒驱动量化因子框架

## 目标
- 数据处理（新闻+社交媒体+行情）→ NLP处理 → 因子计算 → alphalens 因子有效性验证
- 支持 A 股（akshare）和美股（yfinance）
- 新闻来源：东方财富/同花顺爬虫、NewsAPI/RSS、微博/Twitter、StockTwits
- 因子计算模块化，通过 FactorRegistry 装饰器扩展
- NLP：FinBERT-EN（yiyanghkust/finbert-tone）、FinBERT-ZH（hw2942/bert-base-chinese...）、VADER 兜底
- 回测：alphalens-reloaded IC/ICIR + 分层回测

## 目录结构
```
NewsFactor/
├── config/
│   └── config.yaml
├── data/
│   ├── __init__.py
│   ├── base.py              # BaseDataLoader 抽象基类
│   ├── loaders/
│   │   ├── __init__.py
│   │   ├── em_news.py        # 东方财富/同花顺 akshare.stock_news_em()
│   │   ├── newsapi_loader.py # NewsAPI + feedparser RSS
│   │   ├── social_loader.py  # tweepy Twitter、StockTwits API、微博
│   │   └── market_loader.py  # akshare + yfinance
│   └── pipeline.py           # DataPipeline：合并、对齐、缓存
├── nlp/
│   ├── __init__.py
│   ├── preprocessor.py       # clean_text(text, lang)、extract_ticker_mentions()
│   ├── sentiment.py          # SentimentAnalyzer 类，批量推理
│   └── event_detector.py     # 基于关键词的 EventDetector
├── factors/
│   ├── __init__.py
│   ├── base.py               # BaseFactorCalculator 抽象基类 + FactorRegistry
│   ├── sentiment_factor.py   # SentimentMAFactor、SentimentEWMFactor
│   ├── event_factor.py       # EventIntensityFactor、EventTypeFactor
│   └── social_factor.py      # SocialBuzzFactor、SentimentDivergenceFactor
├── backtest/
│   ├── __init__.py
│   ├── signal_generator.py   # 因子 → alphalens MultiIndex 对齐
│   └── analyzer.py           # alphalens 封装：IC、分层回报、tear sheet
├── utils/
│   ├── __init__.py
│   ├── cache.py              # @disk_cache 装饰器（diskcache）
│   ├── logger.py             # 日志配置
│   └── date_utils.py         # 交易日历工具
├── main.py                   # CLI 入口
└── requirements.txt
```

## 分阶段实施计划

### 第一阶段：基础设施（无依赖）
1. `requirements.txt` — 锁定所有依赖版本
2. `config/config.yaml` — 凭证通过环境变量注入，因子/回测参数配置
3. `utils/logger.py` — 日志初始化
4. `utils/cache.py` — 基于 diskcache 的 `@disk_cache(key_fn)` 装饰器
5. `utils/date_utils.py` — `get_trading_dates(market, start, end)`，通过 akshare/pandas_market_calendars 获取交易日历

### 第二阶段：数据层（依赖第一阶段）
6. `data/base.py` — `BaseDataLoader` 抽象基类，接口：`fetch(tickers, start, end) -> pd.DataFrame`
7. `data/loaders/market_loader.py` — `MarketLoader`：A 股用 akshare `stock_zh_a_hist`，美股用 yfinance；输出 prices DataFrame `[日期 × ticker]`
8. `data/loaders/em_news.py` — `EMNewsLoader`：逐 ticker 调用 `akshare.stock_news_em(symbol)` 采集新闻
9. `data/loaders/newsapi_loader.py` — `NewsAPILoader` + 基于 feedparser 的 `RSSLoader`
10. `data/loaders/social_loader.py` — `TwitterLoader`（tweepy v2 按 `$TICKER` cashtag）、`StockTwitsLoader`（REST API）、`WeiboLoader`（stub）
11. `data/pipeline.py` — `DataPipeline`：编排所有 loader，统一 schema 为 `(date, ticker, text, source)`，对齐至交易日，磁盘缓存

### 第三阶段：NLP 层（依赖第二阶段）
12. `nlp/preprocessor.py` — HTML 去除、特殊字符清洗、股票代码识别
13. `nlp/sentiment.py` — `SentimentAnalyzer(backend, batch_size, device)`，三种 backend：
    - `finbert-en`：`yiyanghkust/finbert-tone`（英文）
    - `finbert-zh`：`hw2942/bert-base-chinese-finetuning-financial-news-sentiment-v2`（中文）
    - `vader`：`vaderSentiment`（快速兜底，无需 GPU）
    - 输出列：`[positive, negative, neutral, compound]`
14. `nlp/event_detector.py` — 可配置关键词字典，标注事件类型（财报/并购/诉讼等）及强度

### 第四阶段：因子层（依赖第三阶段，各因子可并行开发）
15. `factors/base.py` — 核心扩展接口：
    - `FactorResult` 数据类
    - `BaseFactorCalculator` 抽象基类，接口：`compute(nlp_df, market_df) -> FactorResult`
    - `FactorRegistry`：`@register` 装饰器 + `list_factors()` + `build()`
16. `factors/sentiment_factor.py` — `SentimentMAFactor(window)` 注册为 `"sentiment_ma"`，`SentimentEWMFactor(halflife)` 注册为 `"sentiment_ewm"`
17. `factors/event_factor.py` — `EventIntensityFactor` 注册为 `"event_intensity"`，`EventTypeFactor(event_type)` 注册为 `"event_type_dummy"`
18. `factors/social_factor.py` — `SocialBuzzFactor(window)` 注册为 `"social_buzz"`，`SentimentDivergenceFactor` 注册为 `"sentiment_divergence"`

### 第五阶段：回测层（依赖第四阶段）
19. `backtest/signal_generator.py` — `FactorSignalGenerator`：将 `FactorResult` 转为 alphalens 所需的 `MultiIndex(date, ticker)` Series，对齐 prices，调用 `get_clean_factor_and_forward_returns(periods=(1, 5, 20))`
20. `backtest/analyzer.py` — `FactorAnalyzer`：`run_ic_analysis()` / `run_quantile_returns()` / `create_full_report()`，图表输出到 `reports/`

### 第六阶段：CLI（依赖全部）
21. `main.py` — argparse CLI 入口：`--factor`、`--tickers`、`--start`、`--end`、`--market (cn/us)`、`--output`

## 关键设计模式

### FactorRegistry 注册装饰器（factors/base.py）
```python
@FactorRegistry.register("sentiment_ma")
class SentimentMAFactor(BaseFactorCalculator):
    def compute(self, nlp_df, market_df, **kwargs) -> FactorResult:
        ...
```
新增因子只需新建类并加装饰器，无需修改任何已有代码。

### alphalens 输入契约（backtest/signal_generator.py）
- `factor`：`pd.Series`，MultiIndex 为 `(date, ticker)` → float
- `prices`：`pd.DataFrame`，index 为日期，columns 为 ticker

### NLP 输出 Schema（nlp/sentiment.py）
- DataFrame 列：`[date, ticker, text, source, positive, negative, neutral, compound]`
- `compound = positive - negative`，取值范围 `[-1, 1]`

## 验收标准
1. `python main.py --factor sentiment_ma --tickers 600519 --start 2024-01-01 --end 2024-06-01 --market cn` 端到端无报错运行
2. `reports/` 目录下生成 alphalens IC 时序图和分层回报图
3. 在 `factors/` 新增因子类并加 `@FactorRegistry.register("test_factor")`，无需修改任何已有文件
4. `python -c "from factors import FactorRegistry; print(FactorRegistry.list_factors())"` 返回所有已注册因子列表
5. 不安装 PyTorch/下载模型时，自动 fallback 到 VADER 正常运行

## 设计决策
- **回测范围**：仅做因子有效性验证（IC/ICIR + 分层回报），不含完整持仓模拟
- **微博 loader**：提供 stub 实现，官方 API 需企业资质
- **FinNLP**：直接通过 transformers 调用（英文用 finbert-tone，中文用 hw2942 模型）
- **alphalens**：使用 `alphalens-reloaded`（Quantopian 原版的社区维护 fork）
- **凭证管理**：全部使用环境变量，`config.yaml` 仅引用 `${VAR_NAME}`，不存储明文
- **缓存策略**：NLP 推理结果（最耗时）缓存到 `.cache/`，行情和新闻数据按日期 key 缓存

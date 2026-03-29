# 框架实现清单

记录当前已实现的新闻数据源、因子及其状态，供后期改进参考。

---

## 新闻/社媒数据源

### 已实现并默认启用

| 数据源 | Loader 类 | 文件 | 市场 | 文本内容 | 历史深度 |
|--------|-----------|------|------|----------|----------|
| 东方财富个股新闻 | `EMNewsLoader` | `data/loaders/em_news.py` | A 股 | 标题 + 正文 | 有限（akshare 返回最近 N 条） |

### 已实现但默认关闭

| 数据源 | Loader 类 | 文件 | 市场 | 文本内容 | 历史深度 | 启用条件 |
|--------|-----------|------|------|----------|----------|----------|
| NewsAPI | `NewsAPILoader` | `data/loaders/newsapi_loader.py` | 美股/全球 | 标题 + 摘要 | 免费近30天 | `NEWSAPI_KEY` 环境变量 |
| RSS 订阅 | `RSSLoader` | `data/loaders/newsapi_loader.py` | 通用 | 标题 + 摘要 | 取决于源 | `config.yaml` 填写 feeds URL |
| Twitter/X | `TwitterLoader` | `data/loaders/social_loader.py` | 美股 | 推文全文 | 免费近7天 | `TWITTER_BEARER_TOKEN` 环境变量 |
| StockTwits | `StockTwitsLoader` | `data/loaders/social_loader.py` | 美股 | 消息全文 | 仅近期 | 无需鉴权，直接开启 |
| GDELT | `GDELTLoader` | `data/loaders/gdelt_loader.py` | 全球 | 仅标题 | 2015年至今 | `enabled: true`；公司名称自动从 `--tickers` 传入的 `.txt` 文件中读取，或 akshare/yfinance 兜底解析，无需配置 |

### Stub（已占位，待实现）

| 数据源 | Loader 类 | 文件 | 阻塞原因 | 改进方向 |
|--------|-----------|------|----------|----------|
| 微博 | `WeiboLoader` | `data/loaders/social_loader.py` | 官方 API 需企业资质 | 可用第三方 RSS 或爬虫替代 |

### 待接入（未实现）

| 数据源 | 类型 | 市场 | 优先级 | 备注 |
|--------|------|------|--------|------|
| akshare 个股公告 | 公告 | A 股 | 高 | `stock_notice_report()`，事件信号更准确 |
| akshare 研究报告 | 研报 | A 股 | 中 | `stock_research_report_em()`，含评级/目标价 |
| akshare 千股千评 | 结构化情绪 | A 股 | 中 | `stock_comment_em()`，已结构化，无需 NLP |
| akshare 百度搜索热度 | 搜索热度 | A 股 | 中 | `stock_hot_search_baidu()`，增强 social_buzz 因子 |
| SEC EDGAR | 公告/财报 | 美股 | 中 | 完全免费，历史完整，官方 RSS 可用 |
| GDELT 正文爬取 | 全文 | 全球 | 低 | 对 GDELT 返回的 url 二次爬取，现只有标题 |

---

## 股票池（Universe）

股票列表通过 `--tickers` 传入（直接输入代码，或指定 `.txt` 文件路径）。`.txt` 文件支持 `code,name` 格式，加载时自动填充 `utils/ticker_names.py` 中的名称缓存供 GDELT 关键词解析使用。`universes/` 目录中预置了常用指数成分股列表（由 `scripts/build_universes.py` 生成），可直接作为 `.txt` 文件传入。

| 文件名 | 指数 | 市场 | 数据来源 | 含名称缓存 |
|--------|------|------|----------|------------|
| `universes/sz50.txt` | 上证50 | cn | akshare csindex | ✅ |
| `universes/hs300.txt` | 沪深300 | cn | akshare csindex | ✅ |
| `universes/zz500.txt` | 中证500 | cn | akshare csindex | ✅ |
| `universes/zz1000.txt` | 中证1000 | cn | akshare csindex | ✅ |
| `universes/sp500.txt` | S&P 500 | us | Wikipedia HTML | ✅ |
| `universes/nasdaq100.txt` | NASDAQ 100 | us | Wikipedia HTML | ✅ |
| `universes/dow30.txt` | 道琼斯30 | us | Wikipedia HTML | ✅ |

---

## 因子

> 每个因子的详细计算公式与参数说明见 [docs/FACTORS.md](docs/FACTORS.md)。

### 已注册因子

| 因子名称 | 类 | 文件 | 默认参数 | 输入依赖 | 说明 |
|----------|-----|------|----------|----------|------|
| `sentiment_ma` | `SentimentMAFactor` | `factors/sentiment_factor.py` | `window=5` | `compound` 列 | 每日均值情绪的滚动均值 |
| `sentiment_ewm` | `SentimentEWMFactor` | `factors/sentiment_factor.py` | `halflife=3` | `compound` 列 | 每日均值情绪的指数加权均值 |
| `event_intensity` | `EventIntensityFactor` | `factors/event_factor.py` | `decay_days=3` | `event_intensity` 列 | 关键词命中次数的 EWM 衰减累积 |
| `event_type_dummy` | `EventTypeFactor` | `factors/event_factor.py` | `event_type=earnings`, `decay_days=3` | `event_type` 列 | 指定事件类型二值信号的 EWM 衰减 |
| `social_buzz` | `SocialBuzzFactor` | `factors/social_factor.py` | `window=5` | `source` 列（twitter/stocktwits/weibo） | 社交媒体提及量的滚动 Z-score |
| `sentiment_divergence` | `SentimentDivergenceFactor` | `factors/social_factor.py` | — | `source` + `compound` 列 | 新闻情绪与社交情绪之差 |

---

## NLP 后端

| 后端 | 状态 | 语言 | 说明 |
|------|------|------|------|
| `vader` | ✅ 默认启用 | 英文为主 | 无需 GPU，中文支持有限 |
| `finbert-en` | ⚠️ 需 PyTorch | 英文 | `yiyanghkust/finbert-tone` |
| `finbert-zh` | ⚠️ 需 PyTorch | 中文 | `hw2942/bert-base-chinese-finetuning-financial-news-sentiment-v2` |

---

## 已知技术债

| 类别 | 描述 | 位置 |
|------|------|------|
| GDELT 分段查询 | 单次最多250条，长周期回测时覆盖不足，未实现自动按月/季分段 | `data/loaders/gdelt_loader.py` |
| GDELT 名称缓存（美股）| US ticker 名称需 yfinance 逐只查询，速度慢；可考虑批量预取 | `utils/ticker_names.py` |
| RSS ticker 关联 | `RSSLoader` 依赖关键词映射，未绑定 ticker 时所有文章归属不明 | `data/loaders/newsapi_loader.py` |
| pipeline 注册硬编码 | 每新增 loader 需手动修改 `pipeline.py` 的 `from_config()`，未实现 Loader Registry | `data/pipeline.py` |
| 微博 Stub | 返回空 DataFrame，实际无数据 | `data/loaders/social_loader.py` |

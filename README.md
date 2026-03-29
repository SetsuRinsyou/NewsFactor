# NewsFactor — 新闻/社媒驱动量化因子框架

基于新闻与社交媒体文本，提取情绪/事件因子，通过 alphalens 进行 IC/ICIR 及分层回测验证。支持 A 股（akshare）和美股（yfinance）。

---

## 目录

- [快速开始](#快速开始)
- [安装依赖](#安装依赖)
- [配置文件](#配置文件)
- [CLI 参数说明](#cli-参数说明)
- [内置因子列表](#内置因子列表)
- [数据来源与环境变量](#数据来源与环境变量)
- [NLP 后端选择](#nlp-后端选择)
- [输出文件说明](#输出文件说明)
- [扩展：注册自定义因子](#扩展注册自定义因子)
- [项目结构](#项目结构)

---

## 快速开始

```bash
# A 股情绪因子（VADER 后端，无需 GPU）
python main.py \
  --factor sentiment_ma \
  --tickers 600519 000858 \
  --start 2024-01-01 \
  --end 2024-06-01 \
  --market cn

# 美股 FinBERT 情绪因子
python main.py \
  --factor sentiment_ewm \
  --tickers AAPL MSFT TSLA \
  --start 2024-01-01 \
  --end 2024-06-01 \
  --market us \
  --nlp-backend finbert-en

# 查看所有已注册因子
python main.py --list-factors

# 传入因子自定义参数
python main.py \
  --factor sentiment_ma \
  --tickers 600519 \
  --start 2024-01-01 \
  --end 2024-06-01 \
  --factor-kwargs window=10
```

---

## 安装依赖

```bash
uv pip install -r requirements.txt
# 或
pip install -r requirements.txt
```

> **注意**：若未安装 PyTorch，NLP 模块自动 fallback 至 VADER（纯 CPU，无需模型下载），不影响框架运行。

---

## 配置文件

配置文件位于 `config/config.yaml`，所有凭证通过环境变量注入，**不在配置文件中存储明文**。

```yaml
market:
  default: cn          # cn | us
  cn_calendar: XSHG
  us_calendar: NYSE

data:
  cache_dir: .cache    # 磁盘缓存目录
  cache_ttl_hours: 24  # 缓存有效期（小时）

news:
  em_news:
    enabled: true        # 东方财富新闻（默认开启，仅 A 股）
    delay_seconds: 0.5

  newsapi:
    enabled: false
    api_key: ${NEWSAPI_KEY}

  rss:
    enabled: false
    feeds: []            # RSS 订阅源 URL 列表

  twitter:
    enabled: false
    bearer_token: ${TWITTER_BEARER_TOKEN}

  stocktwits:
    enabled: false       # 无需鉴权，直接使用公开 API

  weibo:
    enabled: false       # Stub，暂不可用

nlp:
  backend: vader         # finbert-en | finbert-zh | vader
  batch_size: 32
  device: cpu            # cpu | cuda | mps

factors:
  sentiment_ma:
    window: 5
  sentiment_ewm:
    halflife: 3

backtest:
  periods: [1, 5, 20]   # 预测期（交易日）
  quantiles: 5           # 分层数量
  filter_zscore: 20
  max_loss: 0.35
```

---

## CLI 参数说明

```
python main.py [OPTIONS]
```

| 参数 | 缩写 | 类型 | 默认值 | 说明 |
|------|------|------|--------|------|
| `--factor` | `-f` | str | `sentiment_ma` | 要计算的因子名称（见 `--list-factors`） |
| `--tickers` | `-t` | str[] | — | 股票代码列表（A 股用6位数字，美股用 AAPL 等） |
| `--start` | `-s` | str | `2024-01-01` | 起始日期，格式 `YYYY-MM-DD` |
| `--end` | `-e` | str | `2024-06-01` | 结束日期，格式 `YYYY-MM-DD` |
| `--market` | `-m` | choice | `cn` | 市场：`cn`（A 股）或 `us`（美股） |
| `--config` | `-c` | str | `config/config.yaml` | 配置文件路径 |
| `--nlp-backend` | — | choice | （从配置读取） | 覆盖 NLP 后端：`vader` / `finbert-en` / `finbert-zh` |
| `--output` | `-o` | str | `reports` | 报告输出目录 |
| `--list-factors` | — | flag | — | 打印所有已注册因子名称并退出 |
| `--factor-kwargs` | — | str[] | — | 传给因子的额外参数，格式 `KEY=VALUE`（自动解析为 int/float/str） |

---

## 内置因子列表

```bash
python main.py --list-factors
# 输出：
# event_intensity
# event_type_dummy
# sentiment_divergence
# sentiment_ewm
# sentiment_ma
# social_buzz
```

| 因子名称 | 类 | 默认参数 | 说明 |
|----------|-----|----------|------|
| `sentiment_ma` | `SentimentMAFactor` | `window=5` | 每日平均情绪值的滚动均值（5交易日窗口） |
| `sentiment_ewm` | `SentimentEWMFactor` | `halflife=3` | 每日平均情绪值的指数加权均值（半衰期3天） |
| `event_intensity` | `EventIntensityFactor` | `decay_days=3` | 每日关键词命中次数的指数衰减累积 |
| `event_type_dummy` | `EventTypeFactor` | `event_type=earnings`, `decay_days=3` | 指定事件类型（如财报）的二值信号，指数衰减 |
| `social_buzz` | `SocialBuzzFactor` | `window=5` | 社交媒体提及量的滚动 Z-score |
| `sentiment_divergence` | `SentimentDivergenceFactor` | — | 新闻情绪与社交情绪之差（分歧信号） |

**自定义参数示例：**

```bash
# 修改滚动窗口为10天
python main.py --factor sentiment_ma --tickers 600519 \
  --start 2024-01-01 --end 2024-06-01 \
  --factor-kwargs window=10

# 指定事件类型为并购
python main.py --factor event_type_dummy --tickers 600519 \
  --start 2024-01-01 --end 2024-06-01 \
  --factor-kwargs event_type=merger decay_days=5
```

---

## 数据来源与环境变量

### 数据来源汇总

| 来源 | 类 | 市场 | 默认状态 | 所需环境变量 | 备注 |
|------|----|------|----------|-------------|------|
| 东方财富新闻 | `EMNewsLoader` | A 股 | **开启** | 无 | 通过 akshare `stock_news_em()` 抓取 |
| NewsAPI | `NewsAPILoader` | 美股/全球 | 关闭 | `NEWSAPI_KEY` | 需注册 newsapi.org |
| RSS 订阅 | `RSSLoader` | 通用 | 关闭 | 无 | 需在 config 中填写 `feeds` URL 列表 |
| Twitter/X | `TwitterLoader` | 美股 | 关闭 | `TWITTER_BEARER_TOKEN` | 需 X 开发者账号，按 $TICKER cashtag 抓取 |
| StockTwits | `StockTwitsLoader` | 美股 | 关闭 | 无 | 无需鉴权，公开 API |
| 微博 | `WeiboLoader` | A 股 | 关闭 | — | **Stub**，官方 API 需企业资质 |
| A 股行情 | `MarketLoader(market="cn")` | A 股 | 内置 | 无 | akshare `stock_zh_a_hist`，前复权 |
| 美股行情 | `MarketLoader(market="us")` | 美股 | 内置 | 无 | yfinance，自动复权 |

### 启用非默认数据源

1. 在 `config/config.yaml` 中将对应 loader 的 `enabled` 改为 `true`：
   ```yaml
   news:
     newsapi:
       enabled: true
   ```

2. 导出所需环境变量：
   ```bash
   export NEWSAPI_KEY="your-api-key"
   export TWITTER_BEARER_TOKEN="your-bearer-token"
   ```

---

## NLP 后端选择

| 后端 | 语言 | 所需环境 | 速度 | 精度 |
|------|------|----------|------|------|
| `vader` | 中/英（基于词典） | 纯 CPU，无需下载 | 极快 | 中 |
| `finbert-en` | 英文 | PyTorch + 模型下载 (~400MB) | 较慢 | 高 |
| `finbert-zh` | 中文 | PyTorch + 模型下载 (~400MB) | 较慢 | 高 |

- 未安装 PyTorch 时，FinBERT 后端自动 fallback 至 `vader`，并输出警告
- `--market cn` 默认使用中文预处理；`--market us` 默认使用英文预处理
- GPU 加速：在 `config.yaml` 中设置 `nlp.device: cuda`（需 CUDA 环境）

### NLP 输出 Schema

情绪分析后，DataFrame 列结构：

| 列名 | 类型 | 说明 |
|------|------|------|
| `date` | datetime | 新闻/社媒发布日期（对齐至交易日） |
| `ticker` | str | 股票代码 |
| `text` | str | 清洗后文本 |
| `source` | str | 数据来源（em_news / newsapi / twitter 等） |
| `positive` | float | 正面情绪概率，[0, 1] |
| `negative` | float | 负面情绪概率，[0, 1] |
| `neutral` | float | 中性情绪概率，[0, 1] |
| `compound` | float | 综合情绪得分 = positive − negative，[−1, 1] |
| `event_type` | str/None | 事件类型（earnings/merger/litigation/dividend/leadership） |
| `event_intensity` | float | 事件关键词匹配强度 |

---

## 输出文件说明

所有输出保存至 `--output` 指定目录（默认 `reports/`），文件名前缀为因子名称。

### CSV 报告

| 文件 | 内容说明 |
|------|----------|
| `{factor}_ic.csv` | 每日 IC（信息系数）时间序列，每列对应一个预测期（1D/5D/20D） |
| `{factor}_icir.csv` | IC 均值、IC 标准差、ICIR 汇总表 |
| `{factor}_quantile_returns.csv` | 各分层（1\~5组）的平均收益率 |

### PNG 图表

| 文件 | 内容说明 |
|------|----------|
| `{factor}_returns.png` | ① 分层平均收益柱状图；② 各分层累计净值曲线；③ 多空组合累计收益 |
| `{factor}_ic_ts.png` | 各预测期的 IC 时间序列 + 22日滚动均值 |
| `{factor}_ic_hist.png` | 各预测期的 IC 分布直方图 + KDE 核密度曲线 |

### 指标解读参考

| 指标 | 阈值参考 | 含义 |
|------|----------|------|
| `IC_mean` | \|IC\| > 0.02 有效，> 0.05 较强 | 因子预测力的平均水平 |
| `ICIR` | > 0.3 较好，> 0.5 优秀 | 因子预测力稳定性（IC均值/IC标准差） |
| 分层收益 | 各层单调递增/递减 | 因子对收益的排序能力 |

---

## 扩展：注册自定义因子

新增因子**无需修改任何已有文件**，只需：

**1. 创建新文件** `factors/my_factor.py`：

```python
import pandas as pd
from factors.base import BaseFactorCalculator, FactorRegistry, FactorResult

@FactorRegistry.register("my_factor")
class MyFactor(BaseFactorCalculator):
    def __init__(self, window: int = 5):
        self.window = window

    def compute(
        self,
        nlp_df: pd.DataFrame,   # 含 NLP 输出的文本 DataFrame（见上方 Schema）
        market_df: pd.DataFrame, # 行情 DataFrame：index=日期，columns=ticker
        **kwargs,
    ) -> FactorResult:
        # 计算因子值，返回 MultiIndex(date, ticker) → float 的 Series
        factor_values: pd.Series = ...  # 自定义计算逻辑

        return FactorResult(name="my_factor", values=factor_values)
```

**2. 在 `factors/__init__.py` 末尾添加一行导入：**

```python
from . import my_factor  # noqa: F401
```

**3. 验证注册成功：**

```bash
python -c "from factors import FactorRegistry; print(FactorRegistry.list_factors())"
# 输出中应包含 'my_factor'
```

**4. 直接使用：**

```bash
python main.py --factor my_factor --tickers 600519 \
  --start 2024-01-01 --end 2024-06-01 \
  --factor-kwargs window=10
```

---

## 项目结构

```
NewsFactor/
├── config/
│   └── config.yaml              # 全局配置（凭证用环境变量）
├── data/
│   ├── base.py                  # BaseDataLoader 抽象基类
│   ├── pipeline.py              # DataPipeline：编排所有 loader
│   └── loaders/
│       ├── em_news.py           # 东方财富新闻（akshare）
│       ├── market_loader.py     # A 股/美股行情
│       ├── newsapi_loader.py    # NewsAPI + RSS
│       └── social_loader.py     # Twitter / StockTwits / 微博
├── nlp/
│   ├── preprocessor.py          # 文本清洗、股票代码识别
│   ├── sentiment.py             # SentimentAnalyzer（VADER/FinBERT）
│   └── event_detector.py        # 基于关键词的事件标注
├── factors/
│   ├── base.py                  # BaseFactorCalculator + FactorRegistry
│   ├── sentiment_factor.py      # sentiment_ma, sentiment_ewm
│   ├── event_factor.py          # event_intensity, event_type_dummy
│   └── social_factor.py         # social_buzz, sentiment_divergence
├── backtest/
│   ├── signal_generator.py      # FactorResult → alphalens 格式转换
│   └── analyzer.py              # IC/ICIR 分析 + 报告生成
├── utils/
│   ├── cache.py                 # @disk_cache 装饰器（diskcache）
│   ├── logger.py                # 日志初始化
│   └── date_utils.py            # 交易日历工具
├── main.py                      # CLI 入口
├── requirements.txt             # 依赖列表
├── plan.md                      # 英文设计方案
└── plan-zh.md                   # 中文设计方案
```

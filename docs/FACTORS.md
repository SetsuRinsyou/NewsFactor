# 因子计算方式说明

本文档详细描述框架中每个已注册因子的计算逻辑、输入依赖和参数。

---

## 1. `sentiment_ma` — 情绪滚动均值

**类**：`SentimentMAFactor`  
**文件**：[factors/sentiment_factor.py](../factors/sentiment_factor.py)  
**默认参数**：`window=5`

### 输入依赖

- `compound` 列：NLP 后端输出的复合情绪分（范围 $[-1, 1]$，正值偏多、负值偏空）

### 计算步骤

1. **日内聚合**：对每个 `(date, ticker)` 取当天所有文章 `compound` 的均值，得到 `compound_daily`

$$\text{compound\_daily}_{t,i} = \frac{1}{N_{t,i}} \sum_{k=1}^{N_{t,i}} \text{compound}_k$$

2. **宽表对齐**：将结果透视为 `[日期 × 股票]` 宽表，按价格索引重建日期轴，对缺失值向前填充（最多 3 个交易日）

3. **滚动均值**：在时间轴上做 `window` 日等权滚动均值

$$\text{sentiment\_ma}_{t,i} = \frac{1}{\min(w,t)} \sum_{k=t-w+1}^{t} \text{compound\_daily}_{k,i}$$

其中 $w$ 为 `window`，`min_periods=1`（不足 `window` 日时用实际可用天数）。

---

## 2. `sentiment_ewm` — 情绪指数加权均值

**类**：`SentimentEWMFactor`  
**文件**：[factors/sentiment_factor.py](../factors/sentiment_factor.py)  
**默认参数**：`halflife=3`

### 输入依赖

- `compound` 列

### 计算步骤

1. **日内聚合**：同 `sentiment_ma` 步骤 1

2. **宽表对齐**：同 `sentiment_ma` 步骤 2

3. **指数加权均值**：按半衰期 `halflife` 做 EWM，对近期文章赋予更高权重

$$\text{sentiment\_ewm}_{t,i} = \sum_{k \le t} \alpha^{t-k} \cdot \text{compound\_daily}_{k,i} \Big/ \sum_{k \le t} \alpha^{t-k}$$

其中衰减系数 $\alpha = 2^{-1/\text{halflife}}$，`min_periods=1`。

> **与 `sentiment_ma` 的区别**：EWM 对最新情绪更敏感，适合快节奏事件驱动策略；MA 更平滑，适合捕捉持续性情绪趋势。

---

## 3. `event_intensity` — 事件强度衰减因子

**类**：`EventIntensityFactor`  
**文件**：[factors/event_factor.py](../factors/event_factor.py)  
**默认参数**：`decay_days=3`

### 输入依赖

- `event_intensity` 列：`EventDetector` 由关键词命中计算的单条文本强度分（整数，0 表示无命中）

### 计算步骤

1. **日内聚合**：对每个 `(date, ticker)` 对当天所有文本的 `event_intensity` 求**和**

$$\text{intensity\_daily}_{t,i} = \sum_{k=1}^{N_{t,i}} \text{event\_intensity}_k$$

2. **宽表对齐**：透视为宽表，缺失日用 `0.0` 填充（无公告即无事件）

3. **指数衰减**：对日内强度之和做 EWM，使历史事件随时间衰减

$$\text{event\_intensity}_{t,i} = \text{ewm}(\text{intensity\_daily}_{\cdot,i},\ \text{halflife}=\text{decay\_days})_t$$

---

## 4. `event_type_dummy` — 事件类型二值因子

**类**：`EventTypeFactor`  
**文件**：[factors/event_factor.py](../factors/event_factor.py)  
**默认参数**：`event_type="earnings"`, `decay_days=3`

### 输入依赖

- `event_type` 列：`EventDetector` 输出的事件类别标签（可选值：`earnings`、`merger`、`litigation`、`dividend`、`leadership`）

### 计算步骤

1. **匹配判断**：对每一行，若 `event_type == target_type` 则标记为 `1`，否则为 `0`

2. **日内聚合**：取每个 `(date, ticker)` 当天所有行的最大值（即当天存在匹配则为 1）

$$\text{dummy\_daily}_{t,i} = \max_{k} \mathbf{1}[\text{event\_type}_k = \text{target\_type}]$$

3. **指数衰减**：对二值信号做 EWM，使事件影响随天数衰减

$$\text{event\_type\_dummy}_{t,i} = \text{ewm}(\text{dummy\_daily}_{\cdot,i},\ \text{halflife}=\text{decay\_days})_t$$

> **典型用途**：隔离特定事件（如财报发布）对收益的独立影响，排除其他噪音事件的干扰。

---

## 5. `social_buzz` — 社交提及量 Z-score

**类**：`SocialBuzzFactor`  
**文件**：[factors/social_factor.py](../factors/social_factor.py)  
**默认参数**：`window=5`

### 输入依赖

- `source` 列：文章/推文来源标签（仅过滤 `twitter`、`stocktwits`、`weibo` 三种社交源）

### 计算步骤

1. **过滤社交源**：仅保留 `source` 属于社交媒体的行

2. **日内计数**：统计每个 `(date, ticker)` 的提及条数

$$\text{mention\_count}_{t,i} = \#\{k : \text{source}_k \in \text{social\_sources},\ \text{ticker}_k = i,\ \text{date}_k = t\}$$

3. **宽表对齐**：透视为宽表，缺失日用 `0.0` 填充

4. **滚动 Z-score**：在时间轴上做 `window` 日滚动标准化

$$\text{social\_buzz}_{t,i} = \frac{\text{mention\_count}_{t,i} - \mu_{t,i}^{(w)}}{\sigma_{t,i}^{(w)}}$$

其中 $\mu^{(w)}$ 和 $\sigma^{(w)}$ 为 `window` 日滚动均值与标准差（`min_periods=2`）；若 $\sigma = 0$ 则输出 `0.0`。

---

## 6. `sentiment_divergence` — 新闻与社交情绪背离因子

**类**：`SentimentDivergenceFactor`  
**文件**：[factors/social_factor.py](../factors/social_factor.py)  
**默认参数**：使用所有已知新闻源与社交源

### 输入依赖

- `compound` 列
- `source` 列（用于区分新闻源与社交源）

### 计算步骤

1. **分源聚合**：分别对新闻源（`em_news`、`newsapi`、`rss`）和社交源（`twitter`、`stocktwits`、`weibo`）计算每个 `(date, ticker)` 的 `compound` 日均值

$$\bar{s}^{\text{news}}_{t,i} = \text{mean}_{k \in \text{news}}(\text{compound}_k),\quad \bar{s}^{\text{social}}_{t,i} = \text{mean}_{k \in \text{social}}(\text{compound}_k)$$

2. **宽表对齐**：两类分别透视为宽表并按价格日期轴对齐，向前填充（最多 3 日）

3. **差值计算**：

$$\text{sentiment\_divergence}_{t,i} = \bar{s}^{\text{news}}_{t,i} - \bar{s}^{\text{social}}_{t,i}$$

正值表示新闻比社交更乐观，负值表示社交比新闻更乐观。若某源当日无数据则该维度贡献 `NaN` 并传播给最终因子值。

---

## 参数一览

| 因子 | 参数 | 类型 | 默认值 | 说明 |
|------|------|------|--------|------|
| `sentiment_ma` | `window` | int | 5 | 滚动窗口（交易日） |
| `sentiment_ewm` | `halflife` | float | 3.0 | EWM 半衰期（交易日） |
| `event_intensity` | `decay_days` | int | 3 | EWM 半衰期（交易日） |
| `event_type_dummy` | `event_type` | str | `"earnings"` | 目标事件类型 |
| `event_type_dummy` | `decay_days` | int | 3 | EWM 半衰期（交易日） |
| `social_buzz` | `window` | int | 5 | 滚动 Z-score 窗口（交易日） |
| `social_buzz` | `sources` | set | 全部社交源 | 自定义社交源白名单 |
| `sentiment_divergence` | `news_sources` | set | `{em_news, newsapi, rss}` | 新闻源白名单 |
| `sentiment_divergence` | `social_sources` | set | `{twitter, stocktwits, weibo}` | 社交源白名单 |

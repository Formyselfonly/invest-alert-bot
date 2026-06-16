# 需求说明书：Invest Alert Bot

> **Invest Alert Bot** — 实时行情监控与 Telegram 告警工具

---

## 1. 项目背景与目的

构建一个**高频、低延迟**的行情监控与告警工具。系统实时监听配置清单中的交易对，在满足特定技术指标条件时，通过 Telegram Bot **即时推送**告警消息，辅助用户进行交易决策。

**重要边界**：Bot 只负责监控与通知，不提供交易建议、不自动下单。用户收到告警后，自行在 TradingView 等平台进行深度分析。

---

## 2. 核心监控逻辑

系统需对 `config.yaml` 中配置的每个交易对，在对应周期上执行以下两类检测。

### 2.1 均线密集告警

| 项目 | 说明 |
|------|------|
| 监控指标 | 20MA、20EMA、60MA、60EMA、120MA、120EMA（共 6 根） |
| 支持周期 | **4H**、**日线（1D）**、**周线（1W）** |
| 判定标准 | 6 根指标的最大值与最小值之差，占当前价格的 **≤ 0.8%** |

**公式**：

```
spread_ratio = (max(indicators) - min(indicators)) / current_price
触发条件：spread_ratio ≤ threshold_cluster（默认 0.008）
```

**语义**：6 根均线/指数均线高度收敛，通常意味着价格进入整理或方向选择前的密集区。

---

### 2.2 200MA 触底告警

| 项目 | 说明 |
|------|------|
| 监控指标 | **200MA**（不看 200EMA） |
| 支持周期 | **日线（1D）**、**周线（1W）**（**不含 4H**） |
| 判定标准 | 最新价格与 200MA 的绝对差值，占当前价格的 **≤ 1.2%** |

**公式**：

```
touch_ratio = abs(current_price - 200MA) / current_price
触发条件：touch_ratio ≤ threshold_touch（默认 0.012）
```

**语义**：价格接近长期 200 日均线，可能形成支撑/阻力反应位（抄底观察位）。

---

### 2.3 触发机制（关键原则）

| 原则 | 说明 |
|------|------|
| **触碰即触发** | 基于实时 tick / 最新价判断，**不等待 K 线收盘确认** |
| **多周期并行** | 同一交易对在不同周期上独立计算、独立告警 |
| **周期分工** | 均线密集：4H/1D/1W；200MA 触底：仅 1D/1W |

---

## 3. 功能需求

### 3.1 动态配置

通过 `config.yaml` 管理全部运行参数，支持随时增删交易对，**无需修改核心代码**。

**配置项概览**：

```yaml
telegram:
  bot_token: "${TELEGRAM_BOT_TOKEN}"   # 支持环境变量引用
  chat_id: "${TELEGRAM_CHAT_ID}"

symbols:
  - symbol: BTC/USDT
    source: binance
    market: futures
    intervals: [4h, 1d, 1wk]

  - symbol: MSFT
    source: nasdaq                 # binance | nasdaq | yfinance
    intervals: [4h, 1d, 1wk]

  - symbol: XAU
    source: nasdaq
    ticker: GC=F                   # 可选，覆盖 Yahoo ticker
    intervals: [4h, 1d, 1wk]

thresholds:
  cluster: 0.008                   # 密集告警阈值（0.8%）
  touch: 0.012                     # 200MA 触底阈值（1.2%）

alert:
  cooldown_seconds: 3600           # 同一 (symbol, interval, alert_type) 冷却时间
  dedupe_window_seconds: 60        # 防抖窗口，避免同一秒内重复推送

polling:
  yfinance_interval_seconds: 300   # nasdaq/yfinance 轮询间隔

logging:
  level: INFO
  file: logs/app.log
```

> 完整配置 schema 见 [plan.md](./plan.md#配置文件结构)。

---

### 3.2 数据接入

| 资产类型 | 数据源 | 接入方式 | 示例 |
|----------|--------|----------|------|
| 加密货币 | Binance 合约 | WebSocket 实时 + REST 历史 K 线 | BTC/USDT, ETH/USDT |
| 美股 | Nasdaq（Yahoo Finance） | 定时轮询（默认 300s） | MSFT, NVDA, MSTR |
| 黄金 | Nasdaq（Yahoo Finance） | 定时轮询，`ticker: GC=F` | XAU |

**启动流程**：

1. 通过 REST API 拉取足够的历史 K 线（至少 200 根，建议 250 根缓冲）
2. 计算初始 MA/EMA 基线
3. 接入实时数据流，滚动更新指标并检测触发条件

---

### 3.3 告警推送

通过 Telegram Bot 发送告警，消息需包含：

| 字段 | 示例 |
|------|------|
| 资产名称 | `BTC/USDT` |
| 告警类型 | `均线密集` / `200MA 触碰` |
| 周期 | 密集：4H/1D/1W；200MA：1D/1W |
| 当前价格 | `$67,432.50` |
| 触发详情 | 密集区间宽度 0.62% / 距 200MA 1.05% |
| 时间戳 | `2026-06-16 14:32:08 UTC` |

**消息示例**：

```
🔔 均线密集告警
━━━━━━━━━━━━━━━
资产: BTC/USDT
周期: 4H
当前价: $67,432.50
密集宽度: 0.62% (阈值 0.8%)
指标: 20MA/EMA, 60MA/EMA, 120MA/EMA
时间: 2026-06-16 14:32:08 UTC
```

---

### 3.4 告警去重与冷却（建议默认）

| 机制 | 目的 | 建议默认值 |
|------|------|------------|
| **冷却期** | 同一 `(symbol, interval, alert_type)` 在冷却期内不重复推送 | 3600 秒（1 小时） |
| **防抖窗口** | 避免价格来回穿越阈值导致秒级刷屏 | 60 秒 |
| **状态恢复** | 条件解除后再次满足，可重新触发（冷却期已过后） | — |

> 以上默认值可在 `config.yaml` 中调整，详见 [plan.md](./plan.md)。

---

## 4. 非功能性需求

| 类别 | 要求 |
|------|------|
| **性能** | Asyncio 异步架构；多交易对并行监控；从价格更新到告警推送延迟 **< 1 秒** |
| **稳定性** | WebSocket 断线自动重连（指数退避）；7×24 不间断运行 |
| **可维护性** | 模块化分层；逻辑与配置分离；结构化日志 |
| **可观测性** | 记录连接状态、指标计算、告警触发、推送结果 |
| **安全性** | Token / Chat ID 通过环境变量注入，不硬编码、不提交到 Git |

---

## 5. 范围边界

### 5.1 本期包含（In Scope）

- 均线密集（4H/1D/1W 六线）+ 200MA 触底（1D/1W）
- Binance 加密资产 WebSocket 实时监控
- Nasdaq/Yahoo 美股与黄金轮询监控
- Telegram 告警推送
- `config.yaml` 动态配置
- Docker 容器化部署

### 5.2 本期不包含（Out of Scope）

- 自动交易 / 下单
- Web 管理界面
- 用户多租户 / 权限系统
- **数据库 / 数据持久化**（v1 无 SQLite；告警历史、K 线均不持久化，冷却状态存内存）
- TradingView Webhook 集成

> 以上可作为后续迭代方向。

---

## 6. 验收标准

- [ ] 配置清单内所有交易对在对应周期上正确计算 MA/EMA
- [ ] 密集告警：6 根指标 spread ≤ 0.8% 时触发（4H/1D/1W）
- [ ] 200MA 触底：价格距 200MA ≤ 1.2% 时触发（仅 1D/1W）
- [ ] 实时触发，不依赖 K 线收盘
- [ ] Telegram 消息格式完整、字段正确
- [ ] WebSocket 断线后 30 秒内自动恢复
- [ ] 冷却期与防抖机制生效，无告警刷屏
- [ ] 7×24 运行 72 小时无崩溃

---

## 7. 待确认项

| # | 问题 | 当前建议 |
|---|------|----------|
| 1 | 冷却期时长 | 1 小时，可按交易对或告警类型单独配置 |
| 2 | yfinance 轮询间隔 | 300 秒（美股/黄金非实时，可接受） |
| 3 | 历史 K 线初始化 | 启动时 REST 拉取 250 根 K 线 |
| 4 | Binance 接入方式 | 原生 WebSocket + REST（低延迟优先；ccxt 仅作备选） |

---

## 附录：术语表

| 术语 | 说明 |
|------|------|
| MA | Simple Moving Average，简单移动平均线 |
| EMA | Exponential Moving Average，指数移动平均线 |
| 密集 | 多根均线价格收敛，spread 低于阈值 |
| 触碰 | 当前价格接近某条关键均线 |
| 冷却期 | 同一告警条件触发后的静默窗口 |

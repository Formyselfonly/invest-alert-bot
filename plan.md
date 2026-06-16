# 实施计划：Invest Alert Bot 开发指南

> 本文档描述分阶段开发计划、项目结构、模块职责与部署方案。  
> 产品需求详见 [prd.md](./prd.md)。

---

## 阶段概览

| 阶段 | 名称 | 目标 | 状态 |
|------|------|------|------|
| 1 | Setup | 项目骨架、配置、日志 | ⬜ 待开始 |
| 2 | Development | 数据采集、计算引擎、告警推送 | ⬜ 待开始 |
| 3 | Integration | 主循环集成、断线重连、测试 | ⬜ 待开始 |
| 4 | Deployment | 容器化、云部署、运维 | ⬜ 待开始 |

---

## 第一阶段：环境与基础架构 (Setup)

### 1.1 项目初始化

```bash
# 使用 uv 初始化（Python 3.12+）
uv init
uv add pandas pyyaml python-telegram-bot aiohttp websockets yfinance
uv add --dev pytest pytest-asyncio ruff
```

**核心依赖说明**：

| 包 | 用途 |
|----|------|
| `pandas` | MA/EMA 滚动计算 |
| `pyyaml` | 配置文件解析 |
| `python-telegram-bot` | Telegram 异步推送 |
| `aiohttp` / `websockets` | Binance WebSocket 连接 |
| `yfinance` | 美股/传统资产行情 |
| `pytest` / `pytest-asyncio` | 异步单元测试 |
| `ruff` | Lint & Format |

> `ccxt` 不作为主依赖。Binance 优先使用原生 WebSocket + REST，延迟更低、控制更细。

---

### 1.2 项目目录结构

```
invest-alert-bot/
├── app/
│   ├── __init__.py
│   ├── main.py                  # 入口：Event Loop 调度
│   ├── core/
│   │   ├── config.py            # 配置加载与校验
│   │   └── logging.py           # 结构化日志
│   ├── providers/
│   │   ├── binance_ws.py        # Binance WebSocket 管理器
│   │   ├── binance_rest.py      # 历史 K 线 REST 拉取
│   │   └── yfinance_poll.py     # Yahoo Finance 轮询
│   ├── services/
│   │   ├── engine.py            # 指标计算 + 触发检测
│   │   └── alert_manager.py     # 冷却/防抖/去重
│   └── notifiers/
│       └── telegram.py          # Telegram 消息推送
├── tests/
│   ├── test_engine.py
│   └── test_alert_manager.py
├── config.yaml                  # 运行配置（不含密钥）
├── .env.example                 # 环境变量模板
├── Dockerfile
├── pyproject.toml
├── uv.lock
├── prd.md
├── plan.md
└── readme.md
```

---

### 1.3 配置文件结构

**`config.yaml`**（业务配置，可提交 Git）：

```yaml
telegram:
  bot_token: "${TELEGRAM_BOT_TOKEN}"
  chat_id: "${TELEGRAM_CHAT_ID}"

symbols:
  - symbol: BTC/USDT
    source: binance
    market: spot
    intervals: [4h, 1d]

  - symbol: ETH/USDT
    source: binance
    market: spot
    intervals: [4h, 1d]

  - symbol: MSTR
    source: yfinance
    intervals: [4h, 1d, 1wk]

thresholds:
  cluster: 0.008    # 密集告警：0.8%
  touch: 0.008      # 触碰告警：0.8%

alert:
  cooldown_seconds: 3600
  dedupe_window_seconds: 60

polling:
  yfinance_interval_seconds: 30

logging:
  level: INFO
  file: logs/app.log
  max_bytes: 10485760    # 10 MB
  backup_count: 5
```

**`.env`**（密钥，不提交 Git）：

```env
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
```

---

### 1.4 日志系统

- 使用 Python `logging` + 文件轮转（RotatingFileHandler）
- 日志级别：`DEBUG` / `INFO` / `WARNING` / `ERROR`
- 关键事件必须记录：
  - WebSocket 连接 / 断线 / 重连
  - 指标计算异常
  - 告警触发与推送结果
  - 配置热加载（如后续支持）

---

## 第二阶段：核心模块开发 (Development)

### 2.1 数据连接器 (`providers/`)

#### BinanceWebSocketManager (`binance_ws.py`)

```
职责：
  - 订阅 aggTrade / kline 流，获取实时价格
  - 异步连接管理，支持多 symbol 多流复用
  - 断线检测 + 指数退避重连（1s → 2s → 4s → ... → 60s cap）
  - 连接状态回调（connected / disconnected / reconnected）
```

#### BinanceRestClient (`binance_rest.py`)

```
职责：
  - 启动时拉取历史 K 线（limit=250）
  - 支持 interval: 4h, 1d, 1w
  - 返回标准化 OHLCV DataFrame
```

#### YahooFinancePoller (`yfinance_poll.py`)

```
职责：
  - 定时轮询（默认 30s）获取最新价格与 K 线
  - 适配 yfinance symbol 格式（MSTR, AAPL 等）
  - 非交易时段静默，避免无效告警
```

---

### 2.2 计算引擎 (`services/engine.py`)

#### `calculate_indicators(df) -> dict`

输入：OHLCV DataFrame（至少 200 行）  
输出：各周期最新指标值

```python
{
    "20_ma": float,
    "20_ema": float,
    "60_ma": float,
    "60_ema": float,
    "120_ma": float,
    "120_ema": float,
    "200_ma": float,
    "200_ema": float,
}
```

#### `check_cluster_alert(indicators, price, threshold) -> bool`

```python
values = [indicators[k] for k in CLUSTER_KEYS]
spread_ratio = (max(values) - min(values)) / price
return spread_ratio <= threshold
```

#### `check_touch_alert(indicators, price, threshold) -> list[str]`

```python
triggered = []
for key in ("200_ma", "200_ema"):
    ratio = abs(price - indicators[key]) / price
    if ratio <= threshold:
        triggered.append(key)
return triggered
```

#### 实时更新策略

| 数据源 | 更新方式 |
|--------|----------|
| Binance WebSocket | 每笔 aggTrade 更新 `current_price`，滚动重算指标 |
| yfinance 轮询 | 每次轮询更新最新 K 线收盘价 |

> MA/EMA 基于已闭合 K 线序列计算，实时价用于与最新指标值比较。这与 TradingView 行为一致，且满足「触碰即触发」需求。

---

### 2.3 告警管理器 (`services/alert_manager.py`)

```
职责：
  - 冷却期：同一 (symbol, interval, alert_type) 在 cooldown 内不重复推送
  - 防抖：dedupe_window 内相同告警合并
  - 状态追踪：记录上次触发时间与告警类型
  - 条件解除检测：spread 回到阈值以上后，重置可触发状态
```

---

### 2.4 告警推送器 (`notifiers/telegram.py`)

```
职责：
  - 异步发送 Telegram 消息（python-telegram-bot v21+ async API）
  - 标准化消息模板（见 prd.md §3.3）
  - 发送失败重试（最多 3 次，指数退避）
  - 速率限制保护（Telegram API 30 msg/s）
```

---

## 第三阶段：集成与测试 (Integration)

### 3.1 主逻辑调度 (`app/main.py`)

```
启动流程：
  1. 加载 config.yaml + .env
  2. 初始化日志
  3. 对每个 symbol × interval：
     a. REST 拉取历史 K 线 → 计算初始指标
     b. 注册 WebSocket 流 / 轮询任务
  4. 进入 asyncio Event Loop
  5. 价格更新 → engine 检测 → alert_manager 过滤 → telegram 推送
  6. 优雅 shutdown（SIGTERM / SIGINT）
```

### 3.2 断线重连策略

```
WebSocket 断线：
  1. 记录 WARNING 日志
  2. 等待 backoff 间隔（指数退避，上限 60s）
  3. 重新连接并重新订阅
  4. REST 补拉断线期间的 K 线缺口
  5. 记录 INFO 日志（重连成功）

连续失败 10 次：
  → 发送 Telegram 运维告警（「数据源连接异常，请检查」）
```

### 3.3 测试计划

| 测试类型 | 覆盖范围 | 工具 |
|----------|----------|------|
| 单元测试 | `engine.py` 指标计算、触发逻辑 | pytest |
| 单元测试 | `alert_manager.py` 冷却/防抖 | pytest |
| 集成测试 | Binance WS 连接 + 数据接收 | pytest-asyncio |
| 集成测试 | Telegram 消息发送 | 手动 / mock |
| 压力测试 | 10+ symbol 并行，延迟 < 1s | 手动 |

**关键测试用例**：

```python
# test_engine.py
def test_cluster_alert_triggered_when_spread_below_threshold(): ...
def test_cluster_alert_not_triggered_when_spread_above_threshold(): ...
def test_touch_alert_200ma_independent_from_200ema(): ...
def test_indicators_require_minimum_200_candles(): ...

# test_alert_manager.py
def test_cooldown_suppresses_duplicate_alerts(): ...
def test_alert_re_triggers_after_cooldown_expires(): ...
def test_dedupe_merges_rapid_fire_alerts(): ...
```

---

## 第四阶段：部署 (Deployment)

### 4.1 容器化

```dockerfile
# Dockerfile（概要）
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN pip install uv && uv sync --frozen --no-dev
COPY . .
CMD ["uv", "run", "python", "-m", "app.main"]
```

### 4.2 部署目标

| 环境 | 方案 | 说明 |
|------|------|------|
| 本地开发 | `uv run python -m app.main` | 直接运行 |
| 云服务器 | Docker + systemd | 推荐：AWS EC2 / Lightsail |
| CI/CD | GitHub Actions | lint → test → build → deploy |

> **注意**：本项目是长驻 WebSocket 进程，**不适合 Serverless 平台**（如 Vercel、AWS Lambda）。应部署在始终在线的 VM 或容器服务上。

### 4.3 运维清单

- [ ] 配置 `.env` 环境变量（Telegram Token、Chat ID）
- [ ] 挂载 `config.yaml` 和 `logs/` 目录
- [ ] 配置 systemd `Restart=always`
- [ ] 设置日志轮转与磁盘监控
- [ ] 配置进程健康检查（心跳日志 / 外部 uptime monitor）

---

## 开发顺序建议

```
Week 1 ─ Setup + Engine
  ├── 项目初始化 (uv, 目录结构)
  ├── config.yaml + 配置加载
  ├── engine.py (指标计算 + 触发逻辑)
  └── 单元测试 (test_engine.py)

Week 2 ─ Data + Notifier
  ├── binance_rest.py (历史 K 线)
  ├── binance_ws.py (WebSocket)
  ├── telegram.py (推送)
  └── alert_manager.py (冷却/防抖)

Week 3 ─ Integration
  ├── main.py (主循环)
  ├── yfinance_poll.py
  ├── 断线重连
  └── 集成测试

Week 4 ─ Deploy
  ├── Dockerfile
  ├── 72h 稳定性测试
  └── 云部署 + 运维文档
```

---

## 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| Binance WebSocket 频繁断线 | 告警延迟或丢失 | 指数退避重连 + REST 补数据 |
| yfinance 限流 / 延迟 | 美股告警不及时 | 30s 轮询 + 非交易时段静默 |
| Telegram API 限流 | 推送失败 | 消息队列 + 重试 + 速率控制 |
| 指标计算精度 | 误报 / 漏报 | 与 TradingView 对比验证 |
| 内存泄漏（长期运行） | 进程崩溃 | 定期重启策略 + 内存监控 |

---

## 后续迭代方向

- [ ] 告警历史持久化（SQLite / PostgreSQL）
- [ ] Web 管理面板（增删交易对、查看状态）
- [ ] 更多告警类型（RSI 超买超卖、成交量异常）
- [ ] TradingView Webhook 双向集成
- [ ] 多用户 / 多 Chat ID 支持
- [ ] Prometheus 指标暴露 + Grafana 仪表盘

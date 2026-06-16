# Invest Alert Bot（抄底王）

一个基于 Python 的高频、低延迟行情监控与告警系统，专注于**均线簇密集度检测**与**关键均线触碰提醒**。满足条件时通过 Telegram 即时推送，辅助交易决策。

> 当前版本：**v0.1.0** — 核心告警链路已实现（Binance 实时 + Telegram 推送）

---

## 核心思路

1. **价值投资**，只选有价值的标的，不选无价值标的
2. **捡漏**，不到捡漏价格绝对不入场，只要标的够多，一定有我们能捡漏的标的
3. **不输就是赢**，活下来第一
4. **不信新闻，不信数据，只认均线**，因为均线是靠真金白银堆出来的市场最终结果

---

## 核心功能

| 功能 | 说明 | 状态 |
|------|------|------|
| **均线密集告警** | 20/60/120 的 MA 与 EMA（6 根），4H / 1D / 1W spread ≤ 0.8% | ✅ |
| **关键位触碰告警** | 200MA / 200EMA，4H / 1D / 1W，距离 ≤ 0.8% | ✅ |
| **Telegram 交互** | `/start` `/status` `/help` 命令 | ✅ |
| **Binance 实时** | WebSocket aggTrade + K 线闭合更新 | ✅ |
| **Yahoo Finance** | 美股/传统资产轮询（如 MSTR） | ✅ |
| **Telegram 推送** | 触碰即触发，冷却 + 防抖 | ✅ |
| **动态配置** | `config.yaml` 管理交易对 | ✅ |
| **数据库** | 无（v1 纯内存，重启后冷却重置） | — |

---

## 技术栈

| 层级 | 技术 |
|------|------|
| 语言 | Python 3.12+ |
| 包管理 | [uv](https://docs.astral.sh/uv/) |
| 加密行情 | Binance WebSocket + REST |
| 传统/美股 | Yahoo Finance (yfinance) |
| 指标计算 | Pandas |
| 告警推送 | Telegram Bot API |
| 运行时 | Asyncio |
| 部署 | Docker + systemd |

---

## 项目结构

```
invest-alert-bot/
├── app/
│   ├── main.py                 # 入口
│   ├── core/                   # 配置、日志
│   ├── schemas/                # Pydantic 数据模型
│   ├── providers/              # Binance WS/REST, yfinance
│   ├── services/               # 计算引擎、告警管理、编排
│   └── notifiers/              # Telegram 推送
├── tests/
├── config.yaml                 # 监控标的与阈值
├── .env.example                # Telegram 密钥模板
├── Dockerfile
├── prd.md
├── plan.md
└── readme.md
```

---

## 系统架构

### 代码架构图

单进程 Asyncio 应用，按职责分层：`providers` 拉行情，`services` 算指标与编排，`notifiers` 对接 Telegram。

```mermaid
flowchart TB
    subgraph Entry["入口层"]
        MAIN["app/main.py"]
    end

    subgraph Core["core/ — 基础设施"]
        CFG["config.py<br/>加载 config.yaml + .env"]
        LOG["logging.py"]
    end

    subgraph Schemas["schemas/ — 数据模型"]
        MK["market.py<br/>Kline · Tick · Indicators"]
        AL["alert.py<br/>AlertEvent · AlertType"]
        SC["config.py<br/>AppConfig · SymbolConfig"]
    end

    subgraph Providers["providers/ — 外部行情"]
        BREST["binance_rest.py<br/>REST 历史 K 线"]
        BWS["binance_ws.py<br/>WebSocket 实时流"]
        YF["yfinance_poll.py<br/>Yahoo 轮询"]
    end

    subgraph Services["services/ — 业务逻辑"]
        COORD["coordinator.py<br/>总编排"]
        SM["symbol_monitor.py<br/>单标的×周期监控"]
        ENG["engine.py<br/>MA/EMA 计算 & 触发判定"]
        AM["alert_manager.py<br/>冷却 & 防抖"]
    end

    subgraph Notifiers["notifiers/ — 通知"]
        TG["telegram.py<br/>推送告警"]
        TGCMD["telegram_commands.py<br/>/start /status /help"]
    end

    subgraph External["外部服务（无需 API Key）"]
        BINREST["Binance REST<br/>api.binance.com"]
        BINWS["Binance WebSocket<br/>stream.binance.com"]
        YAHOO["Yahoo Finance<br/>via yfinance"]
    end

    subgraph ExternalAuth["外部服务（需 .env）"]
        TGAPI["Telegram Bot API"]
    end

    MAIN --> CFG
    MAIN --> COORD
    MAIN --> TGCMD
    COORD --> BREST & BWS & YF
    COORD --> SM
    SM --> ENG & AM
    SM -->|AlertEvent| COORD
    COORD --> TG
    TGCMD -->|format_status| COORD

    BREST --> BINREST
    BWS --> BINWS
    YF --> YAHOO
    TG & TGCMD --> TGAPI

    COORD -.-> MK & AL & SC
    SM -.-> MK & AL
    ENG -.-> MK & AL
    BREST & BWS & YF -.-> MK
```

| 层级 | 目录 | 职责 |
|------|------|------|
| 入口 | `main.py` | 启动 Coordinator + Telegram 命令 Bot，处理 SIGINT/SIGTERM |
| 编排 | `coordinator.py` | 初始化 Monitor、连接数据源、路由 tick/kline 更新 |
| 监控 | `symbol_monitor.py` | 每个 `symbol × interval` 独立维护 K 线、指标、现价 |
| 引擎 | `engine.py` | Pandas 计算 MA/EMA，判定密集 & 触碰 |
| 告警 | `alert_manager.py` | 同一 `(symbol, interval, type)` 冷却 1h + 60s 防抖 |
| 行情 | `providers/` | Binance REST/WS、Yahoo 轮询，隔离第三方 API |
| 通知 | `notifiers/` | Telegram 推送与交互命令 |

---

### 数据流图

#### 启动阶段（Bootstrap）

```mermaid
flowchart LR
    A["uv run python -m app.main"] --> B["load_config()"]
    B --> C["Coordinator.start()"]
    C --> D["Binance REST<br/>拉 250 根历史 K 线"]
    C --> E["yfinance<br/>拉 250 根历史 K 线"]
    D --> F["SymbolMonitor.initialize()"]
    E --> F
    F --> G["calculate_indicators()<br/>需 ≥200 根 K 线"]
    G --> H["Binance WS 连接<br/>aggTrade + kline"]
    H --> I["Telegram 发送启动消息"]
```

#### 运行阶段（Runtime）

```mermaid
flowchart TB
    subgraph Binance["Binance 实时（source: binance）"]
        WS1["aggTrade 逐笔成交"] -->|实时 price| P["SymbolMonitor.on_price()"]
        WS2["kline 事件"] -->|is_closed=true| K["SymbolMonitor.on_kline_closed()"]
        K --> R["重算 MA/EMA"]
        R --> P
    end

    subgraph Yahoo["Yahoo Finance（source: yfinance）"]
        POLL["每 30s 轮询"] --> U["update_klines()"]
        U --> R2["重算 MA/EMA"]
        R2 --> P2["on_price(最新 close)"]
    end

    P --> E["_evaluate() 告警判定"]
    P2 --> E

    E --> C{"密集 or 触碰?"}
    C -->|否| X["跳过"]
    C -->|是| D{"AlertManager<br/>冷却 & 防抖?"}
    D -->|否| X
    D -->|是| T["TelegramNotifier.send_alert()"]
```

#### 数据源对照

| 配置 `source` | 历史 K 线 | 实时价格 | 是否需要 Key |
|---------------|-----------|----------|--------------|
| `binance` | Binance REST | Binance WS `aggTrade` | 否（公开接口） |
| `yfinance` | yfinance | 轮询最新 close（约 30s） | 否 |

> `.env` 只需配置 Telegram；行情数据走 Binance / Yahoo **公开接口**，无需额外 API Key。

---

### 算法流程图

#### 指标计算

基于**已闭合 K 线**的收盘价序列，用 Pandas 滚动/指数加权计算 8 条均线（最少 200 根 K 线才产出指标）。

```mermaid
flowchart LR
    KL["Kline[]<br/>最多保留 250 根"] --> DF["DataFrame(close)"]
    DF --> MA20["MA 20"]
    DF --> EMA20["EMA 20"]
    DF --> MA60["MA 60"]
    DF --> EMA60["EMA 60"]
    DF --> MA120["MA 120"]
    DF --> EMA120["EMA 120"]
    DF --> MA200["MA 200"]
    DF --> EMA200["EMA 200"]
    MA20 & EMA20 & MA60 & EMA60 & MA120 & EMA120 --> IND["Indicators"]
    MA200 & EMA200 --> IND
```

#### 告警判定（每次价格更新触发）

**现价**来自实时 tick（Binance）或轮询 close（yfinance）；**均线**来自已闭合 K 线——触碰检测不等 K 线收盘。

```mermaid
flowchart TB
    START["on_price(current_price)"] --> CHECK{"indicators<br/>已就绪?"}
    CHECK -->|否| END["跳过"]
    CHECK -->|是| CLUSTER

    subgraph Cluster["均线密集告警（4H / 1D / 1W）"]
        CLUSTER["取 6 根均线<br/>20/60/120 MA & EMA"]
        CLUSTER --> SPREAD["spread = (max - min) / price"]
        SPREAD --> COK{"spread ≤ 0.8%?"}
        COK -->|是| CE["AlertType.CLUSTER"]
    end

    subgraph Touch["关键位触碰告警（4H / 1D / 1W）"]
        TMA["touch_ma = |price - 200MA| / price"]
        TEMA["touch_ema = |price - 200EMA| / price"]
        TMA --> TOK1{"≤ 0.8%?"}
        TEMA --> TOK2{"≤ 0.8%?"}
        TOK1 -->|是| AE1["AlertType.TOUCH_200_MA"]
        TOK2 -->|是| AE2["AlertType.TOUCH_200_EMA"]
    end

    CE & AE1 & AE2 --> AM["AlertManager.should_send()"]
    AM --> COOL{"距上次同类型告警<br/>≥ cooldown(1h)?"}
    COOL -->|否| END
    COOL -->|是| DEDUP{"60s 防抖窗口?"}
    DEDUP -->|重复| END
    DEDUP -->|通过| SEND["Telegram 推送"]
    SEND --> REC["record_sent()"]
    REC --> END
```

#### 公式速查

**均线密集**（6 根均线：20/60/120 的 MA + EMA）：

```
spread = (max(6根均线) - min(6根均线)) / current_price
触发条件：spread ≤ thresholds.cluster（默认 0.8%）
```

**关键均线触碰**（200MA 与 200EMA 独立检测）：

```
touch = abs(current_price - 200MA_or_EMA) / current_price
触发条件：touch ≤ thresholds.touch（默认 0.8%）
```

| 设计要点 | 说明 |
|----------|------|
| 触碰即触发 | 不等 K 线收盘，实时价一到就判定 |
| 指标基于闭合 K 线 | MA/EMA 不含当前未闭合 bar |
| 冷却 | 同一 `(symbol, interval, alert_type)` 默认 1 小时不重复推送 |
| 防抖 | 60 秒内同 key 不重复发送 |
| 纯内存 | 无数据库，重启后冷却状态重置 |

详细算法与验收标准见 [prd.md](./prd.md)。

---

## 快速开始

### 第一步：创建 Telegram Bot（只需做一次）

你需要两个东西：**Bot Token** 和 **Chat ID**。

#### 1. 用 BotFather 创建 Bot

1. 在 Telegram 搜索 **[@BotFather](https://t.me/BotFather)**，打开对话
2. 发送 `/newbot`
3. 按提示输入 Bot 显示名称，例如：`Invest Alert Bot`
4. 输入 Bot 用户名（必须以 `bot` 结尾），例如：`my_invest_alert_bot`
5. 创建成功后，BotFather 会返回一串 **Token**，格式类似：

   ```
   7123456789:AAHxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ```

   复制保存，这就是 `TELEGRAM_BOT_TOKEN`。

#### 2. 获取你的 Chat ID

**方法 A（推荐）：自动脚本**

```bash
uv run python -m app.scripts.get_chat_id
```

按提示给 Bot 发一条消息，脚本会打印 `TELEGRAM_CHAT_ID`。

**方法 B：@userinfobot**

1. Telegram 搜索 **@userinfobot**，点 Start
2. 复制返回的 **Id**（纯数字）

**方法 C：浏览器 getUpdates**

1. 先给 Bot 发 `/start` 或任意消息
2. 访问（把 Token 换进去）：

   ```
   https://api.telegram.org/bot<TOKEN>/getUpdates
   ```

3. 找 `"chat":{"id":123456789}`

> 若 `getUpdates` 返回 `"result":[]`：确认消息已发给**正确的 Bot**，或先访问 `deleteWebhook` 再试。

#### 3. 写入 `.env`

```bash
cp .env.example .env
```

编辑 `.env`：

```env
TELEGRAM_BOT_TOKEN=7123456789:AAHxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TELEGRAM_CHAT_ID=123456789
```

---

### 第二步：安装与配置

```bash
# 安装 uv（如未安装）
curl -LsSf https://astral.sh/uv/install.sh | sh

git clone https://github.com/your-org/invest-alert-bot.git
cd invest-alert-bot

# 安装依赖
uv sync
```

编辑 `config.yaml`，配置要监控的标的：

```yaml
symbols:
  - symbol: BTC/USDT
    source: binance
    intervals: [4h, 1d, 1wk]

  - symbol: ETH/USDT
    source: binance
    intervals: [4h, 1d, 1wk]

  # 美股示例（轮询，非实时）
  # - symbol: MSTR
  #   source: yfinance
  #   intervals: [4h, 1d, 1wk]
```

---

## 怎么运行？（没有 FastAPI）

本项目**不是 Web API**，没有 FastAPI / HTTP 服务。

只需要跑**一个 Python 进程**，它同时做两件事：

1. **监控行情**（Binance WebSocket + 指标计算）
2. **Telegram Bot**（推送告警 + 响应 `/start` 等命令）

```bash
uv run python -m app.main
```

程序在跑 = Bot 在线；关掉终端 = Bot 离线。

---

### 第三步：运行

```bash
uv run python -m app.main
```

启动成功后，Telegram 会收到一条消息：

```
✅ Invest Alert Bot 已启动
正在监控 6 个标的 × 周期组合
触碰条件时将即时推送告警。
```

**Telegram 命令**（程序运行中可用）：

| 方式 | 说明 |
|------|------|
| 输入 `/` | 弹出命令菜单（start / status / help） |
| 底部按钮 | 📡 监控状态、❓ 帮助、🏠 主菜单 |
| 消息内按钮 | `/start` 后消息下方的 inline 快捷按钮 |

| 命令 | 作用 |
|------|------|
| `/start` | 欢迎 & 显示按钮菜单 |
| `/status` | 查看各周期 **200MA/200EMA**、密集宽度、距均线距离 |
| `/help` | 帮助 |

> 若更新后 `/` 菜单没出现：重启 `app.main`，并关闭 Telegram 对话重新打开。

> 若只想验证 Telegram 配置（不启动监控），可运行：
>
> ```bash
> uv run python -m app.scripts.test_telegram
> ```

按 `Ctrl+C` 停止。

---

### 第四步：测试

```bash
uv run pytest tests/ -v
uv run ruff check app tests
```

---

## 告警消息示例

```
📊 Invest Alert Bot
━━━━━━━━━━━━━━━
告警类型: 均线密集
资产: BTC/USDT
周期: 4H
当前价: $67,432.5000
详情: 密集宽度 0.62% (阈值 0.8%)
时间: 2026-06-16 14:32:08 UTC
```

---

## 告警逻辑速览

算法流程图见上方 [算法流程图](#算法流程图) 章节。核心规则：

- **触碰即触发**，不等 K 线收盘
- MA/EMA 基于已闭合 K 线计算，实时价用于比较
- 同一告警默认 **1 小时冷却** + **60 秒防抖**，避免刷屏

---

## 配置说明

| 配置项 | 文件 | 说明 |
|--------|------|------|
| `TELEGRAM_BOT_TOKEN` | `.env` | BotFather 给的 Token |
| `TELEGRAM_CHAT_ID` | `.env` | 你的 Telegram 用户 ID |
| `symbols` | `config.yaml` | 监控标的列表 |
| `thresholds.cluster` | `config.yaml` | 密集阈值，默认 0.008 (0.8%) |
| `thresholds.touch` | `config.yaml` | 触碰阈值，默认 0.008 (0.8%) |
| `alert.cooldown_seconds` | `config.yaml` | 冷却时间，默认 3600 秒 |

---

## Docker 部署

```bash
docker build -t invest-alert-bot .
docker run -d \
  --name invest-alert-bot \
  --restart always \
  --env-file .env \
  -v $(pwd)/config.yaml:/app/config.yaml \
  -v $(pwd)/logs:/app/logs \
  invest-alert-bot
```

推荐部署在**始终在线的 VM**（AWS EC2 / Lightsail），不适合 Serverless。

---

## 文档

| 文档 | 说明 |
|------|------|
| [prd.md](./prd.md) | 产品需求、验收标准 |
| [plan.md](./plan.md) | 开发计划、模块设计 |

---

## License

MIT

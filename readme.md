# Invest Alert Bot(抄底王)

一个基于 Python 的高频、低延迟行情监控与告警系统，专注于**均线簇密集度检测**与**关键均线触碰提醒**。满足条件时通过 Telegram 即时推送，辅助交易决策。
(这里为DEMO版本，完整代码付费，请联系作者)
---

## 核心思路
**1.价值投资，只选有价值的标的，不选无价值标的**

**2.捡漏，不到捡漏价格绝对不入场，只要标的够多，一定有我们能捡漏的标的**

**3.不输就是赢，活下来第一**

**4.不信新闻，不信数据，只认均线，因为均线是靠真金白银白出来的市场最终结果**

## 核心功能

| 功能 | 说明 |
|------|------|
| **均线密集告警** | 监控 20/60/120 的 MA 与 EMA（6 根），4H / 日线级别 spread ≤ 0.8% 时触发 |
| **关键位触碰告警** | 监控 200MA / 200EMA，4H / 日线 / 周线级别，价格距均线 ≤ 0.8% 时触发 |
| **动态配置** | 通过 `config.yaml` 管理监控资产，支持 BTC、ETH、SOL、MSTR 等 |
| **极速推送** | Asyncio + WebSocket，触碰即触发，不等待 K 线收盘 |
| **告警去重** | 冷却期 + 防抖机制，避免重复刷屏 |

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
│   ├── main.py              # 入口
│   ├── core/                # 配置、日志
│   ├── providers/           # 数据源（Binance WS/REST, yfinance）
│   ├── services/            # 计算引擎、告警管理
│   └── notifiers/           # Telegram 推送
├── tests/
├── config.yaml              # 业务配置
├── .env.example             # 环境变量模板
├── Dockerfile
├── prd.md                   # 产品需求文档
├── plan.md                  # 开发实施计划
└── readme.md
```

---

## 快速开始

### 1. 环境准备

```bash
# 安装 uv（如未安装）
curl -LsSf https://astral.sh/uv/install.sh | sh

# 克隆项目
git clone https://github.com/your-org/invest-alert-bot.git
cd invest-alert-bot

# 安装依赖
uv sync
```

### 2. 配置

```bash
# 复制环境变量模板
cp .env.example .env

# 编辑 .env，填入 Telegram 凭据
# TELEGRAM_BOT_TOKEN=your_bot_token
# TELEGRAM_CHAT_ID=your_chat_id
```

编辑 `config.yaml`，添加要监控的交易对：

```yaml
symbols:
  - symbol: BTC/USDT
    source: binance
    intervals: [4h, 1d]

  - symbol: MSTR
    source: yfinance
    intervals: [4h, 1d, 1wk]
```

### 3. 运行

```bash
# 开发模式
uv run python -m app.main

# 或使用 Docker
docker build -t invest-alert-bot .
docker run -d --env-file .env -v $(pwd)/config.yaml:/app/config.yaml invest-alert-bot
```

### 4. 测试

```bash
uv run pytest tests/ -v
```

---

## 告警逻辑速览

**均线密集**（4H / 1D）：

```
spread = (max(20MA, 20EMA, 60MA, 60EMA, 120MA, 120EMA)
        - min(...)) / current_price
触发：spread ≤ 0.8%
```

**关键均线触碰**（4H / 1D / 1W）：

```
touch = abs(current_price - 200MA_or_EMA) / current_price
触发：touch ≤ 0.8%（200MA 与 200EMA 独立检测）
```

详细算法与验收标准见 [prd.md](./prd.md)。

---

## 文档

| 文档 | 说明 |
|------|------|
| [prd.md](./prd.md) | 产品需求：告警逻辑、功能需求、验收标准 |
| [plan.md](./plan.md) | 开发计划：模块设计、目录结构、部署方案 |

---

## 部署

推荐部署在**始终在线的 VM** 上（AWS EC2 / Lightsail 等），不适合 Serverless 平台。

```bash
# Docker 部署
docker build -t invest-alert-bot .
docker run -d \
  --name invest-alert-bot \
  --restart always \
  --env-file .env \
  -v $(pwd)/config.yaml:/app/config.yaml \
  -v $(pwd)/logs:/app/logs \
  invest-alert-bot
```

详见 [plan.md § 第四阶段](./plan.md#第四阶段部署-deployment)。

---

## License

MIT

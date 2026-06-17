"""Map bot symbols to TradingAgents tickers and build snapshots.
Author: Shijie Zheng (Kerry Zheng) — https://github.com/Formyselfonly
Repository: https://github.com/Formyselfonly/invest-alert-bot
"""

from __future__ import annotations

from app.schemas.alert import AlertEvent, AlertType
from app.schemas.analysis import BotSignalSnapshot
from app.schemas.config import SymbolConfig
from app.services.engine import supports_touch
from app.services.status_format import format_ma200_position
from app.services.symbol_monitor import SymbolMonitor


def to_tradingagents_ticker(
    symbol: str,
    yf_ticker: str | None = None,
) -> str:
    if yf_ticker and yf_ticker not in {symbol, symbol.upper()}:
        return yf_ticker

    normalized = symbol.upper().replace("/", "")
    if normalized.endswith("USDT"):
        base = normalized[:-4]
        return f"{base}-USD"
    return symbol


def find_symbol_config(
    symbol: str,
    symbols: list[SymbolConfig],
) -> SymbolConfig | None:
    for cfg in symbols:
        if cfg.symbol == symbol:
            return cfg
    return None


def build_snapshot(
    monitor: SymbolMonitor,
    alert_event: AlertEvent | None = None,
) -> BotSignalSnapshot:
    ind = monitor.indicators
    if ind is None:
        msg = "Monitor indicators not ready"
        raise ValueError(msg)

    metrics = monitor.get_metrics()
    cluster_pct = metrics.cluster_pct if metrics else None
    touch_ma_pct = None
    touch_ma_side = None
    if supports_touch(monitor.interval):
        touch_ma_pct = metrics.touch_ma_pct if metrics else None
        touch_ma_side = format_ma200_position(
            monitor.current_price,
            ind.ma_200,
        )

    alert_type = alert_event.alert_type if alert_event else None
    alert_detail = alert_event.detail if alert_event else None

    return BotSignalSnapshot(
        symbol=monitor.symbol,
        interval=monitor.interval,
        price=monitor.current_price,
        cluster_pct=cluster_pct,
        touch_ma_pct=touch_ma_pct,
        touch_ma_side=touch_ma_side,
        ma_20=ind.ma_20,
        ma_60=ind.ma_60,
        ma_120=ind.ma_120,
        ma_200=ind.ma_200,
        alert_type=alert_type,
        alert_detail=alert_detail,
    )


def build_briefing(snapshot: BotSignalSnapshot) -> str:
    lines = [
        "Invest Alert Bot 监控快照（请以以下均线数据为准，勿编造价格）：",
        f"- 标的: {snapshot.symbol} · 周期: {snapshot.interval}",
        f"- 现价: {snapshot.price:.4f}",
        f"- MA20/60/120/200: "
        f"{snapshot.ma_20:.2f} / {snapshot.ma_60:.2f} / "
        f"{snapshot.ma_120:.2f} / {snapshot.ma_200:.2f}",
    ]
    if snapshot.cluster_pct is not None:
        lines.append(f"- 六线密集宽度: {snapshot.cluster_pct:.2f}%")
    if snapshot.touch_ma_pct is not None:
        side = snapshot.touch_ma_side or "—"
        lines.append(
            f"- 距 200MA: {snapshot.touch_ma_pct:.2f}% · 价格在200MA{side}",
        )
    if snapshot.alert_type is not None:
        label = (
            "均线密集-开仓机会"
            if snapshot.alert_type == AlertType.CLUSTER
            else "200MA 触碰-抄底机会"
        )
        lines.append(f"- 触发告警: {label}")
        if snapshot.alert_detail:
            lines.append(f"- 告警详情: {snapshot.alert_detail}")
    return "\n".join(lines)

"""Per symbol × interval monitoring state and alert evaluation."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from app.schemas.alert import ALERT_TYPE_LABELS, AlertEvent, AlertType
from app.schemas.market import Indicators, Kline
from app.services.alert_manager import AlertManager
from app.services.engine import (
    calculate_indicators,
    check_cluster_alert,
    check_touch_alerts,
    cluster_spread_ratio,
    supports_cluster,
    supports_touch,
    touch_ratio,
)
from app.services.status_format import (
    INTERVAL_LABELS,
    MonitorMetrics,
    build_metrics,
)

logger = logging.getLogger(__name__)

AlertCallback = Callable[[AlertEvent], Awaitable[None]]
MAX_KLINES = 250

INTERVAL_ORDER = {"4h": 0, "1d": 1, "1wk": 2, "1w": 2}


class SymbolMonitor:
    def __init__(
        self,
        symbol: str,
        interval: str,
        cluster_threshold: float,
        touch_threshold: float,
        alert_manager: AlertManager,
        on_alert: AlertCallback,
    ) -> None:
        self.symbol = symbol
        self.interval = interval
        self.cluster_threshold = cluster_threshold
        self.touch_threshold = touch_threshold
        self._alert_manager = alert_manager
        self._on_alert = on_alert
        self.klines: list[Kline] = []
        self.indicators: Indicators | None = None
        self.current_price: float = 0.0

    def initialize(self, klines: list[Kline]) -> None:
        self.klines = klines[-MAX_KLINES:]
        self.indicators = calculate_indicators(self.klines)
        if self.klines:
            self.current_price = self.klines[-1].close
        logger.info(
            "Monitor ready: %s %s klines=%s indicators=%s",
            self.symbol,
            self.interval,
            len(self.klines),
            self.indicators is not None,
        )

    def update_klines(self, klines: list[Kline]) -> None:
        self.klines = klines[-MAX_KLINES:]
        self.indicators = calculate_indicators(self.klines)
        if self.klines:
            self.current_price = self.klines[-1].close

    def on_kline_closed(self, kline: Kline) -> None:
        if self.klines and self.klines[-1].open_time == kline.open_time:
            self.klines[-1] = kline
        elif not self.klines or kline.open_time > self.klines[-1].open_time:
            self.klines.append(kline)
            self.klines = self.klines[-MAX_KLINES:]
        self.indicators = calculate_indicators(self.klines)

    async def on_price(self, price: float) -> None:
        if price <= 0:
            return
        self.current_price = price
        await self._evaluate()

    def get_metrics(self) -> MonitorMetrics | None:
        if self.indicators is None or self.current_price <= 0:
            return None
        return build_metrics(
            self.symbol,
            self.interval,
            self.indicators,
            self.current_price,
        )

    def format_status_line(self) -> str:
        """Status line: per-interval MA values (not duplicate spot price)."""
        label = INTERVAL_LABELS.get(self.interval.lower(), self.interval)
        if self.indicators is None:
            return f"⏳ *{label}*  指标初始化中…"

        ind = self.indicators
        cluster_pct = cluster_spread_ratio(ind, self.current_price) * 100
        dist_ma = touch_ratio(self.current_price, ind.ma_200) * 100
        dist_ema = touch_ratio(self.current_price, ind.ema_200) * 100

        return (
            f"✅ *{label}*\n"
            f"   200MA `${ind.ma_200:,.2f}` | "
            f"200EMA `${ind.ema_200:,.2f}`\n"
            f"   密集 `{cluster_pct:.2f}%` | "
            f"距200MA `{dist_ma:.2f}%` | "
            f"距200EMA `{dist_ema:.2f}%`"
        )

    async def _evaluate(self) -> None:
        if self.indicators is None or self.current_price <= 0:
            return

        events: list[AlertEvent] = []
        now = datetime.now(tz=UTC)

        if supports_cluster(self.interval):
            triggered, ratio = check_cluster_alert(
                self.indicators,
                self.current_price,
                self.cluster_threshold,
            )
            if triggered:
                pct = ratio * 100
                cluster_pct = self.cluster_threshold * 100
                events.append(
                    AlertEvent(
                        symbol=self.symbol,
                        interval=self.interval,
                        alert_type=AlertType.CLUSTER,
                        price=self.current_price,
                        detail=(
                            f"密集宽度 {pct:.2f}% "
                            f"(阈值 {cluster_pct:.1f}%)"
                        ),
                        triggered_at=now,
                    ),
                )

        touch_events: list[AlertEvent] = []
        if supports_touch(self.interval):
            for alert_type, ratio in check_touch_alerts(
                self.indicators,
                self.current_price,
                self.touch_threshold,
            ):
                pct = ratio * 100
                touch_pct = self.touch_threshold * 100
                label = ALERT_TYPE_LABELS[alert_type]
                touch_events.append(
                    AlertEvent(
                        symbol=self.symbol,
                        interval=self.interval,
                        alert_type=alert_type,
                        price=self.current_price,
                        detail=(
                            f"距 {label} {pct:.2f}% "
                            f"(阈值 {touch_pct:.1f}%)"
                        ),
                        triggered_at=now,
                    ),
                )

        # 先推密集，再推 200 线触碰，避免混在一起
        for event in events + touch_events:
            if self._alert_manager.should_send(event):
                logger.info(
                    "Alert triggered: %s %s %s @ %s",
                    event.symbol,
                    event.interval,
                    event.alert_type,
                    event.price,
                )
                await self._on_alert(event)
                self._alert_manager.record_sent(event)

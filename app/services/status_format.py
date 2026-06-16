"""Status metrics for summary and detail views."""

from __future__ import annotations

from dataclasses import dataclass

from app.schemas.market import Indicators
from app.services.engine import cluster_spread_ratio, touch_ratio

WATCH_PCT = 2.0  # 摘要里「接近告警」的显示阈值（%）

INTERVAL_LABELS = {"4h": "4H", "1d": "1D", "1wk": "1W", "1w": "1W"}


def format_pct(value: float) -> str:
    if value != value or value == float("inf"):
        return "—"
    return f"{value:.2f}%"


def format_ma200_position(price: float, ma_200: float) -> str:
    if price != price or ma_200 != ma_200 or price <= 0 or ma_200 <= 0:
        return "—"
    if price > ma_200:
        return "上方"
    if price < ma_200:
        return "下方"
    return "持平"


@dataclass(frozen=True)
class MonitorMetrics:
    symbol: str
    interval: str
    interval_label: str
    cluster_pct: float
    touch_ma_pct: float
    touch_ma_side: str

    @property
    def cluster_near(self) -> bool:
        return self.cluster_pct <= WATCH_PCT

    @property
    def touch_near(self) -> bool:
        return self.touch_ma_pct <= WATCH_PCT


def build_metrics(
    symbol: str,
    interval: str,
    indicators: Indicators,
    price: float,
) -> MonitorMetrics:
    label = INTERVAL_LABELS.get(interval.lower(), interval.upper())
    return MonitorMetrics(
        symbol=symbol,
        interval=interval,
        interval_label=label,
        cluster_pct=cluster_spread_ratio(indicators, price) * 100,
        touch_ma_pct=touch_ratio(price, indicators.ma_200) * 100,
        touch_ma_side=format_ma200_position(price, indicators.ma_200),
    )

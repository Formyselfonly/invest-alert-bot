"""Tests for MA/EMA engine and trigger logic."""

from datetime import UTC, datetime

import pytest

from app.schemas.alert import AlertType
from app.schemas.market import Indicators, Kline
from app.services.engine import (
    MIN_KLINES,
    calculate_indicators,
    check_cluster_alert,
    check_touch_alerts,
    cluster_spread_ratio,
    supports_cluster,
    supports_touch,
)


def _make_klines(count: int, base_price: float = 100.0) -> list[Kline]:
    klines: list[Kline] = []
    for i in range(count):
        price = base_price + (i * 0.01)
        klines.append(
            Kline(
                open_time=datetime(2024, 1, 1, tzinfo=UTC),
                open=price,
                high=price + 1,
                low=price - 1,
                close=price,
                volume=1000.0,
            ),
        )
    return klines


def test_calculate_indicators_requires_minimum_klines() -> None:
    klines = _make_klines(MIN_KLINES - 1)
    assert calculate_indicators(klines) is None


def test_calculate_indicators_returns_values() -> None:
    klines = _make_klines(MIN_KLINES)
    indicators = calculate_indicators(klines)
    assert indicators is not None
    assert indicators.ma_20 > 0
    assert indicators.ema_200 > 0


def test_cluster_alert_triggered_when_spread_below_threshold() -> None:
    indicators = Indicators(
        ma_20=100.0,
        ema_20=100.2,
        ma_60=100.3,
        ema_60=100.1,
        ma_120=100.4,
        ema_120=100.2,
        ma_200=95.0,
        ema_200=95.0,
    )
    triggered, ratio = check_cluster_alert(indicators, 100.0, 0.008)
    assert triggered is True
    assert ratio <= 0.008


def test_cluster_alert_not_triggered_when_spread_above_threshold() -> None:
    indicators = Indicators(
        ma_20=100.0,
        ema_20=105.0,
        ma_60=110.0,
        ema_60=115.0,
        ma_120=120.0,
        ema_120=125.0,
        ma_200=95.0,
        ema_200=95.0,
    )
    triggered, _ratio = check_cluster_alert(indicators, 100.0, 0.008)
    assert triggered is False


def test_touch_alert_only_200ma() -> None:
    indicators = Indicators(
        ma_20=100.0,
        ema_20=100.0,
        ma_60=100.0,
        ema_60=100.0,
        ma_120=100.0,
        ema_120=100.0,
        ma_200=100.5,
        ema_200=100.0,
    )
    alerts = check_touch_alerts(indicators, 100.0, 0.008)
    assert len(alerts) == 1
    assert alerts[0][0] == AlertType.TOUCH_200_MA


def test_cluster_spread_ratio() -> None:
    indicators = Indicators(
        ma_20=100.0,
        ema_20=101.0,
        ma_60=100.5,
        ema_60=100.5,
        ma_120=100.2,
        ema_120=100.8,
        ma_200=90.0,
        ema_200=90.0,
    )
    ratio = cluster_spread_ratio(indicators, 100.0)
    assert ratio == pytest.approx(0.01)


def test_interval_support_flags() -> None:
    assert supports_cluster("4h") is True
    assert supports_cluster("1d") is True
    assert supports_cluster("1wk") is True
    assert supports_touch("4h") is False
    assert supports_touch("1d") is True
    assert supports_touch("1wk") is True

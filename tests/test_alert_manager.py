"""Tests for alert cooldown and deduplication."""

from datetime import UTC, datetime

from app.schemas.alert import AlertEvent, AlertType
from app.services.alert_manager import AlertManager


def _event(alert_type: AlertType = AlertType.CLUSTER) -> AlertEvent:
    return AlertEvent(
        symbol="BTC/USDT",
        interval="4h",
        alert_type=alert_type,
        price=100.0,
        detail="test",
        triggered_at=datetime.now(tz=UTC),
    )


def test_cooldown_suppresses_duplicate_alerts() -> None:
    manager = AlertManager(cooldown_seconds=3600, dedupe_window_seconds=60)
    event = _event()
    assert manager.should_send(event, now=1000.0) is True
    manager.record_sent(event, now=1000.0)
    assert manager.should_send(event, now=2000.0) is False


def test_alert_re_triggers_after_cooldown_expires() -> None:
    manager = AlertManager(cooldown_seconds=3600, dedupe_window_seconds=60)
    event = _event()
    manager.record_sent(event, now=1000.0)
    assert manager.should_send(event, now=5000.0) is True


def test_dedupe_window_blocks_rapid_alerts() -> None:
    manager = AlertManager(cooldown_seconds=0, dedupe_window_seconds=60)
    event = _event()
    manager.record_sent(event, now=1000.0)
    assert manager.should_send(event, now=1030.0) is False
    assert manager.should_send(event, now=1070.0) is True


def test_different_alert_types_are_independent() -> None:
    manager = AlertManager(cooldown_seconds=3600, dedupe_window_seconds=60)
    cluster = _event(AlertType.CLUSTER)
    touch = _event(AlertType.TOUCH_200_MA)
    manager.record_sent(cluster, now=1000.0)
    assert manager.should_send(touch, now=1001.0) is True

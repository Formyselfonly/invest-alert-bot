"""Tests for display timestamp formatting."""

from __future__ import annotations

from datetime import UTC, datetime

from app.notifiers.telegram import format_alert_message
from app.schemas.alert import AlertEvent, AlertType
from app.services.status_format import format_display_timestamp


def test_format_display_timestamp_utc() -> None:
    dt = datetime(2026, 6, 18, 8, 30, tzinfo=UTC)
    assert format_display_timestamp(dt) == "2026-06-18 08:30 UTC"


def test_format_alert_message_includes_time_in_brackets() -> None:
    event = AlertEvent(
        symbol="MSFT",
        interval="1d",
        alert_type=AlertType.TOUCH_200_MA,
        price=378.91,
        detail="距 200MA 0.85% (阈值 1.2%) · 价格在200MA 下方",
        triggered_at=datetime(2026, 6, 18, 8, 30, tzinfo=UTC),
    )
    message = format_alert_message(event)
    assert "【200MA 触碰-抄底机会 · 2026-06-18 08:30 UTC】" in message
    assert "MSFT" in message
    assert message.count("2026-06-18 08:30 UTC") == 1

"""Alert cooldown and deduplication."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from app.schemas.alert import AlertEvent, AlertType


@dataclass
class AlertManager:
    cooldown_seconds: int
    dedupe_window_seconds: int
    _last_sent_at: dict[tuple[str, str, AlertType], float] = field(
        default_factory=dict,
    )
    _pending_dedupe: dict[tuple[str, str, AlertType], float] = field(
        default_factory=dict,
    )

    def should_send(self, event: AlertEvent, now: float | None = None) -> bool:
        ts = now if now is not None else time.time()
        key = event.key
        last = self._last_sent_at.get(key)
        if last is not None and ts - last < self.cooldown_seconds:
            return False

        pending = self._pending_dedupe.get(key)
        if pending is not None and ts - pending < self.dedupe_window_seconds:
            return False

        return True

    def record_sent(self, event: AlertEvent, now: float | None = None) -> None:
        ts = now if now is not None else time.time()
        key = event.key
        self._last_sent_at[key] = ts
        self._pending_dedupe[key] = ts

    def reset(self) -> None:
        self._last_sent_at.clear()
        self._pending_dedupe.clear()

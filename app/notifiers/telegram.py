"""Format and send Telegram alert messages."""

from __future__ import annotations

import logging

from telegram import Bot
from telegram.error import TelegramError

from app.schemas.alert import AlertEvent, AlertType
from app.schemas.config import TelegramConfig

logger = logging.getLogger(__name__)

INTERVAL_LABELS = {
    "4h": "4H",
    "1d": "1D",
    "1w": "1W",
    "1wk": "1W",
}

ALERT_HEADERS = {
    AlertType.CLUSTER: "📊 【均线密集】",
    AlertType.TOUCH_200_MA: "🎯 【200MA 触碰】",
}


def format_alert_message(event: AlertEvent) -> str:
    header = ALERT_HEADERS.get(event.alert_type, "🔔 【告警】")
    interval = INTERVAL_LABELS.get(
        event.interval.lower(),
        event.interval.upper(),
    )
    ts = event.triggered_at.strftime("%Y-%m-%d %H:%M UTC")

    return (
        f"{header}\n"
        f"`{event.symbol}` · {interval} · "
        f"${event.price:,.2f}\n"
        f"{event.detail}\n"
        f"_{ts}_"
    )


class TelegramNotifier:
    def __init__(self, config: TelegramConfig) -> None:
        self._bot = Bot(token=config.bot_token)
        self._chat_id = config.chat_id

    async def send_alert(self, event: AlertEvent) -> None:
        message = format_alert_message(event)
        await self._send_with_retry(message)

    async def send_startup_message(
        self,
        symbol_count: int,
        skipped: list[str] | None = None,
    ) -> None:
        message = (
            "✅ *Invest Alert Bot 已启动*\n"
            f"监控 *{symbol_count}* 个组合 · 告警分两类推送\n"
            "📊 均线密集  🎯 200MA 触碰（1D/1W）\n\n"
            "/status 摘要 · /status BTC 详情 · /clear 清屏"
        )
        if skipped:
            message += f"\n\n⚠️ 跳过 {len(skipped)} 项（K线不足 200 根）"
        await self._send_with_retry(message)

    async def send_error_message(self, text: str) -> None:
        message = f"⚠️ *Invest Alert Bot 异常*\n{text}"
        await self._send_with_retry(message)

    async def _send_with_retry(
        self,
        message: str,
        max_attempts: int = 3,
    ) -> None:
        for attempt in range(1, max_attempts + 1):
            try:
                await self._bot.send_message(
                    chat_id=self._chat_id,
                    text=message,
                    parse_mode="Markdown",
                )
                logger.info("Telegram message sent")
                return
            except TelegramError:
                logger.exception(
                    "Telegram send failed (attempt %s/%s)",
                    attempt,
                    max_attempts,
                )
                if attempt == max_attempts:
                    raise

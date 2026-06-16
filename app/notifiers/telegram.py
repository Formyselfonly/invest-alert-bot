"""Format and send Telegram alert messages."""

from __future__ import annotations

import logging

from telegram import Bot
from telegram.error import TelegramError

from app.schemas.alert import ALERT_TYPE_LABELS, AlertEvent, AlertType
from app.schemas.config import TelegramConfig

logger = logging.getLogger(__name__)

INTERVAL_LABELS = {
    "4h": "4H",
    "1d": "1D",
    "1w": "1W",
    "1wk": "1W",
}

ALERT_EMOJI = {
    AlertType.CLUSTER: "📊",
    AlertType.TOUCH_200_MA: "🎯",
    AlertType.TOUCH_200_EMA: "🎯",
}


def format_alert_message(event: AlertEvent) -> str:
    label = ALERT_TYPE_LABELS[event.alert_type]
    emoji = ALERT_EMOJI.get(event.alert_type, "🔔")
    interval = INTERVAL_LABELS.get(
        event.interval.lower(),
        event.interval.upper(),
    )
    ts = event.triggered_at.strftime("%Y-%m-%d %H:%M:%S UTC")

    return (
        f"{emoji} *Invest Alert Bot*\n"
        f"━━━━━━━━━━━━━━━\n"
        f"*告警类型*: {label}\n"
        f"*资产*: `{event.symbol}`\n"
        f"*周期*: {interval}\n"
        f"*当前价*: `${event.price:,.4f}`\n"
        f"*详情*: {event.detail}\n"
        f"*时间*: {ts}"
    )


class TelegramNotifier:
    def __init__(self, config: TelegramConfig) -> None:
        self._bot = Bot(token=config.bot_token)
        self._chat_id = config.chat_id

    async def send_alert(self, event: AlertEvent) -> None:
        message = format_alert_message(event)
        await self._send_with_retry(message)

    async def send_startup_message(self, symbol_count: int) -> None:
        message = (
            "✅ *Invest Alert Bot 已启动*\n"
            f"正在监控 *{symbol_count}* 个标的 × 周期组合\n"
            "触碰条件时将即时推送告警。\n\n"
            "发送 /status 查看状态，/help 查看帮助。"
        )
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

"""Format and send Telegram alert messages.
Author: Shijie Zheng (Kerry Zheng) — https://github.com/Formyselfonly
Repository: https://github.com/Formyselfonly/invest-alert-bot
"""

from __future__ import annotations

import logging
from pathlib import Path

from telegram import Bot
from telegram.error import TelegramError

from app.schemas.alert import AlertEvent, AlertType
from app.schemas.config import TelegramConfig
from app.services.status_format import format_display_timestamp

logger = logging.getLogger(__name__)

INTERVAL_LABELS = {
    "4h": "4H",
    "1d": "1D",
    "1w": "1W",
    "1wk": "1W",
}

ALERT_LABELS: dict[AlertType, tuple[str, str]] = {
    AlertType.CLUSTER: ("📊", "均线密集-开仓机会"),
    AlertType.TOUCH_200_MA: ("🎯", "200MA 触碰-抄底机会"),
}


def format_alert_message(event: AlertEvent) -> str:
    emoji, label = ALERT_LABELS.get(event.alert_type, ("🔔", "告警"))
    ts = format_display_timestamp(event.triggered_at)
    header = f"{emoji} 【{label} · {ts}】"
    interval = INTERVAL_LABELS.get(
        event.interval.lower(),
        event.interval.upper(),
    )

    return (
        f"{header}\n"
        f"`{event.symbol}` · {interval} · "
        f"${event.price:,.2f}\n"
        f"{event.detail}"
    )


class TelegramNotifier:
    def __init__(self, config: TelegramConfig) -> None:
        self._bot = Bot(token=config.bot_token)
        self._chat_id = config.chat_id

    async def send_alert(self, event: AlertEvent) -> None:
        message = format_alert_message(event)
        await self._send_with_retry(message)

    async def send_text(self, message: str) -> None:
        await self._send_with_retry(message)

    async def send_analysis_report(
        self,
        summary: str,
        html_path: Path,
    ) -> None:
        await self._send_with_retry(summary)
        with html_path.open("rb") as report_file:
            await self._bot.send_document(
                chat_id=self._chat_id,
                document=report_file,
                filename=html_path.name,
                caption="📄 完整 AI 分析报告（HTML）",
            )
        logger.info("Telegram analysis report sent: %s", html_path.name)

    async def send_startup_message(
        self,
        symbol_count: int,
        skipped: list[str] | None = None,
        analysis_status: str | None = None,
    ) -> None:
        message = (
            "✅ *Invest Alert Bot 已启动*\n"
            f"监控 *{symbol_count}* 个组合 · 告警分两类推送\n"
            "📊 均线密集-开仓机会  🎯 200MA 触碰-抄底机会\n"
            "告警后将自动触发 AI 分析（若已启用）\n\n"
            "/status 摘要 · /status BTC · /analyze MSFT · /clear 清屏"
        )
        if analysis_status:
            message += f"\n\n🧠 AI 分析：{analysis_status}"
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

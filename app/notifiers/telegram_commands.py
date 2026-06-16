"""Interactive Telegram command handlers with menu & buttons."""

from __future__ import annotations

import logging
from collections.abc import Callable

from telegram import BotCommand, KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.error import TelegramError
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from app.schemas.config import TelegramConfig

logger = logging.getLogger(__name__)

StatusProvider = Callable[[str | None], str]

MAX_TRACKED_MESSAGES = 100

WELCOME = (
    "👋 *Invest Alert Bot*\n\n"
    "告警分两类推送：\n"
    "📊 均线密集\n"
    "🎯 200MA / 200EMA 触碰\n\n"
    "/status — 全部监控状态\n"
    "/status BTC — 单标的\n"
    "/clear — 清屏"
)

HELP = (
    "*Invest Alert Bot 帮助*\n\n"
    "*告警（分两条线推送）*\n"
    "📊 均线密集 — 六线 spread ≤ 0.8%\n"
    "🎯 200MA/EMA — 距离 ≤ 0.8%\n\n"
    "*命令*\n"
    "/status — 展示全部标的 × 周期\n"
    "/status BTC — 只看单个标的\n"
    "/clear — 清屏\n"
    "/help — 本说明"
)

BOT_COMMANDS = [
    BotCommand("start", "开始使用"),
    BotCommand("status", "全部监控状态"),
    BotCommand("clear", "清屏"),
    BotCommand("help", "帮助说明"),
]

BTN_STATUS = "📡 全部状态"
BTN_HELP = "❓ 帮助"
BTN_CLEAR = "🧹 清屏"


class TelegramCommandBot:
    """Long-polling command listener alongside alert pushes."""

    def __init__(
        self,
        config: TelegramConfig,
        status_provider: StatusProvider,
    ) -> None:
        self._chat_id = int(config.chat_id)
        self._status_provider = status_provider
        self._tracked_message_ids: list[int] = []
        self._application = (
            Application.builder()
            .token(config.bot_token)
            .build()
        )
        self._application.add_handler(
            CommandHandler("start", self._cmd_start),
        )
        self._application.add_handler(
            CommandHandler("help", self._cmd_help),
        )
        self._application.add_handler(
            CommandHandler("status", self._cmd_status),
        )
        self._application.add_handler(
            CommandHandler("clear", self._cmd_clear),
        )
        btn_pattern = f"^({BTN_STATUS}|{BTN_HELP}|{BTN_CLEAR})$"
        self._application.add_handler(
            MessageHandler(filters.Regex(btn_pattern), self._on_button_text),
        )

    @staticmethod
    def _reply_keyboard() -> ReplyKeyboardMarkup:
        return ReplyKeyboardMarkup(
            [
                [KeyboardButton(BTN_STATUS), KeyboardButton(BTN_CLEAR)],
                [KeyboardButton(BTN_HELP)],
            ],
            resize_keyboard=True,
            is_persistent=True,
            input_field_placeholder="/status 或 /status BTC",
        )

    def _authorized(self, update: Update) -> bool:
        chat = update.effective_chat
        if chat is None:
            return False
        if chat.id != self._chat_id:
            logger.warning(
                "Ignored message from unauthorized chat %s",
                chat.id,
            )
            return False
        return True

    def _track_message(self, message_id: int) -> None:
        self._tracked_message_ids.append(message_id)
        if len(self._tracked_message_ids) > MAX_TRACKED_MESSAGES:
            self._tracked_message_ids.pop(0)

    async def _register_commands(self) -> None:
        await self._application.bot.set_my_commands(BOT_COMMANDS)
        logger.info("Telegram bot command menu registered")

    async def _cmd_start(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        if not self._authorized(update) or update.message is None:
            return
        sent = await update.message.reply_text(
            WELCOME,
            parse_mode="Markdown",
            reply_markup=self._reply_keyboard(),
        )
        self._track_message(sent.message_id)

    async def _cmd_help(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        if not self._authorized(update) or update.message is None:
            return
        await self._send_help(update.message)

    async def _cmd_status(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        if not self._authorized(update) or update.message is None:
            return
        symbol = " ".join(context.args) if context.args else None
        await self._send_status(update.message, symbol)

    async def _cmd_clear(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        if not self._authorized(update):
            return
        await self._clear_screen(context, update.message)

    async def _on_button_text(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        if not self._authorized(update) or update.message is None:
            return
        text = update.message.text or ""
        if text == BTN_STATUS:
            await self._send_status(update.message, None)
        elif text == BTN_HELP:
            await self._send_help(update.message)
        elif text == BTN_CLEAR:
            await self._clear_screen(context, update.message)

    async def _send_status(
        self,
        message,
        symbol_query: str | None,
    ) -> None:
        body = self._status_provider(symbol_query)
        sent = await message.reply_text(
            body,
            parse_mode="Markdown",
            reply_markup=self._reply_keyboard(),
        )
        self._track_message(sent.message_id)

    async def _send_help(self, message) -> None:
        sent = await message.reply_text(
            HELP,
            parse_mode="Markdown",
            reply_markup=self._reply_keyboard(),
        )
        self._track_message(sent.message_id)

    async def _clear_screen(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        trigger_message,
    ) -> None:
        deleted = 0
        bot = context.bot
        for message_id in list(self._tracked_message_ids):
            try:
                await bot.delete_message(
                    chat_id=self._chat_id,
                    message_id=message_id,
                )
                deleted += 1
            except TelegramError:
                pass
        self._tracked_message_ids.clear()

        if trigger_message is not None:
            try:
                await trigger_message.delete()
            except TelegramError:
                pass

        logger.info("Chat cleared: %s bot messages deleted", deleted)

        if deleted == 0:
            notice = await bot.send_message(
                chat_id=self._chat_id,
                text="暂无可清理的 Bot 消息（告警推送不会删除）",
            )
            self._track_message(notice.message_id)

    async def start(self) -> None:
        await self._application.initialize()
        await self._application.start()
        await self._register_commands()
        await self._application.updater.start_polling(
            drop_pending_updates=True,
        )
        logger.info("Telegram command bot polling started")

    async def stop(self) -> None:
        if self._application.updater.running:
            await self._application.updater.stop()
        await self._application.stop()
        await self._application.shutdown()
        logger.info("Telegram command bot stopped")

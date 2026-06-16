"""Interactive Telegram command handlers with menu & buttons."""

from __future__ import annotations

import logging
from collections.abc import Callable

from telegram import (
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    Update,
)
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from app.schemas.config import TelegramConfig

logger = logging.getLogger(__name__)

StatusProvider = Callable[[], str]

WELCOME = (
    "👋 *Invest Alert Bot*\n\n"
    "我会监控均线密集 & 200MA/EMA 触碰，条件满足时主动推送告警。\n\n"
    "👇 用下方按钮，或输入 `/` 选择命令\n\n"
    "告警周期：4H / 1D / 1W\n"
    "阈值：密集 & 触碰均为 0.8%"
)

HELP = (
    "*Invest Alert Bot 帮助*\n\n"
    "运行：`uv run python -m app.main`\n\n"
    "*告警类型*\n"
    "• 均线密集：六线 spread ≤ 0.8%\n"
    "• 200MA/EMA 触碰：距离 ≤ 0.8%\n\n"
    "*周期*：4H、1D、1W\n\n"
    "*命令*\n"
    "/start — 欢迎 & 菜单\n"
    "/status — 监控状态\n"
    "/help — 本说明"
)

BOT_COMMANDS = [
    BotCommand("start", "开始使用，显示菜单"),
    BotCommand("status", "查看监控状态与价格"),
    BotCommand("help", "帮助说明"),
]

BTN_STATUS = "📡 监控状态"
BTN_HELP = "❓ 帮助"
BTN_MENU = "🏠 主菜单"


class TelegramCommandBot:
    """Long-polling command listener alongside alert pushes."""

    def __init__(
        self,
        config: TelegramConfig,
        status_provider: StatusProvider,
    ) -> None:
        self._chat_id = int(config.chat_id)
        self._status_provider = status_provider
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
            CallbackQueryHandler(self._on_callback),
        )
        self._application.add_handler(
            MessageHandler(
                filters.Regex(f"^({BTN_STATUS}|{BTN_HELP}|{BTN_MENU})$"),
                self._on_button_text,
            ),
        )

    @staticmethod
    def _reply_keyboard() -> ReplyKeyboardMarkup:
        return ReplyKeyboardMarkup(
            [
                [KeyboardButton(BTN_STATUS), KeyboardButton(BTN_HELP)],
                [KeyboardButton(BTN_MENU)],
            ],
            resize_keyboard=True,
            is_persistent=True,
            input_field_placeholder="点按钮，或输入 / 查看命令",
        )

    @staticmethod
    def _inline_keyboard() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        BTN_STATUS,
                        callback_data="status",
                    ),
                    InlineKeyboardButton(
                        BTN_HELP,
                        callback_data="help",
                    ),
                ],
            ],
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
        await update.message.reply_text(
            WELCOME,
            parse_mode="Markdown",
            reply_markup=self._reply_keyboard(),
        )
        await update.message.reply_text(
            "快捷操作：",
            reply_markup=self._inline_keyboard(),
        )

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
        await self._send_status(update.message)

    async def _on_button_text(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        if not self._authorized(update) or update.message is None:
            return
        text = update.message.text or ""
        if text == BTN_STATUS:
            await self._send_status(update.message)
        elif text == BTN_HELP:
            await self._send_help(update.message)
        elif text == BTN_MENU:
            await self._cmd_start(update, context)

    async def _on_callback(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        query = update.callback_query
        if query is None:
            return
        await query.answer()
        if not self._authorized(update):
            return
        if query.message is None:
            return
        if query.data == "status":
            await self._send_status(query.message)
        elif query.data == "help":
            await self._send_help(query.message)

    async def _send_status(self, message) -> None:
        body = self._status_provider()
        await message.reply_text(
            f"📡 *监控状态*\n\n{body}",
            parse_mode="Markdown",
            reply_markup=self._reply_keyboard(),
        )

    async def _send_help(self, message) -> None:
        await message.reply_text(
            HELP,
            parse_mode="Markdown",
            reply_markup=self._reply_keyboard(),
        )

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

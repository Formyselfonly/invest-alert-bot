"""Invest Alert Bot entry point."""

from __future__ import annotations

import asyncio
import logging
import signal

from app.core.config import (
    get_config_path,
    load_config,
    validate_telegram_credentials,
)
from app.core.logging import setup_logging
from app.notifiers.telegram import TelegramNotifier
from app.notifiers.telegram_commands import TelegramCommandBot
from app.services.coordinator import Coordinator

logger = logging.getLogger(__name__)


async def run() -> None:
    config = load_config(get_config_path())
    validate_telegram_credentials(config)
    setup_logging(config.logging)

    notifier = TelegramNotifier(config.telegram)
    coordinator = Coordinator(config, notifier)
    command_bot = TelegramCommandBot(
        config.telegram,
        status_provider=coordinator.format_status,
    )

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def _request_shutdown() -> None:
        logger.info("Shutdown signal received")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _request_shutdown)

    await command_bot.start()
    await coordinator.start()

    try:
        await stop_event.wait()
    finally:
        await coordinator.stop()
        await command_bot.stop()
        logger.info("Invest Alert Bot stopped")


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()

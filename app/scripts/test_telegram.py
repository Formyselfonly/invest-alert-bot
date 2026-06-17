"""Send a test message to verify Telegram credentials.
Author: Shijie Zheng (Kerry Zheng) — https://github.com/Formyselfonly
Repository: https://github.com/Formyselfonly/invest-alert-bot
"""

from __future__ import annotations

import asyncio
import sys

from app.core.config import (
    get_config_path,
    load_config,
    validate_telegram_credentials,
)
from app.notifiers.telegram import TelegramNotifier


async def main() -> None:
    try:
        config = load_config(get_config_path())
        validate_telegram_credentials(config)
    except (FileNotFoundError, ValueError) as exc:
        print(f"配置错误: {exc}")
        sys.exit(1)

    notifier = TelegramNotifier(config.telegram)
    await notifier._send_with_retry(
        "🧪 *Invest Alert Bot 测试消息*\n\n"
        "Telegram 配置正确，可以收到告警了。\n"
        "（本 Bot 不会回复 /start，只会主动推送告警）",
    )
    print("测试消息已发送，请查看 Telegram。")


if __name__ == "__main__":
    asyncio.run(main())

"""Discover Telegram Chat ID via Bot API getUpdates.
Author: Shijie Zheng (Kerry Zheng) — https://github.com/Formyselfonly
Repository: https://github.com/Formyselfonly/invest-alert-bot
"""

from __future__ import annotations

import asyncio
import os
import sys

import httpx
from dotenv import load_dotenv


async def main() -> None:
    load_dotenv()
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token or token.startswith("your_"):
        print("❌ .env 里 TELEGRAM_BOT_TOKEN 未配置")
        sys.exit(1)

    base = f"https://api.telegram.org/bot{token}"
    async with httpx.AsyncClient(timeout=30) as client:
        me = await client.get(f"{base}/getMe")
        me_data = me.json()
        if not me_data.get("ok"):
            print(f"❌ Token 无效: {me_data}")
            sys.exit(1)
        bot = me_data["result"]
        print(f"✅ Bot 有效: @{bot['username']} ({bot['first_name']})")

        wh = await client.get(f"{base}/getWebhookInfo")
        wh_url = wh.json().get("result", {}).get("url", "")
        if wh_url:
            print(f"⚠️  检测到 webhook: {wh_url}，正在清除…")
            await client.get(f"{base}/deleteWebhook")

        print()
        print("请在 Telegram 打开这个 Bot，发送任意消息（如 /start 或 hi）")
        print(f"   → 搜索 @{bot['username']} 并发送")
        print()
        input("发完后按 Enter 继续…")

        updates = await client.get(f"{base}/getUpdates")
        data = updates.json()
        if not data.get("ok"):
            print(f"❌ getUpdates 失败: {data}")
            sys.exit(1)

        results = data.get("result", [])
        if not results:
            print("❌ 仍然没有消息。请确认：")
            print(f"   1. 消息是发给 @{bot['username']} 的")
            print("   2. Token 和 Bot 是同一个")
            print()
            print("备选方案：Telegram 搜索 @userinfobot → Start → 复制 Id")
            sys.exit(1)

        seen: set[int] = set()
        print("✅ 找到以下 Chat ID：")
        for item in results:
            msg = item.get("message") or item.get("edited_message")
            if not msg:
                continue
            chat = msg["chat"]
            chat_id = chat["id"]
            if chat_id in seen:
                continue
            seen.add(chat_id)
            name = chat.get("first_name") or chat.get("title", "")
            ctype = chat.get("type", "")
            print(f"   TELEGRAM_CHAT_ID={chat_id}  ({name}, {ctype})")

        print()
        print("把上面数字写入 .env，然后运行：")
        print("   uv run python -m app.scripts.test_telegram")


if __name__ == "__main__":
    asyncio.run(main())

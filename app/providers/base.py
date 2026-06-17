"""Invest Alert Bot module.

Author: Shijie Zheng (Kerry Zheng) — https://github.com/Formyselfonly
Repository: https://github.com/Formyselfonly/invest-alert-bot
"""

from collections.abc import Awaitable, Callable
from typing import Protocol

from app.schemas.market import Kline, Tick

TickCallback = Callable[[Tick], Awaitable[None]]
KlineCallback = Callable[[str, str, Kline], Awaitable[None]]


class MarketDataProvider(Protocol):
    async def fetch_history(
        self,
        symbol: str,
        interval: str,
        limit: int = 250,
    ) -> list[Kline]: ...

    async def start(self) -> None: ...

    async def stop(self) -> None: ...

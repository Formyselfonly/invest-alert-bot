"""Binance WebSocket manager for aggTrade and kline streams."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

import websockets
from websockets.asyncio.client import ClientConnection

from app.providers.binance_rest import to_binance_symbol
from app.schemas.market import Kline, Tick
from app.services.engine import normalize_interval

logger = logging.getLogger(__name__)

WS_BASES = {
    "spot": "wss://stream.binance.com:9443/stream",
    "futures": "wss://fstream.binance.com/stream",
}
MAX_BACKOFF = 60

TickHandler = Callable[[Tick], Awaitable[None]]
KlineHandler = Callable[[str, str, Kline], Awaitable[None]]


class BinanceWebSocketManager:
    def __init__(
        self,
        symbols: list[str],
        intervals: list[str],
        on_tick: TickHandler,
        on_kline: KlineHandler,
        market: str = "spot",
    ) -> None:
        self._symbols = symbols
        self._intervals = intervals
        self._on_tick = on_tick
        self._on_kline = on_kline
        self._market = market
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._ws: ClientConnection | None = None

    def _build_streams(self) -> str:
        streams: list[str] = []
        for symbol in self._symbols:
            sym = to_binance_symbol(symbol).lower()
            streams.append(f"{sym}@aggTrade")
            for interval in self._intervals:
                binance_iv = normalize_interval(interval)
                streams.append(f"{sym}@kline_{binance_iv}")
        return "/".join(streams)

    @property
    def url(self) -> str:
        base = WS_BASES.get(self._market, WS_BASES["spot"])
        return f"{base}?streams={self._build_streams()}"

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_forever())
        logger.info(
            "Binance %s WS started for symbols=%s intervals=%s",
            self._market,
            self._symbols,
            self._intervals,
        )

    async def stop(self) -> None:
        self._running = False
        if self._ws is not None:
            await self._ws.close()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Binance WS stopped")

    async def _run_forever(self) -> None:
        backoff = 1
        while self._running:
            try:
                await self._connect_and_listen()
                backoff = 1
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception(
                    "Binance WS error, reconnecting in %ss",
                    backoff,
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, MAX_BACKOFF)

    async def _connect_and_listen(self) -> None:
        url = self.url
        logger.info("Connecting Binance WS: %s", url)
        async with websockets.connect(url, ping_interval=20) as ws:
            self._ws = ws
            logger.info("Binance WS connected")
            async for message in ws:
                if not self._running:
                    break
                await self._handle_message(message)

    async def _handle_message(self, message: str | bytes) -> None:
        payload = json.loads(message)
        data = payload.get("data", payload)
        event_type = data.get("e")
        if event_type == "aggTrade":
            await self._handle_agg_trade(data)
        elif event_type == "kline":
            await self._handle_kline(data)

    async def _handle_agg_trade(self, data: dict) -> None:
        symbol = data["s"]
        price = float(data["p"])
        ts = datetime.fromtimestamp(data["T"] / 1000, tz=UTC)
        tick = Tick(symbol=symbol, price=price, timestamp=ts)
        await self._on_tick(tick)

    async def _handle_kline(self, data: dict) -> None:
        kline = data["k"]
        symbol = kline["s"]
        interval = kline["i"]
        candle = Kline(
            open_time=datetime.fromtimestamp(kline["t"] / 1000, tz=UTC),
            open=float(kline["o"]),
            high=float(kline["h"]),
            low=float(kline["l"]),
            close=float(kline["c"]),
            volume=float(kline["v"]),
            is_closed=bool(kline["x"]),
        )
        await self._on_kline(symbol, interval, candle)

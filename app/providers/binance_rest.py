"""Binance REST client for historical klines."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import aiohttp

from app.schemas.market import Kline
from app.services.engine import normalize_interval

logger = logging.getLogger(__name__)

BASE_URL = "https://api.binance.com/api/v3/klines"


def to_binance_symbol(symbol: str) -> str:
    return symbol.replace("/", "").upper()


class BinanceRestClient:
    def __init__(self, session: aiohttp.ClientSession | None = None) -> None:
        self._session = session
        self._owns_session = session is None

    async def __aenter__(self) -> BinanceRestClient:
        if self._session is None:
            self._session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, *args: object) -> None:
        if self._owns_session and self._session is not None:
            await self._session.close()

    async def fetch_klines(
        self,
        symbol: str,
        interval: str,
        limit: int = 250,
    ) -> list[Kline]:
        if self._session is None:
            msg = "HTTP session is not initialized"
            raise RuntimeError(msg)

        params = {
            "symbol": to_binance_symbol(symbol),
            "interval": normalize_interval(interval),
            "limit": limit,
        }
        async with self._session.get(BASE_URL, params=params) as resp:
            resp.raise_for_status()
            raw = await resp.json()

        klines: list[Kline] = []
        for item in raw:
            klines.append(
                Kline(
                    open_time=datetime.fromtimestamp(
                        item[0] / 1000,
                        tz=UTC,
                    ),
                    open=float(item[1]),
                    high=float(item[2]),
                    low=float(item[3]),
                    close=float(item[4]),
                    volume=float(item[5]),
                    is_closed=True,
                ),
            )
        logger.debug(
            "Fetched %s klines for %s %s",
            len(klines),
            symbol,
            interval,
        )
        return klines

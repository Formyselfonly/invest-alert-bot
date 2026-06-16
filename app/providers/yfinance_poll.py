"""Equity OHLCV via Yahoo Finance (NASDAQ / NYSE listed symbols)."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

import pandas as pd
import yfinance as yf

from app.schemas.market import Kline
from app.services.engine import normalize_interval

logger = logging.getLogger(__name__)

KlineUpdateHandler = Callable[
    [str, str, list[Kline], float],
    Awaitable[None],
]

YF_INTERVAL_MAP = {
    "4h": "1h",
    "1d": "1d",
    "1w": "1wk",
    "1wk": "1wk",
}


def _clean_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """Drop incomplete bars (Yahoo often appends NaN Close for open sessions)."""
    required = ["Open", "High", "Low", "Close"]
    cleaned = df.dropna(subset=required)
    return cleaned.loc[cleaned["Close"] > 0]


def _fetch_live_price(ticker: yf.Ticker, fallback: float) -> float:
    try:
        fast = ticker.fast_info
        for key in ("lastPrice", "regularMarketPrice"):
            raw = fast.get(key) if hasattr(fast, "get") else None
            if raw is not None:
                price = float(raw)
                if price > 0:
                    return price
    except Exception:
        logger.debug("Live price unavailable for %s", ticker.ticker)
    return fallback


def _resample_to_interval(df: pd.DataFrame, interval: str) -> pd.DataFrame:
    normalized = normalize_interval(interval)
    if normalized == "4h":
        return df.resample("4h").agg(
            {
                "Open": "first",
                "High": "max",
                "Low": "min",
                "Close": "last",
                "Volume": "sum",
            },
        ).dropna()
    # 1wk 已用 yfinance 原生周线，无需再 resample
    return df


def _yf_period(interval: str) -> str:
    normalized = normalize_interval(interval)
    if normalized == "4h":
        return "730d"   # 足够聚合出 200+ 根 4H K 线
    if normalized in {"1w", "1wk"}:
        return "max"    # 周线需 200+ 周历史（200MA）
    return "1y"


class YahooFinancePoller:
    def __init__(
        self,
        symbol: str,
        yf_ticker: str,
        interval: str,
        poll_seconds: int,
        on_update: KlineUpdateHandler,
    ) -> None:
        self.symbol = symbol
        self._yf_ticker = yf_ticker
        self.interval = interval
        self.poll_seconds = poll_seconds
        self._on_update = on_update
        self._running = False
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._poll_loop())
        logger.info(
            "Equity poller started: %s %s every %ss",
            self.symbol,
            self.interval,
            self.poll_seconds,
        )

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    def fetch_history(self, limit: int = 250) -> list[Kline]:
        yf_interval = YF_INTERVAL_MAP.get(
            self.interval.lower(),
            normalize_interval(self.interval),
        )
        period = _yf_period(self.interval)
        ticker = yf.Ticker(self._yf_ticker)
        df = ticker.history(period=period, interval=yf_interval)
        if df.empty:
            return []

        df = _clean_ohlcv(df)

        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC")
        else:
            df.index = df.index.tz_convert("UTC")

        df = _resample_to_interval(df, self.interval)
        df = _clean_ohlcv(df)
        df = df.tail(limit)

        klines: list[Kline] = []
        for ts, row in df.iterrows():
            klines.append(
                Kline(
                    open_time=ts.to_pydatetime(),
                    open=float(row["Open"]),
                    high=float(row["High"]),
                    low=float(row["Low"]),
                    close=float(row["Close"]),
                    volume=float(row.get("Volume", 0.0)),
                    is_closed=True,
                ),
            )
        return klines

    async def _poll_loop(self) -> None:
        while self._running:
            try:
                klines = await asyncio.to_thread(self.fetch_history, 250)
                if klines:
                    ticker = yf.Ticker(self._yf_ticker)
                    price = await asyncio.to_thread(
                        _fetch_live_price,
                        ticker,
                        klines[-1].close,
                    )
                    await self._on_update(
                        self.symbol,
                        self.interval,
                        klines,
                        price,
                    )
            except Exception:
                logger.exception(
                    "Yahoo Finance poll failed for %s %s",
                    self.symbol,
                    self.interval,
                )
            await asyncio.sleep(self.poll_seconds)

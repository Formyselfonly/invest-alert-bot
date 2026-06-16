"""Orchestrate data providers, monitors, and alert delivery."""

from __future__ import annotations

import asyncio
import logging

import aiohttp

from app.notifiers.telegram import TelegramNotifier
from app.providers.binance_rest import BinanceRestClient, to_binance_symbol
from app.providers.binance_ws import BinanceWebSocketManager
from app.providers.yfinance_poll import YahooFinancePoller
from app.schemas.alert import AlertEvent
from app.schemas.config import AppConfig, SymbolConfig
from app.schemas.market import DataSource, Kline, Tick
from app.services.alert_manager import AlertManager
from app.services.engine import normalize_interval
from app.services.symbol_monitor import INTERVAL_ORDER, SymbolMonitor

logger = logging.getLogger(__name__)


class Coordinator:
    def __init__(self, config: AppConfig, notifier: TelegramNotifier) -> None:
        self._config = config
        self._notifier = notifier
        self._alert_manager = AlertManager(
            cooldown_seconds=config.alert.cooldown_seconds,
            dedupe_window_seconds=config.alert.dedupe_window_seconds,
        )
        self._monitors: dict[tuple[str, str], SymbolMonitor] = {}
        self._binance_symbol_map: dict[str, str] = {}
        self._ws_manager: BinanceWebSocketManager | None = None
        self._yf_pollers: list[YahooFinancePoller] = []
        self._session: aiohttp.ClientSession | None = None

    @property
    def monitor_count(self) -> int:
        return len(self._monitors)

    def format_status(self) -> str:
        if not self._monitors:
            return "暂无监控任务"

        lines = [
            f"监控组合：*{self.monitor_count}* 个",
            f"冷却：{self._config.alert.cooldown_seconds}s",
            "",
            "_各周期独立均线；现价为实时价，用于触碰判定_",
            "",
        ]

        by_symbol: dict[str, list[tuple[str, SymbolMonitor]]] = {}
        for (symbol, interval), monitor in self._monitors.items():
            by_symbol.setdefault(symbol, []).append((interval, monitor))

        for symbol in sorted(by_symbol):
            monitors = by_symbol[symbol]
            monitors.sort(
                key=lambda x: INTERVAL_ORDER.get(x[0].lower(), 99),
            )
            spot = monitors[0][1].current_price
            spot_text = (
                f"${spot:,.2f}" if spot > 0 else "—"
            )
            lines.append(f"*{symbol}*  现价 {spot_text}")
            for _interval, monitor in monitors:
                lines.append(monitor.format_status_line())
            lines.append("")

        return "\n".join(lines).rstrip()

    async def start(self) -> None:
        self._session = aiohttp.ClientSession()
        await self._bootstrap_monitors()
        await self._start_binance_streams()
        await self._start_yfinance_pollers()
        await self._notifier.send_startup_message(self.monitor_count)
        logger.info("Coordinator started with %s monitors", self.monitor_count)

    async def stop(self) -> None:
        if self._ws_manager is not None:
            await self._ws_manager.stop()
        for poller in self._yf_pollers:
            await poller.stop()
        if self._session is not None:
            await self._session.close()
        logger.info("Coordinator stopped")

    async def _bootstrap_monitors(self) -> None:
        rest = BinanceRestClient(self._session)
        for symbol_cfg in self._config.symbols:
            for interval in symbol_cfg.intervals:
                monitor = SymbolMonitor(
                    symbol=symbol_cfg.symbol,
                    interval=interval,
                    cluster_threshold=self._config.thresholds.cluster,
                    touch_threshold=self._config.thresholds.touch,
                    alert_manager=self._alert_manager,
                    on_alert=self._handle_alert,
                )
                klines = await self._fetch_history(
                    rest,
                    symbol_cfg,
                    interval,
                )
                monitor.initialize(klines)
                key = (symbol_cfg.symbol, interval)
                self._monitors[key] = monitor

                if symbol_cfg.source == DataSource.BINANCE:
                    self._binance_symbol_map[
                        to_binance_symbol(symbol_cfg.symbol)
                    ] = symbol_cfg.symbol

    async def _fetch_history(
        self,
        rest: BinanceRestClient,
        symbol_cfg: SymbolConfig,
        interval: str,
    ) -> list[Kline]:
        if symbol_cfg.source == DataSource.BINANCE:
            return await rest.fetch_klines(symbol_cfg.symbol, interval)
        poller = YahooFinancePoller(
            symbol=symbol_cfg.symbol,
            interval=interval,
            poll_seconds=self._config.polling.yfinance_interval_seconds,
            on_update=self._handle_yfinance_update,
        )
        return await asyncio.to_thread(poller.fetch_history, 250)

    async def _start_binance_streams(self) -> None:
        binance_symbols = [
            cfg.symbol
            for cfg in self._config.symbols
            if cfg.source == DataSource.BINANCE
        ]
        if not binance_symbols:
            return

        intervals = sorted(
            {
                normalize_interval(iv)
                for cfg in self._config.symbols
                if cfg.source == DataSource.BINANCE
                for iv in cfg.intervals
            },
        )
        unique_symbols = sorted(set(binance_symbols))

        self._ws_manager = BinanceWebSocketManager(
            symbols=unique_symbols,
            intervals=intervals,
            on_tick=self._handle_binance_tick,
            on_kline=self._handle_binance_kline,
        )
        await self._ws_manager.start()

    async def _start_yfinance_pollers(self) -> None:
        for symbol_cfg in self._config.symbols:
            if symbol_cfg.source != DataSource.YFINANCE:
                continue
            for interval in symbol_cfg.intervals:
                poller = YahooFinancePoller(
                    symbol=symbol_cfg.symbol,
                    interval=interval,
                    poll_seconds=self._config.polling.yfinance_interval_seconds,
                    on_update=self._handle_yfinance_update,
                )
                self._yf_pollers.append(poller)
                await poller.start()

    async def _handle_alert(self, event: AlertEvent) -> None:
        try:
            await self._notifier.send_alert(event)
        except Exception:
            logger.exception("Failed to send alert for %s", event.symbol)

    async def _handle_binance_tick(self, tick: Tick) -> None:
        config_symbol = self._binance_symbol_map.get(tick.symbol)
        if config_symbol is None:
            return
        for (symbol, _interval), monitor in self._monitors.items():
            if symbol == config_symbol:
                await monitor.on_price(tick.price)

    def _find_monitor(
        self,
        symbol: str,
        interval: str,
    ) -> SymbolMonitor | None:
        normalized = normalize_interval(interval)
        direct = self._monitors.get((symbol, interval))
        if direct is not None:
            return direct
        for (sym, iv), monitor in self._monitors.items():
            if sym == symbol and normalize_interval(iv) == normalized:
                return monitor
        return None

    async def _handle_binance_kline(
        self,
        raw_symbol: str,
        interval: str,
        kline: Kline,
    ) -> None:
        if not kline.is_closed:
            return
        config_symbol = self._binance_symbol_map.get(raw_symbol)
        if config_symbol is None:
            return
        monitor = self._find_monitor(config_symbol, interval)
        if monitor is None:
            return
        monitor.on_kline_closed(kline)
        await monitor.on_price(monitor.current_price)

    async def _handle_yfinance_update(
        self,
        symbol: str,
        interval: str,
        klines: list[Kline],
        price: float,
    ) -> None:
        monitor = self._monitors.get((symbol, interval))
        if monitor is None:
            return
        monitor.update_klines(klines)
        await monitor.on_price(price)

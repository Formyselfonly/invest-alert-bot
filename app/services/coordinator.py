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
from app.services.engine import normalize_interval, supports_touch
from app.services.status_format import MonitorMetrics, format_pct
from app.services.symbol_monitor import INTERVAL_ORDER, SymbolMonitor

logger = logging.getLogger(__name__)

_EQUITY_SOURCES = frozenset({DataSource.YFINANCE, DataSource.NASDAQ})

STATUS_SYMBOL_SEPARATOR = "─────────────────"


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
        self._ws_managers: list[BinanceWebSocketManager] = []
        self._yf_pollers: list[YahooFinancePoller] = []
        self._session: aiohttp.ClientSession | None = None
        self._skipped_monitors: list[str] = []

    @property
    def monitor_count(self) -> int:
        return len(self._monitors)

    def _configured_total(self) -> int:
        return sum(len(s.intervals) for s in self._config.symbols)

    def _collect_metrics(self) -> list[MonitorMetrics]:
        items: list[MonitorMetrics] = []
        for monitor in self._monitors.values():
            metrics = monitor.get_metrics()
            if metrics is not None:
                items.append(metrics)
        return items

    def _resolve_symbol(self, query: str) -> str | None:
        q = query.strip().upper().replace("/", "")
        configured = {cfg.symbol for cfg in self._config.symbols}
        for symbol in configured:
            key = symbol.upper().replace("/", "")
            if q == key or q == key.replace("USDT", ""):
                return symbol
        return None

    def _active_symbols_in_config_order(self) -> list[str]:
        active = {sym for sym, _ in self._monitors}
        ordered: list[str] = []
        seen: set[str] = set()
        for cfg in self._config.symbols:
            if cfg.symbol in active and cfg.symbol not in seen:
                ordered.append(cfg.symbol)
                seen.add(cfg.symbol)
        return ordered

    def format_status(self, symbol_query: str | None = None) -> str:
        if symbol_query:
            symbol = self._resolve_symbol(symbol_query)
            if symbol is None:
                return f"未找到标的 `{symbol_query}`，试试 `/status BTC`"
            return self._format_symbol_detail(symbol)
        return self._format_full_status()

    def _format_full_status(self) -> str:
        if not self._monitors:
            return "暂无监控任务"

        total = self._configured_total()
        active = len(self._monitors)
        symbols = self._active_symbols_in_config_order()

        lines = [
            f"📡 *监控状态*（{active}/{total} 活跃）",
            "",
        ]
        for index, symbol in enumerate(symbols):
            if index > 0:
                lines.append(STATUS_SYMBOL_SEPARATOR)
            lines.append(self._format_symbol_detail(symbol))

        lines.extend(["", "`/status BTC` 单标的 · `/clear` 清屏"])
        return "\n".join(lines).rstrip()

    def _format_symbol_detail(self, symbol: str) -> str:
        monitors = [
            (iv, mon)
            for (sym, iv), mon in self._monitors.items()
            if sym == symbol
        ]
        if not monitors:
            return f"`{symbol}` 暂无活跃监控（可能 K 线不足被跳过）"

        monitors.sort(key=lambda x: INTERVAL_ORDER.get(x[0].lower(), 99))
        spot = monitors[0][1].current_price
        spot_text = f"${spot:,.2f}" if spot > 0 else "—"

        cluster_lines: list[str] = []
        touch_lines: list[str] = []

        for _iv, monitor in monitors:
            metrics = monitor.get_metrics()
            if metrics is None:
                cluster_lines.append(
                    f"⏳ {monitor.interval}  指标初始化中…",
                )
                continue
            cluster_lines.append(
                f"*{metrics.interval_label}*  "
                f"`{format_pct(metrics.cluster_pct)}`",
            )
            if supports_touch(monitor.interval):
                touch_lines.append(
                    f"*{metrics.interval_label}*  "
                    f"200MA `{format_pct(metrics.touch_ma_pct)}` · "
                    f"价格在200MA *{metrics.touch_ma_side}*",
                )

        lines = [
            f"*{symbol}*  现价 {spot_text}",
            "📊 *均线密集*（20/60/120 MA+EMA）",
            *cluster_lines,
        ]
        if touch_lines:
            lines.extend(["🎯 *200MA 触碰*（1D / 1W）", *touch_lines])
        return "\n".join(lines)

    async def start(self) -> None:
        self._session = aiohttp.ClientSession()
        try:
            await self._bootstrap_monitors()
            await self._start_binance_streams()
            await self._start_equity_pollers()
            await self._notifier.send_startup_message(
                self.monitor_count,
                self._skipped_monitors,
            )
            logger.info(
                "Coordinator started with %s monitors (%s skipped)",
                self.monitor_count,
                len(self._skipped_monitors),
            )
        except Exception:
            await self.stop()
            raise

    async def stop(self) -> None:
        for ws_manager in self._ws_managers:
            await ws_manager.stop()
        for poller in self._yf_pollers:
            await poller.stop()
        if self._session is not None:
            await self._session.close()
        logger.info("Coordinator stopped")

    async def _bootstrap_monitors(self) -> None:
        rest = BinanceRestClient(self._session)
        self._skipped_monitors = []
        for symbol_cfg in self._config.symbols:
            for interval in symbol_cfg.intervals:
                label = f"{symbol_cfg.symbol} {interval}"
                try:
                    klines = await self._fetch_history(
                        rest,
                        symbol_cfg,
                        interval,
                    )
                except Exception:
                    logger.exception("Skip monitor (fetch failed): %s", label)
                    self._skipped_monitors.append(label)
                    continue

                if len(klines) < 200:
                    logger.warning(
                        "Skip monitor (need 200 klines, got %s): %s",
                        len(klines),
                        label,
                    )
                    self._skipped_monitors.append(label)
                    continue

                monitor = SymbolMonitor(
                    symbol=symbol_cfg.symbol,
                    interval=interval,
                    cluster_threshold=self._config.thresholds.cluster,
                    touch_threshold=self._config.thresholds.touch,
                    alert_manager=self._alert_manager,
                    on_alert=self._handle_alert,
                )
                monitor.initialize(klines)
                if monitor.indicators is None:
                    logger.warning("Skip monitor (indicators N/A): %s", label)
                    self._skipped_monitors.append(label)
                    continue

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
            return await rest.fetch_klines(
                symbol_cfg.symbol,
                interval,
                market=symbol_cfg.market,
            )
        if symbol_cfg.source not in _EQUITY_SOURCES:
            raise ValueError(f"Unsupported data source: {symbol_cfg.source}")
        poller = YahooFinancePoller(
            symbol=symbol_cfg.symbol,
            yf_ticker=symbol_cfg.yf_ticker,
            interval=interval,
            poll_seconds=self._config.polling.yfinance_interval_seconds,
            on_update=self._handle_equity_update,
        )
        return await asyncio.to_thread(poller.fetch_history, 250)

    async def _start_binance_streams(self) -> None:
        spot_cfgs = [
            cfg
            for cfg in self._config.symbols
            if cfg.source == DataSource.BINANCE and cfg.market == "spot"
        ]
        futures_cfgs = [
            cfg
            for cfg in self._config.symbols
            if cfg.source == DataSource.BINANCE and cfg.market == "futures"
        ]

        for market, cfgs in (("spot", spot_cfgs), ("futures", futures_cfgs)):
            if not cfgs:
                continue
            symbols = sorted(
                {
                    cfg.symbol
                    for cfg in cfgs
                    if self._has_active_monitor(cfg.symbol)
                },
            )
            if not symbols:
                continue
            intervals = sorted(
                {
                    normalize_interval(iv)
                    for cfg in cfgs
                    for iv in cfg.intervals
                },
            )
            manager = BinanceWebSocketManager(
                symbols=symbols,
                intervals=intervals,
                on_tick=self._handle_binance_tick,
                on_kline=self._handle_binance_kline,
                market=market,
            )
            await manager.start()
            self._ws_managers.append(manager)

    def _has_active_monitor(self, symbol: str) -> bool:
        return any(key[0] == symbol for key in self._monitors)

    async def _start_equity_pollers(self) -> None:
        for symbol_cfg in self._config.symbols:
            if symbol_cfg.source not in _EQUITY_SOURCES:
                continue
            for interval in symbol_cfg.intervals:
                if (symbol_cfg.symbol, interval) not in self._monitors:
                    continue
                poller = YahooFinancePoller(
                    symbol=symbol_cfg.symbol,
                    yf_ticker=symbol_cfg.yf_ticker,
                    interval=interval,
                    poll_seconds=self._config.polling.yfinance_interval_seconds,
                    on_update=self._handle_equity_update,
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

    async def _handle_equity_update(
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

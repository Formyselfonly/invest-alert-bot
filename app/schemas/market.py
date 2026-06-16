from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class DataSource(StrEnum):
    BINANCE = "binance"
    YFINANCE = "yfinance"
    NASDAQ = "nasdaq"  # 纳斯达克上市标的，经 Yahoo Finance 拉 OHLCV


@dataclass(frozen=True)
class Kline:
    open_time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    is_closed: bool = True


@dataclass(frozen=True)
class Tick:
    symbol: str
    price: float
    timestamp: datetime


@dataclass
class Indicators:
    ma_20: float
    ema_20: float
    ma_60: float
    ema_60: float
    ma_120: float
    ema_120: float
    ma_200: float
    ema_200: float

    def cluster_values(self) -> list[float]:
        return [
            self.ma_20,
            self.ema_20,
            self.ma_60,
            self.ema_60,
            self.ma_120,
            self.ema_120,
        ]

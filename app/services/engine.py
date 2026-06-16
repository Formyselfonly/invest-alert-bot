"""MA/EMA calculation and alert trigger detection."""

from __future__ import annotations

import pandas as pd

from app.schemas.alert import AlertType
from app.schemas.market import Indicators, Kline

MIN_KLINES = 200
MONITOR_INTERVALS = frozenset({"4h", "1d", "1wk", "1w"})
CLUSTER_INTERVALS = MONITOR_INTERVALS
TOUCH_INTERVALS = frozenset({"1d", "1wk", "1w"})


def klines_to_dataframe(klines: list[Kline]) -> pd.DataFrame:
    rows = [
        {
            "open_time": k.open_time,
            "open": k.open,
            "high": k.high,
            "low": k.low,
            "close": k.close,
            "volume": k.volume,
        }
        for k in klines
    ]
    return pd.DataFrame(rows)


def calculate_indicators(klines: list[Kline]) -> Indicators | None:
    if len(klines) < MIN_KLINES:
        return None

    df = klines_to_dataframe(klines)
    df = df.dropna(subset=["close"])
    if len(df) < MIN_KLINES:
        return None

    close = df["close"]

    return Indicators(
        ma_20=float(close.rolling(20).mean().iloc[-1]),
        ema_20=float(close.ewm(span=20, adjust=False).mean().iloc[-1]),
        ma_60=float(close.rolling(60).mean().iloc[-1]),
        ema_60=float(close.ewm(span=60, adjust=False).mean().iloc[-1]),
        ma_120=float(close.rolling(120).mean().iloc[-1]),
        ema_120=float(close.ewm(span=120, adjust=False).mean().iloc[-1]),
        ma_200=float(close.rolling(200).mean().iloc[-1]),
        ema_200=float(close.ewm(span=200, adjust=False).mean().iloc[-1]),
    )


def cluster_spread_ratio(indicators: Indicators, price: float) -> float:
    values = indicators.cluster_values()
    if price <= 0:
        return float("inf")
    return (max(values) - min(values)) / price


def touch_ratio(price: float, indicator_value: float) -> float:
    if price <= 0:
        return float("inf")
    return abs(price - indicator_value) / price


def check_cluster_alert(
    indicators: Indicators,
    price: float,
    threshold: float,
) -> tuple[bool, float]:
    ratio = cluster_spread_ratio(indicators, price)
    return ratio <= threshold, ratio


def check_touch_alerts(
    indicators: Indicators,
    price: float,
    threshold: float,
) -> list[tuple[AlertType, float]]:
    triggered: list[tuple[AlertType, float]] = []

    ma_ratio = touch_ratio(price, indicators.ma_200)
    if ma_ratio <= threshold:
        triggered.append((AlertType.TOUCH_200_MA, ma_ratio))

    return triggered


def supports_cluster(interval: str) -> bool:
    return interval.lower() in CLUSTER_INTERVALS


def supports_touch(interval: str) -> bool:
    return interval.lower() in TOUCH_INTERVALS


def normalize_interval(interval: str) -> str:
    mapping = {"1wk": "1w", "1w": "1w", "4h": "4h", "1d": "1d"}
    key = interval.lower()
    return mapping.get(key, key)

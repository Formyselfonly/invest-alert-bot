from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class AlertType(StrEnum):
    CLUSTER = "cluster"
    TOUCH_200_MA = "touch_200_ma"
    TOUCH_200_EMA = "touch_200_ema"


ALERT_TYPE_LABELS: dict[AlertType, str] = {
    AlertType.CLUSTER: "均线密集",
    AlertType.TOUCH_200_MA: "200MA 触碰",
    AlertType.TOUCH_200_EMA: "200EMA 触碰",
}


@dataclass(frozen=True)
class AlertEvent:
    symbol: str
    interval: str
    alert_type: AlertType
    price: float
    detail: str
    triggered_at: datetime

    @property
    def key(self) -> tuple[str, str, AlertType]:
        return (self.symbol, self.interval, self.alert_type)

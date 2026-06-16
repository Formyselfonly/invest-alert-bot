from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class AlertType(StrEnum):
    CLUSTER = "cluster"
    TOUCH_200_MA = "touch_200_ma"


ALERT_TYPE_LABELS: dict[AlertType, str] = {
    AlertType.CLUSTER: "均线密集",
    AlertType.TOUCH_200_MA: "200MA 触碰",
}

SIMULTANEOUS_ALERT_HINT = (
    "💡 仓位管理最重要，不输就是赢，不做投机只做投资"
)


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

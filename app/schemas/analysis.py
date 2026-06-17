"""AI analysis request / report models.
Author: Shijie Zheng (Kerry Zheng) — https://github.com/Formyselfonly
Repository: https://github.com/Formyselfonly/invest-alert-bot
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from app.schemas.alert import AlertEvent, AlertType


class AnalysisTrigger(StrEnum):
    ALERT = "alert"
    MANUAL = "manual"


@dataclass(frozen=True)
class BotSignalSnapshot:
    symbol: str
    interval: str
    price: float
    cluster_pct: float | None
    touch_ma_pct: float | None
    touch_ma_side: str | None
    ma_20: float
    ma_60: float
    ma_120: float
    ma_200: float
    alert_type: AlertType | None = None
    alert_detail: str | None = None


@dataclass(frozen=True)
class AnalysisJob:
    symbol: str
    ta_ticker: str
    snapshot: BotSignalSnapshot
    trigger: AnalysisTrigger
    alert_event: AlertEvent | None = None
    requested_at: datetime = field(default_factory=lambda: datetime.now())


@dataclass(frozen=True)
class AnalysisResult:
    job: AnalysisJob
    decision: str
    elapsed_seconds: float
    llm_provider: str
    model: str
    raw_state: object | None = None


@dataclass(frozen=True)
class AnalysisReportPaths:
    html_path: str
    summary: str

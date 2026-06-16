from pydantic import BaseModel, Field

from app.schemas.market import DataSource


class TelegramConfig(BaseModel):
    bot_token: str
    chat_id: str


class SymbolConfig(BaseModel):
    symbol: str
    source: DataSource
    market: str = "futures"
    intervals: list[str] = Field(default_factory=list)
    ticker: str | None = None  # yfinance 拉数用，告警仍显示 symbol

    @property
    def yf_ticker(self) -> str:
        return self.ticker or self.symbol


class ThresholdConfig(BaseModel):
    cluster: float = 0.008
    touch: float = 0.008


class AlertConfig(BaseModel):
    cooldown_seconds: int = 3600
    dedupe_window_seconds: int = 60


class PollingConfig(BaseModel):
    yfinance_interval_seconds: int = 300
    kline_refresh_seconds: int = 60


class LoggingConfig(BaseModel):
    level: str = "INFO"
    file: str = "logs/app.log"
    max_bytes: int = 10_485_760
    backup_count: int = 5


class AppConfig(BaseModel):
    telegram: TelegramConfig
    symbols: list[SymbolConfig]
    thresholds: ThresholdConfig = Field(default_factory=ThresholdConfig)
    alert: AlertConfig = Field(default_factory=AlertConfig)
    polling: PollingConfig = Field(default_factory=PollingConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)

"""Environment-backed settings for TradingAgents analysis."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)


def _env_bool(key: str, default: bool = False) -> bool:
    raw = os.getenv(key)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class AnalysisEnv:
    enabled: bool
    llm_provider: str
    deep_model: str
    quick_model: str
    max_debate_rounds: int
    timeout_seconds: int
    reports_dir: str
    package_installed: bool

    @classmethod
    def load(cls) -> AnalysisEnv:
        try:
            import tradingagents  # noqa: F401

            installed = True
        except ImportError:
            installed = False

        enabled = _env_bool("ANALYSIS_ENABLED", False)
        if enabled and not installed:
            logger.warning(
                "ANALYSIS_ENABLED=true but tradingagents not installed. "
                "Run: uv sync --extra analysis",
            )
            enabled = False

        return cls(
            enabled=enabled and installed,
            llm_provider=os.getenv("LLM_PROVIDER", "deepseek").lower(),
            deep_model=os.getenv(
                "ANALYSIS_DEEP_MODEL",
                "deepseek-chat",
            ),
            quick_model=os.getenv(
                "ANALYSIS_QUICK_MODEL",
                "deepseek-chat",
            ),
            max_debate_rounds=int(
                os.getenv("ANALYSIS_MAX_DEBATE_ROUNDS", "1"),
            ),
            timeout_seconds=int(
                os.getenv("ANALYSIS_TIMEOUT_SECONDS", "300"),
            ),
            reports_dir=os.getenv("ANALYSIS_REPORTS_DIR", "reports"),
            package_installed=installed,
        )

    @property
    def status_label(self) -> str:
        if not _env_bool("ANALYSIS_ENABLED", False):
            return "未启用"
        if not self.package_installed:
            return "未安装 (uv sync --extra analysis)"
        return f"已启用 ({self.llm_provider})"

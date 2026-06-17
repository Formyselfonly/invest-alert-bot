"""Environment-backed settings for TradingAgents analysis."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_VALID_ANALYSTS = frozenset({"market", "social", "news", "fundamentals"})
_DEFAULT_ANALYSTS = ("market", "news", "fundamentals")


def parse_selected_analysts(raw: str | None) -> tuple[str, ...]:
    """Parse ``ANALYSIS_ANALYSTS`` env value.

    Default drops ``social`` (Reddit often 403; overlaps with news).
    """
    if raw is None or not raw.strip():
        return _DEFAULT_ANALYSTS

    parts = [part.strip().lower() for part in raw.split(",") if part.strip()]
    invalid = [part for part in parts if part not in _VALID_ANALYSTS]
    if invalid:
        logger.warning("Ignoring invalid ANALYSIS_ANALYSTS entries: %s", invalid)
    selected = tuple(part for part in parts if part in _VALID_ANALYSTS)
    if not selected:
        logger.warning(
            "ANALYSIS_ANALYSTS resolved to empty list; using default %s",
            _DEFAULT_ANALYSTS,
        )
        return _DEFAULT_ANALYSTS
    return selected


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
    selected_analysts: tuple[str, ...]
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
            selected_analysts=parse_selected_analysts(
                os.getenv("ANALYSIS_ANALYSTS"),
            ),
            timeout_seconds=int(
                os.getenv("ANALYSIS_TIMEOUT_SECONDS", "1800"),
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

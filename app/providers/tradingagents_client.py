"""TradingAgents graph wrapper.
Author: Shijie Zheng (Kerry Zheng) — https://github.com/Formyselfonly
Repository: https://github.com/Formyselfonly/invest-alert-bot
"""

from __future__ import annotations

import logging
import os
import time
from datetime import UTC, date, datetime

from app.core.analysis_env import AnalysisEnv
from app.schemas.analysis import AnalysisJob, AnalysisResult
from app.services.analysis_context import build_briefing
from app.services.analysis_report import compose_decision_text

logger = logging.getLogger(__name__)


class TradingAgentsClient:
    def __init__(self, settings: AnalysisEnv) -> None:
        self._settings = settings

    def run(self, job: AnalysisJob) -> AnalysisResult:
        from tradingagents.default_config import DEFAULT_CONFIG
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        config = DEFAULT_CONFIG.copy()
        config["llm_provider"] = self._settings.llm_provider
        config["deep_think_llm"] = self._settings.deep_model
        config["quick_think_llm"] = self._settings.quick_model
        config["max_debate_rounds"] = self._settings.max_debate_rounds
        config["temperature"] = float(
            os.getenv("ANALYSIS_TEMPERATURE", "0.2"),
        )

        briefing = build_briefing(job.snapshot)
        analysts = list(self._settings.selected_analysts)
        logger.info(
            "TradingAgents run: %s (%s) trigger=%s analysts=%s",
            job.ta_ticker,
            job.symbol,
            job.trigger,
            ",".join(analysts),
        )
        logger.debug("Bot briefing:\n%s", briefing)

        ta = TradingAgentsGraph(
            selected_analysts=analysts,
            debug=False,
            config=config,
        )
        analysis_date = date.today().isoformat()
        started = time.monotonic()
        raw_state, rating = ta.propagate(job.ta_ticker, analysis_date)
        elapsed = time.monotonic() - started

        decision_text = compose_decision_text(raw_state, str(rating))
        if briefing not in decision_text:
            decision_text = f"{briefing}\n\n---\n\n{decision_text}"

        return AnalysisResult(
            job=job,
            decision=decision_text,
            elapsed_seconds=elapsed,
            llm_provider=self._settings.llm_provider,
            model=self._settings.deep_model,
            raw_state=raw_state,
        )


def _stringify_decision(decision: object) -> str:
    """Legacy helper kept for tests / callers that pass pre-rendered decisions."""
    if decision is None:
        return "（TradingAgents 未返回 decision）"
    if isinstance(decision, str):
        return decision
    if isinstance(decision, dict):
        parts: list[str] = []
        for key, value in decision.items():
            parts.append(f"## {key}\n{value}")
        return "\n\n".join(parts)
    return str(decision)


def analysis_date_stamp() -> str:
    return datetime.now(tz=UTC).strftime("%Y%m%d_%H%M%S")

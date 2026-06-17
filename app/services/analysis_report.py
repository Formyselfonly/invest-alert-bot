"""Assemble TradingAgents graph state into human-readable report text.
Author: Shijie Zheng (Kerry Zheng) — https://github.com/Formyselfonly
Repository: https://github.com/Formyselfonly/invest-alert-bot
"""

from __future__ import annotations


def _nested_text(state: dict, key: str, subkey: str) -> str:
    block = state.get(key)
    if not isinstance(block, dict):
        return ""
    value = block.get(subkey)
    return value.strip() if isinstance(value, str) else ""


def _section(title: str, body: str | None) -> str:
    text = (body or "").strip()
    if not text:
        return ""
    return f"## {title}\n\n{text}\n\n"


def compose_decision_text(raw_state: object, rating: str) -> str:
    """Build full report body from LangGraph final state.

    ``propagate()`` returns only a 5-tier rating word (e.g. ``Hold``) via
    ``SignalProcessor``; the detailed analyst reports live in ``raw_state``.
    """
    if not isinstance(raw_state, dict):
        return rating.strip() or "Hold"

    debate_summary = _nested_text(
        raw_state,
        "investment_debate_state",
        "judge_decision",
    )
    if not debate_summary:
        debate_summary = _nested_text(
            raw_state,
            "investment_debate_state",
            "history",
        )

    risk_summary = _nested_text(raw_state, "risk_debate_state", "judge_decision")
    if not risk_summary:
        risk_summary = _nested_text(raw_state, "risk_debate_state", "history")

    trader_plan = raw_state.get("trader_investment_plan")
    if not isinstance(trader_plan, str) or not trader_plan.strip():
        trader_plan = raw_state.get("trader_investment_decision")

    sections = [
        _section("综合评级", f"**{rating.strip() or 'Hold'}**"),
        _section("投资组合经理结论", raw_state.get("final_trade_decision")),
        _section("市场分析", raw_state.get("market_report")),
        _section("新闻与宏观", raw_state.get("news_report")),
        _section("基本面", raw_state.get("fundamentals_report")),
        _section("交易员计划", trader_plan),
        _section("多空辩论", debate_summary),
        _section("风险评估", risk_summary),
    ]
    body = "".join(section for section in sections if section)
    return body.strip() or rating.strip() or "Hold"


def extract_summary_excerpt(decision: str, max_len: int = 400) -> str:
    """Pick a short Telegram-friendly excerpt from the full report."""
    text = decision.strip()
    if not text:
        return "（无分析内容）"

    for marker in ("**Executive Summary**", "**Executive summary**", "Executive Summary"):
        idx = text.find(marker)
        if idx >= 0:
            chunk = text[idx : idx + max_len + 120]
            if len(chunk) > max_len:
                return chunk[:max_len].rstrip() + "…"
            return chunk

    if len(text) <= max_len:
        return text
    return text[:max_len].rstrip() + "…"

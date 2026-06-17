"""Tests for TradingAgents report assembly."""

from app.services.analysis_report import compose_decision_text, extract_summary_excerpt


def test_compose_decision_text_from_raw_state() -> None:
    raw_state = {
        "final_trade_decision": "**Rating**: Hold\n\n**Executive Summary**: Stay flat.",
        "market_report": "RSI is oversold.",
        "news_report": "Fed meeting next week.",
        "fundamentals_report": "FCF declined.",
        "trader_investment_plan": "No new buys.",
        "investment_debate_state": {
            "judge_decision": "Bull and bear are balanced.",
        },
        "risk_debate_state": {
            "judge_decision": "Moderate risk.",
        },
    }
    text = compose_decision_text(raw_state, "Hold")
    assert "## 综合评级" in text
    assert "Executive Summary" in text
    assert "## 市场分析" in text
    assert "RSI is oversold." in text
    assert "## 新闻与宏观" in text
    assert "## 基本面" in text
    assert "## 多空辩论" in text
    assert "## 风险评估" in text


def test_compose_decision_text_rating_only_fallback() -> None:
    text = compose_decision_text({}, "Sell")
    assert "**Sell**" in text


def test_extract_summary_excerpt_prefers_executive_summary() -> None:
    decision = (
        "## 投资组合经理结论\n\n"
        "**Rating**: Hold\n\n"
        "**Executive Summary**: Maintain benchmark weight.\n\n"
        "Long body " * 50
    )
    excerpt = extract_summary_excerpt(decision, max_len=80)
    assert "Executive Summary" in excerpt
    assert len(excerpt) <= 81

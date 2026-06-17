"""Tests for analysis environment parsing.
Author: Shijie Zheng (Kerry Zheng) — https://github.com/Formyselfonly
Repository: https://github.com/Formyselfonly/invest-alert-bot
"""

from app.core.analysis_env import _DEFAULT_ANALYSTS, parse_selected_analysts


def test_parse_selected_analysts_default() -> None:
    assert parse_selected_analysts(None) == _DEFAULT_ANALYSTS
    assert parse_selected_analysts("") == _DEFAULT_ANALYSTS
    assert parse_selected_analysts("   ") == _DEFAULT_ANALYSTS


def test_parse_selected_analysts_explicit() -> None:
    assert parse_selected_analysts("market,news") == ("market", "news")
    assert parse_selected_analysts(" Market , NEWS ") == ("market", "news")


def test_parse_selected_analysts_ignores_invalid() -> None:
    assert parse_selected_analysts("market,foo,fundamentals") == (
        "market",
        "fundamentals",
    )


def test_parse_selected_analysts_fallback_when_all_invalid() -> None:
    assert parse_selected_analysts("foo,bar") == _DEFAULT_ANALYSTS

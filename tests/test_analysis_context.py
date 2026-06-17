"""Tests for TradingAgents symbol mapping."""

from app.services.analysis_context import to_tradingagents_ticker


def test_crypto_symbol_maps_to_yahoo_crypto_ticker() -> None:
    assert to_tradingagents_ticker("BTC/USDT") == "BTC-USD"
    assert to_tradingagents_ticker("ETH/USDT") == "ETH-USD"


def test_equity_symbol_unchanged() -> None:
    assert to_tradingagents_ticker("MSFT") == "MSFT"
    assert to_tradingagents_ticker("QQQ") == "QQQ"


def test_xau_uses_explicit_ticker() -> None:
    assert to_tradingagents_ticker("XAU", "GC=F") == "GC=F"

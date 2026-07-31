"""Unit tests for unusual options scoring helpers (no network)."""

from app.services.uoa_scanner import (
    classify_aggressiveness,
    classify_sentiment,
    india_lot_size,
    score_contract,
)


def test_classify_aggressiveness_near_ask():
    assert classify_aggressiveness(last=1.95, bid=1.80, ask=2.00) == "buy_ask"


def test_classify_aggressiveness_near_bid():
    assert classify_aggressiveness(last=1.82, bid=1.80, ask=2.00) == "sell_bid"


def test_classify_aggressiveness_mid_and_unknown():
    assert classify_aggressiveness(last=1.90, bid=1.80, ask=2.00) == "mid"
    assert classify_aggressiveness(last=None, bid=1.0, ask=1.1) == "unknown"


def test_classify_sentiment_call_put_bias():
    sentiment, reason = classify_sentiment("call", "buy_ask")
    assert sentiment == "bullish"
    assert "call" in reason.lower()
    assert "ask" in reason.lower()

    sentiment, reason = classify_sentiment("put", "buy_ask")
    assert sentiment == "bearish"
    assert "put" in reason.lower()


def test_classify_sentiment_sell_bid_mixed():
    sentiment, _ = classify_sentiment("call", "sell_bid")
    assert sentiment == "mixed"
    sentiment, _ = classify_sentiment("put", "sell_bid")
    assert sentiment == "mixed"


def test_score_contract_ranks_high_vol_oi_and_premium():
    quiet = score_contract(volume=200, open_interest=100, premium=30_000, vol_oi=2.0, dte=30)
    loud = score_contract(volume=5000, open_interest=200, premium=2_000_000, vol_oi=25.0, dte=21)
    assert loud > quiet
    assert quiet > 0


def test_passes_unusual_gates_requires_vol_oi():
    from app.services.uoa_scanner import passes_unusual_gates

    ok, vol_oi = passes_unusual_gates(
        volume=500,
        open_interest=100,
        premium=60_000,
        min_volume=500,
        min_premium=50_000,
        min_vol_oi=3.0,
        require_vol_oi=True,
    )
    assert ok is True
    assert vol_oi == 5.0

    # High premium alone no longer bypasses Vol/OI when require_vol_oi=True
    ok, _ = passes_unusual_gates(
        volume=500,
        open_interest=1000,
        premium=500_000,
        min_volume=500,
        min_premium=50_000,
        min_vol_oi=3.0,
        require_vol_oi=True,
    )
    assert ok is False


def test_india_lot_size_known_and_fallback():
    assert india_lot_size("NIFTY") == 65
    assert india_lot_size("RELIANCE") >= 1
    assert india_lot_size("UNKNOWNXYZ") == 1

"""Unit tests for India PIT normalization (no network)."""

from app.services.india_provider import _normalize_pit_row


def test_normalize_keeps_only_open_market_modes():
    buy = _normalize_pit_row(
        {
            "acqMode": "Market Purchase",
            "acqName": "Damodar Padhi",
            "acqfromDt": "19-Apr-2026",
            "company": "Tata Consultancy Services Limited",
            "date": "25-Apr-2026 17:45",
            "did": "425936",
            "exchange": "BSE",
            "intimDt": "20-Apr-2026",
            "personCategory": "Employees/Designated Employees",
            "secAcq": "57",
            "secVal": "201680",
            "symbol": "TCS",
            "tdpTransactionType": "Buy",
            "xbrl": "https://example.test/xbrl.xml",
            "afterAcqSharesNo": "3057",
        }
    )
    assert buy is not None
    assert buy["market"] == "IN"
    assert buy["transaction_side"] == "buy"
    assert buy["transaction_code"] == "P"
    assert buy["ticker"] == "TCS"
    assert buy["exchange"] == "BSE"
    assert buy["shares"] == 57
    assert buy["total_value"] == 201680
    assert buy["is_officer"] is True

    off = _normalize_pit_row({"acqMode": "Off Market", "tdpTransactionType": "Buy", "symbol": "TCS"})
    assert off is None

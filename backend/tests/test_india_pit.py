"""Unit tests for India PIT role cleanup."""

from app.services.india_provider import _normalize_pit_row, _role_flags


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


def test_role_flags_promoter_and_independent_director():
    promoter = _role_flags("Promoter Group")
    assert promoter["is_ten_percent_owner"] is True
    assert promoter["relationship"] == "Promoter Group"

    director = _role_flags("Independent Director")
    assert director["is_director"] is True
    assert director["relationship"] == "Independent Director"
    assert director["is_officer"] is False


def test_role_flags_chairman_and_president_are_officers():
    chair = _role_flags("Chairman")
    assert chair["is_officer"] is True
    assert chair["officer_title"] == "Chairman"

    president = _role_flags("President")
    assert president["is_officer"] is True

    non_exec = _role_flags("Non-Executive Director")
    assert non_exec["is_officer"] is False

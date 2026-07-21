"""Unit tests for Form 4 parsing (no network)."""

from app.services.sec_form4 import parse_form4_xml
from tests.fixtures import SAMPLE_FORM4_XML


def test_parse_form4_keeps_only_open_market_ps():
    rows = parse_form4_xml(
        SAMPLE_FORM4_XML,
        accession_number="0000320193-26-000123",
        filing_date=None,
        source_url="https://example.test/form4.xml",
    )
    assert len(rows) == 2
    sides = sorted(r["transaction_side"] for r in rows)
    assert sides == ["buy", "sell"]

    buy = next(r for r in rows if r["transaction_side"] == "buy")
    assert buy["ticker"] == "AAPL"
    assert buy["insider_name"] == "Cook Timothy D"
    assert buy["is_officer"] is True
    assert buy["is_director"] is True
    assert buy["officer_title"] == "Chief Executive Officer"
    assert buy["shares"] == 1000
    assert buy["price_per_share"] == 190.5
    assert buy["total_value"] == 190500.0

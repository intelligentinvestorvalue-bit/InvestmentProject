"""Officer / management filter: titles InsideArbitrage includes, SEC isOfficer may not."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.config import Config
from app.extensions import db
from app.models import InsiderTransaction
from app.utils.helpers import is_management_insider, is_management_title


class TestConfig(Config):
    TESTING = True
    SEC_USER_AGENT = "FilingDesk test@example.com"
    SCHEDULER_ENABLED = False
    DEEP_DIVE_BRIDGE_ENABLED = False
    DEEP_DIVE_NTFY_ENABLED = False


@pytest.fixture()
def app(tmp_path):
    TestConfig.SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'test.db'}"
    from app import create_app

    application = create_app(TestConfig)
    with application.app_context():
        db.create_all()
        yield application
        db.session.remove()


def test_is_management_title_matches_insidearbitrage_roles():
    for title in (
        "President",
        "EVP",
        "Chairman",
        "Executive Chairman",
        "Chief Financial Officer",
        "President and CEO",
        "SVP, Strategy & Business Ops",
        "VP",
        "FVP",
    ):
        assert is_management_title(title), title

    assert is_management_title("Director") is False
    assert is_management_title("Independent Director") is False
    assert is_management_title("Non-Executive Director") is False
    assert is_management_insider(
        is_officer=False, officer_title=None, relationship="10% Owner"
    ) is False


def _tx(**overrides):
    base = dict(
        market="US",
        ticker="AAPL",
        company_name="Apple Inc.",
        insider_name="Test Insider",
        relationship="Officer",
        is_director=False,
        is_officer=True,
        is_ten_percent_owner=False,
        officer_title="Chief Executive Officer",
        transaction_code="P",
        transaction_side="buy",
        transaction_date=datetime.now(timezone.utc).date(),
        filing_date=datetime.now(timezone.utc).date(),
        shares=1000,
        price_per_share=100.0,
        total_value=100_000,
        accession_number="0001-26-000001",
        source_url="https://example.test/form4",
    )
    base.update(overrides)
    row = InsiderTransaction(**base)
    db.session.add(row)
    db.session.commit()
    return row


def test_officer_role_includes_management_titles_not_just_is_officer(app):
    with app.app_context():
        _tx(
            insider_name="Plain Officer",
            accession_number="a-officer",
        )
        _tx(
            insider_name="Chair Only",
            is_officer=False,
            is_director=True,
            officer_title="Chairman",
            relationship="Chairman, Director",
            accession_number="a-chair",
        )
        _tx(
            insider_name="President Only",
            is_officer=False,
            is_director=False,
            officer_title="President",
            relationship="President",
            accession_number="a-pres",
        )
        _tx(
            insider_name="EVP Only",
            is_officer=False,
            officer_title="EVP",
            relationship="EVP",
            accession_number="a-evp",
        )
        _tx(
            insider_name="Board Only",
            is_officer=False,
            is_director=True,
            officer_title=None,
            relationship="Director",
            accession_number="a-dir",
        )
        _tx(
            insider_name="Owner Only",
            is_officer=False,
            is_director=False,
            is_ten_percent_owner=True,
            officer_title=None,
            relationship="10% Owner",
            accession_number="a-own",
        )

        client = app.test_client()
        response = client.get("/api/v1/insider/transactions?market=US&role=officer")
        assert response.status_code == 200
        names = {row["insider_name"] for row in response.get_json()["items"]}
        assert "Plain Officer" in names
        assert "Chair Only" in names
        assert "President Only" in names
        assert "EVP Only" in names
        assert "Board Only" not in names
        assert "Owner Only" not in names

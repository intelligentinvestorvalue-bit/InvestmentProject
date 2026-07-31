"""Unit tests for officer-buy → deep-dive bridge (no network)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.config import Config
from app.extensions import db
from app.models import DeepDiveCandidate, InsiderTransaction
from app.services import deep_dive_bridge as bridge


class TestConfig(Config):
    TESTING = True
    SEC_USER_AGENT = "FilingDesk test@example.com"
    SCHEDULER_ENABLED = False
    DEEP_DIVE_BRIDGE_ENABLED = True
    DEEP_DIVE_CONFIRM_SECONDS = 60
    DEEP_DIVE_MIN_VALUE_USD = 100_000
    DEEP_DIVE_NTFY_ENABLED = False
    DEEP_DIVE_ONCE_PER_TICKER = True
    DEEP_DIVE_COOLDOWN_HOURS = 72
    DEEP_DIVE_BACKLOG_RETRY_MINUTES = 60
    DEEP_DIVE_RESEARCH_URL = "http://127.0.0.1:8000"
    DEEP_DIVE_RESEARCH_TEMPLATE = "all"
    DEEP_DIVE_RESEARCH_MODE = "deep"
    DEEP_DIVE_RESEARCH_PIN = ""
    DEEP_DIVE_USE_OVERNIGHT_QUEUE = True
    DEEP_DIVE_QUEUE_START_POLICY = "prompt_now"
    DEEP_DIVE_SKIP_IF_RESEARCHED = True


@pytest.fixture()
def app(tmp_path):
    TestConfig.SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'test.db'}"
    from app import create_app

    application = create_app(TestConfig)
    with application.app_context():
        db.create_all()
        yield application
        db.session.remove()


def _tx(**overrides):
    base = dict(
        market="US",
        ticker="ACME",
        company_name="Acme Corp",
        cik="0001",
        insider_name="Jane CEO",
        relationship="Officer",
        is_director=False,
        is_officer=True,
        is_ten_percent_owner=False,
        officer_title="Chief Executive Officer",
        transaction_code="P",
        transaction_side="buy",
        transaction_date=datetime.now(timezone.utc).date(),
        filing_date=datetime.now(timezone.utc).date(),
        shares=10000,
        price_per_share=55.0,
        total_value=600_000,
        shares_owned_after=50000,
        ownership_form="D",
        accession_number="0001-26-000001",
        source_url="https://example.test/form4",
    )
    base.update(overrides)
    row = InsiderTransaction(**base)
    db.session.add(row)
    db.session.commit()
    return row


def test_is_management_officer_by_flag_and_title(app):
    with app.app_context():
        flagged = SimpleNamespace(
            is_officer=True, officer_title=None, relationship=None
        )
        assert bridge.is_management_officer(flagged) is True

        title_only = SimpleNamespace(
            is_officer=False, officer_title="CFO", relationship=None
        )
        assert bridge.is_management_officer(title_only) is True

        director = SimpleNamespace(
            is_officer=False, officer_title=None, relationship="Director"
        )
        assert bridge.is_management_officer(director) is False


def test_find_qualifying_buys_filters_value_and_role(app):
    with app.app_context():
        _tx(total_value=600_000, accession_number="a1")
        _tx(
            ticker="SMALL",
            total_value=99_000,
            accession_number="a2",
            insider_name="Small Buy",
        )
        _tx(
            ticker="DIR",
            is_officer=False,
            officer_title=None,
            relationship="Director",
            total_value=900_000,
            accession_number="a3",
            insider_name="Only Director",
        )
        rows = bridge.find_qualifying_buys()
        tickers = {r.ticker for r in rows}
        assert "ACME" in tickers
        assert "SMALL" not in tickers
        assert "DIR" not in tickers


def test_stage_cancel_backlog_and_revive(app):
    with app.app_context():
        tx = _tx()
        with patch(
            "app.services.deep_dive_bridge.should_skip_ticker",
            return_value=(False, None),
        ):
            candidate = bridge.stage_candidate_from_tx(tx)
        assert candidate is not None
        assert candidate.status == bridge.STATUS_PENDING
        assert candidate.confirm_deadline_at is not None

        cancelled = bridge.cancel_candidate(candidate.id)
        assert cancelled.status == bridge.STATUS_BACKLOG
        assert cancelled.cancel_count == 1
        assert cancelled.retry_after is not None

        assert bridge.revive_backlog()["revived"] == 0

        cancelled.retry_after = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.session.commit()
        with patch(
            "app.services.deep_dive_bridge.should_skip_ticker",
            return_value=(False, None),
        ):
            assert bridge.revive_backlog()["revived"] == 1
        refreshed = db.session.get(DeepDiveCandidate, candidate.id)
        assert refreshed.status == bridge.STATUS_PENDING


def test_process_expired_pending_pushes(app):
    with app.app_context():
        tx = _tx()
        with patch(
            "app.services.deep_dive_bridge.should_skip_ticker",
            return_value=(False, None),
        ):
            candidate = bridge.stage_candidate_from_tx(tx)
        candidate.confirm_deadline_at = datetime.now(timezone.utc) - timedelta(seconds=5)
        db.session.commit()

        fake_health = MagicMock()
        fake_health.ok = True
        fake_health.status_code = 200

        fake_queue = MagicMock()
        fake_queue.ok = True
        fake_queue.status_code = 200
        fake_queue.json.return_value = {
            "added": 1,
            "tickers": ["ACME"],
            "created": [{"id": "queue-item-1", "ticker": "ACME"}],
            "skipped": [],
        }

        with patch(
            "app.services.deep_dive_bridge.should_skip_ticker",
            return_value=(False, None),
        ), patch("app.services.deep_dive_bridge.requests.get") as get_mock, patch(
            "app.services.deep_dive_bridge.requests.post"
        ) as post_mock:
            get_mock.return_value = fake_health
            post_mock.return_value = fake_queue
            result = bridge.process_expired_pending()

        assert result["pushed"] == 1
        refreshed = db.session.get(DeepDiveCandidate, candidate.id)
        assert refreshed.status == bridge.STATUS_PUSHED
        assert refreshed.research_job_id == "queue-item-1"
        post_mock.assert_called_once()
        assert post_mock.call_args.args[0].endswith("/api/queue")
        payload = post_mock.call_args.kwargs.get("json") or post_mock.call_args[1].get("json")
        assert payload["tickers"] == "ACME"
        assert payload["template"] == "all"
        assert payload["start_policy"] == "prompt_now"


def test_agent_down_goes_to_backlog(app):
    with app.app_context():
        tx = _tx()
        with patch(
            "app.services.deep_dive_bridge.should_skip_ticker",
            return_value=(False, None),
        ):
            candidate = bridge.stage_candidate_from_tx(tx)
        with patch(
            "app.services.deep_dive_bridge.should_skip_ticker",
            return_value=(False, None),
        ), patch(
            "app.services.deep_dive_bridge.research_agent_healthy", return_value=False
        ):
            bridge.push_candidate(candidate)
        refreshed = db.session.get(DeepDiveCandidate, candidate.id)
        assert refreshed.status == bridge.STATUS_BACKLOG
        assert "unreachable" in (refreshed.error_message or "").lower()


def test_skip_when_already_researched(app):
    with app.app_context():
        tx = _tx()
        with patch(
            "app.services.deep_dive_bridge.should_skip_ticker",
            return_value=(True, "already researched (job abc)"),
        ):
            assert bridge.stage_candidate_from_tx(tx) is None
        skipped = DeepDiveCandidate.query.filter_by(ticker="ACME", status="skipped").first()
        assert skipped is not None
        assert "already researched" in (skipped.error_message or "")


def test_cooldown_skips_restage(app):
    with app.app_context():
        tx = _tx()
        with patch(
            "app.services.deep_dive_bridge.should_skip_ticker",
            return_value=(False, None),
        ):
            first = bridge.stage_candidate_from_tx(tx)
        first.status = bridge.STATUS_PUSHED
        first.pushed_at = datetime.now(timezone.utc)
        db.session.commit()

        later = _tx(accession_number="0001-26-000099", total_value=750_000)
        with patch(
            "app.services.deep_dive_bridge.should_skip_ticker",
            return_value=(False, None),
        ):
            again = bridge.stage_candidate_from_tx(later)
        assert again is None
        followups = DeepDiveCandidate.query.filter_by(
            ticker="ACME", status=bridge.STATUS_FOLLOWUP
        ).all()
        assert len(followups) == 1
        assert followups[0].total_value == 750_000


def test_followups_api(app):
    client = app.test_client()
    with app.app_context():
        tx = _tx()
        with patch(
            "app.services.deep_dive_bridge.should_skip_ticker",
            return_value=(False, None),
        ):
            first = bridge.stage_candidate_from_tx(tx)
        first.status = bridge.STATUS_PUSHED
        first.pushed_at = datetime.now(timezone.utc)
        db.session.commit()
        later = _tx(accession_number="0001-26-000088", total_value=900_000)
        with patch(
            "app.services.deep_dive_bridge.should_skip_ticker",
            return_value=(False, None),
        ):
            bridge.stage_candidate_from_tx(later)

    resp = client.get("/api/v1/deep-dive/followups?market=US")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["once_per_ticker"] is True
    assert data["total"] >= 1
    assert data["items"][0]["ticker"] == "ACME"
    assert data["items"][0]["status"] == "followup"


def test_pending_api(app):
    client = app.test_client()
    with app.app_context():
        tx = _tx()
        with patch(
            "app.services.deep_dive_bridge.should_skip_ticker",
            return_value=(False, None),
        ):
            bridge.stage_candidate_from_tx(tx)

    resp = client.get("/api/v1/deep-dive/pending")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["enabled"] is True
    assert len(data["pending"]) == 1
    assert data["pending"][0]["ticker"] == "ACME"

    candidate_id = data["pending"][0]["id"]
    cancel = client.post(f"/api/v1/deep-dive/{candidate_id}/cancel")
    assert cancel.status_code == 200
    assert cancel.get_json()["status"] == "backlog"

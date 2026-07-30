"""Bridge: large officer buys → Equity Research Agent full deep-dive queue.

Flow
----
1. After US insider sync, scan new open-market officer buys >= DEEP_DIVE_MIN_VALUE_USD.
2. Stage a DeepDiveCandidate in ``pending_confirm`` and notify (in-app + optional ntfy).
3. Wait DEEP_DIVE_CONFIRM_SECONDS (default 60). User may Cancel → ``backlog``
   (retry next hour) or Push now → immediate POST to research agent.
4. If the window expires with no cancel, auto-push ``POST /api/research``
   (template=all full pack by default).
5. Cooldown prevents re-pushing the same ticker for DEEP_DIVE_COOLDOWN_HOURS.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import requests
from flask import current_app
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import AppNotification, DeepDiveCandidate, InsiderTransaction, utcnow
from app.services.ntfy import send_ntfy

logger = logging.getLogger(__name__)

STATUS_PENDING = "pending_confirm"
STATUS_BACKLOG = "backlog"
STATUS_PUSHED = "pushed"
STATUS_FAILED = "failed"
STATUS_SKIPPED = "skipped"


def _officer_keywords() -> list[str]:
    raw = current_app.config.get(
        "DEEP_DIVE_OFFICER_TITLE_KEYWORDS",
        "ceo,cfo,coo,cto,chief,president,managing director,general counsel,controller,treasurer",
    )
    return [part.strip().lower() for part in str(raw).split(",") if part.strip()]


def is_management_officer(tx: InsiderTransaction) -> bool:
    """True when the filer is an officer / C-suite / named management role."""
    if tx.is_officer:
        return True
    title = (tx.officer_title or tx.relationship or "").strip().lower()
    if not title:
        return False
    for keyword in _officer_keywords():
        if " " in keyword:
            if keyword in title:
                return True
            continue
        # Short tokens (ceo/cfo/cto) need word boundaries — "director" contains "cto".
        if re.search(rf"(?<![a-z]){re.escape(keyword)}(?![a-z])", title):
            return True
    return False


def _format_usd(value: Optional[float]) -> str:
    if value is None:
        return "$?"
    return f"${value:,.0f}"


def _cooldown_cutoff() -> datetime:
    hours = int(current_app.config.get("DEEP_DIVE_COOLDOWN_HOURS", 72))
    return utcnow() - timedelta(hours=max(hours, 1))


def _has_recent_push(ticker: str, market: str = "US") -> bool:
    cutoff = _cooldown_cutoff()
    existing = (
        DeepDiveCandidate.query.filter(
            DeepDiveCandidate.market == market,
            DeepDiveCandidate.ticker == ticker.upper(),
            DeepDiveCandidate.status == STATUS_PUSHED,
            DeepDiveCandidate.pushed_at.isnot(None),
            DeepDiveCandidate.pushed_at >= cutoff,
        )
        .order_by(DeepDiveCandidate.pushed_at.desc())
        .first()
    )
    return existing is not None


def _active_for_ticker(ticker: str, market: str = "US") -> Optional[DeepDiveCandidate]:
    return (
        DeepDiveCandidate.query.filter(
            DeepDiveCandidate.market == market,
            DeepDiveCandidate.ticker == ticker.upper(),
            DeepDiveCandidate.status.in_([STATUS_PENDING, STATUS_BACKLOG]),
        )
        .order_by(DeepDiveCandidate.created_at.desc())
        .first()
    )


def find_qualifying_buys(
    *,
    since: Optional[datetime] = None,
    market: str = "US",
    min_value: Optional[float] = None,
) -> list[InsiderTransaction]:
    """Return open-market officer buys above the value threshold."""
    threshold = float(
        min_value
        if min_value is not None
        else current_app.config.get("DEEP_DIVE_MIN_VALUE_USD", 500_000)
    )
    query = InsiderTransaction.query.filter(
        InsiderTransaction.market == market,
        InsiderTransaction.transaction_side == "buy",
        InsiderTransaction.total_value.isnot(None),
        InsiderTransaction.total_value >= threshold,
        InsiderTransaction.ticker.isnot(None),
    )
    if since is not None:
        query = query.filter(InsiderTransaction.fetched_at >= since)

    rows = query.order_by(InsiderTransaction.total_value.desc()).all()
    return [row for row in rows if is_management_officer(row)]


def _create_in_app_notification(candidate: DeepDiveCandidate, *, seconds: int) -> int:
    title = f"Deep dive queued: {candidate.ticker}"
    body = (
        f"{candidate.officer_title or 'Officer'} {candidate.insider_name or ''} "
        f"bought {_format_usd(candidate.total_value)} of {candidate.company_name or candidate.ticker}. "
        f"Pushing to Equity Research Agent in ~{seconds}s unless you cancel."
    )
    note = AppNotification(
        kind="deep_dive_push",
        title=title[:255],
        body=body.strip(),
        severity="info",
        ticker=candidate.ticker,
        payload_json=json.dumps(
            {
                "candidate_id": candidate.id,
                "confirm_deadline_at": candidate.confirm_deadline_at.isoformat()
                if candidate.confirm_deadline_at
                else None,
                "total_value": candidate.total_value,
                "officer_title": candidate.officer_title,
                "insider_name": candidate.insider_name,
            }
        )[:4000],
        is_read=False,
    )
    db.session.add(note)
    db.session.commit()
    return note.id


def _notify_external(candidate: DeepDiveCandidate, *, seconds: int) -> None:
    if not current_app.config.get("DEEP_DIVE_NTFY_ENABLED", True):
        return
    send_ntfy(
        title=f"FilingDesk → deep dive {candidate.ticker}",
        message=(
            f"{candidate.officer_title or 'Officer'} bought "
            f"{_format_usd(candidate.total_value)}. "
            f"Auto-push in ~{seconds}s — open FilingDesk to cancel."
        ),
        priority=4,
        tags="chart_with_upwards_trend,warning",
        click=current_app.config.get("DEEP_DIVE_UI_CLICK_URL") or None,
    )


def stage_candidate_from_tx(
    tx: InsiderTransaction,
    *,
    confirm_seconds: Optional[int] = None,
) -> Optional[DeepDiveCandidate]:
    """Create a pending_confirm candidate for a qualifying transaction."""
    ticker = (tx.ticker or "").strip().upper()
    if not ticker:
        return None

    if _has_recent_push(ticker, tx.market or "US"):
        logger.info("Skip %s: already pushed within cooldown", ticker)
        return None

    active = _active_for_ticker(ticker, tx.market or "US")
    if active:
        # Enrich value if this buy is larger; keep existing confirm window.
        if (tx.total_value or 0) > (active.total_value or 0):
            active.total_value = tx.total_value
            active.insider_name = tx.insider_name
            active.officer_title = tx.officer_title or active.officer_title
            active.accession_number = tx.accession_number
            active.source_url = tx.source_url
            try:
                ids = json.loads(active.transaction_ids_json or "[]")
            except json.JSONDecodeError:
                ids = []
            if tx.id not in ids:
                ids.append(tx.id)
            active.transaction_ids_json = json.dumps(ids)
            active.updated_at = utcnow()
            db.session.commit()
        return active

    seconds = int(
        confirm_seconds
        if confirm_seconds is not None
        else current_app.config.get("DEEP_DIVE_CONFIRM_SECONDS", 60)
    )
    deadline = utcnow() + timedelta(seconds=max(seconds, 5))
    candidate = DeepDiveCandidate(
        market=(tx.market or "US").upper(),
        ticker=ticker,
        company_name=tx.company_name,
        insider_name=tx.insider_name,
        officer_title=tx.officer_title or tx.relationship,
        total_value=tx.total_value,
        transaction_ids_json=json.dumps([tx.id]),
        accession_number=tx.accession_number,
        source_url=tx.source_url,
        status=STATUS_PENDING,
        confirm_deadline_at=deadline,
        cancel_count=0,
    )
    db.session.add(candidate)
    db.session.commit()

    try:
        note_id = _create_in_app_notification(candidate, seconds=seconds)
        candidate.notification_id = note_id
        db.session.commit()
    except Exception:  # noqa: BLE001
        logger.exception("Failed to create in-app notification for %s", ticker)

    try:
        _notify_external(candidate, seconds=seconds)
    except Exception:  # noqa: BLE001
        logger.exception("External ntfy failed for %s", ticker)

    logger.info(
        "Staged deep-dive candidate %s id=%s deadline=%s",
        ticker,
        candidate.id,
        deadline.isoformat(),
    )
    return candidate


def scan_and_stage(*, since: Optional[datetime] = None, market: str = "US") -> dict[str, Any]:
    """Find qualifying buys and stage confirmation windows."""
    if not current_app.config.get("DEEP_DIVE_BRIDGE_ENABLED", True):
        return {"enabled": False, "staged": 0, "skipped": 0}

    buys = find_qualifying_buys(since=since, market=market)
    staged = 0
    skipped = 0
    seen_tickers: set[str] = set()
    # Prefer highest-value buy per ticker in this batch.
    buys_sorted = sorted(buys, key=lambda r: r.total_value or 0, reverse=True)
    for tx in buys_sorted:
        ticker = (tx.ticker or "").upper()
        if not ticker or ticker in seen_tickers:
            continue
        seen_tickers.add(ticker)
        existed = _active_for_ticker(ticker, market) is not None
        result = stage_candidate_from_tx(tx)
        if result is None:
            skipped += 1
        elif existed:
            skipped += 1
        else:
            staged += 1
    return {
        "enabled": True,
        "qualifying_buys": len(buys),
        "staged": staged,
        "skipped": skipped,
        "tickers": sorted(seen_tickers),
    }


def revive_backlog(*, now: Optional[datetime] = None) -> dict[str, Any]:
    """Move due backlog items back into a fresh confirmation window."""
    if not current_app.config.get("DEEP_DIVE_BRIDGE_ENABLED", True):
        return {"revived": 0}

    moment = now or utcnow()
    seconds = int(current_app.config.get("DEEP_DIVE_CONFIRM_SECONDS", 60))
    due = (
        DeepDiveCandidate.query.filter(
            DeepDiveCandidate.status == STATUS_BACKLOG,
            or_(
                DeepDiveCandidate.retry_after.is_(None),
                DeepDiveCandidate.retry_after <= moment,
            ),
        )
        .order_by(DeepDiveCandidate.id.asc())
        .all()
    )
    revived = 0
    for candidate in due:
        if _has_recent_push(candidate.ticker, candidate.market):
            candidate.status = STATUS_SKIPPED
            candidate.error_message = "Skipped: cooldown after a recent push"
            candidate.updated_at = moment
            continue
        candidate.status = STATUS_PENDING
        candidate.confirm_deadline_at = moment + timedelta(seconds=max(seconds, 5))
        candidate.retry_after = None
        candidate.updated_at = moment
        candidate.error_message = None
        db.session.flush()
        try:
            note_id = _create_in_app_notification(candidate, seconds=seconds)
            candidate.notification_id = note_id
        except Exception:  # noqa: BLE001
            logger.exception("Notify failed on backlog revive %s", candidate.ticker)
        try:
            _notify_external(candidate, seconds=seconds)
        except Exception:  # noqa: BLE001
            logger.exception("ntfy failed on backlog revive %s", candidate.ticker)
        revived += 1
    db.session.commit()
    return {"revived": revived}


def research_agent_healthy() -> bool:
    base = str(current_app.config.get("DEEP_DIVE_RESEARCH_URL", "http://127.0.0.1:8000")).rstrip("/")
    try:
        resp = requests.get(f"{base}/health", timeout=4)
        return resp.ok
    except Exception:  # noqa: BLE001
        return False


def push_candidate(candidate: DeepDiveCandidate) -> DeepDiveCandidate:
    """POST ticker to Equity Research Agent /api/research (full pack by default)."""
    base = str(current_app.config.get("DEEP_DIVE_RESEARCH_URL", "http://127.0.0.1:8000")).rstrip("/")
    template = current_app.config.get("DEEP_DIVE_RESEARCH_TEMPLATE", "all")
    mode = current_app.config.get("DEEP_DIVE_RESEARCH_MODE", "deep")
    pin = (current_app.config.get("DEEP_DIVE_RESEARCH_PIN") or "").strip() or None

    goal = (
        f"Institutional deep dive triggered by FilingDesk: "
        f"{candidate.officer_title or 'officer'} {candidate.insider_name or ''} "
        f"open-market buy {_format_usd(candidate.total_value)} "
        f"({candidate.company_name or candidate.ticker})."
    )
    payload: dict[str, Any] = {
        "ticker": candidate.ticker,
        "mode": mode,
        "template": template,
        "collaborative": False,
        "goal": re.sub(r"\s+", " ", goal).strip(),
    }
    if pin:
        payload["pin"] = pin

    if not research_agent_healthy():
        candidate.status = STATUS_BACKLOG
        minutes = int(current_app.config.get("DEEP_DIVE_BACKLOG_RETRY_MINUTES", 60))
        candidate.retry_after = utcnow() + timedelta(minutes=max(minutes, 5))
        candidate.error_message = f"Equity Research Agent unreachable at {base}"
        candidate.updated_at = utcnow()
        db.session.commit()
        logger.warning("Research agent down; backlog %s", candidate.ticker)
        return candidate

    try:
        resp = requests.post(f"{base}/api/research", json=payload, timeout=30)
        if resp.status_code >= 400:
            raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        candidate.status = STATUS_PUSHED
        candidate.research_job_id = str(data.get("job_id") or "")
        candidate.pushed_at = utcnow()
        candidate.updated_at = utcnow()
        candidate.error_message = None
        db.session.commit()

        note = AppNotification(
            kind="deep_dive_pushed",
            title=f"Deep dive started: {candidate.ticker}",
            body=(
                f"Pushed to Equity Research Agent (job {candidate.research_job_id}). "
                f"Template={template}."
            ),
            severity="info",
            ticker=candidate.ticker,
            payload_json=json.dumps(
                {"candidate_id": candidate.id, "job_id": candidate.research_job_id}
            )[:4000],
            is_read=False,
        )
        db.session.add(note)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()

        if current_app.config.get("DEEP_DIVE_NTFY_ENABLED", True):
            send_ntfy(
                title=f"Deep dive started: {candidate.ticker}",
                message=f"Equity Research Agent job {candidate.research_job_id}",
                priority=3,
                tags="white_check_mark",
                click=f"{base}/jobs/{candidate.research_job_id}" if candidate.research_job_id else None,
            )
        logger.info("Pushed %s → job %s", candidate.ticker, candidate.research_job_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Push failed for %s", candidate.ticker)
        candidate.status = STATUS_FAILED
        candidate.error_message = str(exc)[:1000]
        candidate.updated_at = utcnow()
        # Retry later from backlog path
        minutes = int(current_app.config.get("DEEP_DIVE_BACKLOG_RETRY_MINUTES", 60))
        candidate.status = STATUS_BACKLOG
        candidate.retry_after = utcnow() + timedelta(minutes=max(minutes, 5))
        db.session.commit()
    return candidate


def cancel_candidate(candidate_id: int) -> DeepDiveCandidate:
    """User cancelled auto-push → backlog for next hourly retry."""
    from flask import abort

    candidate = db.session.get(DeepDiveCandidate, candidate_id)
    if candidate is None:
        abort(404)
    if candidate.status != STATUS_PENDING:
        return candidate
    minutes = int(current_app.config.get("DEEP_DIVE_BACKLOG_RETRY_MINUTES", 60))
    candidate.status = STATUS_BACKLOG
    candidate.cancel_count = int(candidate.cancel_count or 0) + 1
    candidate.retry_after = utcnow() + timedelta(minutes=max(minutes, 5))
    candidate.confirm_deadline_at = None
    candidate.updated_at = utcnow()
    candidate.error_message = "Cancelled by user; will retry from backlog"
    db.session.commit()

    note = AppNotification(
        kind="deep_dive_cancelled",
        title=f"Deep dive deferred: {candidate.ticker}",
        body=f"Cancelled. Will ask again in ~{minutes} minutes.",
        severity="info",
        ticker=candidate.ticker,
        payload_json=json.dumps({"candidate_id": candidate.id})[:4000],
        is_read=False,
    )
    db.session.add(note)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
    return candidate


def confirm_now(candidate_id: int) -> DeepDiveCandidate:
    """User explicitly approved — push immediately."""
    from flask import abort

    candidate = db.session.get(DeepDiveCandidate, candidate_id)
    if candidate is None:
        abort(404)
    if candidate.status not in {STATUS_PENDING, STATUS_BACKLOG}:
        return candidate
    return push_candidate(candidate)


def process_expired_pending(*, now: Optional[datetime] = None) -> dict[str, Any]:
    """Auto-push candidates whose confirmation window has elapsed."""
    if not current_app.config.get("DEEP_DIVE_BRIDGE_ENABLED", True):
        return {"pushed": 0}

    moment = now or utcnow()
    due = (
        DeepDiveCandidate.query.filter(
            DeepDiveCandidate.status == STATUS_PENDING,
            DeepDiveCandidate.confirm_deadline_at.isnot(None),
            DeepDiveCandidate.confirm_deadline_at <= moment,
        )
        .order_by(DeepDiveCandidate.confirm_deadline_at.asc())
        .all()
    )
    pushed = 0
    for candidate in due:
        push_candidate(candidate)
        if candidate.status == STATUS_PUSHED:
            pushed += 1
    return {"due": len(due), "pushed": pushed}


def run_post_sync_bridge(*, sync_started_at: Optional[datetime] = None) -> dict[str, Any]:
    """Hook after insider sync: revive backlog, stage new buys, push expired."""
    if not current_app.config.get("DEEP_DIVE_BRIDGE_ENABLED", True):
        return {"enabled": False}

    revived = revive_backlog()
    staged = scan_and_stage(since=sync_started_at, market="US")
    expired = process_expired_pending()
    return {"enabled": True, "revived": revived, "staged": staged, "expired": expired}


def list_candidates(*, status: Optional[str] = None, limit: int = 50) -> list[dict]:
    query = DeepDiveCandidate.query
    if status:
        query = query.filter_by(status=status)
    rows = (
        query.order_by(DeepDiveCandidate.created_at.desc(), DeepDiveCandidate.id.desc())
        .limit(max(1, min(limit, 200)))
        .all()
    )
    return [row.to_dict() for row in rows]


def pending_summary() -> dict[str, Any]:
    pending = (
        DeepDiveCandidate.query.filter_by(status=STATUS_PENDING)
        .order_by(DeepDiveCandidate.confirm_deadline_at.asc())
        .all()
    )
    backlog = DeepDiveCandidate.query.filter_by(status=STATUS_BACKLOG).count()
    return {
        "pending": [p.to_dict() for p in pending],
        "backlog_count": backlog,
        "server_time": utcnow().isoformat(),
        "research_url": current_app.config.get("DEEP_DIVE_RESEARCH_URL"),
        "research_reachable": research_agent_healthy()
        if current_app.config.get("DEEP_DIVE_BRIDGE_ENABLED", True)
        else False,
        "enabled": bool(current_app.config.get("DEEP_DIVE_BRIDGE_ENABLED", True)),
        "confirm_seconds": int(current_app.config.get("DEEP_DIVE_CONFIRM_SECONDS", 60)),
        "min_value_usd": float(current_app.config.get("DEEP_DIVE_MIN_VALUE_USD", 500_000)),
    }

"""Bridge: large officer buys → Equity Research Agent overnight deep-dive queue.

Flow
----
1. After US insider sync, scan new open-market officer buys >= DEEP_DIVE_MIN_VALUE_USD.
2. Skip tickers already queued / running / researched on the Equity agent.
3. Immediately ``POST /api/queue`` with overnight policy (parked, not started).
4. Research runs only when you click Start overnight on the Equity queue.
5. By default never re-queue a ticker after a successful push (DEEP_DIVE_ONCE_PER_TICKER).
   Later qualifying buys for that ticker are stored as ``followup`` rows for the Follow-ups view
   (optional timed cooldown only when once-per-ticker is off).
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
from app.utils.helpers import is_management_insider, is_management_title

logger = logging.getLogger(__name__)

STATUS_PENDING = "pending_confirm"
STATUS_BACKLOG = "backlog"
STATUS_PUSHED = "pushed"
STATUS_FAILED = "failed"
STATUS_SKIPPED = "skipped"
STATUS_FOLLOWUP = "followup"


def _repo_data_dir():
    from pathlib import Path

    # backend/app/services/this_file.py → repo root / data
    return Path(__file__).resolve().parents[3] / "data"


def resolve_action_base_url() -> str:
    """URL ntfy action buttons hit (laptop ntfy desktop or phone via tunnel)."""
    configured = (current_app.config.get("DEEP_DIVE_PUBLIC_BASE_URL") or "").strip().rstrip("/")
    if configured:
        return configured
    tunnel_file = _repo_data_dir() / "tunnel_url.txt"
    try:
        if tunnel_file.is_file():
            url = tunnel_file.read_text(encoding="utf-8").strip().rstrip("/")
            if url.startswith("http"):
                return url
    except OSError:
        logger.debug("Could not read tunnel_url.txt", exc_info=True)
    return "http://127.0.0.1:5000"


def research_ticker_status(ticker: str) -> dict[str, Any]:
    """Ask Equity Research Agent if ticker is queued / already researched."""
    base = str(current_app.config.get("DEEP_DIVE_RESEARCH_URL", "http://127.0.0.1:8000")).rstrip("/")
    ticker = (ticker or "").upper().strip()
    if not ticker:
        return {"should_skip": False, "reachable": False}
    try:
        resp = requests.get(f"{base}/api/tickers/{ticker}/status", timeout=6)
        if resp.status_code == 404:
            return {"should_skip": False, "reachable": True, "legacy": True}
        resp.raise_for_status()
        data = resp.json()
        data["reachable"] = True
        return data
    except Exception as exc:  # noqa: BLE001
        logger.warning("Research ticker status failed for %s: %s", ticker, exc)
        return {"should_skip": False, "reachable": False, "error": str(exc)}


def should_skip_ticker(ticker: str) -> tuple[bool, str | None]:
    """True when research agent already has this ticker queued or researched."""
    if not current_app.config.get("DEEP_DIVE_SKIP_IF_RESEARCHED", True):
        status = research_ticker_status(ticker)
        if status.get("queued_or_active") or status.get("in_overnight_queue"):
            return True, status.get("skip_reason") or "already active in research agent"
        return False, None

    status = research_ticker_status(ticker)
    if status.get("should_skip"):
        return True, status.get("skip_reason") or "already covered by research agent"
    # If status API missing (older agent), still avoid obvious active queue via /api/queue
    if status.get("legacy") or not status.get("reachable"):
        return False, None
    return False, None


def _officer_keywords() -> list[str]:
    raw = current_app.config.get(
        "DEEP_DIVE_OFFICER_TITLE_KEYWORDS",
        "ceo,cfo,coo,cto,chief,president,managing director,general counsel,controller,treasurer",
    )
    return [part.strip().lower() for part in str(raw).split(",") if part.strip()]


def is_management_officer(tx: InsiderTransaction) -> bool:
    """True when the filer is an officer / C-suite / named management role."""
    if is_management_insider(
        is_officer=bool(tx.is_officer),
        officer_title=tx.officer_title,
        relationship=tx.relationship,
    ):
        return True
    title = (tx.officer_title or tx.relationship or "").strip()
    if not title:
        return False
    # Extra keywords from DEEP_DIVE_OFFICER_TITLE_KEYWORDS beyond the shared list.
    for keyword in _officer_keywords():
        if is_management_title(keyword):
            continue
        lowered = title.lower()
        if " " in keyword:
            if keyword in lowered:
                return True
            continue
        if re.search(rf"(?<![a-z]){re.escape(keyword)}(?![a-z])", lowered):
            return True
    return False


def _format_usd(value: Optional[float]) -> str:
    if value is None:
        return "$?"
    return f"${value:,.0f}"


def _cooldown_cutoff() -> datetime:
    hours = int(current_app.config.get("DEEP_DIVE_COOLDOWN_HOURS", 72))
    return utcnow() - timedelta(hours=max(hours, 1))


def _once_per_ticker() -> bool:
    return bool(current_app.config.get("DEEP_DIVE_ONCE_PER_TICKER", True))


def _has_pushed_ticker(ticker: str, market: str = "US") -> bool:
    """True when this ticker was already pushed to Equity Research."""
    query = DeepDiveCandidate.query.filter(
        DeepDiveCandidate.market == market,
        DeepDiveCandidate.ticker == ticker.upper(),
        DeepDiveCandidate.status == STATUS_PUSHED,
        DeepDiveCandidate.pushed_at.isnot(None),
    )
    if not _once_per_ticker():
        query = query.filter(DeepDiveCandidate.pushed_at >= _cooldown_cutoff())
    return query.order_by(DeepDiveCandidate.pushed_at.desc()).first() is not None


def _followup_exists_for_tx(tx: InsiderTransaction) -> bool:
    ticker = (tx.ticker or "").strip().upper()
    market = (tx.market or "US").upper()
    if tx.accession_number:
        hit = (
            DeepDiveCandidate.query.filter_by(
                market=market,
                ticker=ticker,
                status=STATUS_FOLLOWUP,
                accession_number=tx.accession_number,
            )
            .order_by(DeepDiveCandidate.created_at.desc())
            .first()
        )
        if hit:
            return True
    rows = (
        DeepDiveCandidate.query.filter_by(market=market, ticker=ticker, status=STATUS_FOLLOWUP)
        .order_by(DeepDiveCandidate.created_at.desc())
        .limit(40)
        .all()
    )
    for row in rows:
        try:
            ids = json.loads(row.transaction_ids_json or "[]")
        except json.JSONDecodeError:
            ids = []
        if tx.id in ids:
            return True
    return False


def record_followup_from_tx(tx: InsiderTransaction) -> Optional[DeepDiveCandidate]:
    """Store a later qualifying buy for an already-pushed ticker (no Equity re-queue)."""
    ticker = (tx.ticker or "").strip().upper()
    if not ticker:
        return None
    if _followup_exists_for_tx(tx):
        return None

    prior = (
        DeepDiveCandidate.query.filter(
            DeepDiveCandidate.market == (tx.market or "US").upper(),
            DeepDiveCandidate.ticker == ticker,
            DeepDiveCandidate.status == STATUS_PUSHED,
            DeepDiveCandidate.pushed_at.isnot(None),
        )
        .order_by(DeepDiveCandidate.pushed_at.desc())
        .first()
    )
    prior_note = ""
    if prior and prior.pushed_at:
        prior_note = f" Prior deep dive pushed {prior.pushed_at.date().isoformat()}."

    followup = DeepDiveCandidate(
        market=(tx.market or "US").upper(),
        ticker=ticker,
        company_name=tx.company_name,
        insider_name=tx.insider_name,
        officer_title=tx.officer_title or tx.relationship,
        total_value=tx.total_value,
        transaction_ids_json=json.dumps([tx.id]),
        accession_number=tx.accession_number,
        source_url=tx.source_url,
        status=STATUS_FOLLOWUP,
        error_message=f"Already deep-dived; recorded as follow-up only.{prior_note}".strip(),
        cancel_count=0,
    )
    db.session.add(followup)
    db.session.commit()

    try:
        title = f"Follow-up buy: {ticker}"
        body = (
            f"{followup.officer_title or 'Officer'} {followup.insider_name or ''} "
            f"bought {_format_usd(followup.total_value)} of {followup.company_name or ticker}."
            f"{prior_note} Not re-queued for deep dive — see Follow-ups."
        )
        note = AppNotification(
            kind="deep_dive_followup",
            title=title[:255],
            body=body.strip(),
            severity="info",
            ticker=ticker,
            payload_json=json.dumps(
                {
                    "candidate_id": followup.id,
                    "total_value": followup.total_value,
                    "officer_title": followup.officer_title,
                    "insider_name": followup.insider_name,
                    "accession_number": followup.accession_number,
                    "source_url": followup.source_url,
                    "prior_pushed_at": prior.pushed_at.isoformat() if prior and prior.pushed_at else None,
                }
            ),
        )
        db.session.add(note)
        db.session.commit()
        followup.notification_id = note.id
        db.session.commit()
    except Exception:  # noqa: BLE001
        logger.exception("Failed to create follow-up notification for %s", ticker)

    logger.info("Recorded deep-dive follow-up for %s id=%s", ticker, followup.id)
    return followup


def list_followups(*, market: str = "US", limit: int = 50) -> list[dict[str, Any]]:
    rows = (
        DeepDiveCandidate.query.filter_by(market=market.upper(), status=STATUS_FOLLOWUP)
        .order_by(DeepDiveCandidate.created_at.desc())
        .limit(max(1, min(limit, 200)))
        .all()
    )
    return [row.to_dict() for row in rows]


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
        else current_app.config.get("DEEP_DIVE_MIN_VALUE_USD", 100_000)
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
        f"Parked on the Equity Research queue — start it there when you want; nothing auto-runs."
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
    base = resolve_action_base_url()
    send_ntfy(
        title=f"FilingDesk → deep dive {candidate.ticker}",
        message=(
            f"{candidate.officer_title or 'Officer'} bought "
            f"{_format_usd(candidate.total_value)}. "
            f"Parked on Equity Research queue (not started). "
            f"Open the queue and click Start overnight when you want to run it."
        ),
        priority=4,
        tags="inbox_tray,chart_with_upwards_trend",
        click=base,
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

    if _has_pushed_ticker(ticker, tx.market or "US"):
        reason = "already pushed (once per ticker)" if _once_per_ticker() else "within cooldown"
        logger.info("Skip deep-dive queue for %s: %s — recording follow-up", ticker, reason)
        record_followup_from_tx(tx)
        return None

    skip, reason = should_skip_ticker(ticker)
    if skip:
        logger.info("Skip %s: %s", ticker, reason)
        existing_skip = (
            DeepDiveCandidate.query.filter_by(
                market=(tx.market or "US").upper(),
                ticker=ticker,
                status=STATUS_SKIPPED,
            )
            .order_by(DeepDiveCandidate.created_at.desc())
            .first()
        )
        if existing_skip:
            existing_skip.error_message = reason
            existing_skip.updated_at = utcnow()
            db.session.commit()
            return None
        skipped = DeepDiveCandidate(
            market=(tx.market or "US").upper(),
            ticker=ticker,
            company_name=tx.company_name,
            insider_name=tx.insider_name,
            officer_title=tx.officer_title or tx.relationship,
            total_value=tx.total_value,
            transaction_ids_json=json.dumps([tx.id]),
            accession_number=tx.accession_number,
            source_url=tx.source_url,
            status=STATUS_SKIPPED,
            error_message=reason,
            cancel_count=0,
        )
        db.session.add(skipped)
        db.session.commit()
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
        "Staged deep-dive candidate %s id=%s — pushing to parked Equity queue",
        ticker,
        candidate.id,
    )
    return push_candidate(candidate)


def scan_and_stage(*, since: Optional[datetime] = None, market: str = "US") -> dict[str, Any]:
    """Find qualifying buys and stage confirmation windows."""
    if not current_app.config.get("DEEP_DIVE_BRIDGE_ENABLED", True):
        return {"enabled": False, "staged": 0, "skipped": 0}

    buys = find_qualifying_buys(since=since, market=market)
    staged = 0
    skipped = 0
    followups = 0
    seen_tickers: set[str] = set()
    # Prefer highest-value buy per ticker in this batch.
    buys_sorted = sorted(buys, key=lambda r: r.total_value or 0, reverse=True)
    for tx in buys_sorted:
        ticker = (tx.ticker or "").upper()
        if not ticker or ticker in seen_tickers:
            continue
        seen_tickers.add(ticker)
        existed = _active_for_ticker(ticker, market) is not None
        already_pushed = _has_pushed_ticker(ticker, market)
        result = stage_candidate_from_tx(tx)
        if result is None:
            if already_pushed:
                followups += 1
            else:
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
        "followups": followups,
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
        if _has_pushed_ticker(candidate.ticker, candidate.market):
            candidate.status = STATUS_SKIPPED
            candidate.error_message = (
                "Skipped: ticker already deep-dived"
                if _once_per_ticker()
                else "Skipped: cooldown after a recent push"
            )
            candidate.updated_at = moment
            continue
        skip, reason = should_skip_ticker(candidate.ticker)
        if skip:
            candidate.status = STATUS_SKIPPED
            candidate.error_message = reason or "Skipped: already covered by research agent"
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
            db.session.flush()
            _notify_external(candidate, seconds=seconds)
        except Exception:  # noqa: BLE001
            logger.exception("Notify failed on backlog revive %s", candidate.ticker)
        push_candidate(candidate)
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
    """Enqueue ticker on Equity Research Agent overnight queue (parked, not started)."""
    base = str(current_app.config.get("DEEP_DIVE_RESEARCH_URL", "http://127.0.0.1:8000")).rstrip("/")
    template = current_app.config.get("DEEP_DIVE_RESEARCH_TEMPLATE", "all")
    mode = current_app.config.get("DEEP_DIVE_RESEARCH_MODE", "deep")
    pin = (current_app.config.get("DEEP_DIVE_RESEARCH_PIN") or "").strip() or None

    skip, reason = should_skip_ticker(candidate.ticker)
    if skip:
        candidate.status = STATUS_SKIPPED
        candidate.error_message = reason or "Skipped at push: already covered"
        candidate.updated_at = utcnow()
        db.session.commit()
        logger.info("Skip push %s: %s", candidate.ticker, reason)
        return candidate

    goal = (
        f"Institutional deep dive triggered by FilingDesk: "
        f"{candidate.officer_title or 'officer'} {candidate.insider_name or ''} "
        f"open-market buy {_format_usd(candidate.total_value)} "
        f"({candidate.company_name or candidate.ticker})."
    )
    goal = re.sub(r"\s+", " ", goal).strip()

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
        payload: dict[str, Any] = {
            "tickers": candidate.ticker,
            "mode": mode,
            "template": template,
            "goal": goal,
            "from_scratch": False,
            "start_policy": "overnight",
            "confirm_seconds": 0,
        }
        if pin:
            payload["pin"] = pin
        resp = requests.post(f"{base}/api/queue", json=payload, timeout=30)
        if resp.status_code >= 400:
            raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        skipped = data.get("skipped") or []
        if data.get("added", 0) == 0 and skipped:
            candidate.status = STATUS_SKIPPED
            candidate.error_message = skipped[0].get("reason") or "Skipped by research queue dedupe"
            candidate.updated_at = utcnow()
            db.session.commit()
            return candidate
        created_items = data.get("created") or []
        queue_id = ""
        if created_items and isinstance(created_items[0], dict):
            queue_id = str(created_items[0].get("id") or "")
        if not queue_id:
            tickers = data.get("tickers") or [candidate.ticker]
            queue_id = f"queue:{tickers[0]}"
        candidate.status = STATUS_PUSHED
        candidate.research_job_id = queue_id
        candidate.pushed_at = utcnow()
        candidate.updated_at = utcnow()
        candidate.error_message = None
        db.session.commit()
        dest = "queue (parked until Start overnight)"
        job_ref = candidate.research_job_id
        use_queue = True

        note = AppNotification(
            kind="deep_dive_pushed",
            title=f"Deep dive queued: {candidate.ticker}",
            body=f"Sent to Equity Research Agent {dest}. Template={template}.",
            severity="info",
            ticker=candidate.ticker,
            payload_json=json.dumps(
                {"candidate_id": candidate.id, "job_id": candidate.research_job_id, "via": "queue" if use_queue else "research"}
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
                title=f"Deep dive queued: {candidate.ticker}",
                message=f"Equity Research Agent {dest}",
                priority=3,
                tags="white_check_mark",
                click=f"{base}/queue" if use_queue else (f"{base}/jobs/{job_ref}" if job_ref else base),
            )
        logger.info("Pushed %s → %s", candidate.ticker, dest)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Push failed for %s", candidate.ticker)
        minutes = int(current_app.config.get("DEEP_DIVE_BACKLOG_RETRY_MINUTES", 60))
        candidate.status = STATUS_BACKLOG
        candidate.error_message = str(exc)[:1000]
        candidate.retry_after = utcnow() + timedelta(minutes=max(minutes, 5))
        candidate.updated_at = utcnow()
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
    followups = DeepDiveCandidate.query.filter_by(status=STATUS_FOLLOWUP).count()
    return {
        "pending": [p.to_dict() for p in pending],
        "backlog_count": backlog,
        "followup_count": followups,
        "server_time": utcnow().isoformat(),
        "research_url": current_app.config.get("DEEP_DIVE_RESEARCH_URL"),
        "research_reachable": research_agent_healthy()
        if current_app.config.get("DEEP_DIVE_BRIDGE_ENABLED", True)
        else False,
        "enabled": bool(current_app.config.get("DEEP_DIVE_BRIDGE_ENABLED", True)),
        "confirm_seconds": int(current_app.config.get("DEEP_DIVE_CONFIRM_SECONDS", 60)),
        "min_value_usd": float(current_app.config.get("DEEP_DIVE_MIN_VALUE_USD", 100_000)),
        "once_per_ticker": _once_per_ticker(),
    }

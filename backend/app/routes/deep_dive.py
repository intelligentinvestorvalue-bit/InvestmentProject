"""API for officer-buy → Equity Research Agent deep-dive bridge."""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.services import deep_dive_bridge as bridge

deep_dive_bp = Blueprint("deep_dive", __name__)


def _as_int(value, default: int) -> int:
    try:
        return int(value) if value is not None else default
    except ValueError:
        return default


@deep_dive_bp.get("/deep-dive/pending")
def pending():
    return jsonify(bridge.pending_summary())


@deep_dive_bp.get("/deep-dive/candidates")
def candidates():
    status = (request.args.get("status") or "").strip() or None
    limit = _as_int(request.args.get("limit"), 50)
    return jsonify({"items": bridge.list_candidates(status=status, limit=limit)})


@deep_dive_bp.post("/deep-dive/<int:candidate_id>/cancel")
def cancel(candidate_id: int):
    row = bridge.cancel_candidate(candidate_id)
    return jsonify(row.to_dict())


@deep_dive_bp.post("/deep-dive/<int:candidate_id>/confirm")
def confirm(candidate_id: int):
    row = bridge.confirm_now(candidate_id)
    return jsonify(row.to_dict())


@deep_dive_bp.post("/deep-dive/tick")
def tick():
    """Process expired confirmation windows (also run by scheduler)."""
    result = bridge.process_expired_pending()
    revived = bridge.revive_backlog()
    return jsonify({"expired": result, "revived": revived, "pending": bridge.pending_summary()})


@deep_dive_bp.post("/deep-dive/scan")
def scan():
    """Manual scan of recent insider buys (does not re-fetch SEC)."""
    hours = _as_int(request.args.get("hours") or (request.json or {}).get("hours"), 24)
    from datetime import timedelta

    from app.models import utcnow

    since = utcnow() - timedelta(hours=max(hours, 1))
    staged = bridge.scan_and_stage(since=since, market="US")
    return jsonify({"staged": staged, "pending": bridge.pending_summary()})

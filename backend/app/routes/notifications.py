"""In-app notification routes."""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.extensions import db
from app.models import AppNotification

notifications_bp = Blueprint("notifications", __name__)


def _as_int(value, default: int) -> int:
    try:
        return int(value) if value is not None else default
    except ValueError:
        return default


@notifications_bp.get("/notifications")
def list_notifications():
    unread_only = str(request.args.get("unread_only") or "").lower() in {"1", "true", "yes"}
    kind = (request.args.get("kind") or "").strip().lower()
    page = max(_as_int(request.args.get("page"), 1), 1)
    page_size = min(max(_as_int(request.args.get("page_size"), 30), 1), 100)

    query = AppNotification.query
    if unread_only:
        query = query.filter_by(is_read=False)
    if kind:
        query = query.filter_by(kind=kind)

    total = query.count()
    unread = AppNotification.query.filter_by(is_read=False).count()
    items = (
        query.order_by(AppNotification.created_at.desc(), AppNotification.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return jsonify(
        {
            "total": total,
            "unread": unread,
            "page": page,
            "page_size": page_size,
            "items": [item.to_dict() for item in items],
        }
    )


@notifications_bp.post("/notifications/<int:notification_id>/read")
def mark_read(notification_id: int):
    note = AppNotification.query.get_or_404(notification_id)
    note.is_read = True
    db.session.commit()
    return jsonify(note.to_dict())


@notifications_bp.post("/notifications/read-all")
def mark_all_read():
    updated = AppNotification.query.filter_by(is_read=False).update({"is_read": True})
    db.session.commit()
    return jsonify({"ok": True, "updated": updated})

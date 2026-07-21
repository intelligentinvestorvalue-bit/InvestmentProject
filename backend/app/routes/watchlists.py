"""Watchlist / saved screen routes."""

from __future__ import annotations

from datetime import datetime, timezone

from flask import Blueprint, jsonify, request
from sqlalchemy import func

from app.extensions import db
from app.models import Company, InsiderTransaction, Watchlist, WatchlistItem

watchlists_bp = Blueprint("watchlists", __name__)


def _as_int(value, default: int) -> int:
    try:
        return int(value) if value is not None else default
    except ValueError:
        return default


@watchlists_bp.get("/watchlists")
def list_watchlists():
    market = (request.args.get("market") or "").upper()
    query = Watchlist.query
    if market in {"US", "IN"}:
        query = query.filter_by(market=market)
    items = query.order_by(Watchlist.updated_at.desc()).all()
    return jsonify({"items": [w.to_dict(include_items=False) for w in items]})


@watchlists_bp.post("/watchlists")
def create_watchlist():
    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip()
    market = (body.get("market") or "US").upper()
    if not name:
        return jsonify({"error": "name is required"}), 400
    if market not in {"US", "IN"}:
        return jsonify({"error": "market must be US or IN"}), 400
    wl = Watchlist(name=name, market=market)
    db.session.add(wl)
    db.session.commit()
    return jsonify(wl.to_dict()), 201


@watchlists_bp.get("/watchlists/<int:watchlist_id>")
def get_watchlist(watchlist_id: int):
    wl = Watchlist.query.get_or_404(watchlist_id)
    payload = wl.to_dict()
    # Attach recent insider activity counts per ticker.
    activity = []
    for item in wl.items:
        q = InsiderTransaction.query.filter_by(market=wl.market, ticker=item.ticker)
        activity.append(
            {
                **item.to_dict(),
                "insider_count": q.count(),
                "buy_count": q.filter_by(transaction_side="buy").count(),
                "sell_count": q.filter_by(transaction_side="sell").count(),
                "last_tx_date": (
                    db.session.query(func.max(InsiderTransaction.transaction_date))
                    .filter_by(market=wl.market, ticker=item.ticker)
                    .scalar()
                ),
            }
        )
    for row in activity:
        if row["last_tx_date"]:
            row["last_tx_date"] = row["last_tx_date"].isoformat()
    payload["items"] = activity
    return jsonify(payload)


@watchlists_bp.patch("/watchlists/<int:watchlist_id>")
def rename_watchlist(watchlist_id: int):
    wl = Watchlist.query.get_or_404(watchlist_id)
    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400
    wl.name = name
    wl.updated_at = datetime.now(timezone.utc)
    db.session.commit()
    return jsonify(wl.to_dict())


@watchlists_bp.delete("/watchlists/<int:watchlist_id>")
def delete_watchlist(watchlist_id: int):
    wl = Watchlist.query.get_or_404(watchlist_id)
    db.session.delete(wl)
    db.session.commit()
    return jsonify({"ok": True})


@watchlists_bp.post("/watchlists/<int:watchlist_id>/items")
def add_watchlist_item(watchlist_id: int):
    wl = Watchlist.query.get_or_404(watchlist_id)
    body = request.get_json(silent=True) or {}
    ticker = (body.get("ticker") or "").strip().upper()
    if not ticker:
        return jsonify({"error": "ticker is required"}), 400
    existing = WatchlistItem.query.filter_by(watchlist_id=wl.id, ticker=ticker).first()
    if existing:
        return jsonify(existing.to_dict())

    company = Company.query.filter_by(market=wl.market, ticker=ticker).first()
    item = WatchlistItem(
        watchlist_id=wl.id,
        ticker=ticker,
        company_name=(body.get("company_name") or (company.name if company else None)),
        notes=(body.get("notes") or None),
    )
    db.session.add(item)
    wl.updated_at = datetime.now(timezone.utc)
    db.session.commit()
    return jsonify(item.to_dict()), 201


@watchlists_bp.delete("/watchlists/<int:watchlist_id>/items/<int:item_id>")
def remove_watchlist_item(watchlist_id: int, item_id: int):
    item = WatchlistItem.query.filter_by(id=item_id, watchlist_id=watchlist_id).first_or_404()
    wl = item.watchlist
    db.session.delete(item)
    wl.updated_at = datetime.now(timezone.utc)
    db.session.commit()
    return jsonify({"ok": True})

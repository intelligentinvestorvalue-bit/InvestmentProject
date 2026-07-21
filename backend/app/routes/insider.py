"""Insider activity API routes."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from flask import Blueprint, current_app, jsonify, request
from sqlalchemy import func, or_

from app.extensions import db
from app.models import InsiderTransaction, SyncRun
from app.services.india_provider import list_india_insider_transactions
from app.services.sec_form4 import sync_us_insider_feed
from app.utils.helpers import parse_date

insider_bp = Blueprint("insider", __name__)


def _as_bool(value: Optional[str]) -> Optional[bool]:
    if value is None or value == "":
        return None
    return value.strip().lower() in {"1", "true", "yes", "y"}


def _as_float(value: Optional[str]) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _as_int(value: Optional[str], default: int) -> int:
    try:
        return int(value) if value is not None else default
    except ValueError:
        return default


@insider_bp.get("/insider/transactions")
def list_insider_transactions():
    market = (request.args.get("market") or "US").upper()
    if market == "IN":
        return jsonify(list_india_insider_transactions(**request.args.to_dict()))
    if market != "US":
        return jsonify({"error": f"Unsupported market: {market}"}), 400

    query = InsiderTransaction.query.filter_by(market="US")

    side = (request.args.get("side") or "").strip().lower()
    if side in {"buy", "sell"}:
        query = query.filter(InsiderTransaction.transaction_side == side)

    code = (request.args.get("transaction_code") or "").strip().upper()
    if code in {"P", "S"}:
        query = query.filter(InsiderTransaction.transaction_code == code)

    ticker = (request.args.get("ticker") or "").strip().upper()
    if ticker:
        query = query.filter(InsiderTransaction.ticker == ticker)

    company = (request.args.get("company") or "").strip()
    if company:
        query = query.filter(InsiderTransaction.company_name.ilike(f"%{company}%"))

    insider_name = (request.args.get("insider_name") or "").strip()
    if insider_name:
        query = query.filter(InsiderTransaction.insider_name.ilike(f"%{insider_name}%"))

    relationship = (request.args.get("relationship") or "").strip()
    if relationship:
        query = query.filter(InsiderTransaction.relationship.ilike(f"%{relationship}%"))

    officer_title = (request.args.get("officer_title") or "").strip()
    if officer_title:
        query = query.filter(InsiderTransaction.officer_title.ilike(f"%{officer_title}%"))

    is_director = _as_bool(request.args.get("is_director"))
    if is_director is not None:
        query = query.filter(InsiderTransaction.is_director.is_(is_director))

    is_officer = _as_bool(request.args.get("is_officer"))
    if is_officer is not None:
        query = query.filter(InsiderTransaction.is_officer.is_(is_officer))

    is_ten = _as_bool(request.args.get("is_ten_percent_owner"))
    if is_ten is not None:
        query = query.filter(InsiderTransaction.is_ten_percent_owner.is_(is_ten))

    # Convenience role filter: director | officer | ten_percent | other
    role = (request.args.get("role") or "").strip().lower()
    if role == "director":
        query = query.filter(InsiderTransaction.is_director.is_(True))
    elif role == "officer":
        query = query.filter(InsiderTransaction.is_officer.is_(True))
    elif role in {"ten_percent", "10_percent", "owner"}:
        query = query.filter(InsiderTransaction.is_ten_percent_owner.is_(True))
    elif role == "other":
        query = query.filter(
            InsiderTransaction.is_director.is_(False),
            InsiderTransaction.is_officer.is_(False),
            InsiderTransaction.is_ten_percent_owner.is_(False),
        )

    ownership_form = (request.args.get("ownership_form") or "").strip().upper()
    if ownership_form in {"D", "I"}:
        query = query.filter(InsiderTransaction.ownership_form == ownership_form)

    tx_from = parse_date(request.args.get("transaction_date_from"))
    if tx_from:
        query = query.filter(InsiderTransaction.transaction_date >= tx_from)
    tx_to = parse_date(request.args.get("transaction_date_to"))
    if tx_to:
        query = query.filter(InsiderTransaction.transaction_date <= tx_to)

    filing_from = parse_date(request.args.get("filing_date_from"))
    if filing_from:
        query = query.filter(InsiderTransaction.filing_date >= filing_from)
    filing_to = parse_date(request.args.get("filing_date_to"))
    if filing_to:
        query = query.filter(InsiderTransaction.filing_date <= filing_to)

    min_shares = _as_float(request.args.get("min_shares"))
    if min_shares is not None:
        query = query.filter(InsiderTransaction.shares >= min_shares)
    max_shares = _as_float(request.args.get("max_shares"))
    if max_shares is not None:
        query = query.filter(InsiderTransaction.shares <= max_shares)

    min_price = _as_float(request.args.get("min_price"))
    if min_price is not None:
        query = query.filter(InsiderTransaction.price_per_share >= min_price)
    max_price = _as_float(request.args.get("max_price"))
    if max_price is not None:
        query = query.filter(InsiderTransaction.price_per_share <= max_price)

    min_value = _as_float(request.args.get("min_value"))
    if min_value is not None:
        query = query.filter(InsiderTransaction.total_value >= min_value)
    max_value = _as_float(request.args.get("max_value"))
    if max_value is not None:
        query = query.filter(InsiderTransaction.total_value <= max_value)

    q = (request.args.get("q") or "").strip()
    if q:
        like = f"%{q}%"
        query = query.filter(
            or_(
                InsiderTransaction.ticker.ilike(like),
                InsiderTransaction.company_name.ilike(like),
                InsiderTransaction.insider_name.ilike(like),
                InsiderTransaction.relationship.ilike(like),
            )
        )

    sort = (request.args.get("sort") or "filing_date_desc").strip().lower()
    sort_map = {
        "filing_date_desc": InsiderTransaction.filing_date.desc(),
        "filing_date_asc": InsiderTransaction.filing_date.asc(),
        "transaction_date_desc": InsiderTransaction.transaction_date.desc(),
        "transaction_date_asc": InsiderTransaction.transaction_date.asc(),
        "value_desc": InsiderTransaction.total_value.desc(),
        "value_asc": InsiderTransaction.total_value.asc(),
        "shares_desc": InsiderTransaction.shares.desc(),
        "shares_asc": InsiderTransaction.shares.asc(),
        "price_desc": InsiderTransaction.price_per_share.desc(),
        "price_asc": InsiderTransaction.price_per_share.asc(),
    }
    query = query.order_by(sort_map.get(sort, InsiderTransaction.filing_date.desc()), InsiderTransaction.id.desc())

    page = max(_as_int(request.args.get("page"), 1), 1)
    page_size = min(max(_as_int(request.args.get("page_size"), 50), 1), 200)
    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()

    return jsonify(
        {
            "market": "US",
            "total": total,
            "page": page,
            "page_size": page_size,
            "sort": sort,
            "items": [item.to_dict() for item in items],
            "filters_applied": {k: v for k, v in request.args.items() if k not in {"page", "page_size"}},
        }
    )


@insider_bp.get("/insider/meta")
def insider_meta():
    market = (request.args.get("market") or "US").upper()
    if market == "IN":
        return jsonify(
            {
                "market": "IN",
                "status": "planned",
                "sides": ["buy", "sell"],
                "roles": ["director", "officer", "ten_percent", "other"],
                "message": "India filters will mirror US once Phase 2 data is live.",
            }
        )

    tickers = (
        db.session.query(InsiderTransaction.ticker)
        .filter(InsiderTransaction.market == "US", InsiderTransaction.ticker.isnot(None))
        .distinct()
        .order_by(InsiderTransaction.ticker.asc())
        .limit(500)
        .all()
    )
    relationships = (
        db.session.query(InsiderTransaction.relationship)
        .filter(InsiderTransaction.market == "US", InsiderTransaction.relationship.isnot(None))
        .distinct()
        .order_by(InsiderTransaction.relationship.asc())
        .limit(200)
        .all()
    )
    titles = (
        db.session.query(InsiderTransaction.officer_title)
        .filter(InsiderTransaction.market == "US", InsiderTransaction.officer_title.isnot(None))
        .distinct()
        .order_by(InsiderTransaction.officer_title.asc())
        .limit(200)
        .all()
    )

    aggregates = db.session.query(
        func.count(InsiderTransaction.id),
        func.sum(InsiderTransaction.total_value),
        func.min(InsiderTransaction.transaction_date),
        func.max(InsiderTransaction.transaction_date),
        func.min(InsiderTransaction.filing_date),
        func.max(InsiderTransaction.filing_date),
    ).filter(InsiderTransaction.market == "US").one()

    buy_count = InsiderTransaction.query.filter_by(market="US", transaction_side="buy").count()
    sell_count = InsiderTransaction.query.filter_by(market="US", transaction_side="sell").count()
    latest_sync = SyncRun.query.filter_by(market="US").order_by(SyncRun.started_at.desc()).first()

    return jsonify(
        {
            "market": "US",
            "status": "active",
            "sides": ["buy", "sell"],
            "transaction_codes": ["P", "S"],
            "roles": ["director", "officer", "ten_percent", "other"],
            "ownership_forms": ["D", "I"],
            "sort_options": [
                "filing_date_desc",
                "filing_date_asc",
                "transaction_date_desc",
                "transaction_date_asc",
                "value_desc",
                "value_asc",
                "shares_desc",
                "shares_asc",
                "price_desc",
                "price_asc",
            ],
            "tickers": [row[0] for row in tickers if row[0]],
            "relationships": [row[0] for row in relationships if row[0]],
            "officer_titles": [row[0] for row in titles if row[0]],
            "stats": {
                "total_transactions": aggregates[0] or 0,
                "total_value": float(aggregates[1] or 0),
                "buy_count": buy_count,
                "sell_count": sell_count,
                "transaction_date_min": aggregates[2].isoformat() if aggregates[2] else None,
                "transaction_date_max": aggregates[3].isoformat() if aggregates[3] else None,
                "filing_date_min": aggregates[4].isoformat() if aggregates[4] else None,
                "filing_date_max": aggregates[5].isoformat() if aggregates[5] else None,
            },
            "latest_sync": latest_sync.to_dict() if latest_sync else None,
            "sync_max_filings_default": current_app.config["SYNC_MAX_FILINGS"],
        }
    )


@insider_bp.post("/insider/sync")
def sync_insider():
    market = (request.args.get("market") or (request.json or {}).get("market") or "US").upper()
    if market == "IN":
        return jsonify(
            {
                "market": "IN",
                "status": "planned",
                "message": "India sync is not available yet (Phase 2).",
            }
        ), 501
    if market != "US":
        return jsonify({"error": f"Unsupported market: {market}"}), 400

    body = request.get_json(silent=True) or {}
    days = _as_int(str(body.get("days", request.args.get("days", 7))), 7)
    max_filings = _as_int(
        str(body.get("max_filings", request.args.get("max_filings", current_app.config["SYNC_MAX_FILINGS"]))),
        current_app.config["SYNC_MAX_FILINGS"],
    )
    days = max(1, min(days, 30))
    max_filings = max(1, min(max_filings, 100))

    result = sync_us_insider_feed(days=days, max_filings=max_filings)
    return jsonify(result)


@insider_bp.get("/insider/sync/latest")
def latest_sync():
    market = (request.args.get("market") or "US").upper()
    run = SyncRun.query.filter_by(market=market).order_by(SyncRun.started_at.desc()).first()
    if not run:
        return jsonify({"market": market, "latest_sync": None})
    return jsonify({"market": market, "latest_sync": run.to_dict()})

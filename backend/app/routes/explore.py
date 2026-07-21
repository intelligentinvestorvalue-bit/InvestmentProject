"""Sector / company explore routes."""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.services.explore import list_companies, list_industries, list_sectors, sync_explore_metadata

explore_bp = Blueprint("explore", __name__)


def _as_int(value, default: int) -> int:
    try:
        return int(value) if value is not None else default
    except ValueError:
        return default


@explore_bp.get("/explore/sectors")
def sectors():
    market = (request.args.get("market") or "US").upper()
    return jsonify(list_sectors(market))


@explore_bp.get("/explore/industries")
def industries():
    market = (request.args.get("market") or "US").upper()
    sector = request.args.get("sector") or None
    return jsonify(list_industries(market, sector=sector))


@explore_bp.get("/explore/companies")
def companies():
    market = (request.args.get("market") or "US").upper()
    return jsonify(
        list_companies(
            market,
            sector=request.args.get("sector") or None,
            industry=request.args.get("industry") or None,
            q=request.args.get("q") or None,
            page=_as_int(request.args.get("page"), 1),
            page_size=_as_int(request.args.get("page_size"), 50),
        )
    )


@explore_bp.post("/explore/sync")
def sync_explore():
    market = (request.args.get("market") or (request.json or {}).get("market") or "US").upper()
    body = request.get_json(silent=True) or {}
    limit = _as_int(body.get("limit", request.args.get("limit", 40)), 40)
    limit = max(1, min(limit, 100))
    try:
        result = sync_explore_metadata(market, limit=limit)
        return jsonify(result)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 502

"""Financial research routes."""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.services.india_provider import get_india_financials
from app.services.market_quote import fetch_market_overview
from app.services.sec_financials import get_us_financials

financials_bp = Blueprint("financials", __name__)


@financials_bp.get("/financials/<ticker>")
def get_financials(ticker: str):
    market = (request.args.get("market") or "US").upper()
    years = request.args.get("years", "10")
    refresh = (request.args.get("refresh") or "").lower() in {"1", "true", "yes"}
    try:
        years_i = max(1, min(int(years), 20))
    except ValueError:
        years_i = 10

    try:
        if market == "US":
            payload = get_us_financials(ticker, years=years_i, refresh=refresh)
        elif market == "IN":
            payload = get_india_financials(ticker, years=years_i, refresh=refresh)
        else:
            return jsonify({"error": f"Unsupported market: {market}"}), 400
        return jsonify(payload)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 404
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 502


@financials_bp.get("/financials/<ticker>/market")
def get_market_overview(ticker: str):
    """Company overview + delayed Yahoo price history for research charting."""
    market = (request.args.get("market") or "US").upper()
    range_key = (request.args.get("range") or "1y").lower()
    refresh = (request.args.get("refresh") or "").lower() in {"1", "true", "yes"}
    if market not in {"US", "IN"}:
        return jsonify({"error": f"Unsupported market: {market}"}), 400
    try:
        return jsonify(
            fetch_market_overview(ticker, market=market, range_key=range_key, refresh=refresh)
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 502

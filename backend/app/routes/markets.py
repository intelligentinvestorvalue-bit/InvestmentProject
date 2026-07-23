"""Market metadata routes."""

from flask import Blueprint, jsonify

from app.models import InsiderTransaction
from app.services.india_provider import get_india_status

markets_bp = Blueprint("markets", __name__)


@markets_bp.get("/markets")
def list_markets():
    us_count = InsiderTransaction.query.filter_by(market="US").count()
    india = get_india_status()
    return jsonify(
        {
            "markets": [
                {
                    "code": "US",
                    "name": "United States",
                    "status": "active",
                    "features": ["insider_global_feed", "financials", "sector_explore"],
                    "cached_insider_rows": us_count,
                },
                {
                    "code": "IN",
                    "name": "India",
                    "status": india.get("status", "ready"),
                    "features": ["insider_global_feed", "financials_summary", "sector_explore"],
                    "detail": india,
                },
            ]
        }
    )

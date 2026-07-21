"""Market metadata routes."""

from flask import Blueprint, jsonify

from app.services.india_provider import get_india_status

markets_bp = Blueprint("markets", __name__)


@markets_bp.get("/markets")
def list_markets():
    return jsonify(
        {
            "markets": [
                {
                    "code": "US",
                    "name": "United States",
                    "status": "active",
                    "features": ["insider_global_feed"],
                },
                {
                    "code": "IN",
                    "name": "India",
                    "status": "planned",
                    "features": ["insider_global_feed"],
                    "detail": get_india_status(),
                },
            ]
        }
    )

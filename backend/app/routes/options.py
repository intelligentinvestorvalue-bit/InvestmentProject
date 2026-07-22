"""Unusual options activity API routes."""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

from app.services.uoa_scanner import list_uoa_alerts, run_uoa_scan

options_bp = Blueprint("options", __name__)


def _as_int(value, default: int) -> int:
    try:
        return int(value) if value is not None else default
    except ValueError:
        return default


def _as_float(value):
    if value is None or value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _as_bool(value, default: bool = False) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


@options_bp.get("/options/unusual")
def get_unusual_options():
    market = (request.args.get("market") or "US").upper()
    if market != "US":
        return jsonify(
            {
                "market": market,
                "status": "planned",
                "message": "Unusual options scanning is US-first (Yahoo chains). India F&O comes later.",
                "total": 0,
                "items": [],
            }
        )
    return jsonify(
        list_uoa_alerts(
            sentiment=request.args.get("sentiment"),
            underlying=request.args.get("underlying") or request.args.get("ticker"),
            universe=request.args.get("universe"),
            min_score=_as_float(request.args.get("min_score")),
            page=_as_int(request.args.get("page"), 1),
            page_size=_as_int(request.args.get("page_size"), 50),
        )
    )


@options_bp.post("/options/unusual/scan")
def scan_unusual_options():
    market = (request.args.get("market") or (request.json or {}).get("market") or "US").upper()
    if market != "US":
        return jsonify({"error": "UOA scan currently supports market=US only"}), 400

    body = request.get_json(silent=True) or {}
    include_watchlist = _as_bool(body.get("include_watchlist", True), True)
    include_liquid = _as_bool(body.get("include_liquid", True), True)
    max_tickers = body.get("max_tickers")
    max_tickers_i = None
    if max_tickers is not None and str(max_tickers).strip() != "":
        max_tickers_i = max(1, _as_int(max_tickers, 20))
    try:
        result = run_uoa_scan(
            include_watchlist=include_watchlist,
            include_liquid=include_liquid,
            trigger="manual",
            max_tickers=max_tickers_i,
        )
        return jsonify(result)
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 502


@options_bp.get("/options/unusual/meta")
def unusual_meta():
    return jsonify(
        {
            "market": "US",
            "source": "Yahoo Finance via yfinance (delayed chains)",
            "sentiments": ["bullish", "bearish", "mixed", "unclear"],
            "universes": ["watchlist", "liquid100"],
            "thresholds": {
                "min_volume": current_app.config.get("UOA_MIN_VOLUME"),
                "min_vol_oi": current_app.config.get("UOA_MIN_VOL_OI"),
                "min_premium": current_app.config.get("UOA_MIN_PREMIUM"),
                "max_dte": current_app.config.get("UOA_MAX_DTE"),
                "notify_min_score": current_app.config.get("UOA_NOTIFY_MIN_SCORE"),
            },
            "direction_model": [
                "Calls lean bullish; puts lean bearish",
                "Last near ask ≈ aggressive buy; near bid ≈ aggressive sell/hedge (mixed)",
            ],
            "timing": {
                "near_realtime_minutes": current_app.config.get("UOA_POLL_INTERVAL_MINUTES"),
                "eod_hour_utc": current_app.config.get("UOA_EOD_HOUR_UTC"),
            },
        }
    )

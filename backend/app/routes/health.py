"""Health check routes."""

from flask import Blueprint, jsonify

from app.services.scheduler import scheduler_status

health_bp = Blueprint("health", __name__)


@health_bp.get("/api/health")
def health():
    return jsonify({"ok": True, "service": "filingdesk", "scheduler": scheduler_status()})

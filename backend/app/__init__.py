"""FilingDesk Flask application factory."""

from __future__ import annotations

import os
from pathlib import Path

from flask import Flask
from flask_cors import CORS

from app.config import Config
from app.extensions import db


def create_app(config_class: type[Config] = Config) -> Flask:
    """Create and configure the Flask app."""
    app = Flask(__name__)
    app.config.from_object(config_class)

    if not app.config.get("SEC_USER_AGENT"):
        raise ValueError(
            "SEC_USER_AGENT is required. Set it in backend/.env "
            "(example: FilingDesk you@example.com)."
        )

    # Ensure SQLite parent directory exists for relative sqlite paths.
    db_uri = app.config["SQLALCHEMY_DATABASE_URI"]
    if db_uri.startswith("sqlite:///"):
        sqlite_path = db_uri.replace("sqlite:///", "", 1)
        if not sqlite_path.startswith(":"):
            db_file = (Path(app.root_path).parent / sqlite_path).resolve()
            db_file.parent.mkdir(parents=True, exist_ok=True)

    CORS(app, resources={r"/api/*": {"origins": "*"}})
    db.init_app(app)

    from app.routes.health import health_bp
    from app.routes.insider import insider_bp
    from app.routes.markets import markets_bp
    from app.routes.financials import financials_bp
    from app.routes.explore import explore_bp

    app.register_blueprint(health_bp)
    app.register_blueprint(markets_bp, url_prefix="/api/v1")
    app.register_blueprint(insider_bp, url_prefix="/api/v1")
    app.register_blueprint(financials_bp, url_prefix="/api/v1")
    app.register_blueprint(explore_bp, url_prefix="/api/v1")

    with app.app_context():
        db.create_all()

    return app

"""Application configuration."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_BACKEND_ROOT / ".env")

_DEFAULT_DB = _BACKEND_ROOT / "instance" / "filingdesk.db"


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


class Config:
    """Runtime configuration loaded from environment variables."""

    SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-secret")
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", f"sqlite:///{_DEFAULT_DB}")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SEC_USER_AGENT = os.getenv("SEC_USER_AGENT", "")
    SYNC_MAX_FILINGS = int(os.getenv("SYNC_MAX_FILINGS", "40"))
    SEC_REQUEST_DELAY_SECONDS = float(os.getenv("SEC_REQUEST_DELAY_SECONDS", "0.12"))

    # Scheduled sync
    SCHEDULER_ENABLED = _as_bool(os.getenv("SCHEDULER_ENABLED"), True)
    US_SYNC_INTERVAL_MINUTES = int(os.getenv("US_SYNC_INTERVAL_MINUTES", "60"))
    IN_SYNC_INTERVAL_MINUTES = int(os.getenv("IN_SYNC_INTERVAL_MINUTES", "90"))
    US_SYNC_DAYS = int(os.getenv("US_SYNC_DAYS", "7"))
    US_SYNC_MAX_FILINGS = int(os.getenv("US_SYNC_MAX_FILINGS", "25"))
    IN_SYNC_DAYS = int(os.getenv("IN_SYNC_DAYS", "120"))

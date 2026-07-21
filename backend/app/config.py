"""Application configuration."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_BACKEND_ROOT / ".env")

_DEFAULT_DB = _BACKEND_ROOT / "instance" / "filingdesk.db"


class Config:
    """Runtime configuration loaded from environment variables."""

    SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-secret")
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", f"sqlite:///{_DEFAULT_DB}")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SEC_USER_AGENT = os.getenv("SEC_USER_AGENT", "")
    SYNC_MAX_FILINGS = int(os.getenv("SYNC_MAX_FILINGS", "40"))
    # SEC fair-access guidance is ~10 req/sec; stay conservative.
    SEC_REQUEST_DELAY_SECONDS = float(os.getenv("SEC_REQUEST_DELAY_SECONDS", "0.12"))

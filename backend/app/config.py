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

    # Scheduled sync (incremental / recent Atom feed — not a full 30-day pull)
    SCHEDULER_ENABLED = _as_bool(os.getenv("SCHEDULER_ENABLED"), True)
    US_SYNC_INTERVAL_MINUTES = int(os.getenv("US_SYNC_INTERVAL_MINUTES", "60"))
    IN_SYNC_INTERVAL_MINUTES = int(os.getenv("IN_SYNC_INTERVAL_MINUTES", "90"))
    US_SYNC_DAYS = int(os.getenv("US_SYNC_DAYS", "7"))
    US_SYNC_MAX_FILINGS = int(os.getenv("US_SYNC_MAX_FILINGS", "25"))
    # One-time seed of local insider DB via EFTS date window
    US_BACKFILL_DAYS = int(os.getenv("US_BACKFILL_DAYS", "30"))
    US_BACKFILL_MAX_FILINGS = int(os.getenv("US_BACKFILL_MAX_FILINGS", "300"))
    IN_SYNC_DAYS = int(os.getenv("IN_SYNC_DAYS", "120"))

    # Unusual options activity — US (Yahoo / yfinance)
    UOA_ENABLED = _as_bool(os.getenv("UOA_ENABLED"), True)
    UOA_POLL_INTERVAL_MINUTES = int(os.getenv("UOA_POLL_INTERVAL_MINUTES", "20"))
    UOA_EOD_HOUR_UTC = int(os.getenv("UOA_EOD_HOUR_UTC", "21"))  # ~4pm ET approx depending on DST
    UOA_MAX_EXPIRATIONS = int(os.getenv("UOA_MAX_EXPIRATIONS", "3"))
    UOA_MAX_DTE = int(os.getenv("UOA_MAX_DTE", "90"))
    UOA_MIN_VOLUME = float(os.getenv("UOA_MIN_VOLUME", "200"))
    UOA_MIN_VOL_OI = float(os.getenv("UOA_MIN_VOL_OI", "2.0"))
    UOA_MIN_PREMIUM = float(os.getenv("UOA_MIN_PREMIUM", "25000"))
    UOA_NOTIFY_MIN_SCORE = float(os.getenv("UOA_NOTIFY_MIN_SCORE", "35"))
    UOA_MAX_ALERTS_PER_SCAN = int(os.getenv("UOA_MAX_ALERTS_PER_SCAN", "150"))
    UOA_TICKER_SLEEP_SECONDS = float(os.getenv("UOA_TICKER_SLEEP_SECONDS", "0.35"))
    UOA_POLL_MAX_TICKERS = int(os.getenv("UOA_POLL_MAX_TICKERS", "25"))
    UOA_EOD_MAX_TICKERS = int(os.getenv("UOA_EOD_MAX_TICKERS", "80"))

    # Unusual options activity — India (NSE F&O option-chain-v3)
    UOA_IN_ENABLED = _as_bool(os.getenv("UOA_IN_ENABLED"), True)
    UOA_IN_POLL_INTERVAL_MINUTES = int(os.getenv("UOA_IN_POLL_INTERVAL_MINUTES", "25"))
    UOA_IN_EOD_HOUR_UTC = int(os.getenv("UOA_IN_EOD_HOUR_UTC", "10"))  # ~3:30pm IST
    UOA_IN_MAX_EXPIRATIONS = int(os.getenv("UOA_IN_MAX_EXPIRATIONS", "3"))
    UOA_IN_MAX_DTE = int(os.getenv("UOA_IN_MAX_DTE", "90"))
    UOA_IN_MIN_VOLUME = float(os.getenv("UOA_IN_MIN_VOLUME", "100"))
    UOA_IN_MIN_VOL_OI = float(os.getenv("UOA_IN_MIN_VOL_OI", "1.5"))
    UOA_IN_MIN_PREMIUM = float(os.getenv("UOA_IN_MIN_PREMIUM", "100000"))  # INR notional
    UOA_IN_NOTIFY_MIN_SCORE = float(os.getenv("UOA_IN_NOTIFY_MIN_SCORE", "35"))
    UOA_IN_TICKER_SLEEP_SECONDS = float(os.getenv("UOA_IN_TICKER_SLEEP_SECONDS", "0.6"))
    UOA_IN_POLL_MAX_TICKERS = int(os.getenv("UOA_IN_POLL_MAX_TICKERS", "20"))
    UOA_IN_EOD_MAX_TICKERS = int(os.getenv("UOA_IN_EOD_MAX_TICKERS", "60"))

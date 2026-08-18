"""Application configuration."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_BACKEND_ROOT / ".env", override=True)

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
    # Page-load catch-up when the app/backend was off for several days
    INSIDER_CATCHUP_DAYS = int(os.getenv("INSIDER_CATCHUP_DAYS", "7"))
    INSIDER_CATCHUP_FRESH_HOURS = int(os.getenv("INSIDER_CATCHUP_FRESH_HOURS", "6"))
    US_CATCHUP_MAX_FILINGS = int(os.getenv("US_CATCHUP_MAX_FILINGS", "250"))

    # Unusual options activity — US (Yahoo / yfinance)
    UOA_ENABLED = _as_bool(os.getenv("UOA_ENABLED"), True)
    UOA_POLL_INTERVAL_MINUTES = int(os.getenv("UOA_POLL_INTERVAL_MINUTES", "20"))
    UOA_EOD_HOUR_UTC = int(os.getenv("UOA_EOD_HOUR_UTC", "21"))  # ~4pm ET approx depending on DST
    UOA_MAX_EXPIRATIONS = int(os.getenv("UOA_MAX_EXPIRATIONS", "3"))
    UOA_MAX_DTE = int(os.getenv("UOA_MAX_DTE", "90"))
    UOA_MIN_VOLUME = float(os.getenv("UOA_MIN_VOLUME", "500"))
    UOA_MIN_VOL_OI = float(os.getenv("UOA_MIN_VOL_OI", "3.0"))
    UOA_MIN_PREMIUM = float(os.getenv("UOA_MIN_PREMIUM", "50000"))
    UOA_NOTIFY_MIN_SCORE = float(os.getenv("UOA_NOTIFY_MIN_SCORE", "80"))
    UOA_STORE_MIN_SCORE = float(os.getenv("UOA_STORE_MIN_SCORE", "55"))
    # Require Vol/OI (no high-premium bypass) so stored rows are actually unusual.
    UOA_REQUIRE_VOL_OI = _as_bool(os.getenv("UOA_REQUIRE_VOL_OI"), True)
    # Only notify clear bullish/bearish (skip mixed/unclear).
    UOA_NOTIFY_CLEAR_SENTIMENT_ONLY = _as_bool(os.getenv("UOA_NOTIFY_CLEAR_SENTIMENT_ONLY"), True)
    UOA_MAX_ALERTS_PER_SCAN = int(os.getenv("UOA_MAX_ALERTS_PER_SCAN", "80"))
    UOA_TICKER_SLEEP_SECONDS = float(os.getenv("UOA_TICKER_SLEEP_SECONDS", "0.35"))
    UOA_POLL_MAX_TICKERS = int(os.getenv("UOA_POLL_MAX_TICKERS", "25"))
    UOA_EOD_MAX_TICKERS = int(os.getenv("UOA_EOD_MAX_TICKERS", "80"))

    # Unusual options activity — India (NSE F&O option-chain-v3)
    UOA_IN_ENABLED = _as_bool(os.getenv("UOA_IN_ENABLED"), True)
    UOA_IN_POLL_INTERVAL_MINUTES = int(os.getenv("UOA_IN_POLL_INTERVAL_MINUTES", "25"))
    UOA_IN_EOD_HOUR_UTC = int(os.getenv("UOA_IN_EOD_HOUR_UTC", "10"))  # ~3:30pm IST
    UOA_IN_MAX_EXPIRATIONS = int(os.getenv("UOA_IN_MAX_EXPIRATIONS", "3"))
    UOA_IN_MAX_DTE = int(os.getenv("UOA_IN_MAX_DTE", "90"))
    UOA_IN_MIN_VOLUME = float(os.getenv("UOA_IN_MIN_VOLUME", "150"))
    UOA_IN_MIN_VOL_OI = float(os.getenv("UOA_IN_MIN_VOL_OI", "2.0"))
    UOA_IN_MIN_PREMIUM = float(os.getenv("UOA_IN_MIN_PREMIUM", "150000"))  # INR notional
    UOA_IN_NOTIFY_MIN_SCORE = float(os.getenv("UOA_IN_NOTIFY_MIN_SCORE", "80"))
    UOA_IN_STORE_MIN_SCORE = float(os.getenv("UOA_IN_STORE_MIN_SCORE", "55"))
    UOA_IN_TICKER_SLEEP_SECONDS = float(os.getenv("UOA_IN_TICKER_SLEEP_SECONDS", "0.6"))
    UOA_IN_POLL_MAX_TICKERS = int(os.getenv("UOA_IN_POLL_MAX_TICKERS", "20"))
    UOA_IN_EOD_MAX_TICKERS = int(os.getenv("UOA_IN_EOD_MAX_TICKERS", "60"))

    # Large officer buys → Equity Research Agent full deep-dive pack
    DEEP_DIVE_BRIDGE_ENABLED = _as_bool(os.getenv("DEEP_DIVE_BRIDGE_ENABLED"), True)
    DEEP_DIVE_MIN_VALUE_USD = float(os.getenv("DEEP_DIVE_MIN_VALUE_USD", "100000"))
    DEEP_DIVE_CONFIRM_SECONDS = int(os.getenv("DEEP_DIVE_CONFIRM_SECONDS", "60"))
    # Never re-queue a ticker after a successful deep-dive push (recommended).
    DEEP_DIVE_ONCE_PER_TICKER = _as_bool(os.getenv("DEEP_DIVE_ONCE_PER_TICKER"), True)
    # Only used when DEEP_DIVE_ONCE_PER_TICKER=0
    DEEP_DIVE_COOLDOWN_HOURS = int(os.getenv("DEEP_DIVE_COOLDOWN_HOURS", "72"))
    DEEP_DIVE_BACKLOG_RETRY_MINUTES = int(os.getenv("DEEP_DIVE_BACKLOG_RETRY_MINUTES", "60"))
    DEEP_DIVE_TICK_SECONDS = int(os.getenv("DEEP_DIVE_TICK_SECONDS", "10"))
    DEEP_DIVE_RESEARCH_URL = os.getenv("DEEP_DIVE_RESEARCH_URL", "http://127.0.0.1:8000")
    DEEP_DIVE_RESEARCH_PIN = os.getenv("DEEP_DIVE_RESEARCH_PIN", "")
    DEEP_DIVE_RESEARCH_TEMPLATE = os.getenv("DEEP_DIVE_RESEARCH_TEMPLATE", "all")
    DEEP_DIVE_RESEARCH_MODE = os.getenv("DEEP_DIVE_RESEARCH_MODE", "deep")
    # Always park on the Equity overnight queue; never auto-start research.
    DEEP_DIVE_USE_OVERNIGHT_QUEUE = _as_bool(os.getenv("DEEP_DIVE_USE_OVERNIGHT_QUEUE"), True)
    # overnight: park until Start overnight on the Equity queue page/API
    DEEP_DIVE_QUEUE_START_POLICY = os.getenv("DEEP_DIVE_QUEUE_START_POLICY", "overnight")
    DEEP_DIVE_SKIP_IF_RESEARCHED = _as_bool(os.getenv("DEEP_DIVE_SKIP_IF_RESEARCHED"), True)
    DEEP_DIVE_NTFY_ENABLED = _as_bool(os.getenv("DEEP_DIVE_NTFY_ENABLED"), True)
    # Base URL for ntfy Cancel/Push action buttons (no browser needed).
    # Prefer public/tunnel URL for phone; falls back to data/tunnel_url.txt then localhost:5000.
    DEEP_DIVE_PUBLIC_BASE_URL = os.getenv("DEEP_DIVE_PUBLIC_BASE_URL", "")
    # Comma-separated officer title tokens (matched case-insensitively as substrings)
    DEEP_DIVE_OFFICER_TITLE_KEYWORDS = os.getenv(
        "DEEP_DIVE_OFFICER_TITLE_KEYWORDS",
        "ceo,cfo,coo,cto,chief,president,managing director,general counsel,controller,treasurer",
    )

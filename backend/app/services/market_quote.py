"""Yahoo Finance quote + history helpers for research overview / charts."""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any, Optional

import yfinance as yf

logger = logging.getLogger(__name__)

_RANGE_PERIOD = {
    "1mo": "1mo",
    "3mo": "3mo",
    "6mo": "6mo",
    "1y": "1y",
    "2y": "2y",
    "5y": "5y",
}

# Short in-process TTL so overview/chart loads don't hammer Yahoo on every click.
_CACHE_TTL_SEC = 900  # 15 minutes
_cache_lock = threading.Lock()
_cache: dict[str, tuple[float, dict[str, Any]]] = {}


def resolve_yahoo_symbol(ticker: str, market: str = "US") -> str:
    symbol = (ticker or "").strip().upper().replace(" ", "")
    market = (market or "US").upper()
    if not symbol:
        raise ValueError("Ticker is required")
    if market == "IN":
        if symbol.endswith(".NS") or symbol.endswith(".BO"):
            return symbol
        return f"{symbol}.NS"
    # US: strip accidental suffixes
    return symbol.replace(".NS", "").replace(".BO", "")


def _safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:  # NaN
        return None
    return number


def _cache_key(ticker: str, market: str, range_key: str) -> str:
    return f"{market.upper()}:{ticker.upper()}:{range_key.lower()}"


def fetch_market_overview(
    ticker: str,
    *,
    market: str = "US",
    range_key: str = "1y",
    refresh: bool = False,
) -> dict[str, Any]:
    """Return company overview fields + daily close series for charting."""
    yahoo_symbol = resolve_yahoo_symbol(ticker, market)
    period = _RANGE_PERIOD.get((range_key or "1y").lower(), "1y")
    key = _cache_key(yahoo_symbol, market, period)

    if not refresh:
        with _cache_lock:
            hit = _cache.get(key)
            if hit and (time.time() - hit[0]) < _CACHE_TTL_SEC:
                payload = dict(hit[1])
                payload["cached"] = True
                payload["cache_note"] = "Served from 15-minute in-memory cache."
                return payload

    stock = yf.Ticker(yahoo_symbol)

    info: dict[str, Any] = {}
    try:
        info = stock.info or {}
    except Exception as exc:  # noqa: BLE001
        logger.warning("yfinance info failed for %s: %s", yahoo_symbol, exc)
        info = {}

    history_points: list[dict[str, Any]] = []
    try:
        hist = stock.history(period=period, auto_adjust=True)
        if hist is not None and not hist.empty:
            for idx, row in hist.iterrows():
                close = _safe_float(row.get("Close"))
                if close is None:
                    continue
                if hasattr(idx, "date"):
                    day = idx.date().isoformat()
                else:
                    day = str(idx)[:10]
                history_points.append(
                    {
                        "date": day,
                        "close": round(close, 4),
                        "volume": _safe_float(row.get("Volume")),
                    }
                )
    except Exception as exc:  # noqa: BLE001
        logger.warning("yfinance history failed for %s: %s", yahoo_symbol, exc)

    last_close = history_points[-1]["close"] if history_points else _safe_float(info.get("previousClose"))
    prev_close = (
        history_points[-2]["close"]
        if len(history_points) >= 2
        else _safe_float(info.get("previousClose"))
    )
    change = None
    change_pct = None
    if last_close is not None and prev_close not in (None, 0):
        change = round(last_close - prev_close, 4)
        change_pct = round((change / prev_close) * 100.0, 2)

    currency = info.get("currency") or ("INR" if market.upper() == "IN" else "USD")
    display_ticker = yahoo_symbol.replace(".NS", "").replace(".BO", "")

    payload = {
        "ticker": display_ticker,
        "yahoo_symbol": yahoo_symbol,
        "market": market.upper(),
        "company_name": info.get("longName") or info.get("shortName") or display_ticker,
        "exchange": info.get("exchange") or info.get("fullExchangeName"),
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "currency": currency,
        "website": info.get("website"),
        "summary": (info.get("longBusinessSummary") or "")[:800] or None,
        "price": {
            "last": last_close,
            "previous_close": prev_close,
            "change": change,
            "change_pct": change_pct,
            "open": _safe_float(info.get("open")),
            "day_high": _safe_float(info.get("dayHigh")),
            "day_low": _safe_float(info.get("dayLow")),
            "fifty_two_week_high": _safe_float(info.get("fiftyTwoWeekHigh")),
            "fifty_two_week_low": _safe_float(info.get("fiftyTwoWeekLow")),
            "volume": _safe_float(info.get("volume")),
            "avg_volume": _safe_float(info.get("averageVolume")),
            "market_cap": _safe_float(info.get("marketCap")),
            "pe_trailing": _safe_float(info.get("trailingPE")),
            "pe_forward": _safe_float(info.get("forwardPE")),
            "eps_trailing": _safe_float(info.get("trailingEps")),
            "dividend_yield": _safe_float(info.get("dividendYield")),
            "beta": _safe_float(info.get("beta")),
        },
        "range": period,
        "history": history_points,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "source": "Yahoo Finance via yfinance (delayed overview) · chart via TradingView",
        "cached": False,
        "cache_note": "Fresh from Yahoo; cached in memory for 15 minutes.",
    }

    with _cache_lock:
        _cache[key] = (time.time(), payload)

    return payload

"""Unusual options activity scanners (US Yahoo chains + India NSE F&O chains)."""

from __future__ import annotations

import json
import logging
import math
import time
from datetime import date, datetime, timezone
from typing import Any, Iterable, Optional

import yfinance as yf
from flask import current_app
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import AppNotification, OptionsScanRun, UnusualOptionAlert, Watchlist
from app.services.india_provider import NseClient

logger = logging.getLogger(__name__)

# Liquid US names for broader-universe scans (indexes + mega/large caps).
LIQUID_US_UNIVERSE: list[str] = [
    "SPY", "QQQ", "IWM", "DIA", "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META",
    "TSLA", "AVGO", "AMD", "NFLX", "COST", "JPM", "BAC", "XOM", "CVX", "UNH",
    "LLY", "V", "MA", "HD", "PG", "JNJ", "WMT", "ORCL", "CRM", "ADBE",
    "INTC", "MU", "PLTR", "COIN", "UBER", "ABNB", "SHOP", "BA", "CAT", "GE",
    "DIS", "CMCSA", "T", "VZ", "PFE", "MRK", "ABBV", "KO", "PEP", "MCD",
    "NKE", "SBUX", "GS", "MS", "C", "WFC", "BLK", "SCHW", "PYPL", "SQ",
    "NOW", "SNOW", "PANW", "CRWD", "NET", "DDOG", "SMCI", "ARM", "QCOM", "TXN",
    "AMAT", "LRCX", "KLAC", "ASML", "TSM", "BABA", "JD", "PDD", "NIO", "RIVN",
    "F", "GM", "DAL", "UAL", "AAL", "MAR", "BKNG", "CMG", "ROKU", "SNAP",
    "SPOT", "ZM", "DOCU", "U", "RBLX", "SOFI", "HOOD", "GME", "AMC", "DKNG",
]

# NSE index underlyings for F&O option chains.
IN_INDEX_SYMBOLS: set[str] = {"NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "NIFTYNXT50"}

# Curated liquid India F&O names (indices first, then active equity FO).
LIQUID_IN_UNIVERSE: list[str] = [
    "NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY",
    "RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "SBIN", "BHARTIARTL",
    "ITC", "LT", "AXISBANK", "KOTAKBANK", "BAJFINANCE", "HINDUNILVR", "ASIANPAINT",
    "MARUTI", "SUNPHARMA", "TITAN", "ULTRACEMCO", "NTPC", "POWERGRID", "ONGC",
    "TATAMOTORS", "TATASTEEL", "JSWSTEEL", "ADANIENT", "ADANIPORTS", "WIPRO",
    "HCLTECH", "TECHM", "BAJAJFINSV", "NESTLEIND", "COALINDIA", "M&M", "CIPLA",
    "DRREDDY", "INDUSINDBK", "BPCL", "HEROMOTOCO", "EICHERMOT", "GRASIM",
    "DIVISLAB", "PIDILITIND", "DABUR", "HAVELLS", "GODREJCP", "BRITANNIA",
    "SBILIFE", "HDFCLIFE", "BAJAJ-AUTO", "APOLLOHOSP", "TRENT", "DMART",
    "ZOMATO", "PAYTM", "POLYCAB", "DIXON", "PERSISTENT", "COFORGE", "LTIM",
    "PFC", "RECLTD", "IRCTC", "HAL", "BEL", "BHEL", "VEDL", "HINDALCO",
]

# Approximate NSE market lots (updated periodically; unknown equities fall back to 1).
IN_LOT_SIZES: dict[str, int] = {
    "NIFTY": 65,
    "BANKNIFTY": 30,
    "FINNIFTY": 65,
    "MIDCPNIFTY": 120,
    "NIFTYNXT50": 25,
    "RELIANCE": 500,
    "TCS": 175,
    "INFY": 400,
    "HDFCBANK": 550,
    "ICICIBANK": 700,
    "SBIN": 750,
    "BHARTIARTL": 475,
    "ITC": 1600,
    "LT": 150,
    "AXISBANK": 625,
    "KOTAKBANK": 400,
    "BAJFINANCE": 125,
    "TATAMOTORS": 550,
    "TATASTEEL": 550,
}


def _safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            return None
        num = float(value)
        if math.isnan(num) or math.isinf(num):
            return None
        return num
    except (TypeError, ValueError):
        return None


def _mid(bid: Optional[float], ask: Optional[float], last: Optional[float]) -> Optional[float]:
    if bid is not None and ask is not None and bid > 0 and ask > 0:
        return (bid + ask) / 2.0
    return last


def classify_aggressiveness(last: Optional[float], bid: Optional[float], ask: Optional[float]) -> str:
    """Heuristic: last near ask ≈ aggressive buy; near bid ≈ aggressive sell."""
    if last is None or bid is None or ask is None:
        return "unknown"
    if ask <= 0 or bid < 0 or ask < bid:
        return "unknown"
    spread = ask - bid
    if spread <= 0:
        return "mid"
    if last >= ask - 0.3 * spread:
        return "buy_ask"
    if last <= bid + 0.3 * spread:
        return "sell_bid"
    return "mid"


def classify_sentiment(option_type: str, aggressiveness: str) -> tuple[str, str]:
    """
    Direction model:
    1) call ≈ bullish bias, put ≈ bearish bias
    2) refine with bid/ask aggressiveness when available
    """
    side = (option_type or "").lower()
    reasons: list[str] = []

    if side == "call":
        base = "bullish"
        reasons.append("call volume")
    elif side == "put":
        base = "bearish"
        reasons.append("put volume")
    else:
        return "unclear", "unknown option type"

    if aggressiveness == "buy_ask":
        reasons.append("last near ask (aggressive buy)")
        return base, "; ".join(reasons)
    if aggressiveness == "sell_bid":
        if side == "call":
            return "mixed", "; ".join(reasons + ["last near bid (possible call sell/hedge)"])
        return "mixed", "; ".join(reasons + ["last near bid (possible put sell/hedge)"])
    if aggressiveness == "mid":
        reasons.append("last mid-spread")
        return base, "; ".join(reasons)
    reasons.append("bid/ask unavailable")
    return base, "; ".join(reasons)


def score_contract(
    *,
    volume: float,
    open_interest: float,
    premium: float,
    vol_oi: float,
    dte: int,
) -> float:
    """Simple ranking score — higher is more unusual."""
    score = 0.0
    score += min(vol_oi, 20.0) * 8.0
    score += min(math.log10(max(premium, 1.0)), 7.0) * 10.0
    score += min(math.log10(max(volume, 1.0)), 5.0) * 4.0
    if 1 <= dte <= 45:
        score += 8.0
    elif dte == 0:
        score += 3.0
    elif dte <= 90:
        score += 4.0
    return round(score, 2)


def passes_unusual_gates(
    *,
    volume: float,
    open_interest: float,
    premium: float,
    min_volume: float,
    min_premium: float,
    min_vol_oi: float,
    require_vol_oi: bool = True,
) -> tuple[bool, float]:
    """Return (passes, vol_oi). Require volume/premium; Vol/OI is required when configured."""
    if volume < min_volume or premium < min_premium:
        return False, 0.0
    vol_oi = volume / max(open_interest, 1.0)
    if require_vol_oi:
        if vol_oi < min_vol_oi:
            return False, vol_oi
    elif vol_oi < min_vol_oi and premium < (min_premium * 4):
        return False, vol_oi
    return True, vol_oi


def india_lot_size(symbol: str) -> int:
    return int(IN_LOT_SIZES.get(symbol.upper().strip(), 1))


def collect_scan_tickers(
    *,
    market: str = "US",
    include_watchlist: bool = True,
    include_liquid: bool = True,
) -> dict[str, str]:
    """Return ticker -> universe label."""
    market = (market or "US").upper()
    mapping: dict[str, str] = {}
    liquid = LIQUID_US_UNIVERSE if market == "US" else LIQUID_IN_UNIVERSE
    if include_liquid:
        for t in liquid:
            mapping[t.upper()] = "liquid100"
    if include_watchlist:
        for wl in Watchlist.query.filter_by(market=market).all():
            for item in wl.items:
                if not item.ticker:
                    continue
                ticker = item.ticker.upper().replace(".NS", "").replace(".BO", "")
                mapping[ticker] = "watchlist"
    return mapping


def _parse_expiration(value: str) -> Optional[date]:
    text = (value or "").strip()
    for fmt in ("%Y-%m-%d", "%d-%b-%Y", "%d-%B-%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def scan_ticker_contracts(
    ticker: str,
    *,
    market: str = "US",
    max_expirations: int = 4,
    max_dte: int = 90,
    min_volume: float = 200,
    min_vol_oi: float = 2.0,
    min_premium: float = 25000,
    nse_client: Optional[NseClient] = None,
) -> list[dict[str, Any]]:
    """Fetch option chains and return unusual contract rows for one underlying."""
    market = (market or "US").upper()
    if market == "IN":
        return scan_india_ticker_contracts(
            ticker,
            max_expirations=max_expirations,
            max_dte=max_dte,
            min_volume=min_volume,
            min_vol_oi=min_vol_oi,
            min_premium=min_premium,
            nse_client=nse_client,
        )
    return scan_us_ticker_contracts(
        ticker,
        max_expirations=max_expirations,
        max_dte=max_dte,
        min_volume=min_volume,
        min_vol_oi=min_vol_oi,
        min_premium=min_premium,
    )


def scan_us_ticker_contracts(
    ticker: str,
    *,
    max_expirations: int = 4,
    max_dte: int = 90,
    min_volume: float = 200,
    min_vol_oi: float = 2.0,
    min_premium: float = 25000,
) -> list[dict[str, Any]]:
    """Fetch Yahoo option chains for a US ticker and return unusual contract rows."""
    ticker = ticker.upper().strip()
    try:
        yf_ticker = yf.Ticker(ticker)
        expirations = list(yf_ticker.options or [])
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed loading expirations for %s: %s", ticker, exc)
        return []

    today = date.today()
    selected: list[str] = []
    for exp in expirations:
        exp_date = _parse_expiration(exp)
        if not exp_date:
            continue
        dte = (exp_date - today).days
        if 0 <= dte <= max_dte:
            selected.append(exp)
        if len(selected) >= max_expirations:
            break

    unusual: list[dict[str, Any]] = []
    for exp in selected:
        exp_date = _parse_expiration(exp)
        if not exp_date:
            continue
        dte = (exp_date - today).days
        try:
            chain = yf_ticker.option_chain(exp)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Chain fetch failed %s %s: %s", ticker, exp, exc)
            continue

        for option_type, frame in (("call", chain.calls), ("put", chain.puts)):
            if frame is None or frame.empty:
                continue
            for _, row in frame.iterrows():
                volume = _safe_float(row.get("volume")) or 0.0
                oi = _safe_float(row.get("openInterest")) or 0.0
                last = _safe_float(row.get("lastPrice"))
                bid = _safe_float(row.get("bid"))
                ask = _safe_float(row.get("ask"))
                iv = _safe_float(row.get("impliedVolatility"))
                strike = _safe_float(row.get("strike"))
                contract = str(row.get("contractSymbol") or "")
                if not contract or volume < min_volume:
                    continue
                px = _mid(bid, ask, last)
                if not px or px <= 0:
                    continue
                premium = volume * 100.0 * px
                require_vol_oi = bool(current_app.config.get("UOA_REQUIRE_VOL_OI", True))
                ok, vol_oi = passes_unusual_gates(
                    volume=volume,
                    open_interest=oi,
                    premium=premium,
                    min_volume=min_volume,
                    min_premium=min_premium,
                    min_vol_oi=min_vol_oi,
                    require_vol_oi=require_vol_oi,
                )
                if not ok:
                    continue

                aggressiveness = classify_aggressiveness(last, bid, ask)
                sentiment, reason = classify_sentiment(option_type, aggressiveness)
                score = score_contract(
                    volume=volume,
                    open_interest=oi,
                    premium=premium,
                    vol_oi=vol_oi,
                    dte=dte,
                )
                store_min = float(current_app.config.get("UOA_STORE_MIN_SCORE", 55))
                if score < store_min:
                    continue
                unusual.append(
                    {
                        "market": "US",
                        "underlying": ticker,
                        "contract_symbol": contract,
                        "option_type": option_type,
                        "strike": strike,
                        "expiration": exp_date,
                        "dte": dte,
                        "last_price": last,
                        "bid": bid,
                        "ask": ask,
                        "volume": volume,
                        "open_interest": oi,
                        "implied_volatility": iv,
                        "premium": round(premium, 2),
                        "vol_oi": round(vol_oi, 2),
                        "score": score,
                        "sentiment": sentiment,
                        "aggressiveness": aggressiveness,
                        "reason": reason,
                    }
                )
        time.sleep(0.05)
    return unusual


def scan_india_ticker_contracts(
    ticker: str,
    *,
    max_expirations: int = 4,
    max_dte: int = 90,
    min_volume: float = 100,
    min_vol_oi: float = 1.5,
    min_premium: float = 100_000,
    nse_client: Optional[NseClient] = None,
) -> list[dict[str, Any]]:
    """Fetch NSE F&O option-chain-v3 rows and return unusual contracts."""
    symbol = ticker.upper().strip().replace(".NS", "").replace(".BO", "")
    client = nse_client or NseClient()
    chain_type = "Indices" if symbol in IN_INDEX_SYMBOLS else "Equity"
    lot = india_lot_size(symbol)

    try:
        info = client.get_json(
            "/api/option-chain-contract-info",
            params={"symbol": symbol},
            referer="https://www.nseindia.com/option-chain",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("India contract-info failed for %s: %s", symbol, exc)
        return []

    expiries = list((info or {}).get("expiryDates") or [])
    today = date.today()
    selected: list[str] = []
    for exp in expiries:
        exp_date = _parse_expiration(exp)
        if not exp_date:
            continue
        dte = (exp_date - today).days
        if 0 <= dte <= max_dte:
            selected.append(exp)
        if len(selected) >= max_expirations:
            break

    unusual: list[dict[str, Any]] = []
    for exp in selected:
        exp_date = _parse_expiration(exp)
        if not exp_date:
            continue
        dte = (exp_date - today).days
        try:
            payload = client.get_json(
                "/api/option-chain-v3",
                params={"type": chain_type, "symbol": symbol, "expiry": exp},
                referer="https://www.nseindia.com/option-chain",
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("India chain fetch failed %s %s: %s", symbol, exp, exc)
            continue

        rows = ((payload or {}).get("records") or {}).get("data") or []
        for row in rows:
            strike = _safe_float(row.get("strikePrice"))
            for side_key, option_type in (("CE", "call"), ("PE", "put")):
                leg = row.get(side_key) or {}
                if not leg:
                    continue
                volume = _safe_float(leg.get("totalTradedVolume")) or 0.0
                oi = _safe_float(leg.get("openInterest")) or 0.0
                last = _safe_float(leg.get("lastPrice"))
                bid = _safe_float(leg.get("buyPrice1"))
                ask = _safe_float(leg.get("sellPrice1"))
                iv = _safe_float(leg.get("impliedVolatility"))
                if iv is not None and iv > 3:
                    # NSE often reports IV as percent (e.g. 38.75).
                    iv = iv / 100.0
                contract = str(leg.get("identifier") or "")
                if not contract or volume < min_volume:
                    continue
                px = _mid(bid, ask, last)
                if not px or px <= 0:
                    continue
                premium = volume * float(lot) * px
                require_vol_oi = bool(current_app.config.get("UOA_REQUIRE_VOL_OI", True))
                ok, vol_oi = passes_unusual_gates(
                    volume=volume,
                    open_interest=oi,
                    premium=premium,
                    min_volume=min_volume,
                    min_premium=min_premium,
                    min_vol_oi=min_vol_oi,
                    require_vol_oi=require_vol_oi,
                )
                if not ok:
                    continue

                aggressiveness = classify_aggressiveness(last, bid, ask)
                sentiment, reason = classify_sentiment(option_type, aggressiveness)
                score = score_contract(
                    volume=volume,
                    open_interest=oi,
                    premium=premium,
                    vol_oi=vol_oi,
                    dte=dte,
                )
                store_min = float(
                    current_app.config.get(
                        "UOA_IN_STORE_MIN_SCORE",
                        current_app.config.get("UOA_STORE_MIN_SCORE", 55),
                    )
                )
                if score < store_min:
                    continue
                unusual.append(
                    {
                        "market": "IN",
                        "underlying": symbol,
                        "contract_symbol": contract[:64],
                        "option_type": option_type,
                        "strike": strike if strike is not None else _safe_float(leg.get("strikePrice")),
                        "expiration": exp_date,
                        "dte": dte,
                        "last_price": last,
                        "bid": bid,
                        "ask": ask,
                        "volume": volume,
                        "open_interest": oi,
                        "implied_volatility": iv,
                        "premium": round(premium, 2),
                        "vol_oi": round(vol_oi, 2),
                        "score": score,
                        "sentiment": sentiment,
                        "aggressiveness": aggressiveness,
                        "reason": reason,
                    }
                )
        time.sleep(0.15)
    return unusual


def _upsert_alerts(rows: list[dict[str, Any]], *, universe: str, scan_day: date) -> tuple[int, list[UnusualOptionAlert]]:
    upserted = 0
    created_models: list[UnusualOptionAlert] = []
    for row in rows:
        existing = UnusualOptionAlert.query.filter_by(
            scan_date=scan_day,
            contract_symbol=row["contract_symbol"],
            underlying=row["underlying"],
        ).first()
        payload = {k: v for k, v in row.items() if k != "universe"}
        row_universe = row.get("universe") or universe
        if existing:
            if (row.get("score") or 0) >= (existing.score or 0):
                for key, value in payload.items():
                    setattr(existing, key, value)
                if existing.universe != "watchlist":
                    existing.universe = row_universe
                existing.scanned_at = datetime.now(timezone.utc)
                db.session.commit()
            continue

        alert = UnusualOptionAlert(scan_date=scan_day, universe=row_universe, **payload)
        db.session.add(alert)
        try:
            db.session.commit()
            upserted += 1
            created_models.append(alert)
        except IntegrityError:
            db.session.rollback()
    return upserted, created_models


def _create_notifications(alerts: Iterable[UnusualOptionAlert], *, min_score: float) -> int:
    created = 0
    clear_only = bool(current_app.config.get("UOA_NOTIFY_CLEAR_SENTIMENT_ONLY", True))
    for alert in alerts:
        if (alert.score or 0) < min_score:
            continue
        if clear_only and (alert.sentiment or "") not in {"bullish", "bearish"}:
            continue
        currency = "₹" if alert.market == "IN" else "$"
        title = f"UOA {alert.market} {alert.sentiment or 'signal'}: {alert.underlying} {alert.option_type}"
        body = (
            f"{alert.contract_symbol} · vol {int(alert.volume or 0)} · "
            f"Vol/OI {alert.vol_oi} · premium {currency}{alert.premium:,.0f} · "
            f"score {alert.score} · {alert.aggressiveness} · {alert.reason}"
        )
        note = AppNotification(
            kind="uoa",
            title=title[:255],
            body=body,
            severity="bullish" if alert.sentiment == "bullish" else "bearish" if alert.sentiment == "bearish" else "info",
            ticker=alert.underlying,
            payload_json=json.dumps(alert.to_dict())[:4000],
            is_read=False,
        )
        db.session.add(note)
        try:
            db.session.commit()
            created += 1
        except IntegrityError:
            db.session.rollback()
    return created


def _thresholds_for_market(market: str) -> dict[str, float | int]:
    cfg = current_app.config
    market = market.upper()
    if market == "IN":
        return {
            "max_expirations": int(cfg.get("UOA_IN_MAX_EXPIRATIONS", cfg.get("UOA_MAX_EXPIRATIONS", 3))),
            "max_dte": int(cfg.get("UOA_IN_MAX_DTE", cfg.get("UOA_MAX_DTE", 90))),
            "min_volume": float(cfg.get("UOA_IN_MIN_VOLUME", 150)),
            "min_vol_oi": float(cfg.get("UOA_IN_MIN_VOL_OI", 2.0)),
            "min_premium": float(cfg.get("UOA_IN_MIN_PREMIUM", 150_000)),
            "notify_min_score": float(cfg.get("UOA_IN_NOTIFY_MIN_SCORE", cfg.get("UOA_NOTIFY_MIN_SCORE", 80))),
            "sleep_seconds": float(cfg.get("UOA_IN_TICKER_SLEEP_SECONDS", 0.6)),
        }
    return {
        "max_expirations": int(cfg.get("UOA_MAX_EXPIRATIONS", 3)),
        "max_dte": int(cfg.get("UOA_MAX_DTE", 90)),
        "min_volume": float(cfg.get("UOA_MIN_VOLUME", 500)),
        "min_vol_oi": float(cfg.get("UOA_MIN_VOL_OI", 3.0)),
        "min_premium": float(cfg.get("UOA_MIN_PREMIUM", 50000)),
        "notify_min_score": float(cfg.get("UOA_NOTIFY_MIN_SCORE", 80)),
        "sleep_seconds": float(cfg.get("UOA_TICKER_SLEEP_SECONDS", 0.35)),
    }


def run_uoa_scan(
    *,
    market: str = "US",
    include_watchlist: bool = True,
    include_liquid: bool = True,
    trigger: str = "manual",
    max_tickers: Optional[int] = None,
) -> dict[str, Any]:
    """Scan option chains for unusual activity and create in-app notifications."""
    market = (market or "US").upper()
    if market not in {"US", "IN"}:
        raise ValueError("market must be US or IN")

    cfg = current_app.config
    thresholds = _thresholds_for_market(market)

    universe_label = "mixed"
    if include_watchlist and not include_liquid:
        universe_label = "watchlist"
    elif include_liquid and not include_watchlist:
        universe_label = "liquid100"

    run = OptionsScanRun(
        market=market,
        universe=universe_label,
        trigger=trigger,
        status="running",
    )
    db.session.add(run)
    db.session.commit()

    tickers = collect_scan_tickers(
        market=market,
        include_watchlist=include_watchlist,
        include_liquid=include_liquid,
    )
    symbols = list(tickers.keys())
    if max_tickers is not None:
        symbols = symbols[: max(1, int(max_tickers))]

    scan_day = date.today()
    all_rows: list[dict[str, Any]] = []
    scanned = 0
    nse_client = NseClient() if market == "IN" else None
    try:
        for symbol in symbols:
            universe = tickers.get(symbol, "liquid100")
            rows = scan_ticker_contracts(
                symbol,
                market=market,
                max_expirations=int(thresholds["max_expirations"]),
                max_dte=int(thresholds["max_dte"]),
                min_volume=float(thresholds["min_volume"]),
                min_vol_oi=float(thresholds["min_vol_oi"]),
                min_premium=float(thresholds["min_premium"]),
                nse_client=nse_client,
            )
            for row in rows:
                row["universe"] = universe
            all_rows.extend(rows)
            scanned += 1
            time.sleep(float(thresholds["sleep_seconds"]))

        all_rows.sort(key=lambda r: r.get("score") or 0, reverse=True)
        top_rows = all_rows[: int(cfg.get("UOA_MAX_ALERTS_PER_SCAN", 150))]
        upserted, created = _upsert_alerts(top_rows, universe=universe_label, scan_day=scan_day)
        notifications = _create_notifications(created, min_score=float(thresholds["notify_min_score"]))

        run.status = "completed"
        run.tickers_scanned = scanned
        run.alerts_upserted = upserted
        run.notifications_created = notifications
        run.finished_at = datetime.now(timezone.utc)
        db.session.commit()
        return run.to_dict()
    except Exception as exc:  # noqa: BLE001
        run.status = "failed"
        run.tickers_scanned = scanned
        run.error_message = str(exc)
        run.finished_at = datetime.now(timezone.utc)
        db.session.commit()
        raise


def list_uoa_alerts(
    *,
    market: str = "US",
    sentiment: Optional[str] = None,
    underlying: Optional[str] = None,
    universe: Optional[str] = None,
    option_type: Optional[str] = None,
    aggressiveness: Optional[str] = None,
    min_score: Optional[float] = None,
    min_vol_oi: Optional[float] = None,
    min_premium: Optional[float] = None,
    page: int = 1,
    page_size: int = 50,
) -> dict[str, Any]:
    market = (market or "US").upper()
    query = UnusualOptionAlert.query.filter_by(market=market)
    latest_day = (
        db.session.query(func.max(UnusualOptionAlert.scan_date))
        .filter(UnusualOptionAlert.market == market)
        .scalar()
    )
    if latest_day:
        query = query.filter(UnusualOptionAlert.scan_date == latest_day)
    if sentiment:
        query = query.filter(UnusualOptionAlert.sentiment == sentiment.lower())
    if underlying:
        clean = underlying.upper().replace(".NS", "").replace(".BO", "")
        query = query.filter(UnusualOptionAlert.underlying == clean)
    if universe:
        query = query.filter(UnusualOptionAlert.universe == universe)
    if option_type:
        query = query.filter(UnusualOptionAlert.option_type == option_type.lower())
    if aggressiveness:
        query = query.filter(UnusualOptionAlert.aggressiveness == aggressiveness.lower())
    if min_score is not None:
        query = query.filter(UnusualOptionAlert.score >= min_score)
    if min_vol_oi is not None:
        query = query.filter(UnusualOptionAlert.vol_oi >= min_vol_oi)
    if min_premium is not None:
        query = query.filter(UnusualOptionAlert.premium >= min_premium)

    total = query.count()
    page = max(page, 1)
    page_size = min(max(page_size, 1), 200)
    items = (
        query.order_by(UnusualOptionAlert.score.desc(), UnusualOptionAlert.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    latest_run = (
        OptionsScanRun.query.filter_by(market=market)
        .order_by(OptionsScanRun.started_at.desc())
        .first()
    )
    return {
        "market": market,
        "scan_date": latest_day.isoformat() if latest_day else None,
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [item.to_dict() for item in items],
        "latest_scan": latest_run.to_dict() if latest_run else None,
    }

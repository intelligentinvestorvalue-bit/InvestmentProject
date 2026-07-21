"""India insider + research helpers via free NSE public APIs (covers NSE/BSE-reported PIT)."""

from __future__ import annotations

import logging
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

import requests
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import AnnualFinancial, Company, InsiderTransaction, SyncRun
from app.utils.helpers import clean_whitespace, to_float

logger = logging.getLogger(__name__)

OPEN_MARKET_MODES = {"market purchase": "buy", "market sale": "sell"}


class NseClient:
    """Browser-like NSE session (cookie warm-up required)."""

    BASE = "https://www.nseindia.com"

    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36"
                ),
                "Accept": "application/json,text/plain,*/*",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-origin",
            }
        )
        self._warmed = False

    def warm(self, *, force: bool = False) -> None:
        if self._warmed and not force:
            return
        self.session.cookies.clear()
        self.session.headers["Referer"] = f"{self.BASE}/"
        self.session.get(self.BASE, timeout=30)
        time.sleep(0.2)
        self.session.headers["Referer"] = (
            f"{self.BASE}/companies-listing/corporate-filings-insider-trading"
        )
        self.session.get(
            f"{self.BASE}/companies-listing/corporate-filings-insider-trading",
            timeout=30,
        )
        time.sleep(0.2)
        # Also warm a markets page used by quote endpoints.
        self.session.get(f"{self.BASE}/market-data/live-equity-market", timeout=30)
        self._warmed = True

    def get_json(self, path: str, *, params: Optional[dict] = None) -> Any:
        self.warm()
        url = path if path.startswith("http") else f"{self.BASE}{path}"
        if "quote-equity" in url:
            self.session.headers["Referer"] = f"{self.BASE}/get-quotes/equity?symbol={(params or {}).get('symbol', '')}"
        response = self.session.get(url, params=params, timeout=45)
        if response.status_code in {401, 403}:
            self.warm(force=True)
            if "quote-equity" in url:
                self.session.headers["Referer"] = (
                    f"{self.BASE}/get-quotes/equity?symbol={(params or {}).get('symbol', '')}"
                )
            time.sleep(0.4)
            response = self.session.get(url, params=params, timeout=45)
        response.raise_for_status()
        return response.json()


def _parse_nse_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    text = value.strip()
    # Examples: 27-Apr-2026, 18-Feb-2026 19:06, 16-Feb-2026
    text = text.split(" ")[0]
    for fmt in ("%d-%b-%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _role_flags(person_category: Optional[str]) -> dict[str, Any]:
    cat = (person_category or "").strip()
    lower = cat.lower()
    is_director = "director" in lower
    is_officer = any(
        token in lower
        for token in ("key managerial", "employee", "designated", "officer", "kmp")
    )
    is_ten = "promoter" in lower
    return {
        "relationship": cat or "Other",
        "is_director": is_director,
        "is_officer": is_officer and not is_director,
        "is_ten_percent_owner": is_ten,
        "officer_title": cat if is_officer else None,
    }


def _normalize_pit_row(raw: dict[str, Any]) -> Optional[dict[str, Any]]:
    mode = (raw.get("acqMode") or "").strip().lower()
    side = OPEN_MARKET_MODES.get(mode)
    if not side:
        # Fall back to explicit buy/sell only when mode already says Market *.
        return None

    shares = to_float(raw.get("secAcq"))
    total_value = to_float(raw.get("secVal"))
    price = None
    if shares and total_value and shares != 0:
        price = round(total_value / shares, 4)

    owned_after = to_float(str(raw.get("afterAcqSharesNo") or "").replace(",", ""))
    roles = _role_flags(raw.get("personCategory"))
    symbol = clean_whitespace(raw.get("symbol"))
    if symbol:
        symbol = symbol.upper()

    did = str(raw.get("did") or raw.get("pid") or "")
    accession = did or f"{symbol}-{raw.get('acqfromDt')}-{raw.get('acqName')}-{side}"

    return {
        "market": "IN",
        "ticker": symbol,
        "company_name": clean_whitespace(raw.get("company")),
        "cik": None,
        "exchange": clean_whitespace(raw.get("exchange")) or "NSE",
        "insider_name": clean_whitespace(raw.get("acqName")) or "Unknown",
        "relationship": roles["relationship"],
        "is_director": roles["is_director"],
        "is_officer": roles["is_officer"],
        "is_ten_percent_owner": roles["is_ten_percent_owner"],
        "officer_title": roles["officer_title"],
        "transaction_code": "P" if side == "buy" else "S",
        "transaction_side": side,
        "transaction_date": _parse_nse_date(raw.get("acqfromDt") or raw.get("acqtoDt")),
        "filing_date": _parse_nse_date(raw.get("intimDt") or raw.get("date")),
        "shares": shares,
        "price_per_share": price,
        "total_value": total_value,
        "shares_owned_after": owned_after,
        "ownership_form": None,
        "accession_number": accession[:64],
        "source_url": clean_whitespace(raw.get("xbrl")),
    }


def fetch_india_pit_rows(client: NseClient, *, days: int = 90) -> list[dict[str, Any]]:
    end = date.today()
    start = end - timedelta(days=max(days, 1))
    payload = client.get_json(
        "/api/corporates-pit",
        params={
            "index": "equities",
            "from_date": start.strftime("%d-%m-%Y"),
            "to_date": end.strftime("%d-%m-%Y"),
        },
    )
    rows = payload.get("data") or []
    normalized = []
    for raw in rows:
        item = _normalize_pit_row(raw)
        if item:
            normalized.append(item)
    return normalized


def upsert_india_transactions(rows: list[dict[str, Any]]) -> int:
    inserted = 0
    for row in rows:
        existing = (
            InsiderTransaction.query.filter_by(
                accession_number=row["accession_number"],
                insider_name=row["insider_name"],
                transaction_date=row["transaction_date"],
                transaction_code=row["transaction_code"],
                shares=row["shares"],
                price_per_share=row["price_per_share"],
            ).first()
        )
        if existing:
            continue
        db.session.add(InsiderTransaction(**row))
        try:
            db.session.commit()
            inserted += 1
        except IntegrityError:
            db.session.rollback()

        # Keep company shell for explore.
        if row.get("ticker"):
            company = Company.query.filter_by(market="IN", ticker=row["ticker"]).first()
            if company is None:
                company = Company(market="IN", ticker=row["ticker"])
                db.session.add(company)
            company.name = row.get("company_name") or company.name
            company.exchange = row.get("exchange") or company.exchange
            company.updated_at = datetime.now(timezone.utc)
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
    return inserted


def sync_india_insider_feed(*, days: int = 90) -> dict[str, Any]:
    run = SyncRun(market="IN", status="running")
    db.session.add(run)
    db.session.commit()

    client = NseClient()
    upserted = 0
    seen = 0
    try:
        rows = fetch_india_pit_rows(client, days=days)
        seen = len(rows)
        upserted = upsert_india_transactions(rows)
        run.status = "completed"
        run.filings_seen = seen
        run.transactions_upserted = upserted
        run.finished_at = datetime.now(timezone.utc)
        db.session.commit()
        return run.to_dict()
    except Exception as exc:  # noqa: BLE001
        run.status = "failed"
        run.filings_seen = seen
        run.transactions_upserted = upserted
        run.error_message = str(exc)
        run.finished_at = datetime.now(timezone.utc)
        db.session.commit()
        raise


def enrich_india_company_industry(client: NseClient | None, ticker: str) -> Optional[Company]:
    """Enrich India company sector/industry. Prefers Yahoo (free) when NSE quote is blocked."""
    ticker = ticker.upper().strip()
    company = Company.query.filter_by(market="IN", ticker=ticker).first()
    exchange = company.exchange if company else None

    # Prefer Yahoo — more reliable from restricted networks than NSE quote-equity.
    try:
        from app.services.yahoo_india import fetch_india_profile

        profile = fetch_india_profile(ticker, exchange)
        if company is None:
            company = Company(market="IN", ticker=ticker)
            db.session.add(company)
        if profile.get("name"):
            company.name = profile["name"]
        company.exchange = profile.get("exchange") or company.exchange or "NSE"
        company.sector = profile.get("sector") or company.sector
        company.industry = profile.get("industry") or company.industry
        company.updated_at = datetime.now(timezone.utc)
        db.session.commit()
        return company
    except Exception as yahoo_exc:  # noqa: BLE001
        logger.warning("Yahoo profile failed for %s: %s", ticker, yahoo_exc)

    if client is None:
        client = NseClient()
    try:
        quote = client.get_json("/api/quote-equity", params={"symbol": ticker})
    except Exception as exc:  # noqa: BLE001
        logger.warning("NSE quote-equity failed for %s: %s", ticker, exc)
        return company

    info = quote.get("info") or {}
    metadata = quote.get("metadata") or {}
    industry = info.get("industry") or metadata.get("industry")
    sector = info.get("macro") or info.get("sector") or industry
    name = info.get("companyName") or metadata.get("companyName")

    if company is None:
        company = Company(market="IN", ticker=ticker)
        db.session.add(company)
    if name:
        company.name = name
    company.exchange = company.exchange or "NSE"
    if industry:
        company.industry = industry
    if sector:
        company.sector = sector
    company.updated_at = datetime.now(timezone.utc)
    db.session.commit()
    return company


def get_india_financials(ticker: str, *, years: int = 5, refresh: bool = False) -> dict[str, Any]:
    """India financials via free Yahoo Finance annual statements (.NS / .BO)."""
    ticker = ticker.upper().strip()
    years = max(1, min(int(years), 10))

    if not refresh:
        cached = AnnualFinancial.query.filter_by(market="IN", ticker=ticker).all()
        if cached:
            return _india_shape_from_cache(cached)

    company = Company.query.filter_by(market="IN", ticker=ticker).first()
    exchange = company.exchange if company else None

    from app.services.yahoo_india import fetch_india_statements

    payload = fetch_india_statements(ticker, exchange, years=years)
    company_name = payload["company_name"]
    statements = payload["statements"]

    # Upsert company metadata.
    if company is None:
        company = Company(market="IN", ticker=ticker)
        db.session.add(company)
    company.name = company_name
    company.exchange = payload.get("exchange") or company.exchange or "NSE"
    company.sector = payload.get("sector") or company.sector
    company.industry = payload.get("industry") or company.industry
    company.updated_at = datetime.now(timezone.utc)

    AnnualFinancial.query.filter_by(market="IN", ticker=ticker).delete()
    mapping = {
        "income_statement": "income",
        "balance_sheet": "balance",
        "cash_flow": "cash_flow",
        "summary": "summary",
    }
    for statement_key, rows in statements.items():
        statement = mapping[statement_key]
        for row in rows:
            year = row.get("year")
            if not year:
                continue
            for metric_name, metric_value in row.items():
                if metric_name in {"year", "filed_date"} or metric_value is None:
                    continue
                db.session.add(
                    AnnualFinancial(
                        market="IN",
                        ticker=ticker,
                        company_name=company_name,
                        year=int(year),
                        statement=statement,
                        metric_name=metric_name,
                        metric_value=float(metric_value),
                        unit="INR",
                    )
                )
    db.session.commit()

    return {
        "market": "IN",
        "ticker": ticker,
        "company_name": company_name,
        "sector": company.sector,
        "industry": company.industry,
        "exchange": company.exchange,
        "retrieved_utc": datetime.now(timezone.utc).isoformat(),
        "cached": False,
        "note": f"Free Yahoo Finance annual statements ({payload.get('yahoo_symbol')}).",
        "statements": statements,
    }


def _india_shape_from_cache(rows: list[AnnualFinancial]) -> dict[str, Any]:
    ticker = rows[0].ticker
    company_name = rows[0].company_name
    buckets: dict[str, dict[int, dict[str, Any]]] = {
        "income_statement": {},
        "balance_sheet": {},
        "cash_flow": {},
        "summary": {},
    }
    reverse = {
        "income": "income_statement",
        "balance": "balance_sheet",
        "cash_flow": "cash_flow",
        "summary": "summary",
    }
    for row in rows:
        key = reverse.get(row.statement)
        if not key:
            continue
        bucket = buckets[key].setdefault(row.year, {"year": row.year})
        bucket[row.metric_name] = row.metric_value
    company = Company.query.filter_by(market="IN", ticker=ticker).first()
    return {
        "market": "IN",
        "ticker": ticker,
        "company_name": company_name,
        "sector": company.sector if company else None,
        "industry": company.industry if company else None,
        "exchange": company.exchange if company else None,
        "retrieved_utc": datetime.now(timezone.utc).isoformat(),
        "cached": True,
        "note": "Cached India financial statements.",
        "statements": {
            name: [by_year[y] for y in sorted(by_year.keys(), reverse=True)]
            for name, by_year in buckets.items()
        },
    }


def get_india_status() -> dict[str, Any]:
    total = InsiderTransaction.query.filter_by(market="IN").count()
    return {
        "market": "IN",
        "status": "active" if total else "ready",
        "phase": 2,
        "message": (
            "India open-market insider feed uses free NSE corporates-pit disclosures "
            "(Market Purchase / Market Sale), including trades reported on NSE and BSE. "
            "Financials and sector metadata use free Yahoo Finance (.NS / .BO)."
        ),
        "planned_sources": [
            "NSE corporates-pit (PIT)",
            "Yahoo Finance annual statements + sector/industry",
            "BSE-reported PIT rows included via NSE exchange field",
        ],
        "priority": ["insider", "financials", "sector_browse"],
        "cached_insider_rows": total,
    }


def list_india_insider_transactions(**_: Any) -> dict[str, Any]:
    # Kept for backward compatibility; routes now query the shared table directly.
    return get_india_status()

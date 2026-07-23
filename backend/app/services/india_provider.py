"""India insider + research helpers via free NSE public APIs (covers NSE/BSE-reported PIT)."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

import requests
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import AnnualFinancial, Company, IndiaDisclosure, InsiderTransaction, SyncRun
from app.utils.helpers import clean_whitespace, to_float

logger = logging.getLogger(__name__)

OPEN_MARKET_MODES = {"market purchase": "buy", "market sale": "sell"}
PLEDGE_MODES = {
    "pledge creation": "pledge",
    "revokation of pledge": "unpledge",
    "revocation of pledge": "unpledge",
    "invocation of pledge": "invoke",
}


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
        pages = [
            f"{self.BASE}/option-chain",
            f"{self.BASE}/companies-listing/corporate-filings-insider-trading",
            f"{self.BASE}/companies-listing/corporate-filings-regulation-29",
            f"{self.BASE}/market-data/live-equity-market",
        ]
        for page in pages:
            self.session.headers["Referer"] = page
            try:
                self.session.get(page, timeout=30)
            except Exception:  # noqa: BLE001
                continue
            time.sleep(0.2)
        self._warmed = True

    def get_json(self, path: str, *, params: Optional[dict] = None, referer: Optional[str] = None) -> Any:
        self.warm()
        url = path if path.startswith("http") else f"{self.BASE}{path}"
        if referer:
            self.session.headers["Referer"] = referer
        elif "sast" in url:
            self.session.headers["Referer"] = (
                f"{self.BASE}/companies-listing/corporate-filings-regulation-29"
            )
        elif "pledge" in url:
            self.session.headers["Referer"] = (
                f"{self.BASE}/companies-listing/corporate-filings-insider-trading"
            )
        elif "quote-equity" in url:
            self.session.headers["Referer"] = (
                f"{self.BASE}/get-quotes/equity?symbol={(params or {}).get('symbol', '')}"
            )
        elif "option-chain" in url:
            self.session.headers["Referer"] = f"{self.BASE}/option-chain"
        else:
            self.session.headers["Referer"] = (
                f"{self.BASE}/companies-listing/corporate-filings-insider-trading"
            )

        response = self.session.get(url, params=params, timeout=45)
        if response.status_code in {401, 403} or not response.text or response.text[:1] in {"<", ""}:
            self.warm(force=True)
            time.sleep(0.4)
            response = self.session.get(url, params=params, timeout=45)
        response.raise_for_status()
        try:
            return response.json()
        except Exception as exc:  # noqa: BLE001
            self.warm(force=True)
            time.sleep(0.5)
            response = self.session.get(url, params=params, timeout=45)
            response.raise_for_status()
            try:
                return response.json()
            except Exception:
                raise ValueError(f"NSE returned non-JSON for {url}: {response.text[:120]}") from exc


def _parse_nse_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    text = value.strip().split(" ")[0]
    # Ranges like 27-MAR-2024 to 27-MAR-2024
    if " to " in text.lower():
        text = text.split(" to ")[0].strip()
    for fmt in ("%d-%b-%Y", "%d-%B-%Y", "%d-%m-%Y", "%Y-%m-%d", "%d-%b-%y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    # uppercase month variants already covered by %b with locale; try title-case
    try:
        return datetime.strptime(text.title(), "%d-%b-%Y").date()
    except ValueError:
        return None


def _role_flags(person_category: Optional[str]) -> dict[str, Any]:
    cat = (person_category or "").strip()
    lower = cat.lower()
    is_director = "director" in lower and "independent" not in lower or lower == "director"
    if "independent director" in lower:
        is_director = True
    is_officer = any(
        token in lower
        for token in (
            "key managerial",
            "kmp",
            "employee",
            "designated",
            "officer",
            "ceo",
            "cfo",
            "cto",
            "managing director",
            "whole time",
        )
    )
    is_promoter = "promoter" in lower
    is_relative = "immediate relative" in lower or "relative" in lower
    relationship = cat or "Other"
    if is_promoter and "group" in lower:
        relationship = "Promoter Group"
    elif is_promoter:
        relationship = "Promoter"
    elif "independent director" in lower:
        relationship = "Independent Director"
    elif is_director:
        relationship = "Director"
    elif is_officer:
        relationship = cat
    elif is_relative:
        relationship = "Immediate Relative"
    return {
        "relationship": relationship,
        "is_director": bool(is_director),
        "is_officer": bool(is_officer and not is_promoter),
        "is_ten_percent_owner": bool(is_promoter),
        "officer_title": cat if is_officer else None,
    }


def _normalize_pit_row(raw: dict[str, Any], *, include_pledge_modes: bool = False) -> Optional[dict[str, Any]]:
    mode = (raw.get("acqMode") or "").strip().lower()
    side = OPEN_MARKET_MODES.get(mode)
    if side is None and include_pledge_modes:
        side = PLEDGE_MODES.get(mode)
    if not side:
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
    accession = did or f"{symbol}-{raw.get('acqfromDt')}-{raw.get('acqName')}-{side}-{mode}"
    code = {"buy": "P", "sell": "S"}.get(side, side[:3].upper())

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
        "transaction_code": code,
        "transaction_side": side if side in {"buy", "sell"} else "sell" if side in {"invoke"} else "buy",
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


def fetch_india_pit_rows(client: NseClient, *, days: int = 120) -> list[dict[str, Any]]:
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
        item = _normalize_pit_row(raw, include_pledge_modes=False)
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


def _stable_id(*parts: Any) -> str:
    blob = "|".join("" if p is None else str(p) for p in parts)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:40]


def sync_india_pledge_feed(client: Optional[NseClient] = None) -> dict[str, Any]:
    client = client or NseClient()
    payload = client.get_json("/api/corporate-pledgedata", params={"index": "equities"})
    rows = payload.get("data") or []
    upserted = 0
    for raw in rows:
        company_name = clean_whitespace(raw.get("comName"))
        ticker = None
        # pledge feed often lacks symbol; try match existing companies by name
        if company_name:
            match = Company.query.filter(
                Company.market == "IN",
                Company.name.ilike(company_name),
            ).first()
            if match:
                ticker = match.ticker
        external_id = _stable_id(
            "pledge",
            company_name,
            raw.get("broadcastDt"),
            raw.get("shp"),
            raw.get("numSharesPledged"),
            raw.get("percSharesPledged"),
        )
        existing = IndiaDisclosure.query.filter_by(kind="pledge", external_id=external_id).first()
        if existing:
            continue
        db.session.add(
            IndiaDisclosure(
                kind="pledge",
                external_id=external_id,
                ticker=ticker,
                company_name=company_name,
                party_name="Promoter holdings",
                event_date=_parse_nse_date(raw.get("shp")),
                filing_date=_parse_nse_date(raw.get("broadcastDt")),
                side="pledge",
                shares=to_float(raw.get("numSharesPledged")),
                percent=to_float(str(raw.get("percSharesPledged") or "").strip()),
                details=(
                    f"Promoter holding {str(raw.get('percPromoterHolding') or '').strip()}% · "
                    f"pledged {str(raw.get('percSharesPledged') or '').strip()}%"
                ),
                source_url=None,
                raw_json=json.dumps(raw)[:4000],
            )
        )
        try:
            db.session.commit()
            upserted += 1
        except IntegrityError:
            db.session.rollback()
    return {"kind": "pledge", "seen": len(rows), "upserted": upserted}


def sync_india_sast_for_symbols(symbols: list[str], client: Optional[NseClient] = None) -> dict[str, Any]:
    client = client or NseClient()
    seen = 0
    upserted = 0
    for symbol in symbols:
        symbol = symbol.upper().strip()
        if not symbol:
            continue
        try:
            payload = client.get_json(
                "/api/corporate-sast-reg29",
                params={"index": "equities", "symbol": symbol},
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("SAST fetch failed for %s: %s", symbol, exc)
            continue
        rows = payload.get("data") or []
        seen += len(rows)
        for raw in rows:
            external_id = _stable_id(
                "sast",
                symbol,
                raw.get("application_no"),
                raw.get("acquirerName"),
                raw.get("acquirerDate"),
                raw.get("acqSaleType"),
                raw.get("noOfShareAcq"),
                raw.get("noOfShareSale"),
            )
            if IndiaDisclosure.query.filter_by(kind="sast", external_id=external_id).first():
                continue
            sale = to_float(raw.get("noOfShareSale"))
            acq = to_float(raw.get("noOfShareAcq"))
            side_raw = (raw.get("acqSaleType") or "").strip().lower()
            side = "sell" if "sale" in side_raw else "buy" if "buy" in side_raw or "acq" in side_raw else side_raw
            db.session.add(
                IndiaDisclosure(
                    kind="sast",
                    external_id=external_id,
                    ticker=symbol,
                    company_name=clean_whitespace(raw.get("company")),
                    party_name=clean_whitespace(raw.get("acquirerName")),
                    event_date=_parse_nse_date(raw.get("acquirerDate")),
                    filing_date=_parse_nse_date(raw.get("timestamp") or raw.get("sysTime")),
                    side=side or None,
                    shares=sale or acq,
                    percent=to_float(raw.get("totAftShare")),
                    details=clean_whitespace(
                        f"{raw.get('regType') or ''} · {raw.get('acquisitionMode') or ''} · "
                        f"promoter={raw.get('promoterType')}"
                    ),
                    source_url=clean_whitespace(raw.get("attachement")),
                    raw_json=json.dumps(raw)[:4000],
                )
            )
            try:
                db.session.commit()
                upserted += 1
            except IntegrityError:
                db.session.rollback()
        time.sleep(0.15)
    return {"kind": "sast", "symbols": len(symbols), "seen": seen, "upserted": upserted}


def _india_sast_symbols(limit: int = 25) -> list[str]:
    from app.models import Watchlist

    symbols: list[str] = []
    for wl in Watchlist.query.filter_by(market="IN").all():
        for item in wl.items:
            if item.ticker:
                symbols.append(item.ticker.upper())
    recent = (
        InsiderTransaction.query.with_entities(InsiderTransaction.ticker)
        .filter(
            InsiderTransaction.market == "IN",
            InsiderTransaction.ticker.isnot(None),
        )
        .distinct()
        .limit(limit)
        .all()
    )
    for row in recent:
        if row[0]:
            symbols.append(row[0].upper())
    out = []
    seen = set()
    for s in symbols:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out[:limit]


def sync_india_insider_feed(*, days: int = 120, trigger: str = "manual", include_extra: bool = True) -> dict[str, Any]:
    run = SyncRun(market="IN", status="running", trigger=trigger)
    db.session.add(run)
    db.session.commit()

    client = NseClient()
    upserted = 0
    seen = 0
    extra: dict[str, Any] = {}
    try:
        rows = fetch_india_pit_rows(client, days=days)
        seen = len(rows)
        upserted = upsert_india_transactions(rows)
        if include_extra:
            try:
                extra["pledge"] = sync_india_pledge_feed(client)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Pledge sync failed: %s", exc)
                extra["pledge_error"] = str(exc)
            try:
                symbols = _india_sast_symbols(limit=20)
                extra["sast"] = sync_india_sast_for_symbols(symbols, client)
            except Exception as exc:  # noqa: BLE001
                logger.warning("SAST sync failed: %s", exc)
                extra["sast_error"] = str(exc)

        run.status = "completed"
        run.filings_seen = seen
        run.transactions_upserted = upserted
        run.finished_at = datetime.now(timezone.utc)
        db.session.commit()
        payload = run.to_dict()
        payload["extra"] = extra
        return payload
    except Exception as exc:  # noqa: BLE001
        run.status = "failed"
        run.filings_seen = seen
        run.transactions_upserted = upserted
        run.error_message = str(exc)
        run.finished_at = datetime.now(timezone.utc)
        db.session.commit()
        raise


def list_india_disclosures(*, kind: str, ticker: Optional[str] = None, page: int = 1, page_size: int = 50) -> dict[str, Any]:
    kind = kind.lower().strip()
    query = IndiaDisclosure.query.filter_by(kind=kind)
    if ticker:
        query = query.filter(IndiaDisclosure.ticker == ticker.upper())
    total = query.count()
    page = max(page, 1)
    page_size = min(max(page_size, 1), 200)
    items = (
        query.order_by(IndiaDisclosure.filing_date.desc(), IndiaDisclosure.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "market": "IN",
        "kind": kind,
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [item.to_dict() for item in items],
    }


def enrich_india_company_industry(client: NseClient | None, ticker: str) -> Optional[Company]:
    """Enrich India company sector/industry. Prefers Yahoo (free) when NSE quote is blocked."""
    ticker = ticker.upper().strip()
    company = Company.query.filter_by(market="IN", ticker=ticker).first()
    exchange = company.exchange if company else None

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
    pledge = IndiaDisclosure.query.filter_by(kind="pledge").count()
    sast = IndiaDisclosure.query.filter_by(kind="sast").count()
    return {
        "market": "IN",
        "status": "active" if total else "ready",
        "phase": 2,
        "message": (
            "India open-market insider feed uses free NSE corporates-pit disclosures "
            "(Market Purchase / Market Sale), including trades reported on NSE and BSE. "
            "Pledge and SAST Reg.29 are available as separate views. "
            "Financials/sector metadata use free Yahoo Finance (.NS / .BO)."
        ),
        "cached_insider_rows": total,
        "cached_pledge_rows": pledge,
        "cached_sast_rows": sast,
    }


def list_india_insider_transactions(**_: Any) -> dict[str, Any]:
    return get_india_status()

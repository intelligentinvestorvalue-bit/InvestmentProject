"""SEC EDGAR client for recent Form 4 open-market trades."""

from __future__ import annotations

import logging
import re
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional
from xml.etree import ElementTree as ET

import requests
from flask import current_app
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import InsiderTransaction, SyncRun
from app.utils.helpers import (
    accession_to_path,
    build_relationship,
    clean_whitespace,
    normalize_accession,
    parse_date,
    to_float,
)

logger = logging.getLogger(__name__)

OPEN_MARKET_CODES = {"P": "buy", "S": "sell"}


class SecEdgarClient:
    """Thin SEC HTTP client with rate limiting and required User-Agent."""

    BASE = "https://www.sec.gov"
    DATA = "https://data.sec.gov"
    EFTS = "https://efts.sec.gov"

    def __init__(self, user_agent: str, delay_seconds: float = 0.12) -> None:
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": user_agent,
                "Accept-Encoding": "gzip, deflate",
                "Accept": "application/json, text/html, application/xhtml+xml, */*",
            }
        )
        self.delay_seconds = delay_seconds
        self._last_request_at = 0.0

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self.delay_seconds:
            time.sleep(self.delay_seconds - elapsed)

    def get(self, url: str, *, params: Optional[dict] = None, timeout: int = 30) -> requests.Response:
        self._throttle()
        response = self.session.get(url, params=params, timeout=timeout)
        self._last_request_at = time.monotonic()
        response.raise_for_status()
        return response


def _local(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag


def _find_text(node: Optional[ET.Element], path: str) -> Optional[str]:
    if node is None:
        return None
    parts = path.split("/")
    current: Optional[ET.Element] = node
    for part in parts:
        if current is None:
            return None
        nxt = None
        for child in list(current):
            if _local(child.tag) == part:
                nxt = child
                break
        current = nxt
    if current is None or current.text is None:
        return None
    return current.text.strip()


def _truthy(value: Optional[str]) -> bool:
    return (value or "").strip() in {"1", "true", "True", "yes", "Y"}


def parse_form4_xml(
    xml_text: str,
    *,
    accession_number: str,
    filing_date: Optional[date],
    source_url: str,
) -> list[dict[str, Any]]:
    """Extract open-market P/S non-derivative transactions from a Form 4 XML document."""
    root = ET.fromstring(xml_text)

    issuer = None
    for child in root.iter():
        if _local(child.tag) == "issuer":
            issuer = child
            break

    cik = clean_whitespace(_find_text(issuer, "issuerCik"))
    company_name = clean_whitespace(_find_text(issuer, "issuerName"))
    ticker = clean_whitespace(_find_text(issuer, "issuerTradingSymbol"))
    if ticker:
        ticker = ticker.upper()

    reporting_owners: list[dict[str, Any]] = []
    for child in root.iter():
        if _local(child.tag) != "reportingOwner":
            continue
        owner_id = None
        relationship = None
        for sub in list(child):
            local = _local(sub.tag)
            if local == "reportingOwnerId":
                owner_id = sub
            elif local == "reportingOwnerRelationship":
                relationship = sub
        name = clean_whitespace(_find_text(owner_id, "rptOwnerName")) or "Unknown"
        is_director = _truthy(_find_text(relationship, "isDirector"))
        is_officer = _truthy(_find_text(relationship, "isOfficer"))
        is_ten = _truthy(_find_text(relationship, "isTenPercentOwner"))
        officer_title = clean_whitespace(_find_text(relationship, "officerTitle"))
        reporting_owners.append(
            {
                "insider_name": name,
                "is_director": is_director,
                "is_officer": is_officer,
                "is_ten_percent_owner": is_ten,
                "officer_title": officer_title,
                "relationship": build_relationship(
                    is_director=is_director,
                    is_officer=is_officer,
                    is_ten_percent_owner=is_ten,
                    officer_title=officer_title,
                ),
            }
        )

    if not reporting_owners:
        reporting_owners = [
            {
                "insider_name": "Unknown",
                "is_director": False,
                "is_officer": False,
                "is_ten_percent_owner": False,
                "officer_title": None,
                "relationship": "Other",
            }
        ]

    rows: list[dict[str, Any]] = []
    for child in root.iter():
        if _local(child.tag) != "nonDerivativeTransaction":
            continue

        code = clean_whitespace(_find_text(child, "transactionCoding/transactionCode"))
        if code not in OPEN_MARKET_CODES:
            continue

        tx_date = parse_date(_find_text(child, "transactionDate/value"))
        shares = to_float(_find_text(child, "transactionAmounts/transactionShares/value"))
        price = to_float(_find_text(child, "transactionAmounts/transactionPricePerShare/value"))
        shares_after = to_float(
            _find_text(child, "postTransactionAmounts/sharesOwnedFollowingTransaction/value")
        )
        ownership_form = clean_whitespace(
            _find_text(child, "ownershipNature/directOrIndirectOwnership/value")
        )

        total_value = None
        if shares is not None and price is not None:
            total_value = round(shares * price, 2)

        for owner in reporting_owners:
            rows.append(
                {
                    "market": "US",
                    "ticker": ticker,
                    "company_name": company_name,
                    "cik": cik.zfill(10) if cik and cik.isdigit() else cik,
                    "insider_name": owner["insider_name"],
                    "relationship": owner["relationship"],
                    "is_director": owner["is_director"],
                    "is_officer": owner["is_officer"],
                    "is_ten_percent_owner": owner["is_ten_percent_owner"],
                    "officer_title": owner["officer_title"],
                    "transaction_code": code,
                    "transaction_side": OPEN_MARKET_CODES[code],
                    "transaction_date": tx_date,
                    "filing_date": filing_date,
                    "shares": shares,
                    "price_per_share": price,
                    "total_value": total_value,
                    "shares_owned_after": shares_after,
                    "ownership_form": ownership_form,
                    "accession_number": accession_number,
                    "source_url": source_url,
                }
            )
    return rows


def search_recent_form4_filings(client: SecEdgarClient, *, days: int, limit: int) -> list[dict[str, Any]]:
    """Discover recent Form 4 filings via current-feed, then EFTS, then issuer sample."""
    filings = _form4_from_current_atom(client, limit=limit)
    if filings:
        return filings[:limit]

    end = date.today()
    start = end - timedelta(days=max(days, 1))
    params = {
        "forms": "4",
        "dateRange": "custom",
        "startdt": start.isoformat(),
        "enddt": end.isoformat(),
        "from": 0,
        "size": min(limit, 100),
    }
    try:
        response = client.get(f"{client.EFTS}/LATEST/search-index", params=params)
        payload = response.json()
        hits = payload.get("hits", {}).get("hits", [])
        efts_filings: list[dict[str, Any]] = []
        for hit in hits:
            source = hit.get("_source", {})
            accession = source.get("adsh") or source.get("accession_no") or source.get("file_num")
            if not accession:
                continue
            display = source.get("display_names") or []
            ciks = source.get("ciks") or []
            efts_filings.append(
                {
                    "accession_number": accession,
                    "cik": str(ciks[0] if ciks else source.get("cik") or "").zfill(10),
                    "filing_date": parse_date(source.get("file_date") or source.get("period_of_report")),
                    "company_name": display[0] if display else None,
                    "ticker": None,
                    "form": source.get("form") or "4",
                }
            )
        if efts_filings:
            return efts_filings[:limit]
    except Exception as exc:  # noqa: BLE001
        logger.warning("EFTS Form 4 search failed (%s); falling back to company sample", exc)

    return _fallback_form4_from_sample_issuers(client, limit=limit)


def _form4_from_current_atom(client: SecEdgarClient, *, limit: int) -> list[dict[str, Any]]:
    """Parse SEC 'current filings' Atom feed filtered to Form 4 ownership filings."""
    url = f"{client.BASE}/cgi-bin/browse-edgar"
    params = {
        "action": "getcurrent",
        # owner=only returns true Form 4 ownership filings (not 424B2 false-positives).
        "type": "4",
        "company": "",
        "dateb": "",
        "owner": "only",
        "count": str(min(max(limit * 3, 40), 100)),
        "output": "atom",
    }
    try:
        xml_text = client.get(url, params=params).text
        root = ET.fromstring(xml_text)
    except Exception as exc:  # noqa: BLE001
        logger.warning("SEC current Form 4 atom feed failed: %s", exc)
        return []

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    filings_by_accession: dict[str, dict[str, Any]] = {}
    for entry in root.findall("atom:entry", ns):
        title = (entry.findtext("atom:title", default="", namespaces=ns) or "").strip()
        if not title.startswith("4 ") and not title.startswith("4-") and not title.startswith("4/"):
            # Keep classic "4 - Company..." titles only.
            if not title.startswith("4 -"):
                continue
        summary = (entry.findtext("atom:summary", default="", namespaces=ns) or "").strip()
        updated = entry.findtext("atom:updated", default="", namespaces=ns)
        link = entry.find("atom:link", ns)
        href = link.get("href") if link is not None else ""

        cik_match = re.search(r"\((\d{6,10})\)", title)
        cik = cik_match.group(1).zfill(10) if cik_match else ""
        company_name = title
        if " - " in title:
            company_name = title.split(" - ", 1)[1]
            company_name = re.sub(r"\(\d{6,10}\).*$", "", company_name).strip()

        accession = None
        acc_match = re.search(r"accession[- ]number[=:\s]+([0-9-]+)", summary, re.I)
        if acc_match:
            accession = acc_match.group(1)
        if not accession and href:
            acc_match = re.search(r"/(\d{10}-\d{2}-\d{6})", href)
            if acc_match:
                accession = acc_match.group(1)
        if not accession:
            continue

        is_issuer = "issuer" in title.lower()
        existing = filings_by_accession.get(accession)
        row = {
            "accession_number": accession,
            "cik": cik,
            "filing_date": parse_date((updated or "")[:10]),
            "company_name": clean_whitespace(company_name),
            "ticker": None,
            "form": "4",
            "is_issuer": is_issuer,
        }
        # Prefer issuer entry for company identity; otherwise keep first reporting entry.
        if existing is None or (is_issuer and not existing.get("is_issuer")):
            filings_by_accession[accession] = row
        if len(filings_by_accession) >= limit:
            break

    return list(filings_by_accession.values())[:limit]


def _fallback_form4_from_sample_issuers(client: SecEdgarClient, *, limit: int) -> list[dict[str, Any]]:
    sample_tickers = [
        "AAPL",
        "MSFT",
        "NVDA",
        "AMZN",
        "GOOGL",
        "META",
        "JPM",
        "XOM",
        "JNJ",
        "TSLA",
        "V",
        "UNH",
        "HD",
        "PG",
        "MA",
        "COST",
        "AVGO",
        "WMT",
        "BAC",
        "CRM",
    ]
    ticker_map = _load_ticker_map(client)
    filings: list[dict[str, Any]] = []
    for ticker in sample_tickers:
        if len(filings) >= limit:
            break
        info = ticker_map.get(ticker)
        if not info:
            continue
        cik = info["cik"]
        try:
            subs = client.get(f"{client.DATA}/submissions/CIK{cik}.json").json()
        except Exception:  # noqa: BLE001
            continue
        recent = subs.get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        accessions = recent.get("accessionNumber", [])
        filing_dates = recent.get("filingDate", [])
        primary_docs = recent.get("primaryDocument", [])
        for idx, form in enumerate(forms):
            if form != "4":
                continue
            accession = accessions[idx]
            filings.append(
                {
                    "accession_number": accession,
                    "cik": cik,
                    "filing_date": parse_date(filing_dates[idx] if idx < len(filing_dates) else None),
                    "company_name": info.get("name") or subs.get("name"),
                    "ticker": ticker,
                    "form": "4",
                    "primary_document": primary_docs[idx] if idx < len(primary_docs) else None,
                }
            )
            if len(filings) >= limit:
                break
    return filings[:limit]


_TICKER_CACHE: dict[str, Any] = {"loaded_at": None, "map": {}}


def _load_ticker_map(client: SecEdgarClient) -> dict[str, dict[str, str]]:
    loaded_at = _TICKER_CACHE.get("loaded_at")
    if loaded_at and (datetime.now(timezone.utc) - loaded_at) < timedelta(hours=24):
        return _TICKER_CACHE["map"]

    response = client.get(f"{client.BASE}/files/company_tickers.json")
    raw = response.json()
    mapping: dict[str, dict[str, str]] = {}
    for item in raw.values():
        ticker = str(item.get("ticker", "")).upper()
        cik = str(item.get("cik_str", "")).zfill(10)
        name = item.get("title") or ""
        if ticker:
            mapping[ticker] = {"cik": cik, "name": name}
    _TICKER_CACHE["map"] = mapping
    _TICKER_CACHE["loaded_at"] = datetime.now(timezone.utc)
    return mapping


def resolve_form4_xml_url(client: SecEdgarClient, filing: dict[str, Any]) -> Optional[str]:
    """Locate the ownership XML document URL for a Form 4 accession."""
    accession = filing["accession_number"]
    cik = (filing.get("cik") or "").zfill(10) if filing.get("cik") else ""
    acc_nodash = accession_to_path(accession)

    primary = filing.get("primary_document")
    if primary and cik:
        if primary.lower().endswith(".xml"):
            return f"{client.BASE}/Archives/edgar/data/{int(cik)}/{acc_nodash}/{primary}"

    # Index JSON discovery
    if not cik:
        # Try EFTS-style entity id parsing later; without CIK we cannot build archive URL reliably.
        return None

    index_url = f"{client.BASE}/Archives/edgar/data/{int(cik)}/{acc_nodash}/index.json"
    try:
        index = client.get(index_url).json()
        items = index.get("directory", {}).get("item", [])
        xml_candidates = []
        for item in items:
            name = str(item.get("name", ""))
            lower = name.lower()
            if not lower.endswith(".xml"):
                continue
            if "xsl" in lower:
                continue
            if any(bad in lower for bad in ("exfilingfees", "filingfees", "exhibit", "ex-")):
                continue
            xml_candidates.append(name)

        preferred = [
            name
            for name in xml_candidates
            if any(token in name.lower() for token in ("form4", "ownership", "primary_doc", "primary"))
        ]
        chosen = (preferred or xml_candidates or [None])[0]
        if not chosen:
            return None
        return f"{client.BASE}/Archives/edgar/data/{int(cik)}/{acc_nodash}/{chosen}"
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to resolve Form 4 XML for %s: %s", accession, exc)
        return None


def upsert_transactions(rows: list[dict[str, Any]]) -> int:
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
    return inserted


def sync_us_insider_feed(
    *,
    days: int = 7,
    max_filings: Optional[int] = None,
    trigger: str = "manual",
) -> dict[str, Any]:
    """Fetch recent Form 4s, parse open-market P/S trades, and cache them."""
    user_agent = current_app.config["SEC_USER_AGENT"]
    delay = current_app.config["SEC_REQUEST_DELAY_SECONDS"]
    limit = max_filings or current_app.config["SYNC_MAX_FILINGS"]

    run = SyncRun(market="US", status="running", trigger=trigger)
    db.session.add(run)
    db.session.commit()

    client = SecEdgarClient(user_agent=user_agent, delay_seconds=delay)
    upserted = 0
    seen = 0

    try:
        filings = search_recent_form4_filings(client, days=days, limit=limit)
        seen = len(filings)
        for filing in filings:
            # Ensure CIK / primary doc when missing via submissions if ticker known
            if not filing.get("cik") and filing.get("ticker"):
                info = _load_ticker_map(client).get(str(filing["ticker"]).upper())
                if info:
                    filing["cik"] = info["cik"]
                    filing.setdefault("company_name", info["name"])

            xml_url = resolve_form4_xml_url(client, filing)
            if not xml_url:
                continue
            try:
                xml_text = client.get(xml_url).text
                rows = parse_form4_xml(
                    xml_text,
                    accession_number=filing["accession_number"],
                    filing_date=filing.get("filing_date"),
                    source_url=xml_url,
                )
                # Fill missing issuer fields from filing metadata when XML omits them.
                for row in rows:
                    row["ticker"] = row.get("ticker") or filing.get("ticker")
                    row["company_name"] = row.get("company_name") or filing.get("company_name")
                    row["cik"] = row.get("cik") or filing.get("cik")
                upserted += upsert_transactions(rows)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed parsing Form 4 %s: %s", filing.get("accession_number"), exc)
                continue

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

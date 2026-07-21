"""Explore / sector browse helpers."""

from __future__ import annotations

import logging
import time
from typing import Any

from flask import current_app
from sqlalchemy import func, or_

from app.models import Company, InsiderTransaction
from app.services.india_provider import enrich_india_company_industry
from app.services.sec_financials import _upsert_company_from_submissions
from app.services.sec_form4 import SecEdgarClient, _load_ticker_map

logger = logging.getLogger(__name__)


def list_sectors(market: str) -> dict[str, Any]:
    market = market.upper()
    rows = (
        Company.query.with_entities(Company.sector, func.count(Company.id))
        .filter(Company.market == market, Company.sector.isnot(None), Company.sector != "")
        .group_by(Company.sector)
        .order_by(func.count(Company.id).desc(), Company.sector.asc())
        .all()
    )
    return {
        "market": market,
        "sectors": [{"sector": sector, "company_count": count} for sector, count in rows],
        "total_companies": Company.query.filter_by(market=market).count(),
    }


def list_industries(market: str, sector: str | None = None) -> dict[str, Any]:
    market = market.upper()
    query = Company.query.with_entities(Company.industry, func.count(Company.id)).filter(
        Company.market == market,
        Company.industry.isnot(None),
        Company.industry != "",
    )
    if sector:
        query = query.filter(Company.sector == sector)
    rows = query.group_by(Company.industry).order_by(func.count(Company.id).desc()).all()
    return {
        "market": market,
        "sector": sector,
        "industries": [{"industry": industry, "company_count": count} for industry, count in rows],
    }


def list_companies(
    market: str,
    *,
    sector: str | None = None,
    industry: str | None = None,
    q: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> dict[str, Any]:
    market = market.upper()
    query = Company.query.filter_by(market=market)
    if sector:
        query = query.filter(Company.sector == sector)
    if industry:
        query = query.filter(Company.industry == industry)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(Company.ticker.ilike(like), Company.name.ilike(like)))
    total = query.count()
    page = max(page, 1)
    page_size = min(max(page_size, 1), 200)
    items = (
        query.order_by(Company.ticker.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "market": market,
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [item.to_dict() for item in items],
    }


def sync_explore_metadata(market: str, *, limit: int = 40) -> dict[str, Any]:
    """Enrich company sector/industry metadata from free sources for tickers we already know."""
    market = market.upper()
    tickers = (
        InsiderTransaction.query.with_entities(InsiderTransaction.ticker)
        .filter(
            InsiderTransaction.market == market,
            InsiderTransaction.ticker.isnot(None),
            InsiderTransaction.ticker != "",
        )
        .distinct()
        .limit(limit)
        .all()
    )
    symbols = [row[0].upper() for row in tickers if row[0]]
    updated = 0

    if market == "US":
        client = SecEdgarClient(
            user_agent=current_app.config["SEC_USER_AGENT"],
            delay_seconds=current_app.config["SEC_REQUEST_DELAY_SECONDS"],
        )
        ticker_map = _load_ticker_map(client)
        for symbol in symbols:
            info = ticker_map.get(symbol)
            if not info:
                continue
            try:
                _upsert_company_from_submissions(
                    client,
                    ticker=symbol,
                    cik=info["cik"],
                    name=info.get("name") or symbol,
                )
                updated += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning("US explore enrich failed for %s: %s", symbol, exc)
    elif market == "IN":
        for symbol in symbols:
            try:
                company = enrich_india_company_industry(None, symbol)
                if company and company.sector:
                    updated += 1
                time.sleep(0.1)
            except Exception as exc:  # noqa: BLE001
                logger.warning("India explore enrich failed for %s: %s", symbol, exc)
    else:
        raise ValueError(f"Unsupported market: {market}")

    return {"market": market, "tickers_considered": len(symbols), "companies_updated": updated}

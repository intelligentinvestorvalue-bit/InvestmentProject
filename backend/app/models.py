"""SQLAlchemy models."""

from __future__ import annotations

from datetime import datetime, timezone

from app.extensions import db


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Company(db.Model):
    """Cached company identity / sector metadata for explore + research."""

    __tablename__ = "companies"
    __table_args__ = (
        db.UniqueConstraint("market", "ticker", name="uq_company_market_ticker"),
    )

    id = db.Column(db.Integer, primary_key=True)
    market = db.Column(db.String(8), nullable=False, index=True)
    ticker = db.Column(db.String(32), nullable=False, index=True)
    name = db.Column(db.String(255), nullable=True)
    cik = db.Column(db.String(20), nullable=True, index=True)
    exchange = db.Column(db.String(64), nullable=True)
    sector = db.Column(db.String(128), nullable=True, index=True)
    industry = db.Column(db.String(255), nullable=True, index=True)
    sic = db.Column(db.String(16), nullable=True)
    sic_description = db.Column(db.String(255), nullable=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "market": self.market,
            "ticker": self.ticker,
            "name": self.name,
            "cik": self.cik,
            "exchange": self.exchange,
            "sector": self.sector,
            "industry": self.industry,
            "sic": self.sic,
            "sic_description": self.sic_description,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class AnnualFinancial(db.Model):
    """Cached annual financial statement line items."""

    __tablename__ = "annual_financials"
    __table_args__ = (
        db.UniqueConstraint(
            "market",
            "ticker",
            "year",
            "statement",
            "metric_name",
            name="uq_annual_financial",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    market = db.Column(db.String(8), nullable=False, default="US", index=True)
    ticker = db.Column(db.String(32), nullable=False, index=True)
    company_name = db.Column(db.String(255), nullable=True)
    cik = db.Column(db.String(20), nullable=True, index=True)
    year = db.Column(db.Integer, nullable=False, index=True)
    statement = db.Column(db.String(32), nullable=False, index=True)  # income|balance|cash_flow
    metric_name = db.Column(db.String(128), nullable=False)
    metric_value = db.Column(db.Float, nullable=True)
    unit = db.Column(db.String(32), nullable=True)
    filed_date = db.Column(db.Date, nullable=True)
    fetched_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "market": self.market,
            "ticker": self.ticker,
            "company_name": self.company_name,
            "cik": self.cik,
            "year": self.year,
            "statement": self.statement,
            "metric_name": self.metric_name,
            "metric_value": self.metric_value,
            "unit": self.unit,
            "filed_date": self.filed_date.isoformat() if self.filed_date else None,
            "fetched_at": self.fetched_at.isoformat() if self.fetched_at else None,
        }


class InsiderTransaction(db.Model):
    """Cached open-market insider buy/sell rows (US Form 4 / India NSE PIT)."""

    __tablename__ = "insider_transactions"
    __table_args__ = (
        db.UniqueConstraint(
            "accession_number",
            "insider_name",
            "transaction_date",
            "transaction_code",
            "shares",
            "price_per_share",
            name="uq_insider_tx",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    market = db.Column(db.String(8), nullable=False, default="US", index=True)
    ticker = db.Column(db.String(32), nullable=True, index=True)
    company_name = db.Column(db.String(255), nullable=True, index=True)
    cik = db.Column(db.String(20), nullable=True, index=True)
    exchange = db.Column(db.String(64), nullable=True)

    insider_name = db.Column(db.String(255), nullable=False, index=True)
    relationship = db.Column(db.String(255), nullable=True)
    is_director = db.Column(db.Boolean, default=False, index=True)
    is_officer = db.Column(db.Boolean, default=False, index=True)
    is_ten_percent_owner = db.Column(db.Boolean, default=False, index=True)
    officer_title = db.Column(db.String(255), nullable=True)

    transaction_code = db.Column(db.String(8), nullable=False, index=True)  # P/S or BUY/SELL
    transaction_side = db.Column(db.String(8), nullable=False, index=True)  # buy | sell
    transaction_date = db.Column(db.Date, nullable=True, index=True)
    filing_date = db.Column(db.Date, nullable=True, index=True)

    shares = db.Column(db.Float, nullable=True)
    price_per_share = db.Column(db.Float, nullable=True)
    total_value = db.Column(db.Float, nullable=True, index=True)
    shares_owned_after = db.Column(db.Float, nullable=True)
    ownership_form = db.Column(db.String(8), nullable=True)  # D / I

    accession_number = db.Column(db.String(64), nullable=False, index=True)
    source_url = db.Column(db.String(512), nullable=True)
    fetched_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "market": self.market,
            "ticker": self.ticker,
            "company_name": self.company_name,
            "cik": self.cik,
            "exchange": self.exchange,
            "insider_name": self.insider_name,
            "relationship": self.relationship,
            "is_director": bool(self.is_director),
            "is_officer": bool(self.is_officer),
            "is_ten_percent_owner": bool(self.is_ten_percent_owner),
            "officer_title": self.officer_title,
            "transaction_code": self.transaction_code,
            "transaction_side": self.transaction_side,
            "transaction_date": self.transaction_date.isoformat() if self.transaction_date else None,
            "filing_date": self.filing_date.isoformat() if self.filing_date else None,
            "shares": self.shares,
            "price_per_share": self.price_per_share,
            "total_value": self.total_value,
            "shares_owned_after": self.shares_owned_after,
            "ownership_form": self.ownership_form,
            "accession_number": self.accession_number,
            "source_url": self.source_url,
            "fetched_at": self.fetched_at.isoformat() if self.fetched_at else None,
        }


class SyncRun(db.Model):
    """Tracks background/manual sync attempts."""

    __tablename__ = "sync_runs"

    id = db.Column(db.Integer, primary_key=True)
    market = db.Column(db.String(8), nullable=False, default="US")
    started_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    finished_at = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(32), nullable=False, default="running")
    filings_seen = db.Column(db.Integer, default=0)
    transactions_upserted = db.Column(db.Integer, default=0)
    error_message = db.Column(db.Text, nullable=True)
    trigger = db.Column(db.String(32), nullable=True, default="manual")  # manual | scheduled

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "market": self.market,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "status": self.status,
            "filings_seen": self.filings_seen,
            "transactions_upserted": self.transactions_upserted,
            "error_message": self.error_message,
            "trigger": self.trigger,
        }


class Watchlist(db.Model):
    """Named saved screen / watchlist."""

    __tablename__ = "watchlists"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    market = db.Column(db.String(8), nullable=False, default="US", index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    items = db.relationship(
        "WatchlistItem",
        backref="watchlist",
        cascade="all, delete-orphan",
        order_by="WatchlistItem.ticker",
    )

    def to_dict(self, *, include_items: bool = True) -> dict:
        payload = {
            "id": self.id,
            "name": self.name,
            "market": self.market,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "item_count": len(self.items or []),
        }
        if include_items:
            payload["items"] = [item.to_dict() for item in self.items]
        return payload


class WatchlistItem(db.Model):
    __tablename__ = "watchlist_items"
    __table_args__ = (
        db.UniqueConstraint("watchlist_id", "ticker", name="uq_watchlist_ticker"),
    )

    id = db.Column(db.Integer, primary_key=True)
    watchlist_id = db.Column(db.Integer, db.ForeignKey("watchlists.id"), nullable=False, index=True)
    ticker = db.Column(db.String(32), nullable=False, index=True)
    company_name = db.Column(db.String(255), nullable=True)
    notes = db.Column(db.String(512), nullable=True)
    added_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "watchlist_id": self.watchlist_id,
            "ticker": self.ticker,
            "company_name": self.company_name,
            "notes": self.notes,
            "added_at": self.added_at.isoformat() if self.added_at else None,
        }


class IndiaDisclosure(db.Model):
    """India pledge / SAST disclosures (separate from open-market PIT trades)."""

    __tablename__ = "india_disclosures"
    __table_args__ = (
        db.UniqueConstraint("kind", "external_id", name="uq_india_disclosure"),
    )

    id = db.Column(db.Integer, primary_key=True)
    kind = db.Column(db.String(16), nullable=False, index=True)  # pledge | sast
    external_id = db.Column(db.String(128), nullable=False)
    ticker = db.Column(db.String(32), nullable=True, index=True)
    company_name = db.Column(db.String(255), nullable=True, index=True)
    party_name = db.Column(db.String(255), nullable=True)
    event_date = db.Column(db.Date, nullable=True, index=True)
    filing_date = db.Column(db.Date, nullable=True, index=True)
    side = db.Column(db.String(16), nullable=True)  # buy/sale/pledge/etc
    shares = db.Column(db.Float, nullable=True)
    percent = db.Column(db.Float, nullable=True)
    details = db.Column(db.Text, nullable=True)
    source_url = db.Column(db.String(512), nullable=True)
    raw_json = db.Column(db.Text, nullable=True)
    fetched_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "external_id": self.external_id,
            "ticker": self.ticker,
            "company_name": self.company_name,
            "party_name": self.party_name,
            "event_date": self.event_date.isoformat() if self.event_date else None,
            "filing_date": self.filing_date.isoformat() if self.filing_date else None,
            "side": self.side,
            "shares": self.shares,
            "percent": self.percent,
            "details": self.details,
            "source_url": self.source_url,
            "fetched_at": self.fetched_at.isoformat() if self.fetched_at else None,
        }



class UnusualOptionAlert(db.Model):
    """Cached unusual options activity rows from Yahoo chain scans."""

    __tablename__ = "unusual_option_alerts"
    __table_args__ = (
        db.UniqueConstraint(
            "scan_date",
            "contract_symbol",
            "underlying",
            name="uq_uoa_alert_day_contract",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    market = db.Column(db.String(8), nullable=False, default="US", index=True)
    underlying = db.Column(db.String(32), nullable=False, index=True)
    contract_symbol = db.Column(db.String(64), nullable=False, index=True)
    option_type = db.Column(db.String(8), nullable=False)  # call | put
    strike = db.Column(db.Float, nullable=True)
    expiration = db.Column(db.Date, nullable=True, index=True)
    dte = db.Column(db.Integer, nullable=True)

    last_price = db.Column(db.Float, nullable=True)
    bid = db.Column(db.Float, nullable=True)
    ask = db.Column(db.Float, nullable=True)
    volume = db.Column(db.Float, nullable=True)
    open_interest = db.Column(db.Float, nullable=True)
    implied_volatility = db.Column(db.Float, nullable=True)
    premium = db.Column(db.Float, nullable=True)
    vol_oi = db.Column(db.Float, nullable=True)
    score = db.Column(db.Float, nullable=True, index=True)

    sentiment = db.Column(db.String(16), nullable=True, index=True)  # bullish|bearish|mixed|unclear
    aggressiveness = db.Column(db.String(24), nullable=True)  # buy_ask|sell_bid|mid|unknown
    reason = db.Column(db.String(512), nullable=True)
    universe = db.Column(db.String(24), nullable=True)  # watchlist|liquid100
    scan_date = db.Column(db.Date, nullable=False, index=True)
    scanned_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "market": self.market,
            "underlying": self.underlying,
            "contract_symbol": self.contract_symbol,
            "option_type": self.option_type,
            "strike": self.strike,
            "expiration": self.expiration.isoformat() if self.expiration else None,
            "dte": self.dte,
            "last_price": self.last_price,
            "bid": self.bid,
            "ask": self.ask,
            "volume": self.volume,
            "open_interest": self.open_interest,
            "implied_volatility": self.implied_volatility,
            "premium": self.premium,
            "vol_oi": self.vol_oi,
            "score": self.score,
            "sentiment": self.sentiment,
            "aggressiveness": self.aggressiveness,
            "reason": self.reason,
            "universe": self.universe,
            "scan_date": self.scan_date.isoformat() if self.scan_date else None,
            "scanned_at": self.scanned_at.isoformat() if self.scanned_at else None,
        }


class AppNotification(db.Model):
    """In-app notifications (UOA and future alert types)."""

    __tablename__ = "app_notifications"

    id = db.Column(db.Integer, primary_key=True)
    kind = db.Column(db.String(32), nullable=False, index=True)  # uoa
    title = db.Column(db.String(255), nullable=False)
    body = db.Column(db.Text, nullable=True)
    severity = db.Column(db.String(16), nullable=False, default="info")
    ticker = db.Column(db.String(32), nullable=True, index=True)
    payload_json = db.Column(db.Text, nullable=True)
    is_read = db.Column(db.Boolean, nullable=False, default=False, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "title": self.title,
            "body": self.body,
            "severity": self.severity,
            "ticker": self.ticker,
            "payload_json": self.payload_json,
            "is_read": bool(self.is_read),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class DeepDiveCandidate(db.Model):
    """Officer buy signal staged for Equity Research Agent deep-dive push."""

    __tablename__ = "deep_dive_candidates"
    __table_args__ = (
        db.Index("ix_deep_dive_status_deadline", "status", "confirm_deadline_at"),
        db.Index("ix_deep_dive_ticker_status", "ticker", "status"),
    )

    id = db.Column(db.Integer, primary_key=True)
    market = db.Column(db.String(8), nullable=False, default="US", index=True)
    ticker = db.Column(db.String(32), nullable=False, index=True)
    company_name = db.Column(db.String(255), nullable=True)
    insider_name = db.Column(db.String(255), nullable=True)
    officer_title = db.Column(db.String(255), nullable=True)
    total_value = db.Column(db.Float, nullable=True)
    transaction_ids_json = db.Column(db.Text, nullable=True)
    accession_number = db.Column(db.String(64), nullable=True)
    source_url = db.Column(db.String(512), nullable=True)

    # pending_confirm | backlog | pushed | failed | skipped | followup | cancelled_final
    status = db.Column(db.String(32), nullable=False, default="pending_confirm", index=True)
    confirm_deadline_at = db.Column(db.DateTime, nullable=True, index=True)
    retry_after = db.Column(db.DateTime, nullable=True, index=True)
    research_job_id = db.Column(db.String(64), nullable=True)
    notification_id = db.Column(db.Integer, nullable=True)
    error_message = db.Column(db.Text, nullable=True)
    cancel_count = db.Column(db.Integer, nullable=False, default=0)

    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)
    pushed_at = db.Column(db.DateTime, nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "market": self.market,
            "ticker": self.ticker,
            "company_name": self.company_name,
            "insider_name": self.insider_name,
            "officer_title": self.officer_title,
            "total_value": self.total_value,
            "transaction_ids_json": self.transaction_ids_json,
            "accession_number": self.accession_number,
            "source_url": self.source_url,
            "status": self.status,
            "confirm_deadline_at": self.confirm_deadline_at.isoformat()
            if self.confirm_deadline_at
            else None,
            "retry_after": self.retry_after.isoformat() if self.retry_after else None,
            "research_job_id": self.research_job_id,
            "notification_id": self.notification_id,
            "error_message": self.error_message,
            "cancel_count": self.cancel_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "pushed_at": self.pushed_at.isoformat() if self.pushed_at else None,
        }


class OptionsScanRun(db.Model):
    """Tracks unusual options scan attempts."""

    __tablename__ = "options_scan_runs"

    id = db.Column(db.Integer, primary_key=True)
    market = db.Column(db.String(8), nullable=False, default="US")
    universe = db.Column(db.String(24), nullable=False, default="watchlist")
    trigger = db.Column(db.String(32), nullable=False, default="manual")
    started_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    finished_at = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(32), nullable=False, default="running")
    tickers_scanned = db.Column(db.Integer, default=0)
    alerts_upserted = db.Column(db.Integer, default=0)
    notifications_created = db.Column(db.Integer, default=0)
    error_message = db.Column(db.Text, nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "market": self.market,
            "universe": self.universe,
            "trigger": self.trigger,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "status": self.status,
            "tickers_scanned": self.tickers_scanned,
            "alerts_upserted": self.alerts_upserted,
            "notifications_created": self.notifications_created,
            "error_message": self.error_message,
        }

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
        }

"""SEC XBRL companyfacts → annual financial statements."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from flask import current_app

from app.extensions import db
from app.models import AnnualFinancial, Company
from app.services.sec_form4 import SecEdgarClient, _load_ticker_map
from app.utils.helpers import parse_date
from app.utils.sectors import sic_to_sector

logger = logging.getLogger(__name__)

# Preferred US-GAAP tags per statement line (first match wins).
INCOME_TAGS: list[tuple[str, list[str]]] = [
    (
        "Revenue",
        [
            "RevenueFromContractWithCustomerExcludingAssessedTax",
            "SalesRevenueNet",
            "Revenues",
            "RevenueFromContractWithCustomerIncludingAssessedTax",
            "SalesRevenueGoodsNet",
            "SalesRevenueServicesNet",
            "RevenueFromContractWithCustomerIncludingAssessedTax",
            "TotalRevenuesAndOtherIncome",
            "InterestAndDividendIncomeOperating",
            "InterestIncomeExpenseNet",
            "PremiumsEarnedNet",
        ],
    ),
    (
        "CostOfRevenue",
        [
            "CostOfRevenue",
            "CostOfGoodsAndServicesSold",
            "CostOfGoodsSold",
            "CostOfServices",
            "PolicyholderBenefitsAndClaimsIncurredNet",
        ],
    ),
    ("GrossProfit", ["GrossProfit"]),
    (
        "ResearchAndDevelopment",
        ["ResearchAndDevelopmentExpense", "ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost"],
    ),
    (
        "SellingGeneralAndAdministrative",
        [
            "SellingGeneralAndAdministrativeExpense",
            "SellingAndMarketingExpense",
            "GeneralAndAdministrativeExpense",
        ],
    ),
    (
        "OperatingIncome",
        [
            "OperatingIncomeLoss",
            "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
            "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
        ],
    ),
    (
        "InterestExpense",
        ["InterestExpense", "InterestExpenseDebt", "InterestIncomeExpenseNonoperatingNet"],
    ),
    (
        "IncomeBeforeTax",
        [
            "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
            "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
        ],
    ),
    ("IncomeTaxExpense", ["IncomeTaxExpenseBenefit"]),
    ("NetIncome", ["NetIncomeLoss", "ProfitLoss", "NetIncomeLossAvailableToCommonStockholdersBasic"]),
    ("EPSBasic", ["EarningsPerShareBasic"]),
    ("EPSDiluted", ["EarningsPerShareDiluted"]),
    ("SharesOutstandingBasic", ["WeightedAverageNumberOfSharesOutstandingBasic"]),
    ("SharesOutstandingDiluted", ["WeightedAverageNumberOfDilutedSharesOutstanding"]),
]

BALANCE_TAGS: list[tuple[str, list[str]]] = [
    ("Assets", ["Assets"]),
    ("CurrentAssets", ["AssetsCurrent"]),
    (
        "Cash",
        [
            "CashAndCashEquivalentsAtCarryingAmount",
            "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
            "CashCashEquivalentsAndShortTermInvestments",
            "CashAndCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
            "Cash",
        ],
    ),
    (
        "ShortTermInvestments",
        [
            "ShortTermInvestments",
            "MarketableSecuritiesCurrent",
            "AvailableForSaleSecuritiesDebtSecuritiesCurrent",
        ],
    ),
    (
        "AccountsReceivable",
        ["AccountsReceivableNetCurrent", "ReceivablesNetCurrent", "AccountsReceivableNet"],
    ),
    ("Inventory", ["InventoryNet", "InventoryFinishedGoodsNetOfReserves"]),
    ("Liabilities", ["Liabilities"]),
    ("CurrentLiabilities", ["LiabilitiesCurrent"]),
    (
        "AccountsPayable",
        ["AccountsPayableCurrent", "AccountsPayableAndAccruedLiabilitiesCurrent"],
    ),
    (
        "LongTermDebt",
        [
            "LongTermDebt",
            "LongTermDebtNoncurrent",
            "LongTermDebtAndCapitalLeaseObligations",
            "LongTermDebtNoncurrent",
            "DebtInstrumentCarryingAmount",
        ],
    ),
    (
        "StockholdersEquity",
        [
            "StockholdersEquity",
            "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
            "PartnersCapital",
        ],
    ),
    (
        "RetainedEarnings",
        ["RetainedEarningsAccumulatedDeficit", "RetainedEarnings"],
    ),
]

CASHFLOW_TAGS: list[tuple[str, list[str]]] = [
    (
        "OperatingCashFlow",
        [
            "NetCashProvidedByUsedInOperatingActivities",
            "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
        ],
    ),
    (
        "InvestingCashFlow",
        [
            "NetCashProvidedByUsedInInvestingActivities",
            "NetCashProvidedByUsedInInvestingActivitiesContinuingOperations",
        ],
    ),
    (
        "FinancingCashFlow",
        [
            "NetCashProvidedByUsedInFinancingActivities",
            "NetCashProvidedByUsedInFinancingActivitiesContinuingOperations",
        ],
    ),
    (
        "Capex",
        [
            "PaymentsToAcquirePropertyPlantAndEquipment",
            "PurchaseOfPropertyPlantAndEquipment",
            "PaymentsToAcquireProductiveAssets",
        ],
    ),
    (
        "DividendsPaid",
        ["PaymentsOfDividends", "PaymentsOfDividendsCommonStock", "Dividends"],
    ),
    (
        "ShareRepurchases",
        ["PaymentsForRepurchaseOfCommonStock", "PaymentsForRepurchaseOfEquity"],
    ),
    (
        "FreeCashFlowProxy",
        [],  # computed later if both OCF and Capex present
    ),
]


def _pick_annual_facts(tag_node: dict[str, Any], years: int) -> list[dict[str, Any]]:
    """Return up to `years` annual USD (or shares) facts, newest first, one per FY."""
    units = tag_node.get("units") or {}
    series: list[dict[str, Any]] = []
    for unit_key in ("USD", "USD/shares", "pure", "shares"):
        if unit_key in units:
            series = units[unit_key]
            break
    if not series and units:
        series = next(iter(units.values()))

    by_year: dict[int, dict[str, Any]] = {}
    for point in series:
        form = (point.get("form") or "").upper()
        # Prefer annual 10-K / 20-F style filings.
        if form and form not in {"10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A"}:
            # Some filers put annual numbers on 10-Q; keep only if fy end looks annual via fp.
            if point.get("fp") not in {"FY", None, ""} and form.startswith("10-Q"):
                continue
        fy = point.get("fy")
        if not fy:
            # Fall back to end date year for frames without fy.
            end = parse_date(point.get("end"))
            if not end:
                continue
            fy = end.year
        try:
            fy_i = int(fy)
        except (TypeError, ValueError):
            continue
        # Keep the newest filed annual point per FY.
        filed = parse_date(point.get("filed"))
        existing = by_year.get(fy_i)
        if existing is None:
            by_year[fy_i] = point
            continue
        existing_filed = parse_date(existing.get("filed"))
        if filed and (existing_filed is None or filed >= existing_filed):
            by_year[fy_i] = point

    ordered_years = sorted(by_year.keys(), reverse=True)[:years]
    rows = []
    for year in ordered_years:
        point = by_year[year]
        rows.append(
            {
                "year": year,
                "value": point.get("val"),
                "filed_date": parse_date(point.get("filed")),
                "unit": "USD",
                "form": point.get("form"),
            }
        )
    return rows


def parse_financial_statements(facts_json: dict[str, Any], *, years: int = 10) -> dict[str, list[dict[str, Any]]]:
    gaap = (facts_json.get("facts") or {}).get("us-gaap") or {}
    ifrs = (facts_json.get("facts") or {}).get("ifrs-full") or {}
    taxonomy = gaap or ifrs

    def extract(tag_groups: list[tuple[str, list[str]]]) -> list[dict[str, Any]]:
        # year -> metric dict
        by_year: dict[int, dict[str, Any]] = {}
        for metric_name, candidates in tag_groups:
            if not candidates:
                continue
            node = None
            for tag in candidates:
                if tag in taxonomy:
                    node = taxonomy[tag]
                    break
            if not node:
                continue
            for point in _pick_annual_facts(node, years=years):
                year = point["year"]
                by_year.setdefault(year, {"year": year})
                by_year[year][metric_name] = point["value"]
                if point.get("filed_date") and "filed_date" not in by_year[year]:
                    by_year[year]["filed_date"] = point["filed_date"].isoformat()
        return [by_year[y] for y in sorted(by_year.keys(), reverse=True)]

    income = extract(INCOME_TAGS)
    balance = extract(BALANCE_TAGS)
    cash = extract(CASHFLOW_TAGS)
    for row in cash:
        ocf = row.get("OperatingCashFlow")
        capex = row.get("Capex")
        if ocf is not None and capex is not None:
            # Capex is usually reported as a cash outflow (often negative already).
            row["FreeCashFlowProxy"] = float(ocf) - abs(float(capex))

    return {
        "income_statement": income,
        "balance_sheet": balance,
        "cash_flow": cash,
    }


def _upsert_company_from_submissions(client: SecEdgarClient, *, ticker: str, cik: str, name: str) -> Company:
    sector = None
    industry = None
    sic = None
    sic_description = None
    try:
        subs = client.get(f"{client.DATA}/submissions/CIK{cik}.json").json()
        name = subs.get("name") or name
        sic = str(subs.get("sic") or "") or None
        sic_description = subs.get("sicDescription")
        industry = sic_description
        sector = sic_to_sector(sic)
        exchanges = subs.get("exchanges") or []
        exchange = ",".join(exchanges) if exchanges else None
    except Exception as exc:  # noqa: BLE001
        logger.warning("Submissions lookup failed for %s: %s", ticker, exc)
        exchange = None

    company = Company.query.filter_by(market="US", ticker=ticker).first()
    if company is None:
        company = Company(market="US", ticker=ticker)
        db.session.add(company)
    company.name = name
    company.cik = cik
    company.exchange = exchange
    company.sic = sic
    company.sic_description = sic_description
    company.industry = industry
    company.sector = sector
    company.updated_at = datetime.now(timezone.utc)
    db.session.commit()
    return company


def _cache_statements(
    *,
    ticker: str,
    company_name: str,
    cik: str,
    statements: dict[str, list[dict[str, Any]]],
) -> None:
    AnnualFinancial.query.filter_by(market="US", ticker=ticker).delete()
    mapping = {
        "income_statement": "income",
        "balance_sheet": "balance",
        "cash_flow": "cash_flow",
    }
    for statement_key, rows in statements.items():
        statement = mapping[statement_key]
        for row in rows:
            year = row.get("year")
            filed = parse_date(row.get("filed_date")) if isinstance(row.get("filed_date"), str) else row.get("filed_date")
            for metric_name, metric_value in row.items():
                if metric_name in {"year", "filed_date"}:
                    continue
                if metric_value is None:
                    continue
                try:
                    value = float(metric_value)
                except (TypeError, ValueError):
                    continue
                db.session.add(
                    AnnualFinancial(
                        market="US",
                        ticker=ticker,
                        company_name=company_name,
                        cik=cik,
                        year=int(year),
                        statement=statement,
                        metric_name=metric_name,
                        metric_value=value,
                        unit="USD",
                        filed_date=filed,
                    )
                )
    db.session.commit()


def get_us_financials(ticker: str, *, years: int = 10, refresh: bool = False) -> dict[str, Any]:
    ticker = ticker.upper().strip()
    years = max(1, min(int(years), 20))

    if not refresh:
        cached = AnnualFinancial.query.filter_by(market="US", ticker=ticker).all()
        if cached:
            return _shape_from_cache(cached)

    client = SecEdgarClient(
        user_agent=current_app.config["SEC_USER_AGENT"],
        delay_seconds=current_app.config["SEC_REQUEST_DELAY_SECONDS"],
    )
    ticker_map = _load_ticker_map(client)
    info = ticker_map.get(ticker)
    if not info:
        raise ValueError(f"Unknown US ticker: {ticker}")

    cik = info["cik"]
    company_name = info.get("name") or ticker
    facts = client.get(f"{client.DATA}/api/xbrl/companyfacts/CIK{cik}.json").json()
    company_name = facts.get("entityName") or company_name
    statements = parse_financial_statements(facts, years=years)
    _upsert_company_from_submissions(client, ticker=ticker, cik=cik, name=company_name)
    _cache_statements(ticker=ticker, company_name=company_name, cik=cik, statements=statements)

    return {
        "market": "US",
        "ticker": ticker,
        "cik": cik,
        "company_name": company_name,
        "retrieved_utc": datetime.now(timezone.utc).isoformat(),
        "cached": False,
        "statements": statements,
    }


def _shape_from_cache(rows: list[AnnualFinancial]) -> dict[str, Any]:
    ticker = rows[0].ticker
    company_name = rows[0].company_name
    cik = rows[0].cik
    buckets: dict[str, dict[int, dict[str, Any]]] = {
        "income_statement": {},
        "balance_sheet": {},
        "cash_flow": {},
    }
    reverse = {"income": "income_statement", "balance": "balance_sheet", "cash_flow": "cash_flow"}
    for row in rows:
        key = reverse.get(row.statement)
        if not key:
            continue
        bucket = buckets[key].setdefault(row.year, {"year": row.year})
        bucket[row.metric_name] = row.metric_value
        if row.filed_date:
            bucket["filed_date"] = row.filed_date.isoformat()

    return {
        "market": "US",
        "ticker": ticker,
        "cik": cik,
        "company_name": company_name,
        "retrieved_utc": datetime.now(timezone.utc).isoformat(),
        "cached": True,
        "statements": {
            name: [by_year[y] for y in sorted(by_year.keys(), reverse=True)]
            for name, by_year in buckets.items()
        },
    }

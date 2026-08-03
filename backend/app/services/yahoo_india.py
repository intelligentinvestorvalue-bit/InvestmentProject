"""Free Yahoo Finance helpers for India fundamentals / sector metadata."""

from __future__ import annotations

import logging
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)


class YahooClient:
    BASE = "https://query2.finance.yahoo.com"

    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36"
                ),
                "Accept": "application/json",
            }
        )
        self._crumb: Optional[str] = None

    def _ensure_crumb(self) -> str:
        if self._crumb:
            return self._crumb
        # Seed consent/session cookie then fetch crumb.
        self.session.get("https://fc.yahoo.com", timeout=20, allow_redirects=True)
        crumb_resp = self.session.get(
            "https://query1.finance.yahoo.com/v1/test/getcrumb",
            headers={"Accept": "text/plain,*/*"},
            timeout=20,
        )
        crumb_resp.raise_for_status()
        self._crumb = crumb_resp.text.strip()
        if not self._crumb or "<" in self._crumb:
            raise RuntimeError(f"Yahoo crumb invalid: {self._crumb[:80]!r}")
        return self._crumb

    def quote_summary(self, symbol: str, modules: list[str]) -> dict[str, Any]:
        crumb = self._ensure_crumb()
        url = f"{self.BASE}/v10/finance/quoteSummary/{symbol}"
        headers = {"Accept": "application/json"}
        response = self.session.get(
            url,
            params={"modules": ",".join(modules), "crumb": crumb},
            headers=headers,
            timeout=30,
        )
        if response.status_code in {401, 403}:
            self._crumb = None
            crumb = self._ensure_crumb()
            response = self.session.get(
                url,
                params={"modules": ",".join(modules), "crumb": crumb},
                headers=headers,
                timeout=30,
            )
        response.raise_for_status()
        payload = response.json()
        results = (((payload or {}).get("quoteSummary") or {}).get("result") or [])
        if not results:
            error = (((payload or {}).get("quoteSummary") or {}).get("error"))
            raise ValueError(f"No Yahoo data for {symbol}: {error}")
        return results[0]


def india_yahoo_symbol(ticker: str, exchange: Optional[str] = None) -> list[str]:
    """Candidate Yahoo symbols for an India ticker."""
    base = ticker.upper().strip()
    ex = (exchange or "").upper()
    ordered: list[str] = []
    if "BSE" in ex and "NSE" not in ex:
        ordered.extend([f"{base}.BO", f"{base}.NS"])
    else:
        ordered.extend([f"{base}.NS", f"{base}.BO"])
    seen = set()
    out = []
    for item in ordered:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _raw_number(node: Any) -> Optional[float]:
    if node is None:
        return None
    if isinstance(node, (int, float)):
        return float(node)
    if isinstance(node, dict):
        raw = node.get("raw")
        if raw is None:
            return None
        try:
            return float(raw)
        except (TypeError, ValueError):
            return None
    return None


def fetch_india_profile(ticker: str, exchange: Optional[str] = None) -> dict[str, Any]:
    client = YahooClient()
    last_error: Exception | None = None
    for symbol in india_yahoo_symbol(ticker, exchange):
        try:
            data = client.quote_summary(symbol, ["assetProfile", "price"])
            profile = data.get("assetProfile") or {}
            price = data.get("price") or {}
            return {
                "yahoo_symbol": symbol,
                "name": price.get("longName") or price.get("shortName"),
                "sector": profile.get("sector"),
                "industry": profile.get("industry"),
                "exchange": "BSE" if symbol.endswith(".BO") else "NSE",
            }
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            continue
    raise ValueError(f"Unable to resolve Yahoo profile for {ticker}: {last_error}")


def fetch_india_statements(ticker: str, exchange: Optional[str] = None, *, years: int = 5) -> dict[str, Any]:
    client = YahooClient()
    modules = [
        "assetProfile",
        "price",
        "incomeStatementHistory",
        "balanceSheetHistory",
        "cashflowStatementHistory",
    ]
    last_error: Exception | None = None
    data = None
    yahoo_symbol = None
    for symbol in india_yahoo_symbol(ticker, exchange):
        try:
            data = client.quote_summary(symbol, modules)
            yahoo_symbol = symbol
            break
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            continue
    if data is None:
        raise ValueError(f"Unable to fetch Yahoo financials for {ticker}: {last_error}")

    profile = data.get("assetProfile") or {}
    price = data.get("price") or {}

    income_hist = ((data.get("incomeStatementHistory") or {}).get("incomeStatementHistory")) or []
    balance_hist = ((data.get("balanceSheetHistory") or {}).get("balanceSheetStatements")) or []
    cash_hist = ((data.get("cashflowStatementHistory") or {}).get("cashflowStatements")) or []

    def year_from(row: dict[str, Any]) -> Optional[int]:
        end = row.get("endDate") or {}
        if isinstance(end, dict) and end.get("fmt"):
            try:
                return int(str(end["fmt"])[:4])
            except ValueError:
                return None
        return None

    def map_income(row: dict[str, Any]) -> dict[str, Any]:
        # Insertion order = display order (top-down P&L).
        return {
            "year": year_from(row),
            "Revenue": _raw_number(row.get("totalRevenue")),
            "CostOfRevenue": _raw_number(row.get("costOfRevenue")),
            "GrossProfit": _raw_number(row.get("grossProfit")),
            "OperatingIncome": _raw_number(row.get("operatingIncome")),
            "EBITDA": _raw_number(row.get("ebitda")),
            "NetIncome": _raw_number(row.get("netIncome")),
        }

    def map_balance(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "year": year_from(row),
            "Assets": _raw_number(row.get("totalAssets")),
            "CurrentAssets": _raw_number(row.get("totalCurrentAssets")),
            "Cash": _raw_number(row.get("cash")),
            "Liabilities": _raw_number(row.get("totalLiab")),
            "CurrentLiabilities": _raw_number(row.get("totalCurrentLiabilities")),
            "LongTermDebt": _raw_number(row.get("longTermDebt")),
            "StockholdersEquity": _raw_number(row.get("totalStockholderEquity")),
        }

    def map_cash(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "year": year_from(row),
            "OperatingCashFlow": _raw_number(row.get("totalCashFromOperatingActivities")),
            "InvestingCashFlow": _raw_number(row.get("totalCashflowsFromInvestingActivities")),
            "FinancingCashFlow": _raw_number(row.get("totalCashFromFinancingActivities")),
            "Capex": _raw_number(row.get("capitalExpenditures")),
        }

    income = [r for r in (map_income(x) for x in income_hist[:years]) if r.get("year")]
    balance = [r for r in (map_balance(x) for x in balance_hist[:years]) if r.get("year")]
    cash = [r for r in (map_cash(x) for x in cash_hist[:years]) if r.get("year")]

    return {
        "yahoo_symbol": yahoo_symbol,
        "company_name": price.get("longName") or price.get("shortName") or ticker,
        "sector": profile.get("sector"),
        "industry": profile.get("industry"),
        "exchange": "BSE" if (yahoo_symbol or "").endswith(".BO") else "NSE",
        "statements": {
            "income_statement": income,
            "balance_sheet": balance,
            "cash_flow": cash,
            "summary": [],
        },
    }

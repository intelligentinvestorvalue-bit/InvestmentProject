"""Unit tests for financial statement parsing (no network)."""

from app.services.sec_financials import parse_financial_statements


def test_parse_financial_statements_prefers_annual_tags():
    facts = {
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {
                        "USD": [
                            {"fy": 2024, "fp": "FY", "form": "10-K", "val": 100, "filed": "2025-01-01", "end": "2024-12-31"},
                            {"fy": 2023, "fp": "FY", "form": "10-K", "val": 90, "filed": "2024-01-01", "end": "2023-12-31"},
                        ]
                    }
                },
                "NetIncomeLoss": {
                    "units": {
                        "USD": [
                            {"fy": 2024, "fp": "FY", "form": "10-K", "val": 20, "filed": "2025-01-01", "end": "2024-12-31"},
                        ]
                    }
                },
                "Assets": {
                    "units": {
                        "USD": [
                            {"fy": 2024, "fp": "FY", "form": "10-K", "val": 500, "filed": "2025-01-01", "end": "2024-12-31"},
                        ]
                    }
                },
                "NetCashProvidedByUsedInOperatingActivities": {
                    "units": {
                        "USD": [
                            {"fy": 2024, "fp": "FY", "form": "10-K", "val": 30, "filed": "2025-01-01", "end": "2024-12-31"},
                        ]
                    }
                },
                "PaymentsToAcquirePropertyPlantAndEquipment": {
                    "units": {
                        "USD": [
                            {"fy": 2024, "fp": "FY", "form": "10-K", "val": -8, "filed": "2025-01-01", "end": "2024-12-31"},
                        ]
                    }
                },
            }
        }
    }
    statements = parse_financial_statements(facts, years=5)
    assert statements["income_statement"][0]["year"] == 2024
    assert statements["income_statement"][0]["Revenue"] == 100
    assert statements["income_statement"][0]["NetIncome"] == 20
    assert statements["balance_sheet"][0]["Assets"] == 500
    assert statements["cash_flow"][0]["OperatingCashFlow"] == 30
    assert statements["cash_flow"][0]["FreeCashFlowProxy"] == 22.0

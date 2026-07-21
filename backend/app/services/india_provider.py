"""India market provider stub (Phase 2)."""

from __future__ import annotations

from typing import Any


def get_india_status() -> dict[str, Any]:
    return {
        "market": "IN",
        "status": "planned",
        "phase": 2,
        "message": (
            "India insider feed is planned next. Sources will be NSE + BSE public "
            "disclosures and SEBI/SAST filings (free), prioritizing insider activity "
            "before financials and sector browse."
        ),
        "planned_sources": [
            "NSE India public APIs (insider / SAST)",
            "BSE India public disclosures",
            "SEBI filings where applicable",
        ],
        "priority": ["insider", "financials", "sector_browse"],
    }


def list_india_insider_transactions(**_: Any) -> dict[str, Any]:
    status = get_india_status()
    return {
        **status,
        "total": 0,
        "items": [],
        "filters_applied": {},
    }

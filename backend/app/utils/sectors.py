"""SIC / industry helpers for sector explore."""

from __future__ import annotations

from typing import Optional

# Major SIC division buckets (coarse but useful for browse).
_SIC_DIVISIONS: list[tuple[int, int, str]] = [
    (100, 999, "Agriculture"),
    (1000, 1499, "Mining"),
    (1500, 1799, "Construction"),
    (2000, 3999, "Manufacturing"),
    (4000, 4999, "Transportation & Utilities"),
    (5000, 5199, "Wholesale Trade"),
    (5200, 5999, "Retail Trade"),
    (6000, 6799, "Finance & Insurance"),
    (7000, 8999, "Services"),
    (9100, 9729, "Public Administration"),
]


def sic_to_sector(sic: Optional[str]) -> Optional[str]:
    if not sic:
        return None
    digits = "".join(ch for ch in str(sic) if ch.isdigit())
    if not digits:
        return None
    try:
        value = int(digits)
    except ValueError:
        return None
    # SEC SIC codes are typically 4-digit; normalize shorter codes.
    if value < 100:
        value *= 100
    elif value < 1000:
        value *= 10
    for start, end, label in _SIC_DIVISIONS:
        if start <= value <= end:
            return label
    return "Other"

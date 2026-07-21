"""Shared helpers."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Optional


def parse_date(value: Optional[str]) -> Optional[date]:
    """Parse common SEC / ISO date strings into a date."""
    if not value:
        return None
    text = value.strip()
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(text[:10] if fmt == "%Y-%m-%d" else text, fmt).date()
        except ValueError:
            continue
    return None


def to_float(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def normalize_accession(accession: str) -> str:
    return accession.replace("-", "").strip()


def accession_to_path(accession: str) -> str:
    """Convert accession number to EDGAR archive path segment."""
    clean = normalize_accession(accession)
    return clean


def clean_whitespace(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    cleaned = re.sub(r"\s+", " ", value).strip()
    return cleaned or None


def build_relationship(
    *,
    is_director: bool,
    is_officer: bool,
    is_ten_percent_owner: bool,
    officer_title: Optional[str],
) -> str:
    parts: list[str] = []
    if officer_title:
        parts.append(officer_title)
    elif is_officer:
        parts.append("Officer")
    if is_director:
        parts.append("Director")
    if is_ten_percent_owner:
        parts.append("10% Owner")
    return ", ".join(parts) if parts else "Other"

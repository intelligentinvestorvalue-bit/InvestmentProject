"""Shared helpers."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Optional


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


def to_float(value) -> Optional[float]:
    if value is None:
        return None
    text = str(value).strip().replace(",", "").replace("Nil", "").replace("nil", "")
    if not text or text == "-":
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


# Titles InsideArbitrage-style "officers / management" include, even when Form 4
# isOfficer is unchecked (common for Chairman / President / EVP).
MANAGEMENT_TITLE_KEYWORDS: tuple[str, ...] = (
    "chief",
    "ceo",
    "cfo",
    "coo",
    "cto",
    "cmo",
    "cio",
    "ciso",
    "president",
    "chairman",
    "chairwoman",
    "chairperson",
    "chair of",
    "vice chair",
    "vice-chair",
    "executive chair",
    "evp",
    "svp",
    "fvp",
    "avp",
    "vp",
    "vice president",
    "vice-president",
    "general counsel",
    "controller",
    "treasurer",
    "managing director",
    "executive director",
    "executive officer",
    "founder",
    "co-founder",
    "officer",
    "kmp",
    "key managerial",
    "secretary",
    "principal",
)

# Short tokens must not use naive LIKE ("%cto%" matches "director").
_SHORT_TITLE_TOKENS = frozenset(
    {
        "ceo",
        "cfo",
        "coo",
        "cto",
        "cmo",
        "cio",
        "ciso",
        "evp",
        "svp",
        "fvp",
        "avp",
        "vp",
        "kmp",
    }
)


def is_management_title(title: Optional[str]) -> bool:
    """True for C-suite / operating management titles, not a plain director."""
    text = (title or "").strip().lower()
    if not text:
        return False
    collapsed = re.sub(r"[-_/]+", " ", text)
    collapsed = re.sub(r"\s+", " ", collapsed).strip()
    for keyword in MANAGEMENT_TITLE_KEYWORDS:
        needle = keyword.replace("-", " ")
        if " " in needle:
            if needle == "executive director":
                # "non-executive director" contains this phrase; do not treat it as management.
                if re.search(r"(?<!non )executive director", collapsed):
                    return True
                continue
            if needle in collapsed:
                return True
            continue
        if re.search(rf"(?<![a-z]){re.escape(keyword)}(?![a-z])", text):
            return True
    if re.search(r"(?<![a-z])v\.?p\.?(?![a-z])", text):
        return True
    return False


def is_management_insider(
    *,
    is_officer: bool = False,
    officer_title: Optional[str] = None,
    relationship: Optional[str] = None,
) -> bool:
    """Match SEC officers plus management titles (chairman, president, EVP, …)."""
    if is_officer:
        return True
    return is_management_title(officer_title) or is_management_title(relationship)


def _short_token_clause(column, token: str):
    """Whole-token LIKE patterns so 'cto' does not match 'Director'."""
    from sqlalchemy import or_

    t = token.lower()
    return or_(
        column.ilike(t),
        column.ilike(f"{t} %"),
        column.ilike(f"{t},%"),
        column.ilike(f"{t};%"),
        column.ilike(f"{t}/%"),
        column.ilike(f"{t}-%"),
        column.ilike(f"% {t}"),
        column.ilike(f"% {t} %"),
        column.ilike(f"% {t},%"),
        column.ilike(f"% {t};%"),
        column.ilike(f"% {t}/%"),
        column.ilike(f"%,{t}%"),
        column.ilike(f"%, {t}%"),
        column.ilike(f"%-{t}%"),
        column.ilike(f"%/{t}%"),
        column.ilike(f"%({t}%"),
    )


def _keyword_column_clause(column, keyword: str):
    from sqlalchemy import and_

    token = keyword.lower()
    short = token in _SHORT_TITLE_TOKENS or (
        len(token) <= 4 and " " not in token and "-" not in token
    )
    if short:
        return _short_token_clause(column, token)
    if token == "executive director":
        return and_(
            column.ilike("%executive director%"),
            ~column.ilike("%non-executive director%"),
            ~column.ilike("%non executive director%"),
        )
    return column.ilike(f"%{token}%")


def management_role_filter(model) -> Any:
    """SQLAlchemy clause for the Officer / management dashboard filter."""
    from sqlalchemy import or_

    clauses = [model.is_officer.is_(True)]
    for keyword in MANAGEMENT_TITLE_KEYWORDS:
        clauses.append(_keyword_column_clause(model.officer_title, keyword))
        clauses.append(_keyword_column_clause(model.relationship, keyword))
    return or_(*clauses)


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

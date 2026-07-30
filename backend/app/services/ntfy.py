"""Optional phone / desktop push via ntfy.sh (same topic as tunnel keep-alive)."""

from __future__ import annotations

import logging
import os
from typing import Optional

import requests

logger = logging.getLogger(__name__)


def send_ntfy(
    *,
    title: str,
    message: str,
    priority: int = 4,
    tags: Optional[str] = None,
    click: Optional[str] = None,
) -> bool:
    """Publish to NTFY_TOPIC when configured. Returns True on success."""
    topic = (os.getenv("NTFY_TOPIC") or "").strip()
    if not topic:
        logger.debug("ntfy skipped: NTFY_TOPIC not set")
        return False

    server = (os.getenv("NTFY_SERVER") or "https://ntfy.sh").rstrip("/")
    url = f"{server}/{topic}"
    headers = {
        "Title": title[:200],
        "Priority": str(max(1, min(int(priority), 5))),
    }
    if tags:
        headers["Tags"] = tags
    if click:
        headers["Click"] = click
    token = (os.getenv("NTFY_TOKEN") or "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        resp = requests.post(url, data=message.encode("utf-8"), headers=headers, timeout=8)
        resp.raise_for_status()
        return True
    except Exception:  # noqa: BLE001
        logger.exception("ntfy publish failed")
        return False

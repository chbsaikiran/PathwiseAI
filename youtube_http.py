"""Shared YouTube Data API GET with backoff for 429/503 and quota errors."""

from __future__ import annotations

import random
import time

import requests


def _youtube_error_retryable(payload: dict) -> bool:
    err = payload.get("error") or {}
    code = int(err.get("code") or 0)
    if code in (429, 500, 503):
        return True
    status = (err.get("status") or "").upper()
    if status in ("RESOURCE_EXHAUSTED", "UNAVAILABLE", "INTERNAL"):
        return True
    for e in err.get("errors") or []:
        reason = (e.get("reason") or "").lower()
        if reason in ("quotaexceeded", "ratelimitexceeded", "backenderror"):
            return True
    return False


def youtube_api_get(url: str, params: dict, *, timeout: int = 30, max_retries: int = 6) -> dict:
    """
    GET JSON from YouTube v3. Retries on HTTP 429/503/500 and retryable API error bodies.
    """
    last: dict | None = None
    last_http: int | None = None
    for attempt in range(max_retries):
        r = requests.get(url, params=params, timeout=timeout)
        last_http = r.status_code
        if r.status_code in (429, 500, 503):
            wait = min(2**attempt + random.uniform(0, 0.5), 60)
            time.sleep(wait)
            continue
        try:
            data = r.json()
        except Exception:
            r.raise_for_status()
            raise
        if data.get("error") and _youtube_error_retryable(data):
            wait = min(2**attempt + random.uniform(0, 0.5), 60)
            time.sleep(wait)
            last = data
            continue
        return data
    msg = "YouTube API: max retries exceeded."
    if last is not None:
        msg += " Last error: " + str(last.get("error", last))
    elif last_http is not None:
        msg += f" Last HTTP status: {last_http}"
    raise RuntimeError(msg)

"""Resolve and validate YouTube search locale parameters (language + region)."""

from __future__ import annotations

import os
import re


def _coalesce_str(explicit: str | None, env_key: str) -> str:
    if explicit is not None and str(explicit).strip() != "":
        return str(explicit).strip()
    return (os.getenv(env_key) or "").strip()


def effective_search_locale(
    relevance_language: str | None,
    region_code: str | None,
) -> tuple[str | None, str | None]:
    """
    Merge explicit args with env defaults:
      YOUTUBE_RELEVANCE_LANGUAGE — ISO 639-1 two letters (e.g. en, hi, te)
      YOUTUBE_REGION_CODE — ISO 3166-1 alpha-2 (e.g. IN, US)

    Returns (relevanceLanguage or None, regionCode or None) for search.list only.
    Raises ValueError if a non-empty value is malformed.
    """
    lang = _coalesce_str(relevance_language, "YOUTUBE_RELEVANCE_LANGUAGE").lower()
    reg = _coalesce_str(region_code, "YOUTUBE_REGION_CODE").upper()

    if lang and not re.fullmatch(r"[a-z]{2}", lang):
        raise ValueError(
            f"Invalid relevance_language '{relevance_language or lang}'. "
            "Use ISO 639-1 two-letter code (e.g. en, hi, te)."
        )
    if reg and not re.fullmatch(r"[A-Z]{2}", reg):
        raise ValueError(
            f"Invalid region_code '{region_code or reg}'. "
            "Use ISO 3166-1 alpha-2 (e.g. IN, US)."
        )

    return (lang or None, reg or None)


def apply_search_locale(params: dict, relevance_language: str | None, region_code: str | None) -> None:
    """Mutates params dict for YouTube search.list: adds relevanceLanguage and regionCode if set."""
    lang, reg = effective_search_locale(relevance_language, region_code)
    if lang:
        params["relevanceLanguage"] = lang
    if reg:
        params["regionCode"] = reg

"""isbn.work provider — Chinese ISBN database.

Public endpoint (free, requires an appKey):
    https://data.isbn.work/openApi/getInfoByIsbn?isbn={isbn}&appKey={key}

Set ISBN_WORK_API_KEY in the environment.  When the key is absent the
provider is silently skipped so the system continues to work with the
other sources.

This source is primarily useful for Chinese-published titles and returns
very complete metadata: classification code (中图法分类号), translator,
series, Douban ID, price, binding, and a direct cover URL.

Response shape (code == 0 on success):
    {
      "code": 0,
      "msg": "success",
      "data": {
        "name":        "三体",
        "title":       null,           # subtitle
        "author":      "刘慈欣",
        "translator":  null,
        "publishing":  "重庆出版社",
        "published":   "2008-01-01",
        "designed":    "平装",          # binding
        "series":      null,
        "category":    "I247.5",       # 中图法分类号
        "douban":      "2567698",
        "douban_score":"9.4",
        "isbn":        "9787536692930",
        "price":       "23.00",
        "pages":       "302",
        "cover":       "https://img3.doubanio.com/...",
        "description": "..."
      }
    }
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

import httpx

from app.schemas.external_book import ExternalBookCandidate

from .base import BookProvider

logger = logging.getLogger(__name__)

_BASE_URL = "https://data.isbn.work/openApi/getInfoByIsbn"
_TIMEOUT = 10.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _api_key() -> str | None:
    return os.getenv("ISBN_WORK_API_KEY") or None


def _parse_year(raw: str | None) -> int | None:
    if not raw:
        return None
    m = re.search(r"\d{4}", str(raw))
    return int(m.group()) if m else None


def _safe_int(val: Any) -> int | None:
    try:
        return int(val) if val is not None and str(val).strip() else None
    except (ValueError, TypeError):
        return None


def _clean_isbn(val: Any) -> str | None:
    if not val:
        return None
    cleaned = re.sub(r"[^\dXx]", "", str(val))
    return cleaned if cleaned else None


def _parse_entry(data: dict[str, Any]) -> ExternalBookCandidate | None:
    title: str = (data.get("name") or "").strip()
    if not title:
        return None

    isbn = _clean_isbn(data.get("isbn"))

    # isbn.work uses "title" for subtitle, "name" for the main title
    subtitle: str | None = (data.get("title") or "").strip() or None

    author_raw = (data.get("author") or "").strip()
    # Strip trailing "著"/"编"/"等" labels that some records include
    author = re.sub(r"[\s　]*[著编等译]{1,2}$", "", author_raw).strip() or None

    publisher = (data.get("publishing") or "").strip() or None
    publish_year = _parse_year(data.get("published"))
    cover_url = (data.get("cover") or "").strip() or None
    summary = (data.get("description") or "").strip() or None
    pages = _safe_int(data.get("pages"))

    return ExternalBookCandidate(
        source="isbn_work",
        source_id=isbn or data.get("douban"),
        title=title,
        subtitle=subtitle,
        author=author,
        publisher=publisher,
        publish_year=publish_year,
        isbn=isbn,
        cover_url=cover_url,
        summary=summary,
        language="zh",
        pages=pages,
        raw=data,
    )


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------

class IsbnWorkProvider(BookProvider):
    """isbn.work — free Chinese-book ISBN lookup.

    Only ISBN lookup is supported; keyword search is not available on this
    endpoint.  The provider is a no-op when ISBN_WORK_API_KEY is not set.
    """

    name = "isbn_work"

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key

    async def search(self, query: str, limit: int = 10) -> list[ExternalBookCandidate]:
        # isbn.work has no keyword search endpoint — ISBN lookup only.
        return []

    async def lookup_isbn(self, isbn: str) -> list[ExternalBookCandidate]:
        key = self.api_key or _api_key()
        if not key:
            logger.debug("isbn.work skipped: ISBN_WORK_API_KEY not set")
            return []

        params = {"isbn": isbn, "appKey": key}
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.get(_BASE_URL, params=params)
                resp.raise_for_status()
                payload: dict[str, Any] = resp.json()
        except Exception as exc:
            logger.warning("isbn.work lookup failed for %s: %s", isbn, exc)
            return []

        if payload.get("code") != 0:
            logger.debug(
                "isbn.work returned non-zero code %s for %s: %s",
                payload.get("code"),
                isbn,
                payload.get("msg"),
            )
            return []

        data = payload.get("data")
        if not isinstance(data, dict):
            return []

        try:
            candidate = _parse_entry(data)
            return [candidate] if candidate else []
        except Exception as exc:
            logger.debug("isbn.work parse error for %s: %s", isbn, exc)
            return []

"""National Library of China (国家图书馆, NLC) provider.

Queries the NLC online catalogue at https://find.nlc.cn — no API key
required.  Data originates from official Chinese publication records and
is authoritative for ISBN, classification number (中图法分类号),
publisher, and author.  Cover images are generally unavailable.

Two endpoints are used:
  Search list:  GET https://find.nlc.cn/search/searchList
  Record detail: GET https://find.nlc.cn/search/searchDetail

The catalogue front-end is a Vue SPA; the underlying JSON API is
reverse-engineered from the browser's network calls and may change
without notice.  All parsing failures are caught and logged so that
other providers continue to serve results.

Known limitations:
  - No cover images in the catalogue
  - Page counts are sometimes missing
  - The API rate-limits aggressive crawlers (we use conservative limits)
"""

from __future__ import annotations

import logging
import re
from typing import Any

import httpx

from app.schemas.external_book import ExternalBookCandidate

from .base import BookProvider

logger = logging.getLogger(__name__)

_SEARCH_URL = "https://find.nlc.cn/search/searchList"
_DETAIL_URL = "https://find.nlc.cn/search/searchDetail"
_TIMEOUT = 12.0

# Browser-like headers to avoid 403 / bot-detection
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://find.nlc.cn/",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "X-Requested-With": "XMLHttpRequest",
}


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _parse_year(raw: str | None) -> int | None:
    if not raw:
        return None
    m = re.search(r"\d{4}", str(raw))
    return int(m.group()) if m else None


def _clean_isbn(val: str | None) -> str | None:
    if not val:
        return None
    cleaned = re.sub(r"[^\dXx]", "", val)
    return cleaned if len(cleaned) in (10, 13) else None


def _safe_int(val: Any) -> int | None:
    try:
        return int(val) if val is not None else None
    except (ValueError, TypeError):
        return None


def _strip_role_suffix(text: str) -> str:
    """Remove trailing role labels like 著、编著、译 that NLC appends to names."""
    return re.sub(r"[\s　]*[，,]?\s*[著编译等]{1,3}$", "", text).strip()


def _parse_list_item(item: dict[str, Any]) -> ExternalBookCandidate | None:
    """Parse one record from the searchList response."""
    title: str = (item.get("title") or item.get("name") or "").strip()
    if not title:
        return None

    source_id: str | None = str(item["id"]) if item.get("id") else None

    # Author field varies: "author", "responinfo", "creator"
    author_raw = (
        item.get("author")
        or item.get("responinfo")
        or item.get("creator")
        or ""
    ).strip()
    author = _strip_role_suffix(author_raw) or None

    publisher = (item.get("publisher") or item.get("publish") or "").strip() or None
    publish_year = _parse_year(
        item.get("year") or item.get("publishYear") or item.get("pubdate")
    )

    raw_isbn = item.get("isbn") or item.get("ISBN") or ""
    isbn = _clean_isbn(raw_isbn)

    pages = _safe_int(item.get("pages") or item.get("page"))

    return ExternalBookCandidate(
        source="nlc",
        source_id=source_id,
        title=title,
        subtitle=None,
        author=author,
        publisher=publisher,
        publish_year=publish_year,
        isbn=isbn,
        cover_url=None,   # NLC OPAC does not provide cover images
        summary=None,
        language="zh",
        pages=pages,
        raw=item,
    )


def _parse_detail(detail: dict[str, Any], source_id: str | None) -> ExternalBookCandidate | None:
    """Parse a full record from the searchDetail response."""
    title = (detail.get("title") or detail.get("name") or "").strip()
    if not title:
        return None

    author_raw = (
        detail.get("author")
        or detail.get("responinfo")
        or detail.get("creator")
        or ""
    ).strip()
    author = _strip_role_suffix(author_raw) or None

    publisher = (detail.get("publisher") or detail.get("publish") or "").strip() or None
    publish_year = _parse_year(
        detail.get("year") or detail.get("publishYear") or detail.get("pubdate")
    )

    raw_isbn = detail.get("isbn") or detail.get("ISBN") or ""
    isbn = _clean_isbn(raw_isbn)

    # Summary / abstract
    summary = (detail.get("summary") or detail.get("abstract") or detail.get("description") or "").strip() or None

    pages = _safe_int(detail.get("pages") or detail.get("page"))
    subtitle = (detail.get("subtitle") or "").strip() or None

    return ExternalBookCandidate(
        source="nlc",
        source_id=source_id,
        title=title,
        subtitle=subtitle,
        author=author,
        publisher=publisher,
        publish_year=publish_year,
        isbn=isbn,
        cover_url=None,
        summary=summary,
        language="zh",
        pages=pages,
        raw=detail,
    )


def _extract_items(data: Any) -> list[dict[str, Any]]:
    """Normalise various possible JSON shapes returned by the NLC API."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        # Possible keys: "dataList", "list", "data", "records", "items"
        for key in ("dataList", "list", "data", "records", "items", "result"):
            val = data.get(key)
            if isinstance(val, list):
                return val
            if isinstance(val, dict):
                # Nested one more level
                for inner_key in ("dataList", "list", "records", "items"):
                    inner = val.get(inner_key)
                    if isinstance(inner, list):
                        return inner
    return []


def _unwrap_response(payload: Any) -> Any:
    """Unwrap top-level {code, data, ...} envelope if present."""
    if isinstance(payload, dict):
        # Success envelope: {"code": 200, "data": {...}}
        code = payload.get("code") or payload.get("status")
        if code is not None and code not in (200, 0, "200", "0", True, "success"):
            logger.debug("NLC API returned non-success code: %s", code)
            return None
        inner = payload.get("data") or payload.get("result") or payload
        return inner
    return payload


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

async def _fetch_json(client: httpx.AsyncClient, url: str, params: dict) -> Any:
    try:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        logger.warning("NLC request failed [%s %s]: %s", url, params, exc)
        return None


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------

class NLCProvider(BookProvider):
    """National Library of China (国家图书馆) OPAC provider.

    Authoritative for Chinese-published books.  No API key required.
    Results lack cover images but include the official 中图法分类号 in raw data.
    """

    name = "nlc"

    async def search(self, query: str, limit: int = 10) -> list[ExternalBookCandidate]:
        params = {
            "q": query,
            "searchType": "",
            "pageNo": 1,
            "pageSize": min(limit, 20),
            "orderType": 0,
            "orderWay": "desc",
        }
        async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_HEADERS) as client:
            payload = await _fetch_json(client, _SEARCH_URL, params)

        if payload is None:
            return []

        inner = _unwrap_response(payload)
        if inner is None:
            return []

        items = _extract_items(inner)
        results: list[ExternalBookCandidate] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            try:
                candidate = _parse_list_item(item)
                if candidate:
                    results.append(candidate)
            except Exception as exc:
                logger.debug("NLC list item parse error: %s", exc)
            if len(results) >= limit:
                break

        logger.debug("NLC search '%s' → %d results", query, len(results))
        return results

    async def lookup_isbn(self, isbn: str) -> list[ExternalBookCandidate]:
        # Step 1: search by ISBN to get the record id
        params = {
            "q": isbn,
            "searchType": "isbn",
            "pageNo": 1,
            "pageSize": 5,
            "orderType": 0,
            "orderWay": "desc",
        }
        async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_HEADERS) as client:
            payload = await _fetch_json(client, _SEARCH_URL, params)

            if payload is None:
                return []

            inner = _unwrap_response(payload)
            if inner is None:
                return []

            items = _extract_items(inner)
            if not items:
                # Retry with plain keyword search (some NLC versions ignore searchType)
                params2 = {**params, "searchType": "", "q": isbn}
                payload2 = await _fetch_json(client, _SEARCH_URL, params2)
                if payload2:
                    inner2 = _unwrap_response(payload2)
                    if inner2:
                        items = _extract_items(inner2)

            if not items:
                return []

            # Step 2: fetch full detail for the first matching record
            first = items[0] if isinstance(items[0], dict) else {}
            record_id = first.get("id") or first.get("recordId") or first.get("rid")

            if record_id:
                detail_payload = await _fetch_json(
                    client, _DETAIL_URL, {"id": record_id}
                )
                if detail_payload:
                    detail_inner = _unwrap_response(detail_payload)
                    if isinstance(detail_inner, dict):
                        try:
                            candidate = _parse_detail(detail_inner, str(record_id))
                            if candidate:
                                return [candidate]
                        except Exception as exc:
                            logger.debug("NLC detail parse error: %s", exc)

            # Fallback: use the list item directly
            try:
                candidate = _parse_list_item(first)
                return [candidate] if candidate else []
            except Exception as exc:
                logger.debug("NLC list fallback parse error: %s", exc)
                return []

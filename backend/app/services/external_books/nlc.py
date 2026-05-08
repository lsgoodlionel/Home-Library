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

import html
import logging
import re
from typing import Any

import httpx

from app.schemas.external_book import ExternalBookCandidate

from .base import BookProvider

logger = logging.getLogger(__name__)

# The old JSON paths currently time out on HTTPS from Docker but fail quickly
# on HTTP, allowing the active HTML fallback below to return promptly.
_SEARCH_URL = "http://find.nlc.cn/search/searchList"
_DETAIL_URL = "http://find.nlc.cn/search/searchDetail"
_HTML_SEARCH_URL = "http://find.nlc.cn/search/doSearch"
_HTML_DETAIL_URL = "http://find.nlc.cn/search/showDocDetails"
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

_HTML_HEADERS = {
    **_HEADERS,
    "Referer": "http://find.nlc.cn/",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
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


def _parse_pages(raw: Any) -> int | None:
    if raw is None:
        return None
    text = str(raw)
    if not re.search(r"(页|pages?|p\.)", text, re.I):
        return None
    if "册" in text:
        inner_match = re.search(r"[（(]([^）)]*页)[）)]", text)
        if inner_match:
            volume_pages = [int(item) for item in re.findall(r"\d+", inner_match.group(1))]
            return sum(volume_pages) if volume_pages else None

    matches = re.findall(r"(\d[\d,]*)\s*页", text)
    if not matches:
        return None
    value = matches[-1]
    parts = value.split(",")
    if len(parts) > 1 and len(parts[0]) <= 2:
        value = parts[-1]
    else:
        value = value.replace(",", "")
    return int(value)


def _strip_role_suffix(text: str) -> str:
    """Remove trailing role labels like 著、编著、译 that NLC appends to names."""
    return re.sub(r"[\s　]*[，,]?\s*[著编译等]{1,3}$", "", text).strip()


def _clean_text(raw: str | None) -> str:
    if not raw:
        return ""
    text = re.sub(r"<[^>]+>", " ", raw)
    text = html.unescape(text).replace("\xa0", " ")
    return re.sub(r"[\s　]+", " ", text).strip()


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


def _field_from_html(block: str, label: str) -> str | None:
    pattern = (
        rf"{re.escape(label)}\s*[：:]?\s*</?span[^>]*>\s*"
        rf"(?:<a[^>]*>\s*)?<span[^>]*class=\"(?:book_t_val|book_val|book_type)\"[^>]*>(.*?)</span>"
    )
    match = re.search(pattern, block, re.S)
    return _clean_text(match.group(1)) or None if match else None


def _parse_html_detail(text: str, source_id: str | None, data_source: str | None = None) -> ExternalBookCandidate | None:
    title_match = re.search(r"<div[^>]+class=\"book_name\"[^>]*>(.*?)</div>", text, re.S)
    title = _clean_text(title_match.group(1)) if title_match else ""
    if not title:
        return None

    author = _strip_role_suffix(_field_from_html(text, "责任者") or _field_from_html(text, "所有责任者") or "") or None
    publisher = _field_from_html(text, "出版、发行者")
    publish_year = _parse_year(_field_from_html(text, "出版发行时间"))
    isbn = _clean_isbn(_field_from_html(text, "标识号"))
    pages = _parse_pages(_field_from_html(text, "载体形态"))

    summary_match = re.search(r"<div[^>]+class=\"zy_pp_val\"[^>]*>(.*?)</div>", text, re.S)
    summary = _clean_text(summary_match.group(1)) or None if summary_match else None

    raw = {
        "docId": source_id,
        "dataSource": data_source,
        "classification": _field_from_html(text, "分类"),
    }

    return ExternalBookCandidate(
        source="nlc",
        source_id=source_id,
        title=title,
        subtitle=None,
        author=author,
        publisher=publisher,
        publish_year=publish_year,
        isbn=isbn,
        cover_url=None,
        summary=summary,
        language="zh",
        pages=pages,
        raw=raw,
    )


def _parse_html_list_item(block: str) -> tuple[ExternalBookCandidate | None, str | None]:
    detail_match = re.search(
        r"makeDetailUrl\([^)]*?,\s*'[^']*',\s*'([^']+)',\s*'([^']+)'",
        block,
        re.S,
    )
    source_id = detail_match.group(1) if detail_match else None
    data_source = detail_match.group(2) if detail_match else None

    title_match = re.search(r"<div[^>]+class=\"book_name\"[^>]*>.*?<a[^>]*>(.*?)</a>", block, re.S)
    title = _clean_text(title_match.group(1)) if title_match else ""
    if not title:
        return None, data_source

    author = _strip_role_suffix(_field_from_html(block, "著者") or "") or None
    publisher = _field_from_html(block, "出版社")
    publish_year = _parse_year(_field_from_html(block, "出版年份"))
    cover_match = re.search(r"<img[^>]+class=\"book_img\"[^>]+src=\"([^\"]+)\"", block, re.S)
    cover_url = _clean_text(cover_match.group(1)) if cover_match else None

    raw = {"docId": source_id, "dataSource": data_source}
    candidate = ExternalBookCandidate(
        source="nlc",
        source_id=source_id,
        title=title,
        subtitle=None,
        author=author,
        publisher=publisher,
        publish_year=publish_year,
        isbn=None,
        cover_url=cover_url,
        summary=None,
        language="zh",
        pages=None,
        raw=raw,
    )
    return candidate, data_source


def _parse_html_search(text: str, limit: int) -> list[tuple[ExternalBookCandidate, str | None]]:
    blocks = re.findall(r"<div class=\"article_item\">(.*?)(?=<div class=\"article_item\">|<div class=\"page_fix\"|$)", text, re.S)
    results: list[tuple[ExternalBookCandidate, str | None]] = []
    for block in blocks:
        try:
            candidate, data_source = _parse_html_list_item(block)
            if candidate:
                results.append((candidate, data_source))
        except Exception as exc:
            logger.debug("NLC HTML list item parse error: %s", exc)
        if len(results) >= limit:
            break
    return results


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


async def _fetch_html(client: httpx.AsyncClient, url: str, params: dict) -> str | None:
    try:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        return resp.text
    except Exception as exc:
        logger.warning("NLC HTML request failed [%s %s]: %s", url, params, exc)
        return None


async def _search_html(client: httpx.AsyncClient, query: str, limit: int) -> list[ExternalBookCandidate]:
    params = {
        "query": query,
        "secQuery": "",
        "actualQuery": query,
        "searchType": 2,
        "docType": "图书",
        "targetFieldLog": "全部字段",
    }
    text = await _fetch_html(client, _HTML_SEARCH_URL, params)
    if not text:
        return []

    parsed = _parse_html_search(text, limit)
    results: list[ExternalBookCandidate] = []
    for candidate, data_source in parsed:
        if candidate.source_id and data_source:
            detail_text = await _fetch_html(
                client,
                _HTML_DETAIL_URL,
                {"docId": candidate.source_id, "dataSource": data_source, "query": query},
            )
            if detail_text:
                detail = _parse_html_detail(detail_text, candidate.source_id, data_source)
                if detail:
                    candidate = detail.model_copy(update={"cover_url": detail.cover_url or candidate.cover_url})
        results.append(candidate)
        if len(results) >= limit:
            break
    return results


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
            async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_HTML_HEADERS) as client:
                return await _search_html(client, query, limit)

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
                return await _search_html(client, isbn, 1)

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
                return await _search_html(client, isbn, 1)

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

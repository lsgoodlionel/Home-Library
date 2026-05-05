"""Douban Books provider implementation.

Uses the Douban subject-suggest JSON endpoint which returns structured book data
without requiring authentication.  Primarily useful for Chinese-language books
that Google Books and Open Library cover poorly.

Douban API:
  suggest:  https://book.douban.com/j/subject_suggest?q={query}
  detail:   https://book.douban.com/subject/{id}/ (HTML, used for ISBN enrichment)
"""

from __future__ import annotations

import logging
import re
from typing import Any

import httpx

from app.schemas.external_book import ExternalBookCandidate

from .base import BookProvider

logger = logging.getLogger(__name__)

_SUGGEST_URL = "https://book.douban.com/j/subject_suggest"
_TIMEOUT = 10.0

# Douban returns HTTP 403 for default httpx User-Agent; mimic a real browser.
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://book.douban.com/",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "zh-CN,zh;q=0.9",
}


def _parse_entry(entry: dict[str, Any]) -> ExternalBookCandidate | None:
    """Convert one Douban suggest entry to an ExternalBookCandidate."""
    # Only process book-type entries
    if entry.get("type") != "book":
        return None

    source_id: str | None = entry.get("id") and str(entry["id"])
    title: str = (entry.get("title") or "").strip()
    if not title:
        return None

    author_raw: str = (entry.get("author") or "").strip()
    # Douban may return "/ 作者名" or "[美] 作者名 著" — strip leading slash/brackets
    author_raw = re.sub(r"^[\s/／]+", "", author_raw).strip()
    author = author_raw or None

    year_raw: str = entry.get("year") or ""
    publish_year: int | None = None
    if year_raw and year_raw.isdigit():
        publish_year = int(year_raw)

    publisher: str | None = (entry.get("publisher") or "").strip() or None

    # Cover image — prefer the "normal" size over "small"
    pic: dict[str, str] = entry.get("pic") or {}
    cover_url: str | None = pic.get("normal") or pic.get("large") or pic.get("small") or None
    if cover_url:
        cover_url = cover_url.replace("http://", "https://")

    # Douban subject URL carries the book ID but not the ISBN directly
    url: str | None = entry.get("url")
    subject_id = source_id or (
        re.search(r"/subject/(\d+)/", url or "")
        and re.search(r"/subject/(\d+)/", url or "").group(1)  # type: ignore[union-attr]
    )

    return ExternalBookCandidate(
        source="douban",
        source_id=str(subject_id) if subject_id else None,
        title=title,
        author=author,
        publisher=publisher,
        publish_year=publish_year,
        cover_url=cover_url,
        language="zh",  # Douban is predominantly Chinese-language
        raw=entry,
    )


class DoubanBooksProvider(BookProvider):
    """Douban Books (豆瓣读书) provider.

    Best for Chinese-language books; data quality is generally higher than
    Google Books or Open Library for titles published in mainland China.
    Falls back silently on network or parsing errors.
    """

    name = "douban"

    async def search(self, query: str, limit: int = 10) -> list[ExternalBookCandidate]:
        params = {"q": query}
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_HEADERS) as client:
                resp = await client.get(_SUGGEST_URL, params=params)
                resp.raise_for_status()
                data: list[dict[str, Any]] = resp.json()
        except Exception as exc:
            logger.warning("Douban search failed: %s", exc)
            return []

        if not isinstance(data, list):
            return []

        results: list[ExternalBookCandidate] = []
        for entry in data:
            try:
                candidate = _parse_entry(entry)
                if candidate is not None:
                    results.append(candidate)
            except Exception as exc:
                logger.debug("Douban entry parse error: %s", exc)
            if len(results) >= limit:
                break
        return results

    async def lookup_isbn(self, isbn: str) -> list[ExternalBookCandidate]:
        # Douban suggest accepts ISBNs as query terms and returns the matching book
        results = await self.search(isbn, limit=5)
        # Tag results that came from an ISBN search so dedup can trust the ISBN field
        for r in results:
            if not r.isbn:
                r.isbn = isbn
        return results

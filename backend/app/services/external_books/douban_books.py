"""Douban Books provider implementation.

Uses the Douban subject-suggest JSON endpoint which returns structured book data
without requiring authentication.  Primarily useful for Chinese-language books
that Google Books and Open Library cover poorly.

Actual response shape from https://book.douban.com/j/subject_suggest?q={query}:
    [
      {
        "id": "2567698",
        "type": "b",          # "b" = book (NOT "book")
        "title": "三体",
        "author_name": "刘慈欣",
        "year": "2008",
        "pic": "https://img1.doubanio.com/view/subject/s/public/s2768378.jpg",
        "url": "https://book.douban.com/subject/2567698/"
      },
      ...
    ]

ISBN lookup via subject_suggest returns [] — ISBN queries are intentionally
delegated to Google Books / Open Library which handle them better.
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

# Douban returns HTTP 403 without a browser-like User-Agent.
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

# Cover URLs contain "/s/" (small); swap for "/m/" (medium, ~bigger thumbnails)
_COVER_SIZE_RE = re.compile(r"/view/subject/s/")


def _parse_year(raw: str) -> int | None:
    """Extract a 4-digit year from strings like "2008" or "2008年"."""
    m = re.search(r"\d{4}", raw)
    return int(m.group()) if m else None


def _parse_entry(entry: dict[str, Any]) -> ExternalBookCandidate | None:
    """Convert one Douban suggest entry to an ExternalBookCandidate.

    Actual ``type`` value for books is ``"b"``, not ``"book"``.
    """
    if entry.get("type") != "b":
        return None

    title: str = (entry.get("title") or "").strip()
    if not title:
        return None

    source_id: str | None = str(entry["id"]) if entry.get("id") else None

    author_raw: str = (entry.get("author_name") or "").strip()
    # Strip leading "/" or "／" sometimes prepended by Douban
    author_raw = re.sub(r"^[\s/／]+", "", author_raw).strip()
    author = author_raw or None

    publish_year: int | None = _parse_year(entry.get("year") or "")

    # pic is a plain URL string (e.g. ".../s/public/s123.jpg")
    pic_url: str | None = (entry.get("pic") or "").strip() or None
    if pic_url:
        # Upgrade http → https and swap small (/s/) for medium (/m/) size
        pic_url = pic_url.replace("http://", "https://")
        pic_url = _COVER_SIZE_RE.sub("/view/subject/m/", pic_url)

    return ExternalBookCandidate(
        source="douban",
        source_id=source_id,
        title=title,
        author=author,
        publish_year=publish_year,
        cover_url=pic_url,
        language="zh",  # Douban is predominantly Chinese-language content
        raw=entry,
    )


class DoubanBooksProvider(BookProvider):
    """Douban Books (豆瓣读书) provider.

    Best for Chinese-language title/author keyword searches.  ISBN lookups
    return an empty list intentionally — ``subject_suggest`` does not accept
    raw ISBNs; Google Books and Open Library handle ISBN queries better.
    """

    name = "douban"

    def __init__(self, cookie: str | None = None, user_agent: str | None = None) -> None:
        self.cookie = cookie
        self.user_agent = user_agent

    async def search(self, query: str, limit: int = 10) -> list[ExternalBookCandidate]:
        params = {"q": query}
        headers = dict(_HEADERS)
        if self.user_agent:
            headers["User-Agent"] = self.user_agent
        if self.cookie:
            headers["Cookie"] = self.cookie
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT, headers=headers) as client:
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
        # subject_suggest returns [] for raw ISBN queries; let other providers
        # (Google Books, Open Library) handle ISBN lookups instead.
        return []

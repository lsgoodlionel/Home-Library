"""Google Books provider implementation.

Uses the public Google Books Volumes API.  An API key is optional; omit it for
light-traffic / development use.  Set GOOGLE_BOOKS_API_KEY in the environment to
enable higher quota.

API reference: https://developers.google.com/books/docs/v1/using
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from app.schemas.external_book import ExternalBookCandidate

from .base import BookProvider

logger = logging.getLogger(__name__)

_VOLUMES_URL = "https://www.googleapis.com/books/v1/volumes"
_TIMEOUT = 10.0


def _contains_cjk(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)


def _api_key() -> str | None:
    return os.getenv("GOOGLE_BOOKS_API_KEY") or None


def _parse_volume(volume: dict[str, Any]) -> ExternalBookCandidate:
    info: dict[str, Any] = volume.get("volumeInfo", {})

    authors: list[str] = info.get("authors", [])
    author = ", ".join(authors) if authors else None

    industry_ids: list[dict[str, str]] = info.get("industryIdentifiers", [])
    isbn13 = next((i["identifier"] for i in industry_ids if i.get("type") == "ISBN_13"), None)
    isbn10 = next((i["identifier"] for i in industry_ids if i.get("type") == "ISBN_10"), None)
    isbn = isbn13 or isbn10

    image_links: dict[str, str] = info.get("imageLinks", {})
    cover_url = image_links.get("thumbnail") or image_links.get("smallThumbnail")
    if cover_url:
        cover_url = cover_url.replace("http://", "https://")

    published_date: str = info.get("publishedDate", "")
    publish_year: int | None = None
    year_part = published_date[:4]
    if year_part.isdigit():
        publish_year = int(year_part)

    return ExternalBookCandidate(
        source="google_books",
        source_id=volume.get("id"),
        title=info.get("title", ""),
        subtitle=info.get("subtitle"),
        author=author,
        publisher=info.get("publisher"),
        publish_year=publish_year,
        isbn=isbn,
        cover_url=cover_url or None,
        summary=info.get("description"),
        language=info.get("language"),
        pages=info.get("pageCount"),
        raw=volume,
    )


class GoogleBooksProvider(BookProvider):
    name = "google_books"

    async def search(self, query: str, limit: int = 10) -> list[ExternalBookCandidate]:
        params: dict[str, Any] = {
            "q": query,
            "maxResults": min(limit, 40),
            "printType": "books",
            "orderBy": "relevance",
        }
        if _contains_cjk(query):
            params["langRestrict"] = "zh"
            params["country"] = "CN"
        key = _api_key()
        if key:
            params["key"] = key

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.get(_VOLUMES_URL, params=params)
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            logger.warning("GoogleBooks search failed: %s", exc)
            return []

        results: list[ExternalBookCandidate] = []
        for volume in data.get("items", []):
            try:
                results.append(_parse_volume(volume))
            except Exception as exc:
                logger.debug("GoogleBooks volume parse error: %s", exc)
        return results

    async def lookup_isbn(self, isbn: str) -> list[ExternalBookCandidate]:
        return await self.search(f"isbn:{isbn}", limit=5)

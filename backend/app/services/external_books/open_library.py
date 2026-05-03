"""Open Library provider implementation.

Uses the public Open Library Search and Books APIs:
  Search:  https://openlibrary.org/search.json
  ISBN:    https://openlibrary.org/api/books (bibkeys format)
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.schemas.external_book import ExternalBookCandidate

from .base import BookProvider

logger = logging.getLogger(__name__)

_SEARCH_URL = "https://openlibrary.org/search.json"
_BOOKS_URL = "https://openlibrary.org/api/books"
_COVER_URL = "https://covers.openlibrary.org/b/id/{cover_id}-M.jpg"
_TIMEOUT = 10.0


def _cover_from_id(cover_id: int | None) -> str | None:
    if cover_id:
        return _COVER_URL.format(cover_id=cover_id)
    return None


def _first(values: list[Any] | None) -> str | None:
    if values:
        return str(values[0])
    return None


def _parse_search_doc(doc: dict[str, Any]) -> ExternalBookCandidate:
    isbn_list: list[str] = doc.get("isbn", [])
    isbn = isbn_list[0] if isbn_list else None

    authors = doc.get("author_name", [])
    author = ", ".join(authors) if authors else None

    publishers = doc.get("publisher", [])
    publisher = _first(publishers)

    publish_year = doc.get("first_publish_year")

    source_id = doc.get("key", "").lstrip("/")

    return ExternalBookCandidate(
        source="open_library",
        source_id=source_id or None,
        title=doc.get("title", ""),
        subtitle=doc.get("subtitle"),
        author=author,
        publisher=publisher,
        publish_year=int(publish_year) if publish_year else None,
        isbn=isbn,
        cover_url=_cover_from_id(doc.get("cover_i")),
        language=_first(doc.get("language")),
        pages=doc.get("number_of_pages_median"),
        raw=doc,
    )


def _parse_books_entry(bibkey: str, entry: dict[str, Any]) -> ExternalBookCandidate:
    identifiers: dict[str, list[str]] = entry.get("identifiers", {})
    isbn13 = _first(identifiers.get("isbn_13"))
    isbn10 = _first(identifiers.get("isbn_10"))
    isbn = isbn13 or isbn10

    authors: list[dict[str, str]] = entry.get("authors", [])
    author = ", ".join(a.get("name", "") for a in authors) or None

    publishers: list[dict[str, str]] = entry.get("publishers", [])
    publisher = _first([p.get("name", "") for p in publishers])

    publish_date: str = entry.get("publish_date", "")
    publish_year: int | None = None
    for token in publish_date.split():
        if token.isdigit() and len(token) == 4:
            publish_year = int(token)
            break

    cover: dict[str, str] = entry.get("cover", {})
    cover_url = cover.get("medium") or cover.get("large") or cover.get("small")

    source_id = bibkey.replace("ISBN:", "")

    return ExternalBookCandidate(
        source="open_library",
        source_id=source_id,
        title=entry.get("title", ""),
        subtitle=entry.get("subtitle"),
        author=author,
        publisher=publisher,
        publish_year=publish_year,
        isbn=isbn,
        cover_url=cover_url or None,
        pages=entry.get("number_of_pages"),
        raw=entry,
    )


class OpenLibraryProvider(BookProvider):
    name = "open_library"

    async def search(self, query: str, limit: int = 10) -> list[ExternalBookCandidate]:
        params = {
            "q": query,
            "limit": limit,
            "fields": (
                "key,title,subtitle,author_name,publisher,"
                "first_publish_year,isbn,cover_i,language,number_of_pages_median"
            ),
        }
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.get(_SEARCH_URL, params=params)
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            logger.warning("OpenLibrary search failed: %s", exc)
            return []

        docs: list[dict[str, Any]] = data.get("docs", [])
        results: list[ExternalBookCandidate] = []
        for doc in docs:
            try:
                results.append(_parse_search_doc(doc))
            except Exception as exc:
                logger.debug("OpenLibrary doc parse error: %s", exc)
        return results

    async def lookup_isbn(self, isbn: str) -> list[ExternalBookCandidate]:
        params = {
            "bibkeys": f"ISBN:{isbn}",
            "format": "json",
            "jscmd": "data",
        }
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.get(_BOOKS_URL, params=params)
                resp.raise_for_status()
                data: dict[str, Any] = resp.json()
        except Exception as exc:
            logger.warning("OpenLibrary ISBN lookup failed: %s", exc)
            return []

        results: list[ExternalBookCandidate] = []
        for bibkey, entry in data.items():
            try:
                results.append(_parse_books_entry(bibkey, entry))
            except Exception as exc:
                logger.debug("OpenLibrary entry parse error: %s", exc)
        return results

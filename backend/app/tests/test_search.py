"""Tests for Task G: external book search backend."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.schemas.external_book import (
    ExternalBookCandidate,
    ImportResultRequest,
    ImportResultResponse,
)
from app.services import external_book_service
from app.services.external_books.open_library import (
    _parse_books_entry,
    _parse_search_doc,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _candidate(**kwargs: Any) -> ExternalBookCandidate:
    defaults = dict(
        source="open_library",
        source_id="OL123",
        title="乡土中国",
        author="费孝通",
        publisher="三联书店",
        publish_year=2013,
        isbn="9787108045269",
        cover_url="https://covers.openlibrary.org/b/id/1-M.jpg",
        summary="社会学经典",
    )
    defaults.update(kwargs)
    return ExternalBookCandidate(**defaults)


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------

class TestExternalBookCandidate:
    def test_minimal_fields(self) -> None:
        c = ExternalBookCandidate(source="open_library", title="Test Book")
        assert c.title == "Test Book"
        assert c.isbn is None
        assert c.raw == {}

    def test_full_fields(self) -> None:
        c = _candidate()
        assert c.source == "open_library"
        assert c.isbn == "9787108045269"

    def test_raw_defaults_empty_dict(self) -> None:
        c = ExternalBookCandidate(source="x", title="t")
        assert isinstance(c.raw, dict)


class TestImportResultRequest:
    def test_default_import_mode(self) -> None:
        req = ImportResultRequest(result=_candidate())
        assert req.import_mode == "draft"

    def test_book_mode(self) -> None:
        req = ImportResultRequest(result=_candidate(), import_mode="book")
        assert req.import_mode == "book"

    def test_optional_ids(self) -> None:
        req = ImportResultRequest(result=_candidate(), category_id=5, location_id=2)
        assert req.category_id == 5
        assert req.location_id == 2


# ---------------------------------------------------------------------------
# ISBN normalisation
# ---------------------------------------------------------------------------

class TestCleanIsbn:
    def test_strips_hyphens(self) -> None:
        assert external_book_service.clean_isbn("978-7-108-04526-9") == "9787108045269"

    def test_keeps_x(self) -> None:
        assert external_book_service.clean_isbn("0-306-40615-X") == "030640615X"

    def test_already_clean(self) -> None:
        assert external_book_service.clean_isbn("9787108045269") == "9787108045269"

    def test_empty(self) -> None:
        assert external_book_service.clean_isbn("") == ""


# ---------------------------------------------------------------------------
# Open Library parser tests
# ---------------------------------------------------------------------------

class TestOpenLibraryParsers:
    def test_parse_search_doc_full(self) -> None:
        doc: dict[str, Any] = {
            "key": "/works/OL123W",
            "title": "乡土中国",
            "subtitle": "副标题",
            "author_name": ["费孝通"],
            "publisher": ["三联书店"],
            "first_publish_year": 2013,
            "isbn": ["9787108045269"],
            "cover_i": 99,
            "language": ["chi"],
            "number_of_pages_median": 120,
        }
        c = _parse_search_doc(doc)
        assert c.title == "乡土中国"
        assert c.author == "费孝通"
        assert c.isbn == "9787108045269"
        assert c.publish_year == 2013
        assert "99" in (c.cover_url or "")
        assert c.source == "open_library"
        assert c.source_id == "works/OL123W"

    def test_parse_search_doc_minimal(self) -> None:
        doc: dict[str, Any] = {"title": "A Book"}
        c = _parse_search_doc(doc)
        assert c.title == "A Book"
        assert c.author is None
        assert c.isbn is None

    def test_parse_search_doc_multiple_authors(self) -> None:
        doc: dict[str, Any] = {
            "title": "Book",
            "author_name": ["Author A", "Author B"],
        }
        c = _parse_search_doc(doc)
        assert c.author == "Author A, Author B"

    def test_parse_books_entry(self) -> None:
        entry: dict[str, Any] = {
            "title": "乡土中国",
            "authors": [{"name": "费孝通"}],
            "publishers": [{"name": "三联书店"}],
            "publish_date": "January 2013",
            "identifiers": {"isbn_13": ["9787108045269"]},
            "cover": {"medium": "https://covers.example.com/m.jpg"},
            "number_of_pages": 120,
        }
        c = _parse_books_entry("ISBN:9787108045269", entry)
        assert c.title == "乡土中国"
        assert c.author == "费孝通"
        assert c.isbn == "9787108045269"
        assert c.publish_year == 2013
        assert c.pages == 120
        assert c.source_id == "9787108045269"


# ---------------------------------------------------------------------------
# Deduplication tests
# ---------------------------------------------------------------------------

class TestDeduplicate:
    def test_dedup_by_isbn(self) -> None:
        a = _candidate(source="open_library", summary=None)
        b = _candidate(source="google_books", summary="Has summary")
        result = external_book_service._deduplicate([a, b])
        assert len(result) == 1
        assert result[0].summary == "Has summary"

    def test_keeps_no_isbn_entries(self) -> None:
        a = _candidate(isbn=None, title="No ISBN A")
        b = _candidate(isbn=None, title="No ISBN B")
        result = external_book_service._deduplicate([a, b])
        assert len(result) == 2

    def test_mixed(self) -> None:
        a = _candidate(isbn="111")
        b = _candidate(isbn="111")
        c = _candidate(isbn=None)
        result = external_book_service._deduplicate([a, b, c])
        assert len(result) == 2


# ---------------------------------------------------------------------------
# candidate_to_book_create_dict tests
# ---------------------------------------------------------------------------

class TestCandidateToBookCreateDict:
    def test_basic_mapping(self) -> None:
        c = _candidate()
        d = external_book_service.candidate_to_book_create_dict(c)
        assert d["title"] == "乡土中国"
        assert d["author"] == "费孝通"
        assert d["isbn"] == "9787108045269"
        assert d["source"] == "isbn_lookup"
        assert d["tag_names"] == []

    def test_no_isbn_gives_title_search_source(self) -> None:
        c = _candidate(isbn=None)
        d = external_book_service.candidate_to_book_create_dict(c)
        assert d["source"] == "title_search"

    def test_category_location_forwarded(self) -> None:
        c = _candidate()
        d = external_book_service.candidate_to_book_create_dict(c, category_id=5, location_id=3)
        assert d["category_id"] == 5
        assert d["location_id"] == 3


# ---------------------------------------------------------------------------
# Route tests (via TestClient, with mocked service)
# ---------------------------------------------------------------------------

class TestSearchBooksRoute:
    def test_missing_query_param(self, client: TestClient) -> None:
        resp = client.get("/api/search/books")
        assert resp.status_code == 422

    def test_returns_items(self, client: TestClient) -> None:
        mock_candidates = [_candidate()]
        with patch(
            "app.services.external_book_service.search_books",
            new=AsyncMock(return_value=mock_candidates),
        ):
            resp = client.get("/api/search/books", params={"query": "乡土中国"})
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert len(data["items"]) == 1
        assert data["items"][0]["title"] == "乡土中国"

    def test_empty_results(self, client: TestClient) -> None:
        with patch(
            "app.services.external_book_service.search_books",
            new=AsyncMock(return_value=[]),
        ):
            resp = client.get("/api/search/books", params={"query": "xyznotfound"})
        assert resp.status_code == 200
        assert resp.json()["items"] == []

    def test_provider_failure_degrades_to_empty_results(self, db_session: Session) -> None:
        mock_provider = MagicMock()
        mock_provider.name = "broken"
        mock_provider.search = AsyncMock(side_effect=RuntimeError("network down"))

        results = asyncio.run(
            external_book_service.search_books(
                db_session,
                query="乡土中国",
                limit=5,
                providers=[mock_provider],
            )
        )

        assert results == []
        mock_provider.search.assert_awaited_once()


class TestIsbnRoute:
    def test_isbn_lookup(self, client: TestClient) -> None:
        mock_candidates = [_candidate()]
        with patch(
            "app.services.external_book_service.lookup_isbn",
            new=AsyncMock(return_value=mock_candidates),
        ):
            resp = client.get("/api/search/isbn/9787108045269")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"][0]["isbn"] == "9787108045269"

    def test_isbn_with_hyphens_cleaned(self, client: TestClient) -> None:
        with patch(
            "app.services.external_book_service.lookup_isbn",
            new=AsyncMock(return_value=[]),
        ) as mock_lookup:
            client.get("/api/search/isbn/978-7-108-04526-9")
        mock_lookup.assert_awaited_once()
        called_isbn = mock_lookup.call_args[1]["isbn"]
        assert "-" not in called_isbn

    def test_isbn_not_found(self, client: TestClient) -> None:
        with patch(
            "app.services.external_book_service.lookup_isbn",
            new=AsyncMock(return_value=[]),
        ):
            resp = client.get("/api/search/isbn/0000000000000")
        assert resp.status_code == 200
        assert resp.json()["items"] == []

    def test_isbn_provider_failure_degrades_to_empty_results(self, db_session: Session) -> None:
        mock_provider = MagicMock()
        mock_provider.name = "broken"
        mock_provider.lookup_isbn = AsyncMock(side_effect=RuntimeError("timeout"))

        results = asyncio.run(
            external_book_service.lookup_isbn(
                db_session,
                isbn="9787108045269",
                providers=[mock_provider],
            )
        )

        assert results == []
        mock_provider.lookup_isbn.assert_awaited_once()


class TestImportResultRoute:
    def test_draft_mode_does_not_save(self, client: TestClient, db_session: Session) -> None:
        from app.models.book import Book

        payload = {
            "result": {
                "source": "open_library",
                "source_id": "OL1",
                "title": "乡土中国",
                "author": "费孝通",
                "isbn": "9787108045269",
            },
            "import_mode": "draft",
        }
        resp = client.post("/api/search/import-result", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["import_mode"] == "draft"
        assert data["book_id"] is None
        assert data["title"] == "乡土中国"
        assert db_session.query(Book).count() == 0

    def test_book_mode_creates_record(self, client: TestClient, db_session: Session) -> None:
        from app.models.book import Book

        payload = {
            "result": {
                "source": "open_library",
                "source_id": "OL1",
                "title": "乡土中国",
                "author": "费孝通",
                "isbn": "9787108045269",
            },
            "import_mode": "book",
        }
        resp = client.post("/api/search/import-result", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["import_mode"] == "book"
        assert data["book_id"] is not None
        assert data["title"] == "乡土中国"
        assert db_session.query(Book).count() == 1

    def test_book_mode_with_category_location(
        self, client: TestClient, db_session: Session
    ) -> None:
        from app.models.book import Book
        from app.models.category import Category
        from app.models.location import Location
        from datetime import datetime, timezone

        now = datetime.now(tz=timezone.utc)
        cat = Category(code="C91", name="社会学", sort_order=0, is_system=False, created_at=now, updated_at=now)
        loc = Location(room="书房", shelf="A", full_path="书房/A", sort_order=0, created_at=now, updated_at=now)
        db_session.add_all([cat, loc])
        db_session.commit()

        payload = {
            "result": {
                "source": "open_library",
                "title": "乡土中国",
                "isbn": "9787108045269",
            },
            "category_id": cat.id,
            "location_id": loc.id,
            "import_mode": "book",
        }
        resp = client.post("/api/search/import-result", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["category_id"] == cat.id
        assert data["location_id"] == loc.id

    def test_invalid_import_mode(self, client: TestClient) -> None:
        payload = {
            "result": {"source": "open_library", "title": "X"},
            "import_mode": "invalid",
        }
        resp = client.post("/api/search/import-result", json=payload)
        assert resp.status_code == 422

    def test_missing_title(self, client: TestClient) -> None:
        payload = {
            "result": {"source": "open_library"},
            "import_mode": "draft",
        }
        resp = client.post("/api/search/import-result", json=payload)
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Cache integration test (in-memory db)
# ---------------------------------------------------------------------------

class TestCacheIntegration:
    def test_cache_miss_then_hit(self, db_session: Session) -> None:
        mock_provider = MagicMock()
        mock_provider.name = "mock"
        mock_provider.search = AsyncMock(return_value=[_candidate(source="mock")])

        async def _run() -> list[ExternalBookCandidate]:
            return await external_book_service.search_books(
                db_session, query="乡土中国", limit=5, providers=[mock_provider]
            )

        results_first = asyncio.run(_run())
        assert len(results_first) == 1
        assert mock_provider.search.await_count == 1

        results_second = asyncio.run(_run())
        assert len(results_second) == 1
        assert mock_provider.search.await_count == 1  # no second call; cache hit

    def test_isbn_cache(self, db_session: Session) -> None:
        mock_provider = MagicMock()
        mock_provider.name = "mock"
        mock_provider.lookup_isbn = AsyncMock(return_value=[_candidate(source="mock")])

        async def _run() -> list[ExternalBookCandidate]:
            return await external_book_service.lookup_isbn(
                db_session, isbn="9787108045269", providers=[mock_provider]
            )

        asyncio.run(_run())
        asyncio.run(_run())
        assert mock_provider.lookup_isbn.await_count == 1

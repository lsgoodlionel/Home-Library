"""External book search routes.

GET  /api/search/books?query=&limit=    keyword search
GET  /api/search/isbn/{isbn}            ISBN lookup
POST /api/search/import-result          import candidate as draft or book record
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.book import BookCreate
from app.schemas.external_book import (
    ExternalBookSearchResponse,
    ImportResultRequest,
    ImportResultResponse,
)
from app.services import book_service, external_book_service

router = APIRouter(prefix="/search", tags=["search"])


@router.get("/books", response_model=ExternalBookSearchResponse)
async def search_books(
    db: Annotated[Session, Depends(get_db)],
    query: Annotated[str, Query(min_length=1)],
    limit: Annotated[int, Query(ge=1, le=40)] = 10,
) -> ExternalBookSearchResponse:
    """Search external providers by title, author, or combined keyword."""
    candidates = await external_book_service.search_books(db, query=query, limit=limit)
    return ExternalBookSearchResponse(items=candidates)


@router.get("/isbn/{isbn}", response_model=ExternalBookSearchResponse)
async def search_by_isbn(
    isbn: str,
    db: Annotated[Session, Depends(get_db)],
) -> ExternalBookSearchResponse:
    """Look up a book by ISBN across all configured providers."""
    clean = external_book_service.clean_isbn(isbn)
    candidates = await external_book_service.lookup_isbn(db, isbn=clean)
    return ExternalBookSearchResponse(items=candidates)


@router.post("/import-result", response_model=ImportResultResponse)
def import_result(
    payload: ImportResultRequest,
    db: Annotated[Session, Depends(get_db)],
) -> ImportResultResponse:
    """Convert an external book candidate to a draft or a saved book record.

    import_mode="draft"  — return mapped fields without writing to the database.
    import_mode="book"   — create a Book record and return it with its new id.
    """
    book_data = external_book_service.candidate_to_book_create_dict(
        payload.result,
        category_id=payload.category_id,
        location_id=payload.location_id,
    )

    if payload.import_mode == "draft":
        return ImportResultResponse(
            import_mode="draft",
            book_id=None,
            **book_data,
        )

    book_create = BookCreate(**book_data)
    book = book_service.create_book(db, book_create)
    return ImportResultResponse(
        import_mode="book",
        book_id=book.id,
        title=book.title,
        subtitle=book.subtitle,
        author=book.author,
        translator=book.translator,
        publisher=book.publisher,
        publish_year=book.publish_year,
        isbn=book.isbn,
        language=book.language,
        pages=book.pages,
        cover_url=book.cover_url,
        summary=book.summary,
        category_id=book.category_id,
        location_id=book.location_id,
        source=book.source,
        tag_names=[bt.tag.name for bt in book.book_tags],
    )

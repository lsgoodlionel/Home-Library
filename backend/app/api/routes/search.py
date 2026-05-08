"""External book search routes.

GET  /api/search/books?query=&limit=    keyword search
GET  /api/search/isbn/{isbn}            ISBN lookup
POST /api/search/import-result          import candidate as draft or book record
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.security import get_current_user, get_optional_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.book import BookCreate
from app.schemas.external_book import (
    ExternalBookSearchResponse,
    ImportResultRequest,
    ImportResultResponse,
)
from app.schemas.external_search_setting import (
    ExternalProviderValidateResponse,
    ExternalSearchProviderConfigUpdate,
    ExternalSearchSettingsResponse,
    ExternalSearchSettingsUpdate,
)
from app.services import book_service, external_book_service
from app.services.external_search_setting_service import (
    get_effective_external_configs,
    get_external_search_settings,
    update_external_search_settings,
    validate_external_provider,
)

router = APIRouter(prefix="/search", tags=["search"])


def _parse_provider_order(provider_order: str | None) -> list[str] | None:
    if not provider_order:
        return None
    return [item.strip() for item in provider_order.split(",") if item.strip()]


@router.get("/books", response_model=ExternalBookSearchResponse)
async def search_books(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User | None, Depends(get_optional_current_user)],
    query: Annotated[str, Query(min_length=1)],
    limit: Annotated[int, Query(ge=1, le=40)] = 10,
    mode: Annotated[str | None, Query(pattern="^(title|title_author|title_publisher)$")] = None,
    provider: Annotated[str | None, Query()] = None,
    provider_order: Annotated[str | None, Query()] = None,
) -> ExternalBookSearchResponse:
    """Search external providers by title, author, or combined keyword.

    mode: controls query-variant generation
      - title         (default) plain title search
      - title_author  "书名 作者" format
      - title_publisher "书名 出版社" format
    provider: restrict to a single provider by name (e.g. "douban")
    """
    candidates = await external_book_service.search_books(
        db,
        query=query,
        limit=limit,
        mode=mode,
        provider_filter=provider,
        provider_order=_parse_provider_order(provider_order),
        provider_configs=get_effective_external_configs(db, current_user),
    )
    return ExternalBookSearchResponse(items=candidates)


@router.get("/isbn/{isbn}", response_model=ExternalBookSearchResponse)
async def search_by_isbn(
    isbn: str,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User | None, Depends(get_optional_current_user)],
    provider_order: Annotated[str | None, Query()] = None,
) -> ExternalBookSearchResponse:
    """Look up a book by ISBN across all configured providers."""
    clean = external_book_service.clean_isbn(isbn)
    candidates = await external_book_service.lookup_isbn(
        db,
        isbn=clean,
        provider_order=_parse_provider_order(provider_order),
        provider_configs=get_effective_external_configs(db, current_user),
    )
    return ExternalBookSearchResponse(items=candidates)


@router.get("/config", response_model=ExternalSearchSettingsResponse)
def get_external_search_config(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ExternalSearchSettingsResponse:
    return get_external_search_settings(db, current_user)


@router.put("/config", response_model=ExternalSearchSettingsResponse)
def update_external_search_config(
    payload: ExternalSearchSettingsUpdate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ExternalSearchSettingsResponse:
    return update_external_search_settings(db, current_user, payload)


@router.post("/providers/{provider}/validate", response_model=ExternalProviderValidateResponse)
async def validate_external_search_provider(
    provider: str,
    payload: ExternalSearchProviderConfigUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
) -> ExternalProviderValidateResponse:
    _ = current_user
    return await validate_external_provider(provider, payload.api_key)


@router.get("/cover")
async def cached_external_cover(
    url: Annotated[str, Query(min_length=1)],
) -> FileResponse:
    try:
        path, content_type = await external_book_service.cache_external_cover(url)
    except Exception as exc:
        raise HTTPException(status_code=404, detail="封面图片不可用") from exc
    return FileResponse(path, media_type=content_type)


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

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.book import BookBatchUpdate, BookCreate, BookResponse, BookUpdate, PaginatedBooks
from app.services import book_service

router = APIRouter(prefix="/books", tags=["books"])


def get_current_user_id() -> int | None:
    return None


@router.get("", response_model=PaginatedBooks)
def list_books(
    db: Annotated[Session, Depends(get_db)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    keyword: str | None = None,
    category_id: int | None = None,
    location_id: int | None = None,
    status: str | None = None,
    read_status: str | None = None,
    is_favorite: bool | None = None,
    publish_year_from: int | None = None,
    publish_year_to: int | None = None,
) -> PaginatedBooks:
    items, total = book_service.list_books(
        db,
        page=page,
        page_size=page_size,
        keyword=keyword,
        category_id=category_id,
        location_id=location_id,
        status=status,
        read_status=read_status,
        is_favorite=is_favorite,
        publish_year_from=publish_year_from,
        publish_year_to=publish_year_to,
    )
    return PaginatedBooks(items=items, total=total, page=page, page_size=page_size)


@router.get("/{book_id}", response_model=BookResponse)
def get_book(book_id: int, db: Annotated[Session, Depends(get_db)]) -> dict:
    book = book_service.get_book_or_error(db, book_id)
    return book_service.book_to_response(book)


@router.post("", response_model=BookResponse, status_code=status.HTTP_201_CREATED)
def create_book(
    payload: BookCreate,
    db: Annotated[Session, Depends(get_db)],
    current_user_id: Annotated[int | None, Depends(get_current_user_id)] = None,
) -> dict:
    book = book_service.create_book(db, payload, current_user_id=current_user_id)
    return book_service.book_to_response(book)


@router.patch("/{book_id}", response_model=BookResponse)
def update_book(
    book_id: int,
    payload: BookUpdate,
    db: Annotated[Session, Depends(get_db)],
    current_user_id: Annotated[int | None, Depends(get_current_user_id)] = None,
) -> dict:
    book = book_service.update_book(db, book_id, payload, current_user_id=current_user_id)
    return book_service.book_to_response(book)


@router.delete("/{book_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_book(book_id: int, db: Annotated[Session, Depends(get_db)]) -> Response:
    book_service.delete_book(db, book_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/batch-update")
def batch_update_books(
    payload: BookBatchUpdate,
    db: Annotated[Session, Depends(get_db)],
    current_user_id: Annotated[int | None, Depends(get_current_user_id)] = None,
) -> dict:
    return book_service.batch_update_books(db, payload, current_user_id=current_user_id)

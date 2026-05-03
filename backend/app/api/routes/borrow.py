from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.borrow_record import (
    BorrowRecordCreate,
    BorrowRecordResponse,
    BorrowReturn,
    PaginatedBorrowRecords,
)
from app.services import borrow_service

router = APIRouter(prefix="/borrow", tags=["borrow"])


@router.post("", response_model=BorrowRecordResponse, status_code=status.HTTP_201_CREATED)
def create_borrow(
    payload: BorrowRecordCreate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> object:
    return borrow_service.create_borrow(db, payload, current_user_id=current_user.id)


@router.get("/records", response_model=list[BorrowRecordResponse])
def list_borrow_records(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
    book_id: int | None = None,
    status: str | None = None,
    borrower_name: str | None = None,
) -> list[object]:
    records, _total = borrow_service.list_records(
        db,
        book_id=book_id,
        status=status,
        borrower_name=borrower_name,
    )
    return records


@router.get("/records/page", response_model=PaginatedBorrowRecords)
def list_borrow_records_page(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    book_id: int | None = None,
    status: str | None = None,
    borrower_name: str | None = None,
) -> PaginatedBorrowRecords:
    records, total = borrow_service.list_records(
        db,
        book_id=book_id,
        status=status,
        borrower_name=borrower_name,
        page=page,
        page_size=page_size,
    )
    return PaginatedBorrowRecords(items=records, total=total, page=page, page_size=page_size)


@router.get("/active", response_model=list[BorrowRecordResponse])
def list_active_borrows(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
) -> list[object]:
    return borrow_service.list_active_records(db)


@router.get("/{record_id}", response_model=BorrowRecordResponse)
def get_borrow_record(
    record_id: int,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
) -> object:
    return borrow_service.get_record_or_error(db, record_id)


@router.post("/{record_id}/return", response_model=BorrowRecordResponse)
def return_borrow(
    record_id: int,
    payload: BorrowReturn,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> object:
    return borrow_service.return_borrow(db, record_id, payload, current_user_id=current_user.id)


@router.delete("/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_borrow_record(
    record_id: int,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
) -> Response:
    borrow_service.delete_record(db, record_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

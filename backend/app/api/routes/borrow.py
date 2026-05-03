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

CurrentUser = Annotated[User, Depends(get_current_user)]
DB = Annotated[Session, Depends(get_db)]


@router.get("/active", response_model=PaginatedBorrowRecords)
def list_active_borrows(
    db: DB,
    _: CurrentUser,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 100,
) -> PaginatedBorrowRecords:
    items, total = borrow_service.list_active_borrows(db, page=page, page_size=page_size)
    return PaginatedBorrowRecords(items=items, total=total, page=page, page_size=page_size)


@router.get("/records", response_model=PaginatedBorrowRecords)
def list_borrow_records(
    db: DB,
    _: CurrentUser,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    book_id: int | None = None,
    status: str | None = None,
    borrower_name: str | None = None,
) -> PaginatedBorrowRecords:
    items, total = borrow_service.list_borrow_records(
        db,
        page=page,
        page_size=page_size,
        book_id=book_id,
        status=status,
        borrower_name=borrower_name,
    )
    return PaginatedBorrowRecords(items=items, total=total, page=page, page_size=page_size)


@router.post("", response_model=BorrowRecordResponse, status_code=status.HTTP_201_CREATED)
def create_borrow(
    payload: BorrowRecordCreate,
    db: DB,
    current_user: CurrentUser,
) -> BorrowRecordResponse:
    return borrow_service.create_borrow(db, payload, created_by=current_user.id)


@router.post("/{record_id}/return", response_model=BorrowRecordResponse)
def return_borrow(
    record_id: int,
    payload: BorrowReturn,
    db: DB,
    _: CurrentUser,
) -> BorrowRecordResponse:
    return borrow_service.return_borrow(db, record_id, payload)


@router.get("/{record_id}", response_model=BorrowRecordResponse)
def get_borrow_record(
    record_id: int,
    db: DB,
    _: CurrentUser,
) -> BorrowRecordResponse:
    return borrow_service.get_borrow_or_error(db, record_id)


@router.delete("/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_borrow_record(
    record_id: int,
    db: DB,
    current_user: CurrentUser,
) -> Response:
    from app.core.errors import ApiError

    record = borrow_service.get_borrow_or_error(db, record_id)
    if record.status == "active":
        raise ApiError("CONFLICT", "借阅中的记录不能删除，请先归还", status_code=409)
    if current_user.role != "admin" and record.created_by != current_user.id:
        raise ApiError("FORBIDDEN", "无权删除此借阅记录", status_code=403)

    db.delete(record)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)

from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.db.session import get_db
from app.schemas.import_export import ImportConfirmResponse, ImportPreviewResponse
from app.services import import_export_service

router = APIRouter(prefix="/books", tags=["import-export"])


def _parse_field_mapping(value: str | None) -> dict[str, str] | None:
    if not value:
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ApiError("VALIDATION_ERROR", "field_mapping 必须是 JSON 对象字符串", status_code=422) from exc
    if not isinstance(parsed, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in parsed.items()):
        raise ApiError("VALIDATION_ERROR", "field_mapping 必须是字符串到字符串的 JSON 对象", status_code=422)
    return parsed


@router.post("/import/preview", response_model=ImportPreviewResponse)
async def preview_import(
    db: Annotated[Session, Depends(get_db)],
    file: Annotated[UploadFile, File()],
    format: Annotated[str, Form()],
    field_mapping: Annotated[str | None, Form()] = None,
) -> ImportPreviewResponse:
    content = await file.read()
    return import_export_service.preview_import(db, content, format, _parse_field_mapping(field_mapping))


@router.post("/import", response_model=ImportConfirmResponse)
async def confirm_import(
    db: Annotated[Session, Depends(get_db)],
    file: Annotated[UploadFile, File()],
    format: Annotated[str, Form()],
    field_mapping: Annotated[str | None, Form()] = None,
) -> ImportConfirmResponse:
    content = await file.read()
    return import_export_service.confirm_import(db, content, format, _parse_field_mapping(field_mapping))


@router.get("/export")
def export_books(
    db: Annotated[Session, Depends(get_db)],
    format: Annotated[str, Query(pattern="^(csv|json|xlsx|excel)$")] = "csv",
) -> StreamingResponse:
    content, media_type, filename = import_export_service.export_books(db, format)
    return StreamingResponse(
        iter([content]),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

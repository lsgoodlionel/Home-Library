from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


ImportExportFormat = Literal["csv", "json", "xlsx", "excel"]


class ImportRowIssue(BaseModel):
    row_number: int
    field: str | None = None
    code: str
    message: str
    severity: Literal["error", "warning"] = "error"


class ImportPreviewRow(BaseModel):
    row_number: int
    data: dict[str, Any]
    errors: list[ImportRowIssue] = Field(default_factory=list)
    warnings: list[ImportRowIssue] = Field(default_factory=list)


class ImportPreviewResponse(BaseModel):
    total_rows: int
    valid_rows: int
    invalid_rows: int
    rows: list[ImportPreviewRow]
    errors: list[ImportRowIssue] = Field(default_factory=list)


class ImportConfirmResponse(BaseModel):
    imported_count: int
    skipped_count: int
    errors: list[ImportRowIssue] = Field(default_factory=list)

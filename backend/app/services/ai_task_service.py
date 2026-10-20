from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models import AITask

_MAX_AUDIT_STRING_LENGTH = 512
_MAX_AUDIT_LIST_ITEMS = 20
_AUDIT_FIELD_ALLOWLIST = frozenset(
    {
        "model",
        "title",
        "subtitle",
        "author",
        "translator",
        "publisher",
        "publish_year",
        "isbn",
        "language",
        "pages",
        "summary",
        "author_intro",
        "binding",
        "series",
        "note",
        "category_name",
        "existing_tags",
        "current",
        "candidates",
        "missing_fields",
        "raw_summary",
        "raw_author_intro",
        "first",
        "second",
        "query",
        "source",
        "source_id",
        "hostname",
    }
)


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def sanitize_ai_task_input(input_data: dict[str, Any]) -> dict[str, Any]:
    return {
        key: sanitized
        for key, value in input_data.items()
        if key in _AUDIT_FIELD_ALLOWLIST
        and (sanitized := _sanitize_audit_value(value)) is not None
    }


def _sanitize_audit_value(value: Any) -> Any:
    if isinstance(value, str):
        return value[:_MAX_AUDIT_STRING_LENGTH]
    if isinstance(value, bool) or value is None or isinstance(value, (int, float)):
        return value
    if isinstance(value, list):
        return [
            sanitized
            for item in value[:_MAX_AUDIT_LIST_ITEMS]
            if (sanitized := _sanitize_audit_value(item)) is not None
        ]
    if isinstance(value, dict):
        return sanitize_ai_task_input(value)
    return None


def create_ai_task(
    db: Session,
    *,
    task_type: str,
    model: str | None,
    input_data: dict[str, Any],
    status: str,
    output_data: dict[str, Any] | None = None,
    error_message: str | None = None,
    created_by: int | None = None,
) -> AITask:
    now = _now()
    task = AITask(
        task_type=task_type,
        model=model,
        input_data=json.dumps(sanitize_ai_task_input(input_data), ensure_ascii=False),
        output_data=json.dumps(output_data, ensure_ascii=False, default=str) if output_data is not None else None,
        status=status,
        error_message=error_message,
        created_by=created_by,
        created_at=now,
        updated_at=now,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task

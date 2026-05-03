from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models import AITask


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


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
        input_data=json.dumps(input_data, ensure_ascii=False, default=str),
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

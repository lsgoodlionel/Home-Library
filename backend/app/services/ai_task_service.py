from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models import AITask

_MAX_AUDIT_STRING_LENGTH = 512
_MAX_AUDIT_LIST_ITEMS = 20
_MAX_AUDIT_DEPTH = 6
_MAX_AUDIT_NODES = 256
_MAX_AUDIT_JSON_BYTES = 16_384
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


@dataclass
class _AuditSanitizeState:
    nodes: int = 0
    active_container_ids: set[int] = field(default_factory=set)


def sanitize_ai_task_input(input_data: dict[str, Any]) -> dict[str, Any]:
    sanitized = _sanitize_audit_value(input_data, _AuditSanitizeState(), depth=0)
    result = sanitized if isinstance(sanitized, dict) else {}
    _bound_audit_json_size(result)
    return result


def _sanitize_audit_value(
    value: Any,
    state: _AuditSanitizeState,
    *,
    depth: int,
) -> Any:
    if depth > _MAX_AUDIT_DEPTH or state.nodes >= _MAX_AUDIT_NODES:
        return None
    state.nodes += 1

    if isinstance(value, str):
        return value[:_MAX_AUDIT_STRING_LENGTH]
    if isinstance(value, bool) or value is None or isinstance(value, (int, float)):
        return value
    if not isinstance(value, (dict, list)):
        return None

    container_id = id(value)
    if container_id in state.active_container_ids:
        return None
    state.active_container_ids.add(container_id)
    try:
        if isinstance(value, list):
            sanitized_list: list[Any] = []
            for item in value[:_MAX_AUDIT_LIST_ITEMS]:
                sanitized = _sanitize_audit_value(item, state, depth=depth + 1)
                if sanitized is not None:
                    sanitized_list.append(sanitized)
            return sanitized_list

        sanitized_dict: dict[str, Any] = {}
        for key, item in value.items():
            if key not in _AUDIT_FIELD_ALLOWLIST:
                continue
            sanitized = _sanitize_audit_value(item, state, depth=depth + 1)
            if sanitized is not None:
                sanitized_dict[key] = sanitized
        return sanitized_dict
    finally:
        state.active_container_ids.remove(container_id)


def _bound_audit_json_size(value: dict[str, Any]) -> None:
    while _audit_json_size(value) > _MAX_AUDIT_JSON_BYTES:
        excess = _audit_json_size(value) - _MAX_AUDIT_JSON_BYTES
        if _truncate_longest_string(value, excess):
            continue
        if _drop_largest_list_tail(value):
            continue
        if _drop_last_mapping_value(value, is_root=True):
            continue
        value.clear()
        return


def _audit_json_size(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def _truncate_longest_string(value: Any, excess_bytes: int) -> bool:
    candidate: tuple[Any, str | int, str] | None = None

    def visit(current: Any) -> None:
        nonlocal candidate
        if isinstance(current, dict):
            items = current.items()
        elif isinstance(current, list):
            items = enumerate(current)
        else:
            return
        for key, item in items:
            if isinstance(item, str) and len(item) > 32:
                if candidate is None or len(item) > len(candidate[2]):
                    candidate = (current, key, item)
            elif isinstance(item, (dict, list)):
                visit(item)

    visit(value)
    if candidate is None:
        return False
    parent, key, text = candidate
    chars_to_remove = max(1, min(len(text) - 32, (excess_bytes + 2) // 3))
    parent[key] = text[: len(text) - chars_to_remove]
    return True


def _drop_largest_list_tail(value: Any) -> bool:
    candidate: list[Any] | None = None

    def visit(current: Any) -> None:
        nonlocal candidate
        if isinstance(current, list):
            if current and (candidate is None or _audit_json_size(current[-1]) > _audit_json_size(candidate[-1])):
                candidate = current
            for item in current:
                visit(item)
        elif isinstance(current, dict):
            for item in current.values():
                visit(item)

    visit(value)
    if candidate is None:
        return False
    candidate.pop()
    return True


def _drop_last_mapping_value(value: Any, *, is_root: bool = False) -> bool:
    if isinstance(value, list):
        for item in reversed(value):
            if _drop_last_mapping_value(item):
                return True
        return False
    if not isinstance(value, dict):
        return False
    for item in reversed(list(value.values())):
        if _drop_last_mapping_value(item):
            return True
    protected = {"title", "model", "hostname"} if is_root else set()
    for key in reversed(list(value)):
        if key not in protected:
            del value[key]
            return True
    return False


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

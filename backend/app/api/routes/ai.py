from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ApiError
from app.db.session import get_db
from app.schemas.ai import (
    ClassifyBookRequest,
    ClassifyBookResponse,
    DetectDuplicateRequest,
    DetectDuplicateResponse,
    GenerateTagsRequest,
    GenerateTagsResponse,
    NaturalSearchRequest,
    NaturalSearchResponse,
    OllamaModelsResponse,
    SummarizeBookRequest,
    SummarizeBookResponse,
)
from app.services.ai_task_service import create_ai_task
from app.services.ollama_service import (
    OllamaInvalidJSONError,
    OllamaService,
    OllamaServiceError,
    OllamaUnavailableError,
    OllamaValidationError,
    load_prompt_template,
)

router = APIRouter(prefix="/ai", tags=["ai"])


def _model_name(requested_model: str | None) -> str:
    return requested_model or get_settings().ollama_default_model


def _clean_text(value: str | None) -> str:
    return value.strip() if value else ""


def _dump(value: Any) -> str:
    if isinstance(value, BaseModel):
        return json.dumps(value.model_dump(exclude_none=True), ensure_ascii=False, indent=2)
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


def _ai_error_from_ollama(exc: OllamaServiceError) -> ApiError:
    if isinstance(exc, OllamaUnavailableError):
        return ApiError("AI_SERVICE_UNAVAILABLE", str(exc), status_code=503)
    if isinstance(exc, (OllamaInvalidJSONError, OllamaValidationError)):
        return ApiError("EXTERNAL_SERVICE_ERROR", str(exc), status_code=502)
    return ApiError("EXTERNAL_SERVICE_ERROR", "AI 服务调用失败", status_code=502)


def _record_failure_and_raise(
    db: Session,
    *,
    task_type: str,
    model: str | None,
    input_data: dict[str, Any],
    exc: OllamaServiceError,
) -> None:
    create_ai_task(
        db,
        task_type=task_type,
        model=model,
        input_data=input_data,
        status="failed",
        error_message=str(exc),
    )
    raise _ai_error_from_ollama(exc)


def _run_json_task(
    db: Session,
    *,
    task_type: str,
    model: str,
    input_data: dict[str, Any],
    prompt: str,
    response_model: type[BaseModel],
) -> BaseModel:
    service = OllamaService()
    try:
        result = service.generate_json(prompt=prompt, response_model=response_model, model=model)
    except OllamaServiceError as exc:
        _record_failure_and_raise(db, task_type=task_type, model=model, input_data=input_data, exc=exc)

    output_data = result.model_dump(mode="json")
    create_ai_task(
        db,
        task_type=task_type,
        model=model,
        input_data=input_data,
        output_data=output_data,
        status="success",
    )
    return result


@router.get("/models", response_model=OllamaModelsResponse)
def list_models(db: Annotated[Session, Depends(get_db)]) -> OllamaModelsResponse:
    input_data = {"base_url": get_settings().ollama_base_url}
    service = OllamaService()
    try:
        result = service.list_models()
    except OllamaServiceError as exc:
        _record_failure_and_raise(db, task_type="models", model=None, input_data=input_data, exc=exc)

    create_ai_task(
        db,
        task_type="models",
        model=None,
        input_data=input_data,
        output_data=result.model_dump(mode="json"),
        status="success",
    )
    return result


@router.post("/classify-book", response_model=ClassifyBookResponse)
def classify_book(
    payload: ClassifyBookRequest,
    db: Annotated[Session, Depends(get_db)],
) -> ClassifyBookResponse:
    model = _model_name(payload.model)
    input_data = payload.model_dump(mode="json")
    prompt = load_prompt_template("classify_book.txt").format(
        title=payload.title,
        author=_clean_text(payload.author),
        publisher=_clean_text(payload.publisher),
        summary=_clean_text(payload.summary),
    )
    return _run_json_task(
        db,
        task_type="classify_book",
        model=model,
        input_data=input_data,
        prompt=prompt,
        response_model=ClassifyBookResponse,
    )


@router.post("/generate-tags", response_model=GenerateTagsResponse)
def generate_tags(
    payload: GenerateTagsRequest,
    db: Annotated[Session, Depends(get_db)],
) -> GenerateTagsResponse:
    model = _model_name(payload.model)
    input_data = payload.model_dump(mode="json")
    prompt = load_prompt_template("generate_tags.txt").format(
        title=payload.title,
        author=_clean_text(payload.author),
        publisher=_clean_text(payload.publisher),
        category_name=_clean_text(payload.category_name),
        summary=_clean_text(payload.summary),
        existing_tags=", ".join(payload.existing_tags),
    )
    return _run_json_task(
        db,
        task_type="generate_tags",
        model=model,
        input_data=input_data,
        prompt=prompt,
        response_model=GenerateTagsResponse,
    )


@router.post("/summarize-book", response_model=SummarizeBookResponse)
def summarize_book(
    payload: SummarizeBookRequest,
    db: Annotated[Session, Depends(get_db)],
) -> SummarizeBookResponse:
    model = _model_name(payload.model)
    input_data = payload.model_dump(mode="json")
    prompt = load_prompt_template("summarize_book.txt").format(
        title=payload.title,
        author=_clean_text(payload.author),
        publisher=_clean_text(payload.publisher),
        raw_summary=_clean_text(payload.raw_summary),
        raw_author_intro=_clean_text(payload.raw_author_intro),
    )
    return _run_json_task(
        db,
        task_type="summarize_book",
        model=model,
        input_data=input_data,
        prompt=prompt,
        response_model=SummarizeBookResponse,
    )


@router.post("/detect-duplicate", response_model=DetectDuplicateResponse)
def detect_duplicate(
    payload: DetectDuplicateRequest,
    db: Annotated[Session, Depends(get_db)],
) -> DetectDuplicateResponse:
    model = _model_name(payload.model)
    input_data = payload.model_dump(mode="json")
    prompt = load_prompt_template("detect_duplicate.txt").format(
        first=_dump(payload.first),
        second=_dump(payload.second),
    )
    return _run_json_task(
        db,
        task_type="detect_duplicate",
        model=model,
        input_data=input_data,
        prompt=prompt,
        response_model=DetectDuplicateResponse,
    )


@router.post("/natural-search", response_model=NaturalSearchResponse)
def natural_search(
    payload: NaturalSearchRequest,
    db: Annotated[Session, Depends(get_db)],
) -> NaturalSearchResponse:
    model = _model_name(payload.model)
    input_data = payload.model_dump(mode="json")
    prompt = load_prompt_template("natural_search.txt").format(query=payload.query)
    return _run_json_task(
        db,
        task_type="natural_search",
        model=model,
        input_data=input_data,
        prompt=prompt,
        response_model=NaturalSearchResponse,
    )

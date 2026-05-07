from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.core.security import get_current_user, get_optional_current_user
from app.db.session import get_db
from app.models.user import User
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
    RecommendBookContentRequest,
    RecommendBookContentResponse,
    SummarizeBookRequest,
    SummarizeBookResponse,
)
from app.schemas.ai_setting import AISettingsResponse, AISettingsUpdate
from app.services.ai_setting_service import (
    get_effective_ai_settings,
    get_ollama_runtime_config,
    update_user_ai_settings,
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


def _model_name(requested_model: str | None, default_model: str) -> str:
    return requested_model or default_model


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
    created_by: int | None = None,
) -> None:
    create_ai_task(
        db,
        task_type=task_type,
        model=model,
        input_data=input_data,
        status="failed",
        error_message=str(exc),
        created_by=created_by,
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
    base_url: str,
    created_by: int | None = None,
) -> BaseModel:
    service = OllamaService(base_url=base_url, default_model=model)
    try:
        result = service.generate_json(prompt=prompt, response_model=response_model, model=model)
    except OllamaServiceError as exc:
        _record_failure_and_raise(
            db,
            task_type=task_type,
            model=model,
            input_data=input_data,
            exc=exc,
            created_by=created_by,
        )

    output_data = result.model_dump(mode="json")
    create_ai_task(
        db,
        task_type=task_type,
        model=model,
        input_data=input_data,
        output_data=output_data,
        status="success",
        created_by=created_by,
    )
    return result


@router.get("/config", response_model=AISettingsResponse)
def get_ai_config(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> AISettingsResponse:
    return get_effective_ai_settings(db, current_user)


@router.put("/config", response_model=AISettingsResponse)
def update_ai_config(
    payload: AISettingsUpdate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> AISettingsResponse:
    return update_user_ai_settings(db, current_user, payload)


@router.get("/models", response_model=OllamaModelsResponse)
def list_models(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User | None, Depends(get_optional_current_user)],
) -> OllamaModelsResponse:
    base_url, default_model = get_ollama_runtime_config(db, current_user)
    input_data = {"base_url": base_url}
    service = OllamaService(base_url=base_url, default_model=default_model)
    try:
        result = service.list_models()
    except OllamaServiceError as exc:
        _record_failure_and_raise(
            db,
            task_type="models",
            model=None,
            input_data=input_data,
            exc=exc,
            created_by=current_user.id if current_user else None,
        )

    create_ai_task(
        db,
        task_type="models",
        model=None,
        input_data=input_data,
        output_data=result.model_dump(mode="json"),
        status="success",
        created_by=current_user.id if current_user else None,
    )
    return result


@router.post("/classify-book", response_model=ClassifyBookResponse)
def classify_book(
    payload: ClassifyBookRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User | None, Depends(get_optional_current_user)],
) -> ClassifyBookResponse:
    base_url, default_model = get_ollama_runtime_config(db, current_user)
    model = _model_name(payload.model, default_model)
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
        base_url=base_url,
        created_by=current_user.id if current_user else None,
    )


@router.post("/generate-tags", response_model=GenerateTagsResponse)
def generate_tags(
    payload: GenerateTagsRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User | None, Depends(get_optional_current_user)],
) -> GenerateTagsResponse:
    base_url, default_model = get_ollama_runtime_config(db, current_user)
    model = _model_name(payload.model, default_model)
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
        base_url=base_url,
        created_by=current_user.id if current_user else None,
    )


@router.post("/recommend-book-content", response_model=RecommendBookContentResponse)
def recommend_book_content(
    payload: RecommendBookContentRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User | None, Depends(get_optional_current_user)],
) -> RecommendBookContentResponse:
    base_url, default_model = get_ollama_runtime_config(db, current_user)
    model = _model_name(payload.model, default_model)
    input_data = payload.model_dump(mode="json")
    prompt = load_prompt_template("recommend_book_content.txt").format(
        current=_dump(payload.current),
        candidates=_dump(payload.candidates),
        missing_fields=", ".join(payload.missing_fields),
    )
    return _run_json_task(
        db,
        task_type="recommend_book_content",
        model=model,
        input_data=input_data,
        prompt=prompt,
        response_model=RecommendBookContentResponse,
        base_url=base_url,
        created_by=current_user.id if current_user else None,
    )


@router.post("/summarize-book", response_model=SummarizeBookResponse)
def summarize_book(
    payload: SummarizeBookRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User | None, Depends(get_optional_current_user)],
) -> SummarizeBookResponse:
    base_url, default_model = get_ollama_runtime_config(db, current_user)
    model = _model_name(payload.model, default_model)
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
        base_url=base_url,
        created_by=current_user.id if current_user else None,
    )


@router.post("/detect-duplicate", response_model=DetectDuplicateResponse)
def detect_duplicate(
    payload: DetectDuplicateRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User | None, Depends(get_optional_current_user)],
) -> DetectDuplicateResponse:
    base_url, default_model = get_ollama_runtime_config(db, current_user)
    model = _model_name(payload.model, default_model)
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
        base_url=base_url,
        created_by=current_user.id if current_user else None,
    )


@router.post("/natural-search", response_model=NaturalSearchResponse)
def natural_search(
    payload: NaturalSearchRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User | None, Depends(get_optional_current_user)],
) -> NaturalSearchResponse:
    base_url, default_model = get_ollama_runtime_config(db, current_user)
    model = _model_name(payload.model, default_model)
    input_data = payload.model_dump(mode="json")
    prompt = load_prompt_template("natural_search.txt").format(query=payload.query)
    return _run_json_task(
        db,
        task_type="natural_search",
        model=model,
        input_data=input_data,
        prompt=prompt,
        response_model=NaturalSearchResponse,
        base_url=base_url,
        created_by=current_user.id if current_user else None,
    )

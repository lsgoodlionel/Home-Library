from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Annotated, Any
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.core.security import get_current_user, get_optional_current_user, require_admin
from app.db.session import get_db
from app.models import Category
from app.models.user import User
from app.schemas.ai import (
    AIConnectionTestRequest,
    AIHealthResponse,
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
from app.services.ollama_client import (
    OllamaAccessDeniedError,
    OllamaClient,
    OllamaClientError,
    OllamaConnectTimeoutError,
    OllamaDisabledError,
    OllamaModelError,
    OllamaReadTimeoutError,
    OllamaResponseInvalidError,
    OllamaTunnelError,
    OllamaUpstreamError,
)
from app.services.ollama_service import (
    OllamaInvalidJSONError,
    OllamaService,
    OllamaServiceError,
    OllamaUnavailableError,
    OllamaValidationError,
    load_prompt_template,
)

router = APIRouter(prefix="/ai", tags=["ai"])
_last_health_status = AIHealthResponse()
_MAX_STATUS_TEXT_LENGTH = 256


def _model_name(requested_model: str | None, default_model: str) -> str:
    return requested_model or default_model


def _clean_text(value: str | None) -> str:
    return value.strip() if value else ""


def _format_categories_for_prompt(db: Session) -> str:
    """从数据库读取 L1+L2 分类（约 235 条），格式化为提示词注入文本。
    仅注入前两层以控制提示词长度，避免超出小模型上下文窗口。
    """
    # 取所有分类，内存中过滤 L1（parent_id=None）和 L2（父是 L1）
    all_cats = db.query(Category).order_by(Category.code).all()
    l1_ids = {c.id for c in all_cats if c.parent_id is None}
    filtered = [
        c for c in all_cats
        if c.parent_id is None or c.parent_id in l1_ids
    ]
    return "\n".join(f"{c.code}: {c.name}" for c in filtered)


def _dump(value: Any) -> str:
    if isinstance(value, BaseModel):
        return json.dumps(value.model_dump(exclude_none=True), ensure_ascii=False, indent=2)
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


def _ai_error_from_ollama(
    exc: OllamaServiceError | OllamaClientError,
    *,
    hostname: str | None = None,
) -> ApiError:
    if isinstance(exc, OllamaUnavailableError):
        return ApiError("AI_SERVICE_UNAVAILABLE", str(exc), status_code=503)
    if isinstance(exc, (OllamaInvalidJSONError, OllamaValidationError)):
        return ApiError("EXTERNAL_SERVICE_ERROR", str(exc), status_code=502)
    mappings: tuple[tuple[type[OllamaClientError], str, str, int], ...] = (
        (OllamaDisabledError, "AI_SERVICE_DISABLED", "AI 服务尚未启用", 503),
        (
            OllamaAccessDeniedError,
            "AI_ACCESS_DENIED",
            "Cloudflare Access 凭据缺失、无效或策略不允许",
            502,
        ),
        (
            OllamaTunnelError,
            "AI_TUNNEL_UNAVAILABLE",
            "Tunnel 或远程 Ollama Origin 不可用",
            503,
        ),
        (OllamaConnectTimeoutError, "AI_CONNECT_TIMEOUT", "无法在限定时间内连接 AI 服务", 504),
        (OllamaReadTimeoutError, "AI_RESPONSE_TIMEOUT", "模型启动或生成超时", 504),
        (OllamaModelError, "AI_MODEL_ERROR", "模型配置或请求参数错误", 502),
        (OllamaUpstreamError, "AI_UPSTREAM_ERROR", "上游 AI 服务异常", 502),
        (OllamaResponseInvalidError, "AI_RESPONSE_INVALID", "模型返回内容不能安全使用", 502),
    )
    for error_type, code, message, status_code in mappings:
        if isinstance(exc, error_type):
            details: dict[str, Any] = {"category": exc.category}
            if hostname:
                details["hostname"] = hostname
            if exc.status_code is not None:
                details["status"] = exc.status_code
            return ApiError(code, message, status_code=status_code, details=details)
    return ApiError("EXTERNAL_SERVICE_ERROR", "AI 服务调用失败", status_code=502)


def _bounded_status_text(value: str | None) -> str | None:
    return value[:_MAX_STATUS_TEXT_LENGTH] if value else None


def _safe_hostname(url: str) -> str | None:
    try:
        return urlsplit(url).hostname
    except ValueError:
        return None


def _safe_runtime_status(db: Session, user: User) -> Any:
    runtime = get_effective_ai_settings(db, user).ollama_runtime
    hostname = _safe_hostname(runtime.base_url)
    safe_base_url = ""
    if hostname:
        try:
            parsed = urlsplit(runtime.base_url)
            port = f":{parsed.port}" if parsed.port is not None else ""
            safe_base_url = f"{parsed.scheme}://{hostname}{port}"
        except ValueError:
            safe_base_url = ""
    return runtime.model_copy(
        update={
            "base_url": _bounded_status_text(safe_base_url) or "",
            "default_model": _bounded_status_text(runtime.default_model) or "",
        }
    )


async def _check_ollama(
    db: Session,
    user: User,
    *,
    generate: bool,
) -> AIHealthResponse:
    global _last_health_status

    runtime = get_ollama_runtime_config(db, user)
    safe_runtime = _safe_runtime_status(db, user)
    client = OllamaClient(runtime)
    try:
        version = await client.version()
        models = await client.list_models()
        running_models = await client.running_models()
        if generate:
            await client.generate_text(prompt="请回复 OK", keep_alive=0)
    except OllamaClientError as exc:
        api_error = _ai_error_from_ollama(exc, hostname=_safe_hostname(runtime.base_url))
        _last_health_status = AIHealthResponse(
            status="error",
            message=_bounded_status_text(api_error.message) or "AI 服务检查失败",
            checked_at=datetime.now(timezone.utc),
            ollama_runtime=safe_runtime,
        )
        raise api_error

    _last_health_status = AIHealthResponse(
        status="healthy",
        message="AI 服务连接正常",
        checked_at=datetime.now(timezone.utc),
        version=_bounded_status_text(version.version),
        installed_model_count=len(models.models),
        running_model_count=len(running_models.models),
        generated=generate,
        ollama_runtime=safe_runtime,
    )
    return _last_health_status


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


@router.get("/health", response_model=AIHealthResponse)
async def get_ai_health(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    refresh: Annotated[bool, Query()] = False,
) -> AIHealthResponse:
    if not refresh:
        return _last_health_status
    return await _check_ollama(db, current_user, generate=False)


@router.post("/test-connection", response_model=AIHealthResponse)
async def test_ai_connection(
    payload: AIConnectionTestRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin)],
) -> AIHealthResponse:
    return await _check_ollama(db, current_user, generate=payload.generate)


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
    categories_text = _format_categories_for_prompt(db)
    prompt = load_prompt_template("classify_book.txt").format(
        title=payload.title,
        author=_clean_text(payload.author),
        publisher=_clean_text(payload.publisher),
        summary=_clean_text(payload.summary),
        categories=categories_text,
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

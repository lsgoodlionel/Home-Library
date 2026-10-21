from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from typing import Annotated, Any
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.core.errors import ApiError
from app.core.ollama_url import InvalidOllamaBaseURL, normalize_ollama_base_url
from app.core.security import get_current_user, require_admin
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
from app.schemas.ai_provider import AIProviderStatusResponse
from app.schemas.ai_setting import AISettingsResponse, AISettingsUpdate, OllamaRuntimeStatus
from app.services.ai_setting_service import (
    OllamaRuntimeConfig,
    get_effective_ai_settings,
    get_ollama_runtime_config,
    get_server_ollama_runtime_config,
    normalize_access_origin,
    update_user_ai_settings,
)
from app.services.ai_health_status_cache import ai_health_status_cache as _health_status_cache
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
from app.services.ollama_service import load_prompt_template

router = APIRouter(prefix="/ai", tags=["ai"])
_MAX_STATUS_TEXT_LENGTH = 256


@dataclass(frozen=True, slots=True)
class _SafeApiFailure:
    error: ApiError


@dataclass(frozen=True, slots=True)
class _SafeHealthCancellation:
    pass


_HEALTH_CANCELLED = _SafeHealthCancellation()


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
    exc: OllamaClientError,
    *,
    hostname: str | None = None,
) -> ApiError:
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
            if exc.reason:
                details["reason"] = exc.reason
            if isinstance(exc, OllamaUpstreamError):
                if exc.status_code is not None:
                    message = f"上游 AI 服务返回 HTTP {exc.status_code}"
                elif exc.reason == "connection_failed":
                    message = "未收到上游 HTTP 响应，无法建立连接"
                elif exc.reason == "request_failed":
                    message = "上游 AI 请求在传输过程中失败"
                if hostname:
                    message = f"{message}（{hostname}）"
            return ApiError(code, message, status_code=status_code, details=details)
    return ApiError("EXTERNAL_SERVICE_ERROR", "AI 服务调用失败", status_code=502)


def _raise_api_error(error: ApiError) -> None:
    raise error from None


def _bounded_status_text(value: str | None) -> str | None:
    return value[:_MAX_STATUS_TEXT_LENGTH] if value else None


def _safe_hostname(url: str) -> str | None:
    try:
        return urlsplit(normalize_ollama_base_url(url)).hostname
    except (InvalidOllamaBaseURL, ValueError):
        return None


def _safe_runtime_status(runtime: OllamaRuntimeConfig) -> OllamaRuntimeStatus:
    safe_base_url = ""
    try:
        safe_base_url = normalize_ollama_base_url(runtime.base_url).rstrip("/")
    except (InvalidOllamaBaseURL, ValueError):
        safe_base_url = ""
    access_configured = bool(runtime.access_client_id and runtime.access_client_secret)
    trusted_origin = normalize_access_origin(runtime.trusted_base_url)
    return OllamaRuntimeStatus(
        enabled=runtime.enabled,
        base_url=_bounded_status_text(safe_base_url) or "",
        default_model=_bounded_status_text(runtime.default_model) or "",
        connect_timeout_seconds=runtime.connect_timeout_seconds,
        read_timeout_seconds=runtime.read_timeout_seconds,
        verify_tls=runtime.verify_tls,
        access_configured=access_configured,
        uses_access=(
            access_configured
            and trusted_origin is not None
            and normalize_access_origin(runtime.base_url) == trusted_origin
        ),
    )


def _load_health_context(
    db: Session,
    user: User,
    *,
    server_only: bool = False,
) -> tuple[OllamaRuntimeConfig, OllamaRuntimeStatus]:
    runtime = (
        get_server_ollama_runtime_config(db)
        if server_only
        else get_ollama_runtime_config(db, user)
    )
    return runtime, _safe_runtime_status(runtime)


def _runtime_fingerprint(runtime: OllamaRuntimeConfig) -> str:
    try:
        base_url = normalize_ollama_base_url(runtime.base_url).rstrip("/")
    except (InvalidOllamaBaseURL, ValueError):
        base_url = "invalid"
    payload = json.dumps(
        {
            "enabled": runtime.enabled,
            "base_url": base_url,
            "trusted_base_url": runtime.trusted_base_url,
            "default_model": runtime.default_model,
            "connect_timeout_seconds": runtime.connect_timeout_seconds,
            "read_timeout_seconds": runtime.read_timeout_seconds,
            "verify_tls": runtime.verify_tls,
            "access_client_id_digest": sha256(runtime.access_client_id.encode("utf-8")).hexdigest(),
            "access_client_secret_digest": sha256(
                runtime.access_client_secret.encode("utf-8")
            ).hexdigest(),
        },
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256(payload.encode("utf-8")).hexdigest()


def _disabled_api_error(runtime: OllamaRuntimeConfig) -> ApiError | None:
    if runtime.enabled:
        return None
    return _ai_error_from_ollama(
        OllamaDisabledError("AI service disabled"),
        hostname=_safe_hostname(runtime.base_url),
    )


def _prepare_runtime_and_template(
    db: Session,
    user: User | None,
    template_name: str,
) -> tuple[OllamaRuntimeConfig, str]:
    return get_ollama_runtime_config(db, user), load_prompt_template(template_name)


def _prepare_classify_context(
    db: Session,
    user: User | None,
) -> tuple[OllamaRuntimeConfig, str, str]:
    return (
        get_ollama_runtime_config(db, user),
        _format_categories_for_prompt(db),
        load_prompt_template("classify_book.txt"),
    )


async def _check_ollama(
    db: Session,
    user: User,
    *,
    generate: bool,
    server_only: bool = False,
) -> AIHealthResponse:
    outcome = await _check_ollama_outcome(
        db,
        user,
        generate=generate,
        server_only=server_only,
    )
    del db, user
    if outcome is _HEALTH_CANCELLED:
        # The original cancellation never crosses this safe value boundary.
        raise asyncio.CancelledError() from None
    if isinstance(outcome, _SafeApiFailure):
        _raise_api_error(outcome.error)
    return outcome


async def _check_ollama_outcome(
    db: Session,
    user: User,
    *,
    generate: bool,
    server_only: bool = False,
) -> AIHealthResponse | _SafeApiFailure | _SafeHealthCancellation:
    try:
        return await _probe_ollama_health(
            db,
            user,
            generate=generate,
            server_only=server_only,
        )
    except asyncio.CancelledError as exc:
        exc.__traceback__ = None
        exc.__cause__ = None
        exc.__context__ = None
    return _HEALTH_CANCELLED


async def _drain_health_probes(
    group: asyncio.Future[Any],
    tasks: list[asyncio.Task[Any]],
) -> bool:
    for task in tasks:
        if not task.done():
            task.cancel()
    drain = asyncio.gather(group, *tasks, return_exceptions=True)
    cancelled = False
    while True:
        try:
            # Repeated owner cancellation must not cancel child cleanup.
            await asyncio.shield(drain)
            return cancelled
        except asyncio.CancelledError:
            cancelled = True


async def _probe_ollama_health(
    db: Session,
    user: User,
    *,
    generate: bool,
    server_only: bool = False,
) -> AIHealthResponse | _SafeApiFailure:
    if server_only:
        runtime, safe_runtime = await run_in_threadpool(
            _load_health_context,
            db,
            user,
            server_only=True,
        )
    else:
        runtime, safe_runtime = await run_in_threadpool(_load_health_context, db, user)
    fingerprint = _runtime_fingerprint(runtime)
    disabled_error = _disabled_api_error(runtime)
    if disabled_error is not None:
        status = AIHealthResponse(
            status="error",
            message=_bounded_status_text(disabled_error.message) or "AI 服务尚未启用",
            checked_at=datetime.now(timezone.utc),
            ollama_runtime=safe_runtime,
        )
        _health_status_cache.put(user.id, fingerprint, status)
        return _SafeApiFailure(disabled_error)
    client = OllamaClient(runtime)
    api_error: ApiError | None = None
    try:
        probes = [
            client.version(),
            client.list_models(),
            client.running_models(),
        ]
        if generate:
            probes.append(client.generate_text(prompt="请回复 OK", keep_alive=0))
        probe_tasks = [asyncio.create_task(probe) for probe in probes]
        probe_group = asyncio.gather(*probe_tasks)
        try:
            # Own cancellation here so a failing child cleanup cannot replace
            # the caller's cancellation with an upstream error.
            version, models, running_models, *_ = await asyncio.shield(probe_group)
        finally:
            cancelled_during_drain = await _drain_health_probes(probe_group, probe_tasks)
            # Completed tasks can retain cancellation tracebacks containing
            # client credentials. Drop every probe handle before raising.
            del probes, probe_tasks, probe_group
            if cancelled_during_drain:
                raise asyncio.CancelledError() from None
    except OllamaClientError as exc:
        api_error = _ai_error_from_ollama(exc, hostname=_safe_hostname(runtime.base_url))
        status = AIHealthResponse(
            status="error",
            message=_bounded_status_text(api_error.message) or "AI 服务检查失败",
            checked_at=datetime.now(timezone.utc),
            ollama_runtime=safe_runtime,
        )
        _health_status_cache.put(user.id, fingerprint, status)
        exc.__traceback__ = None
        exc.__cause__ = None
        exc.__context__ = None

    if api_error is not None:
        del client, runtime, safe_runtime, fingerprint, db, user
        return _SafeApiFailure(api_error)

    status = AIHealthResponse(
        status="healthy",
        message="AI 服务连接正常",
        checked_at=datetime.now(timezone.utc),
        version=_bounded_status_text(version.version),
        installed_model_count=len(models.models),
        running_model_count=len(running_models.models),
        generated=generate,
        ollama_runtime=safe_runtime,
    )
    _health_status_cache.put(user.id, fingerprint, status)
    return status


def _record_failure(
    db: Session,
    *,
    task_type: str,
    model: str | None,
    input_data: dict[str, Any],
    exc: OllamaClientError,
    created_by: int | None = None,
) -> None:
    create_ai_task(
        db,
        task_type=task_type,
        model=model,
        input_data=input_data,
        status="failed",
        error_message=exc.category,
        created_by=created_by,
    )


async def _run_json_task(
    db: Session,
    *,
    task_type: str,
    model: str,
    input_data: dict[str, Any],
    prompt: str,
    response_model: type[BaseModel],
    runtime: OllamaRuntimeConfig,
    created_by: int | None = None,
) -> BaseModel | _SafeApiFailure:
    disabled_error = _disabled_api_error(runtime)
    if disabled_error is not None:
        await run_in_threadpool(
            _record_failure,
            db,
            task_type=task_type,
            model=model,
            input_data=input_data,
            exc=OllamaDisabledError("AI service disabled"),
            created_by=created_by,
        )
        return _SafeApiFailure(disabled_error)
    client = OllamaClient(runtime)
    api_error: ApiError | None = None
    try:
        result = await client.generate_json(prompt=prompt, response_model=response_model, model=model)
    except OllamaClientError as exc:
        await run_in_threadpool(
            _record_failure,
            db,
            task_type=task_type,
            model=model,
            input_data=input_data,
            exc=exc,
            created_by=created_by,
        )
        api_error = _ai_error_from_ollama(exc, hostname=_safe_hostname(runtime.base_url))
        exc.__traceback__ = None
        exc.__cause__ = None
        exc.__context__ = None

    if api_error is not None:
        del client, db, input_data, prompt, response_model, runtime
        return _SafeApiFailure(api_error)

    output_data = result.model_dump(mode="json")
    await run_in_threadpool(
        create_ai_task,
        db,
        task_type=task_type,
        model=model,
        input_data=input_data,
        output_data=output_data,
        status="success",
        created_by=created_by,
    )
    return result


@router.get("/health", response_model=AIProviderStatusResponse)
async def get_ai_health(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    refresh: Annotated[bool, Query()] = False,
) -> AIProviderStatusResponse:
    from app.api.routes.ai_providers import get_active_provider_health

    return await get_active_provider_health(db, current_user, refresh=refresh)


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
    response = update_user_ai_settings(db, current_user, payload)
    _health_status_cache.invalidate_user(current_user.id)
    from app.services.ai_health_status_cache import provider_health_cache

    provider_health_cache.invalidate_user(current_user.id)
    return response


@router.get("/models", response_model=OllamaModelsResponse)
async def list_models(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> OllamaModelsResponse:
    from app.api.routes.ai_providers import list_active_provider_models_compatibility

    operation = list_active_provider_models_compatibility(db, current_user)
    del db, current_user
    return await operation


async def _list_models_for_runtime(
    db: Session,
    current_user: User,
    runtime: OllamaRuntimeConfig,
) -> OllamaModelsResponse:
    input_data = {"hostname": _safe_hostname(runtime.base_url)}
    disabled_error = _disabled_api_error(runtime)
    if disabled_error is not None:
        await run_in_threadpool(
            _record_failure,
            db,
            task_type="models",
            model=None,
            input_data=input_data,
            exc=OllamaDisabledError("AI service disabled"),
            created_by=current_user.id,
        )
        del runtime, input_data, db, current_user
        _raise_api_error(disabled_error)
    client = OllamaClient(runtime)
    api_error: ApiError | None = None
    try:
        result = await client.list_models()
    except OllamaClientError as exc:
        await run_in_threadpool(
            _record_failure,
            db,
            task_type="models",
            model=None,
            input_data=input_data,
            exc=exc,
            created_by=current_user.id,
        )
        api_error = _ai_error_from_ollama(exc, hostname=_safe_hostname(runtime.base_url))
        exc.__traceback__ = None
        exc.__cause__ = None
        exc.__context__ = None

    if api_error is not None:
        del client, runtime, input_data, db, current_user
        _raise_api_error(api_error)

    await run_in_threadpool(
        create_ai_task,
        db,
        task_type="models",
        model=None,
        input_data=input_data,
        output_data=result.model_dump(mode="json"),
        status="success",
        created_by=current_user.id,
    )
    return result


@router.post("/classify-book", response_model=ClassifyBookResponse)
async def classify_book(
    payload: ClassifyBookRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ClassifyBookResponse:
    runtime, categories_text, template = await run_in_threadpool(
        _prepare_classify_context,
        db,
        current_user,
    )
    model = _model_name(payload.model, runtime.default_model)
    input_data = payload.model_dump(mode="json")
    prompt = template.format(
        title=payload.title,
        author=_clean_text(payload.author),
        publisher=_clean_text(payload.publisher),
        summary=_clean_text(payload.summary),
        categories=categories_text,
    )
    outcome = await _run_json_task(
        db,
        task_type="classify_book",
        model=model,
        input_data=input_data,
        prompt=prompt,
        response_model=ClassifyBookResponse,
        runtime=runtime,
        created_by=current_user.id,
    )
    if isinstance(outcome, _SafeApiFailure):
        del payload, db, current_user, runtime, categories_text, template, model, input_data, prompt
        _raise_api_error(outcome.error)
    return outcome


@router.post("/generate-tags", response_model=GenerateTagsResponse)
async def generate_tags(
    payload: GenerateTagsRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> GenerateTagsResponse:
    runtime, template = await run_in_threadpool(
        _prepare_runtime_and_template,
        db,
        current_user,
        "generate_tags.txt",
    )
    model = _model_name(payload.model, runtime.default_model)
    input_data = payload.model_dump(mode="json")
    prompt = template.format(
        title=payload.title,
        author=_clean_text(payload.author),
        publisher=_clean_text(payload.publisher),
        category_name=_clean_text(payload.category_name),
        summary=_clean_text(payload.summary),
        existing_tags=", ".join(payload.existing_tags),
    )
    outcome = await _run_json_task(
        db,
        task_type="generate_tags",
        model=model,
        input_data=input_data,
        prompt=prompt,
        response_model=GenerateTagsResponse,
        runtime=runtime,
        created_by=current_user.id,
    )
    if isinstance(outcome, _SafeApiFailure):
        del payload, db, current_user, runtime, template, model, input_data, prompt
        _raise_api_error(outcome.error)
    return outcome


@router.post("/recommend-book-content", response_model=RecommendBookContentResponse)
async def recommend_book_content(
    payload: RecommendBookContentRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> RecommendBookContentResponse:
    runtime, template = await run_in_threadpool(
        _prepare_runtime_and_template,
        db,
        current_user,
        "recommend_book_content.txt",
    )
    model = _model_name(payload.model, runtime.default_model)
    input_data = payload.model_dump(mode="json")
    prompt = template.format(
        current=_dump(payload.current),
        candidates=_dump(payload.candidates),
        missing_fields=", ".join(payload.missing_fields),
    )
    outcome = await _run_json_task(
        db,
        task_type="recommend_book_content",
        model=model,
        input_data=input_data,
        prompt=prompt,
        response_model=RecommendBookContentResponse,
        runtime=runtime,
        created_by=current_user.id,
    )
    if isinstance(outcome, _SafeApiFailure):
        del payload, db, current_user, runtime, template, model, input_data, prompt
        _raise_api_error(outcome.error)
    return outcome


@router.post("/summarize-book", response_model=SummarizeBookResponse)
async def summarize_book(
    payload: SummarizeBookRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> SummarizeBookResponse:
    runtime, template = await run_in_threadpool(
        _prepare_runtime_and_template,
        db,
        current_user,
        "summarize_book.txt",
    )
    model = _model_name(payload.model, runtime.default_model)
    input_data = payload.model_dump(mode="json")
    prompt = template.format(
        title=payload.title,
        author=_clean_text(payload.author),
        publisher=_clean_text(payload.publisher),
        raw_summary=_clean_text(payload.raw_summary),
        raw_author_intro=_clean_text(payload.raw_author_intro),
    )
    outcome = await _run_json_task(
        db,
        task_type="summarize_book",
        model=model,
        input_data=input_data,
        prompt=prompt,
        response_model=SummarizeBookResponse,
        runtime=runtime,
        created_by=current_user.id,
    )
    if isinstance(outcome, _SafeApiFailure):
        del payload, db, current_user, runtime, template, model, input_data, prompt
        _raise_api_error(outcome.error)
    return outcome


@router.post("/detect-duplicate", response_model=DetectDuplicateResponse)
async def detect_duplicate(
    payload: DetectDuplicateRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> DetectDuplicateResponse:
    runtime, template = await run_in_threadpool(
        _prepare_runtime_and_template,
        db,
        current_user,
        "detect_duplicate.txt",
    )
    model = _model_name(payload.model, runtime.default_model)
    input_data = payload.model_dump(mode="json")
    prompt = template.format(
        first=_dump(payload.first),
        second=_dump(payload.second),
    )
    outcome = await _run_json_task(
        db,
        task_type="detect_duplicate",
        model=model,
        input_data=input_data,
        prompt=prompt,
        response_model=DetectDuplicateResponse,
        runtime=runtime,
        created_by=current_user.id,
    )
    if isinstance(outcome, _SafeApiFailure):
        del payload, db, current_user, runtime, template, model, input_data, prompt
        _raise_api_error(outcome.error)
    return outcome


@router.post("/natural-search", response_model=NaturalSearchResponse)
async def natural_search(
    payload: NaturalSearchRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> NaturalSearchResponse:
    runtime, template = await run_in_threadpool(
        _prepare_runtime_and_template,
        db,
        current_user,
        "natural_search.txt",
    )
    model = _model_name(payload.model, runtime.default_model)
    input_data = payload.model_dump(mode="json")
    prompt = template.format(query=payload.query)
    outcome = await _run_json_task(
        db,
        task_type="natural_search",
        model=model,
        input_data=input_data,
        prompt=prompt,
        response_model=NaturalSearchResponse,
        runtime=runtime,
        created_by=current_user.id,
    )
    if isinstance(outcome, _SafeApiFailure):
        del payload, db, current_user, runtime, template, model, input_data, prompt
        _raise_api_error(outcome.error)
    return outcome

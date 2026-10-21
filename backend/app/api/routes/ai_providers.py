from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Awaitable, Callable, TypeVar

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.core.errors import ApiError
from app.core.security import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.ai import OllamaModel, OllamaModelsResponse
from app.schemas.ai_provider import (
    AIProviderModelResponse,
    AIProviderOperationRequest,
    AIProviderStatusResponse,
)
from app.schemas.ai_setting import AIProvider
from app.services import ai_provider_runtime as runtime_service
from app.services.ai_health_status_cache import (
    provider_health_cache,
    provider_model_cache,
)
from app.services.ai_task_service import create_ai_task
from app.services.ai_providers.base import (
    AIProviderAuthenticationError,
    AIProviderClient,
    AIProviderConnectTimeoutError,
    AIProviderDisabledError,
    AIProviderError,
    AIProviderHealth,
    AIProviderInvalidConfigurationError,
    AIProviderInvalidResponseError,
    AIProviderModelError,
    AIProviderModelList,
    AIProviderQuotaError,
    AIProviderRateLimitError,
    AIProviderReadTimeoutError,
    AIProviderRuntime,
    AIProviderUpstreamError,
    map_provider_exception,
    run_provider_operation,
)

router = APIRouter(prefix="/ai/providers", tags=["ai"])
ResultT = TypeVar("ResultT")
_GENERATION_TEST_PROMPT = "请仅回复：连接测试成功"

_ERROR_MAPPING: tuple[tuple[type[AIProviderError], str, str, int], ...] = (
    (AIProviderDisabledError, "AI_SERVICE_DISABLED", "AI 服务尚未启用", 503),
    (AIProviderInvalidConfigurationError, "AI_CONFIG_INVALID", "AI 服务配置无效", 422),
    (AIProviderAuthenticationError, "AI_ACCESS_DENIED", "AI 服务认证失败", 502),
    (AIProviderQuotaError, "AI_QUOTA_EXCEEDED", "AI 服务额度不足", 402),
    (AIProviderRateLimitError, "AI_RATE_LIMITED", "AI 服务请求过于频繁", 429),
    (AIProviderModelError, "AI_MODEL_ERROR", "模型不存在或无权访问", 502),
    (AIProviderConnectTimeoutError, "AI_CONNECT_TIMEOUT", "无法在限定时间内连接 AI 服务", 504),
    (AIProviderReadTimeoutError, "AI_RESPONSE_TIMEOUT", "模型启动或生成超时", 504),
    (AIProviderUpstreamError, "AI_UPSTREAM_ERROR", "上游 AI 服务异常", 502),
    (AIProviderInvalidResponseError, "AI_RESPONSE_INVALID", "模型返回内容不能安全使用", 502),
)


@dataclass(frozen=True, slots=True)
class _RouteFailure:
    error: ApiError


@dataclass(frozen=True, slots=True)
class _RuntimeSnapshot:
    runtime: AIProviderRuntime
    user_id: int
    use_shared_cache: bool = True


def _provider_api_error(exc: Exception, runtime: AIProviderRuntime | None = None) -> ApiError:
    del runtime
    safe = map_provider_exception(exc)
    for error_type, code, message, status_code in _ERROR_MAPPING:
        if isinstance(safe, error_type):
            details: dict[str, object] = {"category": safe.category}
            if safe.status_code is not None:
                details["status"] = safe.status_code
            if safe.reason is not None:
                details["reason"] = safe.reason
            return ApiError(code, message, status_code=status_code, details=details)
    return ApiError("AI_UPSTREAM_ERROR", "上游 AI 服务异常", 502)


def _raise_provider_api_error(exc: Exception, runtime: AIProviderRuntime | None = None) -> None:
    error = _provider_api_error(exc, runtime)
    exc.__traceback__ = None
    exc.__cause__ = None
    exc.__context__ = None
    del exc, runtime
    raise error from None


def _resolve_saved_runtime(db: Session, user: User) -> AIProviderRuntime:
    try:
        return runtime_service.resolve_ai_provider_runtime(db, user)
    except Exception as exc:
        _raise_provider_api_error(exc)


def _runtime_for_request(
    db: Session,
    user: User,
    path_provider: str,
    draft: AIProviderOperationRequest,
) -> _RuntimeSnapshot:
    try:
        if draft.provider is not None and draft.provider != path_provider:
            raise AIProviderInvalidConfigurationError()
        replacement = draft.api_key.get_secret_value() if draft.api_key is not None else None
        use_shared_cache = not replacement and draft.base_url is None and draft.model is None
        replacement = ""
        return _RuntimeSnapshot(
            runtime=runtime_service.resolve_ai_provider_operation_runtime(
                db, user, path_provider, base_url=draft.base_url, model=draft.model,
                credential=draft.api_key,
            ),
            user_id=user.id,
            use_shared_cache=use_shared_cache,
        )
    finally:
        draft.api_key = None


def _saved_runtime_snapshot(db: Session, user: User) -> _RuntimeSnapshot:
    return _RuntimeSnapshot(
        runtime=_resolve_saved_runtime(db, user),
        user_id=user.id,
    )


def _record_models_failure(db: Session, user_id: int, category: str) -> None:
    create_ai_task(
        db,
        task_type="models",
        model=None,
        input_data={},
        status="failed",
        error_message=category,
        created_by=user_id,
    )


def _client(runtime: AIProviderRuntime) -> AIProviderClient:
    try:
        return runtime_service.create_ai_provider_client(runtime)
    except Exception as exc:
        _raise_provider_api_error(exc, runtime)


async def _call(
    operation: Callable[[], Awaitable[ResultT]],
    runtime: AIProviderRuntime,
) -> ResultT:
    failure: ApiError | None = None
    try:
        return await run_provider_operation(operation)
    except Exception as exc:
        failure = _provider_api_error(exc, runtime)
        exc.__traceback__ = None
        exc.__cause__ = None
        exc.__context__ = None
    del operation, runtime
    if failure is not None:
        raise failure from None
    raise RuntimeError("provider operation completed without a result")


def _status_response(
    health: AIProviderHealth,
    *,
    models: AIProviderModelList | None = None,
    message: str | None = None,
    details: dict[str, object] | None = None,
) -> AIProviderStatusResponse:
    merged_details = dict(health.details)
    if details:
        merged_details.update(details)
    return AIProviderStatusResponse(
        provider=health.provider,  # type: ignore[arg-type]
        status=health.status,
        message=message or health.message,
        checked_at=health.checked_at,
        effective_model=health.effective_model,
        safe_base_url=health.safe_base_url,
        credential_state=health.credential_state,
        models=(
            [
                AIProviderModelResponse(
                    provider=item.provider,  # type: ignore[arg-type]
                    id=item.id,
                    name=item.name,
                )
                for item in models.models
            ]
            if models is not None
            else []
        ),
        details=merged_details,
    )


def _runtime_status(
    runtime: AIProviderRuntime,
    *,
    status: str,
    message: str,
    models: AIProviderModelList | None = None,
    details: dict[str, object] | None = None,
) -> AIProviderStatusResponse:
    health = AIProviderHealth(
        provider=runtime.provider,
        status=status,  # type: ignore[arg-type]
        message=message,
        checked_at=datetime.now(tz=UTC),
        effective_model=runtime.default_model,
        safe_base_url=runtime.base_url,
        credential_state=runtime.credential_state,
    )
    return _status_response(health, models=models, details=details)


async def test_active_provider(
    runtime: AIProviderRuntime,
    user_id: int,
    *,
    use_shared_cache: bool = True,
) -> AIProviderStatusResponse:
    health = await _call(_client(runtime).test_connection, runtime)
    response = _status_response(health)
    if use_shared_cache:
        provider_health_cache.put(
            user_id,
            runtime_service.provider_runtime_fingerprint(runtime),
            response,
        )
    return response


async def list_active_provider_models(
    runtime: AIProviderRuntime,
    user_id: int,
    *,
    use_shared_cache: bool = True,
) -> AIProviderStatusResponse:
    fingerprint = runtime_service.provider_runtime_fingerprint(runtime)
    models = (
        provider_model_cache.get(user_id, runtime.provider, fingerprint)
        if use_shared_cache
        else None
    )
    if models is None:
        models = await _call(_client(runtime).list_models, runtime)
        if use_shared_cache:
            provider_model_cache.put(user_id, runtime.provider, fingerprint, models)
    status = "available" if models.capability == "supported" else "unchecked"
    message = "模型列表获取成功" if models.capability == "supported" else "供应商不支持模型列表"
    return _runtime_status(
        runtime,
        status=status,
        message=message,
        models=models,
        details={"model_list_capability": models.capability},
    )


async def get_active_provider_health(
    db: Session,
    user: User,
    *,
    refresh: bool,
) -> AIProviderStatusResponse:
    snapshot = await run_in_threadpool(_saved_runtime_snapshot, db, user)
    del db, user
    runtime = snapshot.runtime
    fingerprint = runtime_service.provider_runtime_fingerprint(runtime)
    if refresh:
        failure: ApiError | None = None
        response: AIProviderStatusResponse | None = None
        try:
            response = await test_active_provider(runtime, snapshot.user_id)
        except ApiError as exc:
            failure = ApiError(exc.code, exc.message, exc.status_code, dict(exc.details))
            exc.__traceback__ = None
            exc.__cause__ = None
            exc.__context__ = None
        del runtime, snapshot
        if failure is not None:
            raise failure from None
        if response is None:
            raise ApiError("AI_UPSTREAM_ERROR", "上游 AI 服务异常", 502) from None
        return response
    cached = provider_health_cache.get(snapshot.user_id, fingerprint)
    if cached is not None:
        return cached
    return _runtime_status(runtime, status="unchecked", message="尚未检查").model_copy(
        update={"checked_at": None}
    )


async def list_active_provider_models_compatibility(
    db: Session,
    user: User,
) -> OllamaModelsResponse:
    runtime: AIProviderRuntime | None = None
    user_id: int | None = None
    failure: ApiError | None = None
    response: AIProviderStatusResponse | None = None
    try:
        snapshot = await run_in_threadpool(_saved_runtime_snapshot, db, user)
        runtime = snapshot.runtime
        user_id = snapshot.user_id
        del snapshot
        response = await list_active_provider_models(runtime, user_id)
    except ApiError as exc:
        failure = ApiError(exc.code, exc.message, exc.status_code, dict(exc.details))
        exc.__traceback__ = None
        exc.__cause__ = None
        exc.__context__ = None
    if failure is not None:
        category = str(failure.details.get("category") or "provider_error")
        audit_user_id = user_id if user_id is not None else user.id
        await run_in_threadpool(
            _record_models_failure,
            db,
            audit_user_id,
            category,
        )
        del runtime, response, db, user, user_id, audit_user_id, category
        raise failure from None
    if response is None:
        raise ApiError("AI_UPSTREAM_ERROR", "上游 AI 服务异常", 502) from None
    result = OllamaModelsResponse(
        models=[OllamaModel(name=item.name, model=item.id) for item in response.models]
    )
    del runtime, response, db, user
    return result


async def _provider_route_outcome(
    operation: str,
    provider: str,
    payload: AIProviderOperationRequest,
    db: Session,
    user: User,
) -> AIProviderStatusResponse | _RouteFailure:
    runtime: AIProviderRuntime | None = None
    client: AIProviderClient | None = None
    response: AIProviderStatusResponse | None = None
    failure: ApiError | None = None
    try:
        snapshot = await run_in_threadpool(
            _runtime_for_request,
            db,
            user,
            provider,
            payload,
        )
        runtime = snapshot.runtime
        user_id = snapshot.user_id
        use_shared_cache = snapshot.use_shared_cache
        del snapshot, db, user
        if operation == "test":
            response = await test_active_provider(
                runtime,
                user_id,
                use_shared_cache=use_shared_cache,
            )
        elif operation == "models":
            response = await list_active_provider_models(
                runtime,
                user_id,
                use_shared_cache=use_shared_cache,
            )
        elif operation == "generate":
            client = _client(runtime)
            generated = await _call(
                lambda: client.generate_text(_GENERATION_TEST_PROMPT, runtime.default_model),
                runtime,
            )
            del generated
            response = _runtime_status(
                runtime,
                status="available",
                message="生成测试成功",
                details={"generation_confirmed": True},
            )
        else:
            failure = _provider_api_error(AIProviderInvalidConfigurationError())
    except ApiError as exc:
        failure = ApiError(exc.code, exc.message, exc.status_code, dict(exc.details))
        exc.__traceback__ = None
        exc.__cause__ = None
        exc.__context__ = None
    except Exception as exc:
        failure = _provider_api_error(exc, runtime)
        exc.__traceback__ = None
        exc.__cause__ = None
        exc.__context__ = None
    payload.api_key = None
    del runtime, client, payload
    if failure is not None:
        return _RouteFailure(failure)
    if response is None:
        return _RouteFailure(
            ApiError("AI_UPSTREAM_ERROR", "上游 AI 服务异常", 502)
        )
    return response


def _raise_route_failure(outcome: _RouteFailure) -> None:
    error = outcome.error
    del outcome
    raise error from None


@router.post("/{provider}/test", response_model=AIProviderStatusResponse)
async def test_provider(
    provider: AIProvider,
    payload: AIProviderOperationRequest,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> AIProviderStatusResponse:
    outcome = await _provider_route_outcome("test", provider, payload, db, user)
    del provider, payload, db, user
    if isinstance(outcome, _RouteFailure):
        _raise_route_failure(outcome)
    return outcome


@router.post("/{provider}/models", response_model=AIProviderStatusResponse)
async def list_provider_models(
    provider: AIProvider,
    payload: AIProviderOperationRequest,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> AIProviderStatusResponse:
    outcome = await _provider_route_outcome("models", provider, payload, db, user)
    del provider, payload, db, user
    if isinstance(outcome, _RouteFailure):
        _raise_route_failure(outcome)
    return outcome


@router.post("/{provider}/generate-test", response_model=AIProviderStatusResponse)
async def generate_provider_test(
    provider: AIProvider,
    payload: AIProviderOperationRequest,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> AIProviderStatusResponse:
    outcome = await _provider_route_outcome("generate", provider, payload, db, user)
    del provider, payload, db, user
    if isinstance(outcome, _RouteFailure):
        _raise_route_failure(outcome)
    return outcome

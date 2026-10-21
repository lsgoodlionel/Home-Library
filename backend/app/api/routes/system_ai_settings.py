from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, Depends, Request
from sqlalchemy.orm import Session

from app.api.routes.ai import _check_ollama, _list_models_for_runtime
from app.core.errors import ApiError
from app.core.security import (
    require_admin,
    require_secure_server_config_transport,
    verify_admin_secondary_auth,
)
from app.db.session import get_db
from app.models.user import User
from app.schemas.ai import AIHealthResponse, OllamaModelsResponse
from app.schemas.system_ai_setting import (
    SystemAIConfigResetRequest,
    SystemAIConfigResponse,
    SystemAIConfigTestRequest,
    SystemAIConfigUpdateRequest,
)
from app.services.credential_crypto import CredentialCryptoError
from app.services.ai_health_status_cache import ai_health_status_cache, provider_health_cache
from app.services.ai_setting_service import get_server_ollama_runtime_config
from app.services.system_ai_setting_service import (
    ServerAIConfigConflictError,
    ServerAIConfigWriteError,
    get_effective_server_ai_config,
    reset_server_ai_config,
    update_server_ai_config,
)

router = APIRouter(prefix="/system/ai-config", tags=["system-ai-config"])


@router.get("", response_model=SystemAIConfigResponse)
def get_system_ai_config(
    db: Annotated[Session, Depends(get_db)],
    _admin: Annotated[User, Depends(require_admin)],
) -> SystemAIConfigResponse:
    return SystemAIConfigResponse.from_config(get_effective_server_ai_config(db))


@router.put("", response_model=SystemAIConfigResponse)
def put_system_ai_config(
    request: Request,
    payload: SystemAIConfigUpdateRequest,
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[User, Depends(require_admin)],
) -> SystemAIConfigResponse:
    require_secure_server_config_transport(request)
    verify_admin_secondary_auth(admin, payload.admin_password, payload.upgrade_password)
    try:
        config = update_server_ai_config(
            db,
            values=payload.update_values(),
            credentials=payload.credential_update(),
            actor_id=admin.id,
        )
    except CredentialCryptoError:
        error = ApiError(
            "AI_SERVER_CREDENTIAL_ERROR",
            "服务器密钥强度不足，不能保存凭据",
            status_code=400,
        )
    except ValueError:
        error = ApiError(
            "AI_SERVER_CONFIG_INVALID",
            "服务器 AI 配置无效",
            status_code=422,
        )
    except ServerAIConfigConflictError:
        error = ApiError(
            "AI_SERVER_CONFIG_CONFLICT",
            "服务器 AI 配置已被其他请求修改，请刷新后重试",
            status_code=409,
        )
    except ServerAIConfigWriteError:
        error = ApiError(
            "AI_SERVER_CONFIG_WRITE_FAILED",
            "服务器 AI 配置保存失败，请稍后重试",
            status_code=500,
        )
    else:
        ai_health_status_cache.invalidate_all()
        provider_health_cache.invalidate_all()
        return SystemAIConfigResponse.from_config(config)
    del request, payload, db, admin
    raise error from None


@router.delete("", response_model=SystemAIConfigResponse)
def delete_system_ai_config(
    request: Request,
    payload: SystemAIConfigResetRequest,
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[User, Depends(require_admin)],
) -> SystemAIConfigResponse:
    require_secure_server_config_transport(request)
    verify_admin_secondary_auth(admin, payload.admin_password, payload.upgrade_password)
    try:
        config = reset_server_ai_config(db, actor_id=admin.id)
    except ServerAIConfigConflictError:
        error = ApiError(
            "AI_SERVER_CONFIG_CONFLICT",
            "服务器 AI 配置已被其他请求修改，请刷新后重试",
            status_code=409,
        )
    except ServerAIConfigWriteError:
        error = ApiError(
            "AI_SERVER_CONFIG_WRITE_FAILED",
            "服务器 AI 配置恢复失败，请稍后重试",
            status_code=500,
        )
    else:
        ai_health_status_cache.invalidate_all()
        provider_health_cache.invalidate_all()
        return SystemAIConfigResponse.from_config(config)
    del request, payload, db, admin
    raise error from None


@router.post("/test", response_model=AIHealthResponse)
async def test_system_ai_config(
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[User, Depends(require_admin)],
    _payload: Annotated[SystemAIConfigTestRequest | None, Body()] = None,
) -> AIHealthResponse:
    get_effective_server_ai_config(db)
    return await _check_ollama(db, admin, generate=False, server_only=True)


@router.get("/models", response_model=OllamaModelsResponse)
async def list_system_ai_models(
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[User, Depends(require_admin)],
) -> OllamaModelsResponse:
    runtime = get_server_ollama_runtime_config(db)
    operation = _list_models_for_runtime(db, admin, runtime)
    del runtime, db, admin
    return await operation

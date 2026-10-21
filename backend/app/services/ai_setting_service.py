from __future__ import annotations

import ipaddress
import json
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.core.ollama_url import InvalidOllamaBaseURL, normalize_ollama_base_url
from app.models.user import User
from app.models.user_ai_provider_credential import UserAIProviderCredential
from app.models.user_ai_setting import UserAISetting
from app.schemas.ai_setting import AIProviderConfig, AISettingsResponse, AISettingsUpdate, OllamaRuntimeStatus
from app.services.ai_provider_credential_service import (
    ProviderCredentialState,
    _cipher as _account_credential_cipher,
    get_provider_credential_state,
)
from app.services.system_ai_setting_service import _get_effective_server_ai_state


_CLOUD_PROVIDERS = {"openai", "gemini", "deepseek", "moonshot", "qwen", "custom"}


@dataclass(frozen=True)
class OllamaRuntimeConfig:
    enabled: bool
    base_url: str
    trusted_base_url: str
    default_model: str
    connect_timeout_seconds: float
    read_timeout_seconds: float
    verify_tls: bool
    access_client_id: str
    access_client_secret: str

def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def default_provider_configs() -> dict[str, dict[str, Any]]:
    settings = get_settings()
    return {
        "ollama": {
            "provider": "ollama",
            "enabled": True,
            "base_url": settings.ollama_base_url,
            "default_model": settings.ollama_default_model,
            "note": "本地或远程 Ollama 服务，兼容现有本地模型调用。",
        },
        "openai": {
            "provider": "openai",
            "enabled": False,
            "base_url": "https://api.openai.com/v1",
            "default_model": "",
            "note": "预留 OpenAI Chat Completions / Responses API 配置。",
        },
        "gemini": {
            "provider": "gemini",
            "enabled": False,
            "base_url": "https://generativelanguage.googleapis.com",
            "default_model": "",
            "note": "预留 Google Gemini API 配置。",
        },
        "deepseek": {
            "provider": "deepseek",
            "enabled": False,
            "base_url": "https://api.deepseek.com",
            "default_model": "",
            "note": "预留 DeepSeek API 配置。",
        },
        "moonshot": {
            "provider": "moonshot",
            "enabled": False,
            "base_url": "https://api.moonshot.cn/v1",
            "default_model": "",
            "note": "预留 Kimi / Moonshot API 配置。",
        },
        "qwen": {
            "provider": "qwen",
            "enabled": False,
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "default_model": "",
            "note": "预留通义千问 DashScope OpenAI 兼容接口配置。",
        },
        "custom": {
            "provider": "custom",
            "enabled": False,
            "base_url": "",
            "default_model": "",
            "note": "预留自定义 OpenAI 兼容接口。",
        },
    }


def _decode_configs(raw: str | None) -> dict[str, dict[str, Any]]:
    configs = default_provider_configs()
    if not raw:
        return configs
    try:
        saved = json.loads(raw)
    except json.JSONDecodeError:
        return configs
    if not isinstance(saved, dict):
        return configs

    for provider, value in saved.items():
        if provider not in configs or not isinstance(value, dict):
            continue
        sanitized = {key: item for key, item in value.items() if key != "api_key"}
        configs[provider].update(sanitized)
        configs[provider]["provider"] = provider
    return configs


def _encode_configs(configs: dict[str, dict[str, Any]]) -> str:
    sanitized = {
        provider: {key: value for key, value in config.items() if key != "api_key"}
        for provider, config in configs.items()
    }
    return json.dumps(sanitized, ensure_ascii=False, sort_keys=True)


def validate_account_ai_selection(
    ai_enabled: bool,
    active_provider: str,
    configs: dict[str, dict[str, Any]],
    credential_states: dict[str, ProviderCredentialState],
) -> None:
    if not ai_enabled:
        return

    active = configs.get(active_provider)
    if active is None:
        raise ApiError("AI_CONFIG_INVALID", "当前 AI 服务商配置不存在", 422)
    if not bool(active.get("enabled")):
        raise ApiError("AI_CONFIG_INVALID", "当前 AI 服务商未启用", 422)
    if not str(active.get("default_model") or "").strip():
        raise ApiError("AI_CONFIG_INVALID", "当前 AI 服务商默认模型不能为空", 422)
    if active_provider in _CLOUD_PROVIDERS:
        state = credential_states.get(active_provider, "missing")
        if state == "missing":
            raise ApiError("AI_CONFIG_INVALID", "当前 AI 服务商 API Key 未配置", 422)
        if state == "unusable":
            raise ApiError("AI_CONFIG_INVALID", "当前 AI 服务商 API Key 不可用", 422)


def _credential_states(
    db: Session,
    user_id: int,
    configs: dict[str, dict[str, Any]],
) -> dict[str, ProviderCredentialState]:
    return {
        provider: get_provider_credential_state(db, user_id, provider)
        for provider in configs
    }


def _stage_provider_api_key(
    db: Session,
    user_id: int,
    provider: str,
    api_key: str | None,
    clear_api_key: bool,
) -> None:
    credential = db.query(UserAIProviderCredential).filter_by(
        user_id=user_id,
        provider=provider,
    ).first()
    if clear_api_key:
        if credential is not None:
            db.delete(credential)
        return
    if api_key in (None, ""):
        return

    try:
        ciphertext = _account_credential_cipher().encrypt(api_key)
    except Exception:
        raise ApiError("AI_CREDENTIAL_ERROR", "账号供应商凭据保存失败", 422) from None
    if credential is None:
        credential = UserAIProviderCredential(
            user_id=user_id,
            provider=provider,
            api_key_ciphertext=ciphertext,
        )
    else:
        credential.api_key_ciphertext = ciphertext
    db.add(credential)


def get_or_create_user_ai_setting(db: Session, user: User) -> UserAISetting:
    setting = db.query(UserAISetting).filter_by(user_id=user.id).first()
    if setting:
        return setting

    defaults = default_provider_configs()
    setting = UserAISetting(
        user_id=user.id,
        ai_enabled=True,
        active_provider="ollama",
        default_model=defaults["ollama"]["default_model"],
        provider_configs=_encode_configs(defaults),
        created_at=_now(),
        updated_at=_now(),
    )
    db.add(setting)
    db.commit()
    db.refresh(setting)
    return setting


def get_effective_ai_settings(db: Session, user: User | None) -> AISettingsResponse:
    if user is None:
        defaults = default_provider_configs()
        return _to_response(True, "ollama", defaults["ollama"]["default_model"], defaults)

    setting = db.query(UserAISetting).filter_by(user_id=user.id).first()
    if setting is None:
        defaults = default_provider_configs()
        runtime = get_ollama_runtime_config(db, user)
        defaults["ollama"]["base_url"] = runtime.base_url
        defaults["ollama"]["default_model"] = runtime.default_model
        return _to_response(
            True,
            "ollama",
            runtime.default_model,
            defaults,
            _credential_states(db, user.id, defaults),
            runtime,
        )
    runtime = get_ollama_runtime_config(db, user)
    return _to_response(
        setting.ai_enabled,
        setting.active_provider,
        setting.default_model,
        _decode_configs(setting.provider_configs),
        _credential_states(db, user.id, _decode_configs(setting.provider_configs)),
        runtime,
    )


def update_user_ai_settings(db: Session, user: User, payload: AISettingsUpdate) -> AISettingsResponse:
    setting = db.query(UserAISetting).filter_by(user_id=user.id).first()
    if setting is None:
        defaults = default_provider_configs()
        setting = UserAISetting(
            user_id=user.id,
            ai_enabled=True,
            active_provider="ollama",
            default_model=defaults["ollama"]["default_model"],
            provider_configs=_encode_configs(defaults),
            created_at=_now(),
            updated_at=_now(),
        )
        db.add(setting)
    configs = _decode_configs(setting.provider_configs)

    for incoming in payload.providers:
        current = deepcopy(configs[incoming.provider])
        current["enabled"] = incoming.enabled
        current["base_url"] = incoming.base_url
        current["default_model"] = incoming.default_model
        current["note"] = incoming.note
        configs[incoming.provider] = current

    credential_states = _credential_states(db, user.id, configs)
    for incoming in payload.providers:
        if incoming.clear_api_key:
            credential_states[incoming.provider] = "missing"
        elif incoming.api_key not in (None, ""):
            credential_states[incoming.provider] = "configured"

    validate_account_ai_selection(
        payload.ai_enabled,
        payload.active_provider,
        configs,
        credential_states,
    )
    active_model = str(configs[payload.active_provider].get("default_model") or "").strip()
    if payload.ai_enabled and payload.default_model != active_model:
        raise ApiError(
            "AI_CONFIG_INVALID",
            "账号默认模型必须与当前 AI 服务商默认模型一致",
            422,
        )

    for incoming in payload.providers:
        _stage_provider_api_key(
            db,
            user.id,
            incoming.provider,
            incoming.api_key,
            incoming.clear_api_key,
        )

    setting.ai_enabled = payload.ai_enabled
    setting.active_provider = payload.active_provider
    setting.default_model = payload.default_model
    setting.provider_configs = _encode_configs(configs)
    setting.updated_at = _now()
    db.add(setting)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise ApiError("AI_CONFIG_SAVE_FAILED", "AI 配置保存失败", 500) from None
    db.refresh(setting)
    credential_states = _credential_states(db, user.id, configs)
    return _to_response(
        setting.ai_enabled,
        setting.active_provider,
        setting.default_model,
        configs,
        credential_states,
        get_ollama_runtime_config(db, user),
    )


def get_ollama_runtime_config(db: Session, user: User | None) -> OllamaRuntimeConfig:
    server_state = _get_effective_server_ai_state(db)
    server = server_state.config
    base_url = server.default_base_url
    default_model = server.default_model
    if user is not None:
        setting = db.query(UserAISetting).filter_by(user_id=user.id).first()
        if setting is not None:
            configs = _decode_configs(setting.provider_configs)
            if setting.active_provider == "ollama":
                ollama = configs.get("ollama", {})
                base_url = str(ollama.get("base_url") or server.default_base_url)
                default_model = (
                    setting.default_model
                    or str(ollama.get("default_model") or "")
                    or server.default_model
                )
            else:
                default_model = setting.default_model or server.default_model
    return OllamaRuntimeConfig(
        enabled=server.enabled,
        base_url=base_url,
        trusted_base_url=server.trusted_base_url,
        default_model=default_model,
        connect_timeout_seconds=server.connect_timeout_seconds,
        read_timeout_seconds=server.read_timeout_seconds,
        verify_tls=server.verify_tls,
        access_client_id=server_state.client_id,
        access_client_secret=server_state.client_secret,
    )


def get_server_ollama_runtime_config(db: Session) -> OllamaRuntimeConfig:
    server_state = _get_effective_server_ai_state(db)
    server = server_state.config
    return OllamaRuntimeConfig(
        enabled=server.enabled,
        base_url=server.default_base_url,
        trusted_base_url=server.trusted_base_url,
        default_model=server.default_model,
        connect_timeout_seconds=server.connect_timeout_seconds,
        read_timeout_seconds=server.read_timeout_seconds,
        verify_tls=server.verify_tls,
        access_client_id=server_state.client_id,
        access_client_secret=server_state.client_secret,
    )


def normalize_ollama_origin(url: str) -> tuple[str, str, int | None] | None:
    try:
        parsed = httpx.URL(normalize_ollama_base_url(url))
    except (InvalidOllamaBaseURL, httpx.InvalidURL):
        return None
    port = (
        parsed.port
        if parsed.port is not None
        else {"http": 80, "https": 443}.get(parsed.scheme)
    )
    return parsed.scheme, parsed.host.lower(), port


def normalize_access_origin(url: str) -> tuple[str, str, int | None] | None:
    origin = normalize_ollama_origin(url)
    if origin is None:
        return None
    scheme, hostname, port = origin
    hostname = hostname.rstrip(".")
    if scheme != "https":
        return None
    try:
        ipaddress.ip_address(hostname)
        return None
    except ValueError:
        pass
    if (
        "." not in hostname
        or hostname == "localhost"
        or hostname == "host.docker.internal"
        or hostname.endswith(".local")
    ):
        return None
    return scheme, hostname, port


def _runtime_status(
    active_provider: str,
    default_model: str,
    configs: dict[str, dict[str, Any]],
    settings: Settings,
) -> OllamaRuntimeStatus:
    active = configs.get(active_provider)
    if active_provider != "ollama" or active is None:
        base_url = settings.ollama_base_url
        model = default_model or settings.ollama_default_model
    else:
        base_url = str(active.get("base_url") or settings.ollama_base_url)
        model = default_model or str(active.get("default_model") or settings.ollama_default_model)

    access_configured = bool(
        settings.ollama_cf_access_client_id and settings.ollama_cf_access_client_secret
    )
    trusted_origin = normalize_access_origin(settings.ollama_trusted_base_url)
    uses_access = (
        access_configured
        and trusted_origin is not None
        and normalize_access_origin(base_url) == trusted_origin
    )
    return OllamaRuntimeStatus(
        enabled=settings.ollama_enabled,
        base_url=base_url,
        default_model=model,
        connect_timeout_seconds=settings.ollama_connect_timeout_seconds,
        read_timeout_seconds=settings.ollama_read_timeout_seconds,
        verify_tls=settings.ollama_verify_tls,
        access_configured=access_configured,
        uses_access=uses_access,
    )


def _to_response(
    ai_enabled: bool,
    active_provider: str,
    default_model: str,
    configs: dict[str, dict[str, Any]],
    credential_states: dict[str, ProviderCredentialState] | None = None,
    runtime_config: OllamaRuntimeConfig | None = None,
) -> AISettingsResponse:
    settings = get_settings()
    providers: list[AIProviderConfig] = []
    for key, config in configs.items():
        providers.append(
            AIProviderConfig(
                provider=key,  # type: ignore[arg-type]
                enabled=bool(config.get("enabled")),
                base_url=str(config.get("base_url") or ""),
                default_model=str(config.get("default_model") or ""),
                note=str(config.get("note") or ""),
                credential_state=(credential_states or {}).get(key, "missing"),
            )
        )
    return AISettingsResponse(
        ai_enabled=ai_enabled,
        active_provider=active_provider,  # type: ignore[arg-type]
        default_model=default_model,
        providers=providers,
        ollama_runtime=(
            _runtime_status_from_config(runtime_config)
            if runtime_config is not None
            else _runtime_status(active_provider, default_model, configs, settings)
        ),
    )


def _runtime_status_from_config(runtime: OllamaRuntimeConfig) -> OllamaRuntimeStatus:
    access_configured = bool(runtime.access_client_id and runtime.access_client_secret)
    trusted_origin = normalize_access_origin(runtime.trusted_base_url)
    return OllamaRuntimeStatus(
        enabled=runtime.enabled,
        base_url=runtime.base_url,
        default_model=runtime.default_model,
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

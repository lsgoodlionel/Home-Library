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
from app.core.ollama_url import InvalidOllamaBaseURL, normalize_ollama_base_url
from app.models.user import User
from app.models.user_ai_setting import UserAISetting
from app.schemas.ai_setting import AIProviderConfig, AISettingsResponse, AISettingsUpdate, OllamaRuntimeStatus
from app.services.system_ai_setting_service import _get_effective_server_ai_state


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
            "api_key": "",
            "default_model": settings.ollama_default_model,
            "note": "本地或远程 Ollama 服务，兼容现有本地模型调用。",
        },
        "openai": {
            "provider": "openai",
            "enabled": False,
            "base_url": "https://api.openai.com/v1",
            "api_key": "",
            "default_model": "",
            "note": "预留 OpenAI Chat Completions / Responses API 配置。",
        },
        "gemini": {
            "provider": "gemini",
            "enabled": False,
            "base_url": "https://generativelanguage.googleapis.com",
            "api_key": "",
            "default_model": "",
            "note": "预留 Google Gemini API 配置。",
        },
        "deepseek": {
            "provider": "deepseek",
            "enabled": False,
            "base_url": "https://api.deepseek.com",
            "api_key": "",
            "default_model": "",
            "note": "预留 DeepSeek API 配置。",
        },
        "moonshot": {
            "provider": "moonshot",
            "enabled": False,
            "base_url": "https://api.moonshot.cn/v1",
            "api_key": "",
            "default_model": "",
            "note": "预留 Kimi / Moonshot API 配置。",
        },
        "qwen": {
            "provider": "qwen",
            "enabled": False,
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "api_key": "",
            "default_model": "",
            "note": "预留通义千问 DashScope OpenAI 兼容接口配置。",
        },
        "custom": {
            "provider": "custom",
            "enabled": False,
            "base_url": "",
            "api_key": "",
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
        configs[provider].update(value)
        configs[provider]["provider"] = provider
    return configs


def _encode_configs(configs: dict[str, dict[str, Any]]) -> str:
    return json.dumps(configs, ensure_ascii=False, sort_keys=True)


def get_or_create_user_ai_setting(db: Session, user: User) -> UserAISetting:
    setting = db.query(UserAISetting).filter_by(user_id=user.id).first()
    if setting:
        return setting

    defaults = default_provider_configs()
    setting = UserAISetting(
        user_id=user.id,
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
        return _to_response("ollama", defaults["ollama"]["default_model"], defaults)

    setting = get_or_create_user_ai_setting(db, user)
    return _to_response(
        setting.active_provider,
        setting.default_model,
        _decode_configs(setting.provider_configs),
    )


def update_user_ai_settings(db: Session, user: User, payload: AISettingsUpdate) -> AISettingsResponse:
    setting = get_or_create_user_ai_setting(db, user)
    configs = _decode_configs(setting.provider_configs)

    for incoming in payload.providers:
        current = deepcopy(configs[incoming.provider])
        current["enabled"] = incoming.enabled
        current["base_url"] = incoming.base_url
        current["default_model"] = incoming.default_model
        current["note"] = incoming.note
        if incoming.api_key is not None and incoming.api_key != "":
            current["api_key"] = incoming.api_key
        configs[incoming.provider] = current

    setting.active_provider = payload.active_provider
    setting.default_model = payload.default_model or configs[payload.active_provider].get("default_model", "")
    setting.provider_configs = _encode_configs(configs)
    setting.updated_at = _now()
    db.add(setting)
    db.commit()
    db.refresh(setting)
    return _to_response(setting.active_provider, setting.default_model, configs)


def get_ollama_runtime_config(db: Session, user: User | None) -> OllamaRuntimeConfig:
    server_state = _get_effective_server_ai_state(db)
    server = server_state.config
    base_url = server.default_base_url
    default_model = server.default_model
    if user is not None:
        setting = get_or_create_user_ai_setting(db, user)
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
    active_provider: str,
    default_model: str,
    configs: dict[str, dict[str, Any]],
) -> AISettingsResponse:
    settings = get_settings()
    providers: list[AIProviderConfig] = []
    for key, config in configs.items():
        api_key = str(config.get("api_key") or "")
        providers.append(
            AIProviderConfig(
                provider=key,  # type: ignore[arg-type]
                enabled=bool(config.get("enabled")),
                base_url=str(config.get("base_url") or ""),
                api_key="",
                default_model=str(config.get("default_model") or ""),
                note=str(config.get("note") or ""),
                has_api_key=bool(api_key),
            )
        )
    return AISettingsResponse(
        active_provider=active_provider,  # type: ignore[arg-type]
        default_model=default_model,
        providers=providers,
        ollama_runtime=_runtime_status(active_provider, default_model, configs, settings),
    )

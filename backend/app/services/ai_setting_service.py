from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.user import User
from app.models.user_ai_setting import UserAISetting
from app.schemas.ai_setting import AIProviderConfig, AISettingsResponse, AISettingsUpdate


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


def get_ollama_runtime_config(db: Session, user: User | None) -> tuple[str, str]:
    settings = get_effective_ai_settings(db, user)
    active = next((item for item in settings.providers if item.provider == settings.active_provider), None)
    fallback = get_settings()
    if active is None or active.provider != "ollama":
        return fallback.ollama_base_url, settings.default_model or fallback.ollama_default_model
    return (
        active.base_url or fallback.ollama_base_url,
        settings.default_model or active.default_model or fallback.ollama_default_model,
    )


def _to_response(
    active_provider: str,
    default_model: str,
    configs: dict[str, dict[str, Any]],
) -> AISettingsResponse:
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
    )

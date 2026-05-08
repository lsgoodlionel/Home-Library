from __future__ import annotations

import json
import os
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.models.user import User
from app.models.user_external_search_setting import UserExternalSearchSetting
from app.schemas.external_search_setting import (
    ExternalProviderValidateResponse,
    ExternalSearchProviderConfig,
    ExternalSearchSettingsResponse,
    ExternalSearchSettingsUpdate,
)


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def default_external_provider_configs() -> dict[str, dict[str, Any]]:
    return {
        "google_books": {
            "provider": "google_books",
            "enabled": True,
            "api_key": os.getenv("GOOGLE_BOOKS_API_KEY") or "",
            "extra": "",
            "note": "Google Books API Key；未配置时使用公共额度，可能很快触发 429 限流。",
        },
        "isbn_work": {
            "provider": "isbn_work",
            "enabled": True,
            "api_key": os.getenv("ISBN_WORK_API_KEY") or "",
            "extra": "",
            "note": "ISBN Work appKey；配置后可按 ISBN 获取中文书目和封面。",
        },
        "douban": {
            "provider": "douban",
            "enabled": True,
            "api_key": "",
            "extra": "",
            "note": "豆瓣个人 Cookie（可选）；仅用于辅助检索，封面通过后端 Referer 代理缓存。",
        },
    }


def _decode_configs(raw: str | None) -> dict[str, dict[str, Any]]:
    configs = default_external_provider_configs()
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


def get_or_create_user_external_setting(db: Session, user: User) -> UserExternalSearchSetting:
    setting = db.query(UserExternalSearchSetting).filter_by(user_id=user.id).first()
    if setting:
        return setting
    setting = UserExternalSearchSetting(
        user_id=user.id,
        provider_configs=_encode_configs(default_external_provider_configs()),
        created_at=_now(),
        updated_at=_now(),
    )
    db.add(setting)
    db.commit()
    db.refresh(setting)
    return setting


def get_effective_external_configs(db: Session, user: User | None) -> dict[str, dict[str, Any]]:
    if user is None:
        return default_external_provider_configs()
    setting = get_or_create_user_external_setting(db, user)
    return _decode_configs(setting.provider_configs)


def get_external_search_settings(db: Session, user: User) -> ExternalSearchSettingsResponse:
    return _to_response(_decode_configs(get_or_create_user_external_setting(db, user).provider_configs))


def update_external_search_settings(
    db: Session,
    user: User,
    payload: ExternalSearchSettingsUpdate,
) -> ExternalSearchSettingsResponse:
    setting = get_or_create_user_external_setting(db, user)
    configs = _decode_configs(setting.provider_configs)

    for incoming in payload.providers:
        current = deepcopy(configs[incoming.provider])
        current["enabled"] = incoming.enabled
        current["note"] = incoming.note
        if incoming.api_key is not None and incoming.api_key != "":
            current["api_key"] = incoming.api_key
        if incoming.extra is not None and incoming.extra != "":
            current["extra"] = incoming.extra
        configs[incoming.provider] = current

    setting.provider_configs = _encode_configs(configs)
    setting.updated_at = _now()
    db.add(setting)
    db.commit()
    db.refresh(setting)
    return _to_response(configs)


async def validate_external_provider(
    provider: str,
    api_key: str | None,
) -> ExternalProviderValidateResponse:
    key = (api_key or "").strip()
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            if provider == "google_books":
                params: dict[str, Any] = {"q": "isbn:9780261102217", "maxResults": 1, "printType": "books"}
                if key:
                    params["key"] = key
                resp = await client.get("https://www.googleapis.com/books/v1/volumes", params=params)
                if resp.status_code == 200:
                    return ExternalProviderValidateResponse(provider="google_books", ok=True, message="Google Books API 可访问")
                return ExternalProviderValidateResponse(provider="google_books", ok=False, message=f"Google Books 返回 {resp.status_code}")

            if provider == "isbn_work":
                if not key:
                    return ExternalProviderValidateResponse(provider="isbn_work", ok=False, message="请先填写 ISBN Work appKey")
                resp = await client.get(
                    "https://data.isbn.work/openApi/getInfoByIsbn",
                    params={"isbn": "9787536692930", "appKey": key},
                )
                if resp.status_code != 200:
                    return ExternalProviderValidateResponse(provider="isbn_work", ok=False, message=f"ISBN Work 返回 HTTP {resp.status_code}")
                payload = resp.json()
                ok = payload.get("code") == 0
                return ExternalProviderValidateResponse(
                    provider="isbn_work",
                    ok=ok,
                    message="ISBN Work appKey 可用" if ok else f"ISBN Work 返回：{payload.get('msg') or payload.get('code')}",
                )
    except Exception as exc:
        return ExternalProviderValidateResponse(provider=provider, ok=False, message=f"验证失败：{type(exc).__name__}")

    return ExternalProviderValidateResponse(provider=provider, ok=False, message="该数据源暂不支持验证")


def _to_response(configs: dict[str, dict[str, Any]]) -> ExternalSearchSettingsResponse:
    providers: list[ExternalSearchProviderConfig] = []
    for key, config in configs.items():
        api_key = str(config.get("api_key") or "")
        extra = str(config.get("extra") or "")
        providers.append(
            ExternalSearchProviderConfig(
                provider=key,  # type: ignore[arg-type]
                enabled=bool(config.get("enabled")),
                api_key="",
                extra="",
                note=str(config.get("note") or ""),
                has_api_key=bool(api_key),
                has_extra=bool(extra),
            )
        )
    return ExternalSearchSettingsResponse(providers=providers)

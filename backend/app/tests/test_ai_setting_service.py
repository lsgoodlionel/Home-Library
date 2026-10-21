"""Account AI setting validation and persistence contracts."""

from __future__ import annotations

import json
import logging

import pytest
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.models import User, UserAIProviderCredential, UserAISetting
from app.schemas.ai_setting import AISettingsUpdate
from app.services import ai_setting_service as service
from app.services.ai_provider_credential_service import (
    get_provider_api_key,
    set_provider_api_key,
)


_SECRET_KEY = "ai-setting-service-strong-key-value-00001"


def _user(db: Session, username: str) -> User:
    user = User(
        username=username,
        password_hash="hash",
        display_name=username,
        role="member",
        status="active",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _configs() -> dict[str, dict[str, object]]:
    return {
        "ollama": {
            "provider": "ollama",
            "enabled": True,
            "base_url": "http://localhost:11434",
            "default_model": "qwen3:8b",
            "note": "",
        },
        "openai": {
            "provider": "openai",
            "enabled": True,
            "base_url": "https://api.openai.com/v1",
            "default_model": "gpt-test",
            "note": "",
        },
    }


def _payload(
    *,
    ai_enabled: bool = True,
    api_key: str | None = None,
    clear_api_key: bool = False,
) -> AISettingsUpdate:
    return AISettingsUpdate.model_validate(
        {
            "ai_enabled": ai_enabled,
            "active_provider": "openai",
            "default_model": "gpt-test",
            "providers": [
                {
                    "provider": "ollama",
                    "enabled": False,
                    "base_url": "http://localhost:11434",
                    "default_model": "qwen3:8b",
                },
                {
                    "provider": "openai",
                    "enabled": True,
                    "base_url": "https://api.openai.com/v1",
                    "api_key": api_key,
                    "clear_api_key": clear_api_key,
                    "default_model": "gpt-test",
                },
            ],
        }
    )


def _saved_setting(
    db: Session,
    user: User,
    *,
    ai_enabled: bool = False,
) -> UserAISetting:
    setting = UserAISetting(
        user_id=user.id,
        ai_enabled=ai_enabled,
        active_provider="ollama",
        default_model="qwen3:8b",
        provider_configs=json.dumps(_configs()),
    )
    db.add(setting)
    db.commit()
    db.refresh(setting)
    return setting


def test_account_ai_config_disabled_allows_all_providers_disabled() -> None:
    configs = _configs()
    for config in configs.values():
        config["enabled"] = False

    service.validate_account_ai_selection(
        False,
        "openai",
        configs,
        {"ollama": "missing", "openai": "missing"},
    )


@pytest.mark.parametrize(
    ("configs", "states", "message"),
    [
        (
            {**_configs(), "openai": {**_configs()["openai"], "enabled": False}},
            {"openai": "configured"},
            "当前 AI 服务商未启用",
        ),
        (_configs(), {"openai": "missing"}, "当前 AI 服务商 API Key 未配置"),
        (_configs(), {"openai": "unusable"}, "当前 AI 服务商 API Key 不可用"),
        (
            {**_configs(), "openai": {**_configs()["openai"], "default_model": ""}},
            {"openai": "configured"},
            "当前 AI 服务商默认模型不能为空",
        ),
    ],
)
def test_account_ai_config_rejects_invalid_active_provider_without_fallback(
    configs: dict[str, dict[str, object]],
    states: dict[str, str],
    message: str,
) -> None:
    with pytest.raises(ApiError) as exc_info:
        service.validate_account_ai_selection(
            True,
            "openai",
            configs,
            states,
        )
    assert exc_info.value.message == message


def test_account_ai_config_allows_switching_away_then_disabling_ollama() -> None:
    configs = _configs()
    configs["ollama"]["enabled"] = False

    service.validate_account_ai_selection(
        True,
        "openai",
        configs,
        {"ollama": "missing", "openai": "configured"},
    )


def test_account_ai_config_rejects_provider_default_model_mismatch(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME_LIBRARY_SECRET_KEY", _SECRET_KEY)
    user = _user(db, "settings-model-mismatch-user")
    set_provider_api_key(db, user.id, "openai", "provider-key")
    payload = _payload()
    payload.default_model = "qwen3:8b"

    with pytest.raises(ApiError) as exc_info:
        service.update_user_ai_settings(db, user, payload)

    assert exc_info.value.message == "账号默认模型必须与当前 AI 服务商默认模型一致"


def test_account_ai_config_omitted_ai_enabled_preserves_disabled_setting(
    db: Session,
) -> None:
    user = _user(db, "settings-omitted-ai-enabled-user")
    _saved_setting(db, user, ai_enabled=False)
    payload = AISettingsUpdate.model_validate(
        {
            "active_provider": "ollama",
            "default_model": "qwen3:8b",
            "providers": [{"provider": "ollama", "note": "旧客户端更新"}],
        }
    )
    assert "ai_enabled" not in payload.model_fields_set

    response = service.update_user_ai_settings(db, user, payload)

    db.expire_all()
    saved = db.query(UserAISetting).filter_by(user_id=user.id).one()
    assert saved.ai_enabled is False
    assert response.ai_enabled is False


def test_account_ai_config_partial_provider_update_preserves_omitted_fields_and_applies_explicit_values(
    db: Session,
) -> None:
    user = _user(db, "settings-partial-provider-user")
    _saved_setting(db, user, ai_enabled=False)

    service.update_user_ai_settings(
        db,
        user,
        AISettingsUpdate.model_validate(
            {
                "active_provider": "ollama",
                "default_model": "qwen3:8b",
                "providers": [{"provider": "openai", "note": "只修改备注"}],
            }
        ),
    )
    first = json.loads(
        db.query(UserAISetting.provider_configs).filter_by(user_id=user.id).scalar()
    )["openai"]
    assert first == {
        "provider": "openai",
        "enabled": True,
        "base_url": "https://api.openai.com/v1",
        "default_model": "gpt-test",
        "note": "只修改备注",
    }

    service.update_user_ai_settings(
        db,
        user,
        AISettingsUpdate.model_validate(
            {
                "active_provider": "ollama",
                "default_model": "qwen3:8b",
                "providers": [
                    {
                        "provider": "openai",
                        "enabled": False,
                        "base_url": "",
                        "default_model": "",
                        "note": "",
                    }
                ],
            }
        ),
    )
    second = json.loads(
        db.query(UserAISetting.provider_configs).filter_by(user_id=user.id).scalar()
    )["openai"]
    assert second == {
        "provider": "openai",
        "enabled": False,
        "base_url": "",
        "default_model": "",
        "note": "",
    }


def test_account_ai_config_api_key_preserve_replace_and_clear(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME_LIBRARY_SECRET_KEY", _SECRET_KEY)
    user = _user(db, "settings-credential-user")
    set_provider_api_key(db, user.id, "openai", "provider-key-one")

    preserved = service.update_user_ai_settings(db, user, _payload(api_key=""))
    assert get_provider_api_key(db, user.id, "openai") == "provider-key-one"
    assert next(item for item in preserved.providers if item.provider == "openai").credential_state == "configured"

    replaced = service.update_user_ai_settings(db, user, _payload(api_key="provider-key-two"))
    assert get_provider_api_key(db, user.id, "openai") == "provider-key-two"
    assert next(item for item in replaced.providers if item.provider == "openai").has_api_key is True

    cleared = service.update_user_ai_settings(
        db,
        user,
        _payload(ai_enabled=False, clear_api_key=True),
    )
    assert get_provider_api_key(db, user.id, "openai") == ""
    openai = next(item for item in cleared.providers if item.provider == "openai")
    assert openai.credential_state == "missing"
    assert openai.has_api_key is False


def test_account_ai_config_rejects_api_key_replace_and_clear_together() -> None:
    with pytest.raises(ValueError, match="不能同时提交新 API Key 和清除 API Key"):
        _payload(api_key="provider-key-marker", clear_api_key=True)


def test_account_ai_config_failed_commit_rolls_back_config_and_api_key(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME_LIBRARY_SECRET_KEY", _SECRET_KEY)
    user = _user(db, "settings-rollback-user")
    set_provider_api_key(db, user.id, "openai", "original-provider-key")
    original = UserAISetting(
        user_id=user.id,
        ai_enabled=True,
        active_provider="openai",
        default_model="gpt-test",
        provider_configs=json.dumps(_configs()),
    )
    db.add(original)
    db.commit()

    original_commit = db.commit

    commit_calls = 0

    def fail_commit() -> None:
        nonlocal commit_calls
        commit_calls += 1
        raise RuntimeError("synthetic commit failure")

    monkeypatch.setattr(db, "commit", fail_commit)
    with pytest.raises(ApiError) as exc_info:
        service.update_user_ai_settings(db, user, _payload(api_key="replacement-provider-key"))
    assert exc_info.value.message == "AI 配置保存失败"
    assert commit_calls == 1
    monkeypatch.setattr(db, "commit", original_commit)

    db.expire_all()
    saved = db.query(UserAISetting).filter_by(user_id=user.id).one()
    assert saved.active_provider == "openai"
    assert saved.default_model == "gpt-test"
    assert get_provider_api_key(db, user.id, "openai") == "original-provider-key"


@pytest.mark.parametrize("failure_point", ["runtime", "response"])
def test_account_ai_config_precommit_failure_rolls_back_config_and_api_key(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
    failure_point: str,
) -> None:
    monkeypatch.setenv("HOME_LIBRARY_SECRET_KEY", _SECRET_KEY)
    user = _user(db, f"settings-precommit-{failure_point}-user")
    set_provider_api_key(db, user.id, "openai", "original-provider-key")
    original = UserAISetting(
        user_id=user.id,
        ai_enabled=True,
        active_provider="openai",
        default_model="gpt-test",
        provider_configs=json.dumps(_configs()),
    )
    db.add(original)
    db.commit()

    def fail_after_flush(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise RuntimeError(f"synthetic {failure_point} failure")

    target = "get_ollama_runtime_config" if failure_point == "runtime" else "_to_response"
    monkeypatch.setattr(service, target, fail_after_flush)

    with pytest.raises(RuntimeError, match=f"synthetic {failure_point} failure"):
        service.update_user_ai_settings(
            db,
            user,
            _payload(api_key="replacement-provider-key"),
        )

    db.expire_all()
    saved = db.query(UserAISetting).filter_by(user_id=user.id).one()
    assert saved.active_provider == "openai"
    assert saved.default_model == "gpt-test"
    assert json.loads(saved.provider_configs) == _configs()
    assert get_provider_api_key(db, user.id, "openai") == "original-provider-key"


def test_account_ai_config_never_persists_or_reports_api_key(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("HOME_LIBRARY_SECRET_KEY", _SECRET_KEY)
    user = _user(db, "settings-secret-user")
    marker = "provider-key-sensitive-marker"

    with caplog.at_level(logging.INFO):
        response = service.update_user_ai_settings(db, user, _payload(api_key=marker))

    stored = db.query(UserAISetting.provider_configs).filter_by(user_id=user.id).scalar()
    serialized = response.model_dump()
    assert stored is not None
    assert "api_key" not in stored
    assert all("api_key" not in provider for provider in serialized["providers"])
    assert marker not in stored
    assert marker not in response.model_dump_json()
    assert marker not in caplog.text
    ciphertext = db.query(UserAIProviderCredential.api_key_ciphertext).filter_by(
        user_id=user.id,
        provider="openai",
    ).scalar()
    assert ciphertext is not None
    assert marker not in ciphertext

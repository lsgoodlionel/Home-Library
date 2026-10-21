from __future__ import annotations

import json
import socket
from dataclasses import asdict

import pytest
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import SystemAISetting, User, UserAISetting
from app.schemas.ai_setting import AISettingsUpdate
from app.services.ai_health_status_cache import ProviderModelCache
from app.services.ai_provider_credential_service import set_provider_api_key
from app.services.ai_provider_runtime import (
    create_ai_provider_client,
    provider_runtime_fingerprint,
    resolve_ai_provider_runtime,
)
from app.services.ai_providers.base import (
    AIProviderDisabledError,
    AIProviderInvalidConfigurationError,
    AIProviderModel,
    AIProviderModelList,
    AIProviderRuntime,
    OllamaProviderRuntimeOptions,
)
from app.services.ai_providers.gemini import GeminiProviderClient
from app.services.ai_providers.ollama import OllamaProviderClient
from app.services.ai_providers.openai_compatible import OpenAICompatibleProviderClient
from app.services.ai_setting_service import update_user_ai_settings
from app.services.system_ai_setting_service import (
    CredentialUpdate,
    ServerAIConfigUpdateValues,
    reset_server_ai_config,
    update_server_ai_config,
)


_SECRET_KEY = "task-6-account-provider-key-material-0001"


def _user(db: Session, name: str = "runtime-user") -> User:
    user = User(
        username=name,
        password_hash="hash",
        display_name=name,
        role="member",
        status="active",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _configs(
    *,
    provider: str = "openai",
    enabled: bool = True,
    base_url: str | None = None,
    model: str | None = None,
) -> dict[str, dict[str, object]]:
    urls = {
        "ollama": "https://account-ollama.example.test",
        "openai": "https://api.example.test/v1",
        "gemini": "https://generativelanguage.example.test",
    }
    models = {"ollama": "ollama-account-model", "openai": "gpt-test", "gemini": "gemini-test"}
    return {
        key: {
            "provider": key,
            "enabled": enabled if key == provider else False,
            "base_url": base_url if key == provider and base_url is not None else urls[key],
            "default_model": model if key == provider and model is not None else models[key],
            "note": "",
        }
        for key in urls
    }


def _setting(
    db: Session,
    user: User,
    *,
    provider: str = "openai",
    ai_enabled: bool = True,
    enabled: bool = True,
    base_url: str | None = None,
    model: str | None = None,
    account_model: str | None = None,
) -> UserAISetting:
    configs = _configs(
        provider=provider,
        enabled=enabled,
        base_url=base_url,
        model=model,
    )
    selected_model = str(configs[provider]["default_model"])
    row = UserAISetting(
        user_id=user.id,
        ai_enabled=ai_enabled,
        active_provider=provider,
        default_model=account_model if account_model is not None else selected_model,
        provider_configs=json.dumps(configs),
    )
    db.add(row)
    db.commit()
    return row


@pytest.fixture(autouse=True)
def _runtime_environment(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("HOME_LIBRARY_SECRET_KEY", _SECRET_KEY)
    monkeypatch.setenv("HOME_LIBRARY_OLLAMA_ENABLED", "true")
    monkeypatch.setenv("HOME_LIBRARY_OLLAMA_BASE_URL", "https://server-ollama.example.test")
    monkeypatch.setenv("HOME_LIBRARY_OLLAMA_TRUSTED_BASE_URL", "https://account-ollama.example.test")
    monkeypatch.setenv("HOME_LIBRARY_OLLAMA_DEFAULT_MODEL", "server-model")
    monkeypatch.setenv("HOME_LIBRARY_OLLAMA_CONNECT_TIMEOUT_SECONDS", "4.5")
    monkeypatch.setenv("HOME_LIBRARY_OLLAMA_READ_TIMEOUT_SECONDS", "45")
    monkeypatch.setenv("HOME_LIBRARY_OLLAMA_VERIFY_TLS", "false")
    monkeypatch.setenv("HOME_LIBRARY_OLLAMA_CF_ACCESS_CLIENT_ID", "access-id-sensitive")
    monkeypatch.setenv("HOME_LIBRARY_OLLAMA_CF_ACCESS_CLIENT_SECRET", "access-secret-sensitive")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _install_public_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    def getaddrinfo(host: str, port: int, *args: object, **kwargs: object):
        del host, args, kwargs
        return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("93.184.216.34", port))]

    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)


@pytest.mark.parametrize(
    ("ai_enabled", "provider", "provider_enabled", "expected"),
    [
        (False, "openai", True, AIProviderDisabledError),
        (True, "missing-provider", True, AIProviderInvalidConfigurationError),
        (True, "openai", False, AIProviderInvalidConfigurationError),
    ],
)
def test_runtime_rejects_disabled_or_invalid_account_selection(
    db: Session,
    ai_enabled: bool,
    provider: str,
    provider_enabled: bool,
    expected: type[Exception],
) -> None:
    user = _user(db, f"invalid-{provider}-{ai_enabled}")
    if provider == "missing-provider":
        row = _setting(db, user)
        row.active_provider = provider
        db.commit()
    else:
        _setting(db, user, provider=provider, ai_enabled=ai_enabled, enabled=provider_enabled)

    with pytest.raises(expected):
        resolve_ai_provider_runtime(db, user)


def test_runtime_rejects_provider_model_mismatch_without_fallback(db: Session) -> None:
    user = _user(db, "model-mismatch")
    _setting(db, user, provider="openai", account_model="other-model")
    set_provider_api_key(db, user.id, "openai", "cloud-key")

    with pytest.raises(AIProviderInvalidConfigurationError):
        resolve_ai_provider_runtime(db, user)


@pytest.mark.parametrize(
    ("provider_configs", "account_model"),
    [
        ("{", "server-model"),
        (json.dumps({"openai": _configs()["openai"]}), "server-model"),
        (
            json.dumps(
                {
                    "ollama": {
                        **_configs(provider="ollama")["ollama"],
                        "provider": "openai",
                    }
                }
            ),
            "ollama-account-model",
        ),
        (
            json.dumps(
                {
                    "ollama": {
                        **_configs(provider="ollama")["ollama"],
                        "enabled": "true",
                    }
                }
            ),
            "ollama-account-model",
        ),
        (
            json.dumps(
                {
                    "ollama": {
                        **_configs(provider="ollama")["ollama"],
                        "base_url": "",
                    }
                }
            ),
            "ollama-account-model",
        ),
        (
            json.dumps(
                {
                    "ollama": {
                        **_configs(provider="ollama")["ollama"],
                        "default_model": " ollama-account-model ",
                    }
                }
            ),
            "ollama-account-model",
        ),
    ],
    ids=[
        "malformed-json",
        "missing-active-provider",
        "embedded-provider-mismatch",
        "enabled-not-bool",
        "empty-base-url",
        "model-not-canonical",
    ],
)
def test_runtime_strictly_rejects_corrupt_persisted_provider_config(
    db: Session,
    provider_configs: str,
    account_model: str,
) -> None:
    user = _user(db, f"strict-config-{abs(hash(provider_configs))}")
    row = _setting(db, user, provider="ollama")
    row.provider_configs = provider_configs
    row.default_model = account_model
    db.commit()

    with pytest.raises(AIProviderInvalidConfigurationError):
        resolve_ai_provider_runtime(db, user)


def test_cloud_runtime_decrypts_only_into_secret_safe_runtime(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_public_dns(monkeypatch)
    user = _user(db, "cloud-runtime")
    _setting(db, user, provider="openai")
    marker = "cloud-api-key-sensitive-marker"
    set_provider_api_key(db, user.id, "openai", marker)

    runtime = resolve_ai_provider_runtime(db, user)

    assert runtime.provider == "openai"
    assert runtime.default_model == "gpt-test"
    assert runtime.get_credential_value() == marker
    for rendered in (repr(runtime), repr(asdict(runtime)), repr(jsonable_encoder(runtime)), repr(runtime.to_safe_dict())):
        assert marker not in rendered
    assert marker not in provider_runtime_fingerprint(runtime)
    assert isinstance(create_ai_provider_client(runtime), OpenAICompatibleProviderClient)


def test_cloud_runtime_rejects_missing_or_unusable_credentials(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_public_dns(monkeypatch)
    user = _user(db, "missing-key")
    _setting(db, user, provider="gemini")

    with pytest.raises(AIProviderInvalidConfigurationError):
        resolve_ai_provider_runtime(db, user)


def test_ollama_runtime_composes_account_override_and_exact_access_origin(db: Session) -> None:
    user = _user(db, "ollama-runtime")
    _setting(db, user, provider="ollama")

    runtime = resolve_ai_provider_runtime(db, user)

    assert runtime.provider == "ollama"
    assert runtime.base_url == "https://account-ollama.example.test"
    assert runtime.default_model == "ollama-account-model"
    assert runtime.connect_timeout_seconds == 4.5
    assert runtime.read_timeout_seconds == 45.0
    assert runtime.verify_tls is False
    assert runtime.ollama is not None
    assert runtime.ollama.trusted_base_url == "https://account-ollama.example.test"
    assert runtime.ollama.uses_access is True
    assert runtime.ollama.config_version == 0
    assert runtime.ollama.get_access_credentials() == (
        "access-id-sensitive",
        "access-secret-sensitive",
    )
    rendered = " ".join((repr(runtime), repr(asdict(runtime)), repr(jsonable_encoder(runtime))))
    assert "access-id-sensitive" not in rendered
    assert "access-secret-sensitive" not in rendered
    assert isinstance(create_ai_provider_client(runtime), OllamaProviderClient)


def test_ollama_runtime_does_not_trust_near_match_origin(db: Session) -> None:
    user = _user(db, "ollama-origin-mismatch")
    _setting(db, user, provider="ollama", base_url="https://account-ollama.example.test:444")

    runtime = resolve_ai_provider_runtime(db, user)

    assert runtime.ollama is not None
    assert runtime.ollama.uses_access is False


def test_ollama_runtime_rejects_disabled_server(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME_LIBRARY_OLLAMA_ENABLED", "false")
    get_settings.cache_clear()
    user = _user(db, "ollama-server-disabled")
    _setting(db, user, provider="ollama")

    with pytest.raises(AIProviderDisabledError):
        resolve_ai_provider_runtime(db, user)


def test_new_account_ollama_runtime_inherits_database_server_defaults(db: Session) -> None:
    actor = _user(db, "database-default-actor")
    user = _user(db, "database-default-account")
    update_server_ai_config(
        db,
        values=ServerAIConfigUpdateValues(
            enabled=True,
            default_base_url="https://database-ollama.example.test",
            trusted_base_url="https://database-ollama.example.test",
            default_model="database-default-model",
            connect_timeout_seconds=6,
            read_timeout_seconds=70,
            verify_tls=True,
        ),
        credentials=CredentialUpdate(mode="clear_pair"),
        actor_id=actor.id,
    )

    runtime = resolve_ai_provider_runtime(db, user)

    assert runtime.base_url == "https://database-ollama.example.test"
    assert runtime.default_model == "database-default-model"


def test_factory_selects_gemini_and_rejects_unknown_runtime(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_public_dns(monkeypatch)
    user = _user(db, "gemini-factory")
    _setting(db, user, provider="gemini")
    set_provider_api_key(db, user.id, "gemini", "gemini-key")
    runtime = resolve_ai_provider_runtime(db, user)

    assert isinstance(create_ai_provider_client(runtime), GeminiProviderClient)

    object.__setattr__(runtime, "provider", "unknown")
    with pytest.raises(AIProviderInvalidConfigurationError):
        create_ai_provider_client(runtime)


def test_factory_rejects_known_cloud_runtime_without_usable_credential() -> None:
    runtime = AIProviderRuntime(
        provider="openai",
        enabled=True,
        base_url="https://api.example.test/v1",
        default_model="gpt-test",
        credential_state="configured",
    )

    with pytest.raises(AIProviderInvalidConfigurationError):
        create_ai_provider_client(runtime)


def _ollama_options(
    *,
    trusted_base_url: str = "https://ollama.example.test",
    client_id: str | None = "access-id",
    client_secret: str | None = "access-secret",
    uses_access: bool = True,
) -> OllamaProviderRuntimeOptions:
    return OllamaProviderRuntimeOptions(
        trusted_base_url=trusted_base_url,
        access_client_id=client_id,
        access_client_secret=client_secret,
        uses_access=uses_access,
        config_version=1,
    )


@pytest.mark.parametrize(
    "runtime",
    [
        AIProviderRuntime(
            provider="openai",
            enabled=True,
            base_url="http://127.0.0.1",
            default_model="gpt-test",
            credential_state="configured",
            credential="cloud-key",
        ),
        AIProviderRuntime(
            provider="openai",
            enabled=True,
            base_url="https://api.example.test/v1",
            default_model="gpt-test",
            credential_state="configured",
            credential="cloud-key",
            ollama=_ollama_options(),
        ),
        AIProviderRuntime(
            provider="ollama",
            enabled=True,
            base_url="ftp://ollama.example.test",
            default_model="qwen-test",
            credential_state="configured",
            ollama=_ollama_options(),
        ),
        AIProviderRuntime(
            provider="ollama",
            enabled=True,
            base_url="https://ollama.example.test",
            default_model="qwen-test",
            credential_state="configured",
            ollama=_ollama_options(trusted_base_url="https://ollama.example.test/path"),
        ),
        AIProviderRuntime(
            provider="ollama",
            enabled=True,
            base_url="https://ollama.example.test",
            default_model="qwen-test",
            credential_state="configured",
            credential="cloud-key",
            ollama=_ollama_options(),
        ),
        AIProviderRuntime(
            provider="ollama",
            enabled=True,
            base_url="https://ollama.example.test",
            default_model="qwen-test",
            credential_state="configured",
            ollama=_ollama_options(client_secret=None, uses_access=False),
        ),
        AIProviderRuntime(
            provider="ollama",
            enabled=True,
            base_url="https://ollama.example.test",
            default_model="qwen-test",
            credential_state="missing",
            ollama=_ollama_options(uses_access=False),
        ),
        AIProviderRuntime(
            provider="ollama",
            enabled=True,
            base_url="https://ollama.example.test",
            default_model="qwen-test",
            credential_state="configured",
            ollama=_ollama_options(uses_access=False),
        ),
        AIProviderRuntime(
            provider="ollama",
            enabled=True,
            base_url="https://other.example.test",
            default_model="qwen-test",
            credential_state="configured",
            ollama=_ollama_options(uses_access=True),
        ),
        AIProviderRuntime(
            provider="ollama",
            enabled=True,
            base_url="https://ollama.example.test",
            default_model="qwen-test",
            credential_state="configured",
            ollama=_ollama_options(client_id=None, client_secret=None, uses_access=False),
        ),
    ],
    ids=[
        "cloud-forbidden-url",
        "cloud-with-ollama-options",
        "ollama-invalid-base-url",
        "ollama-trusted-url-is-not-origin",
        "ollama-with-cloud-credential",
        "ollama-partial-access-pair",
        "ollama-pair-with-missing-state",
        "ollama-exact-origin-uses-access-false",
        "ollama-other-origin-uses-access-true",
        "ollama-configured-state-without-pair",
    ],
)
def test_factory_rejects_provider_invariants_before_client_creation(
    runtime: AIProviderRuntime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: list[str] = []

    def unexpected_client(*args: object, **kwargs: object) -> object:
        del args, kwargs
        created.append("created")
        return object()

    monkeypatch.setattr("app.services.ai_provider_runtime.OllamaProviderClient", unexpected_client)
    monkeypatch.setattr("app.services.ai_provider_runtime.GeminiProviderClient", unexpected_client)
    monkeypatch.setattr(
        "app.services.ai_provider_runtime.OpenAICompatibleProviderClient",
        unexpected_client,
    )

    with pytest.raises(AIProviderInvalidConfigurationError):
        create_ai_provider_client(runtime)

    assert created == []


def test_provider_model_cache_isolates_keys_expires_and_evicts_lru() -> None:
    now = [100.0]
    cache = ProviderModelCache(max_entries=2, ttl_seconds=300, clock=lambda: now[0])
    first = AIProviderModelList(
        capability="supported",
        models=(AIProviderModel(provider="openai", id="a", name="A"),),
    )
    second = AIProviderModelList(capability="unsupported")

    cache.put(1, "openai", "fp-a", first)
    assert cache.get(1, "openai", "fp-a") is first
    assert cache.get(2, "openai", "fp-a") is None
    assert cache.get(1, "gemini", "fp-a") is None
    assert cache.get(1, "openai", "fp-b") is None

    cache.put(1, "gemini", "fp-b", second)
    assert cache.get(1, "openai", "fp-a") is first
    cache.put(2, "openai", "fp-c", second)
    assert cache.get(1, "gemini", "fp-b") is None
    assert cache.get(1, "openai", "fp-a") is first

    now[0] = 400.0
    assert cache.get(1, "openai", "fp-a") is None


def test_provider_model_cache_invalidates_user_and_all() -> None:
    cache = ProviderModelCache()
    models = AIProviderModelList(capability="unsupported")
    cache.put(1, "openai", "a", models)
    cache.put(2, "gemini", "b", models)

    cache.invalidate_user(1)
    assert cache.get(1, "openai", "a") is None
    assert cache.get(2, "gemini", "b") is models

    cache.invalidate_all()
    assert cache.get(2, "gemini", "b") is None


def test_account_setting_update_invalidates_only_that_users_model_cache(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = _user(db, "account-cache-invalidation")
    _setting(db, user, provider="ollama", ai_enabled=False)
    invalidated: list[int] = []
    monkeypatch.setattr(
        "app.services.ai_setting_service.provider_model_cache.invalidate_user",
        invalidated.append,
    )

    update_user_ai_settings(
        db,
        user,
        AISettingsUpdate.model_validate(
            {
                "ai_enabled": False,
                "active_provider": "ollama",
                "default_model": "ollama-account-model",
                "providers": [{"provider": "ollama", "note": "updated"}],
            }
        ),
    )

    assert invalidated == [user.id]


def test_server_setting_update_and_reset_invalidate_all_model_cache(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actor = _user(db, "server-cache-invalidation")
    invalidations: list[str] = []
    monkeypatch.setattr(
        "app.services.system_ai_setting_service.provider_model_cache.invalidate_all",
        lambda: invalidations.append("all"),
    )
    values = ServerAIConfigUpdateValues(
        enabled=True,
        default_base_url="https://server-ollama.example.test",
        trusted_base_url="https://server-ollama.example.test",
        default_model="server-model",
        connect_timeout_seconds=5,
        read_timeout_seconds=60,
        verify_tls=True,
    )

    update_server_ai_config(
        db,
        values=values,
        credentials=CredentialUpdate(mode="preserve"),
        actor_id=actor.id,
    )
    reset_server_ai_config(db, actor_id=actor.id)

    assert invalidations == ["all", "all"]


def test_account_update_returns_committed_success_when_model_cache_invalidation_fails(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    user = _user(db, "account-cache-failure")
    _setting(db, user, provider="ollama", ai_enabled=False)
    marker = "account-cache-secret-marker"
    monkeypatch.setattr(
        "app.services.ai_setting_service.provider_model_cache.invalidate_user",
        lambda user_id: (_ for _ in ()).throw(RuntimeError(f"{marker}-{user_id}")),
    )

    response = update_user_ai_settings(
        db,
        user,
        AISettingsUpdate.model_validate(
            {
                "ai_enabled": False,
                "active_provider": "ollama",
                "default_model": "ollama-account-model",
                "providers": [{"provider": "ollama", "note": "committed-note"}],
            }
        ),
    )

    db.expire_all()
    saved = db.query(UserAISetting).filter_by(user_id=user.id).one()
    assert response.ai_enabled is False
    assert json.loads(saved.provider_configs)["ollama"]["note"] == "committed-note"
    assert marker not in "\n".join(record.getMessage() for record in caplog.records)


def test_server_update_returns_committed_success_when_model_cache_invalidation_fails(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    actor = _user(db, "server-update-cache-failure")
    marker = "server-update-cache-secret-marker"
    monkeypatch.setattr(
        "app.services.system_ai_setting_service.provider_model_cache.invalidate_all",
        lambda: (_ for _ in ()).throw(RuntimeError(marker)),
    )

    result = update_server_ai_config(
        db,
        values=ServerAIConfigUpdateValues(
            enabled=True,
            default_base_url="https://committed-ollama.example.test",
            trusted_base_url="https://committed-ollama.example.test",
            default_model="committed-model",
            connect_timeout_seconds=8,
            read_timeout_seconds=80,
            verify_tls=True,
        ),
        credentials=CredentialUpdate(mode="clear_pair"),
        actor_id=actor.id,
    )

    db.expire_all()
    saved = db.get(SystemAISetting, 1)
    assert result.config_version == 1
    assert saved is not None
    assert saved.default_model == "committed-model"
    assert marker not in "\n".join(record.getMessage() for record in caplog.records)


def test_server_reset_returns_committed_success_when_model_cache_invalidation_fails(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    actor = _user(db, "server-reset-cache-failure")
    update_server_ai_config(
        db,
        values=ServerAIConfigUpdateValues(
            enabled=True,
            default_base_url="https://reset-ollama.example.test",
            trusted_base_url="https://reset-ollama.example.test",
            default_model="reset-model",
            connect_timeout_seconds=8,
            read_timeout_seconds=80,
            verify_tls=True,
        ),
        credentials=CredentialUpdate(mode="clear_pair"),
        actor_id=actor.id,
    )
    marker = "server-reset-cache-secret-marker"
    monkeypatch.setattr(
        "app.services.system_ai_setting_service.provider_model_cache.invalidate_all",
        lambda: (_ for _ in ()).throw(RuntimeError(marker)),
    )

    result = reset_server_ai_config(db, actor_id=actor.id)

    db.expire_all()
    assert result.configuration_source in {"environment", "default"}
    assert db.get(SystemAISetting, 1) is None
    assert marker not in "\n".join(record.getMessage() for record in caplog.records)

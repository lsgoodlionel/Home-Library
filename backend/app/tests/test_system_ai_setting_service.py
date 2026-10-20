from __future__ import annotations

import json
import threading
from dataclasses import asdict

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.models import SystemAISetting, SystemConfigAudit, User, UserAISetting
from app.models.base import Base
from app.services.credential_crypto import CredentialCryptoError
from app.services.system_ai_setting_service import (
    CredentialUpdate,
    ServerAIConfigUpdateValues,
    get_effective_server_ai_config,
    reset_server_ai_config,
    update_server_ai_config,
)
from app.services.ai_setting_service import get_ollama_runtime_config


_AI_ENVIRONMENT_NAMES = (
    "HOME_LIBRARY_OLLAMA_ENABLED",
    "OLLAMA_ENABLED",
    "HOME_LIBRARY_OLLAMA_BASE_URL",
    "OLLAMA_BASE_URL",
    "HOME_LIBRARY_OLLAMA_TRUSTED_BASE_URL",
    "OLLAMA_TRUSTED_BASE_URL",
    "HOME_LIBRARY_OLLAMA_DEFAULT_MODEL",
    "OLLAMA_DEFAULT_MODEL",
    "HOME_LIBRARY_OLLAMA_CONNECT_TIMEOUT_SECONDS",
    "OLLAMA_CONNECT_TIMEOUT_SECONDS",
    "HOME_LIBRARY_OLLAMA_READ_TIMEOUT_SECONDS",
    "OLLAMA_READ_TIMEOUT_SECONDS",
    "HOME_LIBRARY_OLLAMA_TIMEOUT_SECONDS",
    "OLLAMA_TIMEOUT_SECONDS",
    "HOME_LIBRARY_OLLAMA_VERIFY_TLS",
    "OLLAMA_VERIFY_TLS",
    "HOME_LIBRARY_OLLAMA_CF_ACCESS_CLIENT_ID",
    "OLLAMA_CF_ACCESS_CLIENT_ID",
    "HOME_LIBRARY_OLLAMA_CF_ACCESS_CLIENT_SECRET",
    "OLLAMA_CF_ACCESS_CLIENT_SECRET",
    "HOME_LIBRARY_SECRET_KEY",
    "APP_SECRET_KEY",
)


def _clear_ai_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _AI_ENVIRONMENT_NAMES:
        monkeypatch.delenv(name, raising=False)
    get_settings.cache_clear()


def _set_strong_secret_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME_LIBRARY_SECRET_KEY", "task-2-test-key-32-bytes-minimum-value")
    get_settings.cache_clear()


def _values(**overrides: object) -> ServerAIConfigUpdateValues:
    values: dict[str, object] = {
        "enabled": True,
        "default_base_url": "https://db-ollama.example.test/api/",
        "trusted_base_url": "https://db-ollama.example.test/",
        "default_model": "db-model",
        "connect_timeout_seconds": 4.5,
        "read_timeout_seconds": 45.0,
        "verify_tls": False,
    }
    values.update(overrides)
    return ServerAIConfigUpdateValues(**values)  # type: ignore[arg-type]


def test_server_config_falls_back_to_environment_then_defaults(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_ai_environment(monkeypatch)

    defaults = get_effective_server_ai_config(db)

    assert defaults.configuration_source == "default"
    assert defaults.config_version == 0
    assert defaults.enabled is False
    assert defaults.default_base_url == "https://openclaw.lsgood.cn"
    assert defaults.trusted_base_url == "https://openclaw.lsgood.cn"
    assert defaults.default_model == "qwen3.5:4b"
    assert defaults.connect_timeout_seconds == 20.0
    assert defaults.read_timeout_seconds == 180.0
    assert defaults.verify_tls is True
    assert defaults.credential_state.configured is False

    monkeypatch.setenv("OLLAMA_ENABLED", "true")
    monkeypatch.setenv("HOME_LIBRARY_OLLAMA_BASE_URL", "https://env.example.test/path")
    monkeypatch.setenv("OLLAMA_DEFAULT_MODEL", "env-model")
    get_settings.cache_clear()

    environment = get_effective_server_ai_config(db)

    assert environment.configuration_source == "environment"
    assert environment.enabled is True
    assert environment.default_base_url == "https://env.example.test/path"
    assert environment.default_model == "env-model"


def test_database_server_config_overrides_environment_and_increments_version(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_ai_environment(monkeypatch)
    _set_strong_secret_key(monkeypatch)
    monkeypatch.setenv("OLLAMA_BASE_URL", "https://environment.example.test")
    get_settings.cache_clear()

    first = update_server_ai_config(
        db,
        values=_values(),
        credentials=CredentialUpdate(mode="preserve"),
        actor_id=41,
    )
    second = update_server_ai_config(
        db,
        values=_values(default_model="db-model-v2"),
        credentials=CredentialUpdate(mode="preserve"),
        actor_id=42,
    )

    assert first.configuration_source == "database"
    assert first.config_version == 1
    assert first.default_base_url == "https://db-ollama.example.test/api/"
    assert second.configuration_source == "database"
    assert second.config_version == 2
    assert second.default_model == "db-model-v2"
    assert db.query(SystemAISetting).count() == 1


def test_reset_immediately_restores_environment_config(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_ai_environment(monkeypatch)
    _set_strong_secret_key(monkeypatch)
    update_server_ai_config(
        db,
        values=_values(),
        credentials=CredentialUpdate(mode="preserve"),
        actor_id=51,
    )
    monkeypatch.setenv("OLLAMA_ENABLED", "true")
    monkeypatch.setenv("OLLAMA_BASE_URL", "https://reset-env.example.test/runtime")
    monkeypatch.setenv("OLLAMA_DEFAULT_MODEL", "reset-env-model")
    get_settings.cache_clear()

    restored = reset_server_ai_config(db, actor_id=52)

    assert restored.configuration_source == "environment"
    assert restored.config_version == 0
    assert restored.default_base_url == "https://reset-env.example.test/runtime"
    assert restored.default_model == "reset-env-model"
    assert db.get(SystemAISetting, 1) is None
    audit = db.query(SystemConfigAudit).order_by(SystemConfigAudit.id.desc()).first()
    assert audit is not None
    assert audit.action == "reset"
    assert audit.config_version == 2


def test_empty_credentials_preserve_and_explicit_clear_removes_both(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client_id_marker = "task2-client-id-marker"
    client_secret_marker = "task2-client-secret-marker"
    _clear_ai_environment(monkeypatch)
    _set_strong_secret_key(monkeypatch)
    monkeypatch.setenv("OLLAMA_CF_ACCESS_CLIENT_ID", client_id_marker)
    monkeypatch.setenv("OLLAMA_CF_ACCESS_CLIENT_SECRET", client_secret_marker)
    get_settings.cache_clear()

    created = update_server_ai_config(
        db,
        values=_values(),
        credentials=CredentialUpdate(mode="preserve"),
        actor_id=61,
    )
    preserved = update_server_ai_config(
        db,
        values=_values(default_model="preserved-model"),
        credentials=CredentialUpdate(mode="preserve"),
        actor_id=61,
    )
    runtime_before_clear = get_ollama_runtime_config(db, None)
    cleared = update_server_ai_config(
        db,
        values=_values(default_model="cleared-model"),
        credentials=CredentialUpdate(mode="clear_pair"),
        actor_id=61,
    )
    runtime_after_clear = get_ollama_runtime_config(db, None)

    assert created.credential_state.configured is True
    assert preserved.credential_state.configured is True
    assert runtime_before_clear.access_client_id == client_id_marker
    assert runtime_before_clear.access_client_secret == client_secret_marker
    assert cleared.credential_state.configured is False
    assert runtime_after_clear.access_client_id == ""
    assert runtime_after_clear.access_client_secret == ""
    row = db.get(SystemAISetting, 1)
    assert row is not None
    assert row.access_client_id_ciphertext is None
    assert row.access_client_secret_ciphertext is None

    with pytest.raises(ValueError):
        CredentialUpdate(mode="preserve", client_id="not-allowed")
    with pytest.raises(ValueError):
        CredentialUpdate(mode="replace_pair", client_id="only-one-side")
    with pytest.raises(ValueError):
        CredentialUpdate(mode="clear_pair", client_secret="not-allowed")


def test_partial_or_failed_encryption_rolls_back_the_entire_update(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_ai_environment(monkeypatch)
    _set_strong_secret_key(monkeypatch)
    update_server_ai_config(
        db,
        values=_values(default_model="stable-model"),
        credentials=CredentialUpdate(
            mode="replace_pair",
            client_id="stable-client-marker",
            client_secret="stable-secret-marker",
        ),
        actor_id=71,
    )
    old_row = db.get(SystemAISetting, 1)
    assert old_row is not None
    old_ciphertexts = (
        old_row.access_client_id_ciphertext,
        old_row.access_client_secret_ciphertext,
    )
    old_audit_count = db.query(SystemConfigAudit).count()

    from app.services import system_ai_setting_service as service

    real_encrypt = service.CredentialCipher.encrypt
    calls = 0

    def fail_second_encryption(cipher, plaintext: str) -> str:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise CredentialCryptoError("凭据加密失败")
        return real_encrypt(cipher, plaintext)

    monkeypatch.setattr(service.CredentialCipher, "encrypt", fail_second_encryption)

    with pytest.raises(CredentialCryptoError, match="凭据加密失败"):
        update_server_ai_config(
            db,
            values=_values(default_model="must-not-commit"),
            credentials=CredentialUpdate(
                mode="replace_pair",
                client_id="failed-client-marker",
                client_secret="failed-secret-marker",
            ),
            actor_id=72,
        )

    db.expire_all()
    row = db.get(SystemAISetting, 1)
    assert row is not None
    assert row.default_model == "stable-model"
    assert (row.access_client_id_ciphertext, row.access_client_secret_ciphertext) == old_ciphertexts
    assert db.query(SystemConfigAudit).count() == old_audit_count


def test_changed_fields_audit_contains_names_only(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    client_id_marker = "audit-client-id-marker"
    client_secret_marker = "audit-client-secret-marker"
    _clear_ai_environment(monkeypatch)
    _set_strong_secret_key(monkeypatch)

    result = update_server_ai_config(
        db,
        values=_values(),
        credentials=CredentialUpdate(
            mode="replace_pair",
            client_id=client_id_marker,
            client_secret=client_secret_marker,
        ),
        actor_id=81,
    )

    audit = db.query(SystemConfigAudit).one()
    assert audit.action == "update"
    assert set(audit.changed_fields) == {
        "enabled",
        "default_base_url",
        "trusted_base_url",
        "default_model",
        "connect_timeout_seconds",
        "read_timeout_seconds",
        "verify_tls",
        "credentials",
    }
    serialized = json.dumps({"config": asdict(result), "audit": audit.changed_fields})
    captured_logs = "\n".join(record.getMessage() for record in caplog.records)
    for marker in (client_id_marker, client_secret_marker):
        assert marker not in serialized
        assert marker not in captured_logs


def test_corrupt_credentials_fail_closed_without_secret_in_error(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    ciphertext_marker = "corrupt-ciphertext-marker"
    _clear_ai_environment(monkeypatch)
    _set_strong_secret_key(monkeypatch)
    db.add(
        SystemAISetting(
            id=1,
            enabled=True,
            default_base_url="https://corrupt.example.test/",
            trusted_base_url="https://corrupt.example.test/",
            default_model="corrupt-model",
            connect_timeout_seconds=2.0,
            read_timeout_seconds=20.0,
            verify_tls=True,
            access_client_id_ciphertext=f"v1:{ciphertext_marker}",
            access_client_secret_ciphertext=f"v1:{ciphertext_marker}",
            config_version=1,
        )
    )
    db.commit()

    with pytest.raises(CredentialCryptoError) as exc_info:
        get_effective_server_ai_config(db)

    rendered_error = str(exc_info.value)
    captured_logs = "\n".join(record.getMessage() for record in caplog.records)
    assert rendered_error == "凭据解密失败"
    assert ciphertext_marker not in rendered_error
    assert ciphertext_marker not in captured_logs


def test_account_target_and_model_override_server_defaults_without_overriding_security(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_ai_environment(monkeypatch)
    _set_strong_secret_key(monkeypatch)
    update_server_ai_config(
        db,
        values=_values(
            enabled=True,
            connect_timeout_seconds=8.0,
            read_timeout_seconds=88.0,
            verify_tls=False,
        ),
        credentials=CredentialUpdate(
            mode="replace_pair",
            client_id="runtime-client-marker",
            client_secret="runtime-secret-marker",
        ),
        actor_id=91,
    )
    user = User(
        username="task2-runtime-user",
        password_hash="x",
        display_name="Task 2",
        role="member",
        status="active",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    db.add(
        UserAISetting(
            user_id=user.id,
            active_provider="ollama",
            default_model="account-model",
            provider_configs=json.dumps(
                {
                    "ollama": {
                        "provider": "ollama",
                        "enabled": False,
                        "base_url": "http://account-target.local:11434",
                        "api_key": "",
                        "default_model": "account-provider-model",
                        "note": "",
                    }
                }
            ),
        )
    )
    db.commit()

    runtime = get_ollama_runtime_config(db, user)

    assert runtime.base_url == "http://account-target.local:11434"
    assert runtime.default_model == "account-model"
    assert runtime.enabled is True
    assert runtime.trusted_base_url == "https://db-ollama.example.test/"
    assert runtime.connect_timeout_seconds == 8.0
    assert runtime.read_timeout_seconds == 88.0
    assert runtime.verify_tls is False
    assert runtime.access_client_id == "runtime-client-marker"
    assert runtime.access_client_secret == "runtime-secret-marker"


def test_concurrent_reader_observes_only_complete_committed_versions(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_ai_environment(monkeypatch)
    _set_strong_secret_key(monkeypatch)
    engine = create_engine(
        f"sqlite:///{tmp_path / 'task2-concurrency.sqlite3'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    initial_session = sessions()
    update_server_ai_config(
        initial_session,
        values=_values(default_model="version-one", read_timeout_seconds=11.0),
        credentials=CredentialUpdate(mode="preserve"),
        actor_id=101,
    )
    initial_session.close()

    writer = sessions()
    reader = sessions()
    commit_started = threading.Event()
    allow_commit = threading.Event()
    writer_error: list[BaseException] = []

    @event.listens_for(writer, "before_commit")
    def pause_before_commit(_session: Session) -> None:
        commit_started.set()
        assert allow_commit.wait(timeout=5)

    def write_version_two() -> None:
        try:
            update_server_ai_config(
                writer,
                values=_values(default_model="version-two", read_timeout_seconds=22.0),
                credentials=CredentialUpdate(mode="preserve"),
                actor_id=102,
            )
        except BaseException as exc:  # pragma: no cover - asserted in parent thread
            writer_error.append(exc)

    thread = threading.Thread(target=write_version_two)
    thread.start()
    assert commit_started.wait(timeout=5)

    before_commit = get_effective_server_ai_config(reader)
    allow_commit.set()
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert writer_error == []
    reader.expire_all()
    after_commit = get_effective_server_ai_config(reader)

    assert (before_commit.config_version, before_commit.default_model, before_commit.read_timeout_seconds) == (
        1,
        "version-one",
        11.0,
    )
    assert (after_commit.config_version, after_commit.default_model, after_commit.read_timeout_seconds) == (
        2,
        "version-two",
        22.0,
    )
    writer.close()
    reader.close()
    engine.dispose()

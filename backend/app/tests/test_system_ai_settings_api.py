from __future__ import annotations

import json
from collections.abc import Generator
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import create_access_token
from app.db.session import get_db
from app.main import app
from app.models import SystemAISetting, SystemConfigAudit
from app.services.credential_crypto import CredentialCipher
from app.tests.conftest import make_user


_ADMIN_PASSWORD = "task-3-admin-password"
_UPGRADE_PASSWORD = "task-3-upgrade-password"
_STRONG_APP_KEY = "task-3-strong-application-key-value-000001"
_SECRET_MARKERS = (
    "task-3-admin-secret-marker",
    "task-3-upgrade-secret-marker",
    "task-3-client-id-secret-marker",
    "task-3-client-secret-marker",
)


@pytest.fixture(autouse=True)
def configured_environment(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    monkeypatch.delenv("HOME_LIBRARY_SERVER_CONFIG_TRUSTED_PROXY_IPS", raising=False)
    monkeypatch.delenv("SERVER_CONFIG_TRUSTED_PROXY_IPS", raising=False)
    monkeypatch.setenv("APP_SECRET_KEY", _STRONG_APP_KEY)
    monkeypatch.setenv("UPGRADE_PASSWORD", _UPGRADE_PASSWORD)
    monkeypatch.setenv("OLLAMA_ENABLED", "true")
    monkeypatch.setenv("OLLAMA_BASE_URL", "https://environment.example.test")
    monkeypatch.setenv("OLLAMA_TRUSTED_BASE_URL", "https://environment.example.test")
    monkeypatch.setenv("OLLAMA_DEFAULT_MODEL", "environment-model")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _auth_headers(db: Session, *, role: str = "admin") -> tuple[dict[str, str], int]:
    user, _ = make_user(db, role=role, password=_ADMIN_PASSWORD)
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}, user.id


def _valid_update(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "enabled": True,
        "default_base_url": "https://runtime.example.test/ollama",
        "trusted_base_url": "https://runtime.example.test",
        "default_model": "qwen3.5:4b",
        "connect_timeout_seconds": 5.0,
        "read_timeout_seconds": 180.0,
        "verify_tls": True,
        "admin_password": _ADMIN_PASSWORD,
        "upgrade_password": _UPGRADE_PASSWORD,
        "clear_access_credentials": False,
        "confirm_insecure_tls": False,
    }
    payload.update(overrides)
    return payload


def _put(client: TestClient, headers: dict[str, str], payload: dict[str, object]):
    return client.put("https://library.test/api/system/ai-config", headers=headers, json=payload)


def _delete(client: TestClient, headers: dict[str, str], payload: dict[str, object]):
    return client.request(
        "DELETE",
        "https://library.test/api/system/ai-config",
        headers=headers,
        json=payload,
    )


@contextmanager
def _transport_client(
    db: Session,
    *,
    direct_host: str,
    base_url: str = "http://library.test",
) -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(
            app,
            base_url=base_url,
            client=(direct_host, 43210),
            raise_server_exceptions=False,
        ) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


def test_server_ai_config_requires_admin_for_every_endpoint(
    client: TestClient,
    db: Session,
) -> None:
    member_headers, _ = _auth_headers(db, role="member")

    responses = (
        client.get("/api/system/ai-config", headers=member_headers),
        _put(client, member_headers, _valid_update()),
        _delete(
            client,
            member_headers,
            {
                "admin_password": _ADMIN_PASSWORD,
                "upgrade_password": _UPGRADE_PASSWORD,
                "confirm_reset": True,
            },
        ),
        client.post("/api/system/ai-config/test", headers=member_headers),
    )

    assert [response.status_code for response in responses] == [403, 403, 403, 403]
    assert db.query(SystemAISetting).count() == 0
    assert db.query(SystemConfigAudit).count() == 0


def test_get_returns_only_sanitized_config_and_credential_state(
    client: TestClient,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OLLAMA_CF_ACCESS_CLIENT_ID", _SECRET_MARKERS[2])
    monkeypatch.setenv("OLLAMA_CF_ACCESS_CLIENT_SECRET", _SECRET_MARKERS[3])
    get_settings.cache_clear()
    headers, _ = _auth_headers(db)

    response = client.get("/api/system/ai-config", headers=headers)

    assert response.status_code == 200
    assert response.json() == {
        "enabled": True,
        "default_base_url": "https://environment.example.test",
        "trusted_base_url": "https://environment.example.test",
        "default_model": "environment-model",
        "connect_timeout_seconds": 20.0,
        "read_timeout_seconds": 180.0,
        "verify_tls": True,
        "credential_state": {
            "access_client_id_configured": True,
            "access_client_secret_configured": True,
            "credentials_usable": True,
            "source": "environment",
        },
        "configuration_source": "environment",
        "config_version": 0,
    }
    serialized = response.text
    assert "ciphertext" not in serialized
    assert "access_client_id\"" not in serialized
    assert "access_client_secret\"" not in serialized
    for marker in _SECRET_MARKERS:
        assert marker not in serialized


def test_put_requires_current_admin_and_upgrade_password_atomically(
    client: TestClient,
    db: Session,
) -> None:
    headers, _ = _auth_headers(db)

    wrong_admin = _put(client, headers, _valid_update(admin_password="wrong-admin-password"))
    wrong_upgrade = _put(client, headers, _valid_update(upgrade_password="wrong-upgrade-password"))
    missing_admin = _put(client, headers, {k: v for k, v in _valid_update().items() if k != "admin_password"})
    missing_upgrade = _put(
        client,
        headers,
        {k: v for k, v in _valid_update().items() if k != "upgrade_password"},
    )

    assert wrong_admin.status_code == 403
    assert wrong_admin.json()["error"]["message"] == "管理员密码错误"
    assert wrong_upgrade.status_code == 403
    assert wrong_upgrade.json()["error"]["message"] == "服务器升级专用密码错误"
    assert missing_admin.status_code == 422
    assert missing_upgrade.status_code == 422
    assert db.query(SystemAISetting).count() == 0
    assert db.query(SystemConfigAudit).count() == 0


def test_put_rejects_when_upgrade_password_is_not_configured(
    client: TestClient,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("UPGRADE_PASSWORD", raising=False)
    monkeypatch.delenv("HOME_LIBRARY_UPGRADE_PASSWORD", raising=False)
    get_settings.cache_clear()
    headers, _ = _auth_headers(db)

    response = _put(client, headers, _valid_update())

    assert response.status_code == 400
    assert response.json()["error"]["message"] == "服务器二次认证未配置"
    assert db.query(SystemAISetting).count() == 0
    assert db.query(SystemConfigAudit).count() == 0


def test_put_preserves_blank_credentials_replaces_pair_and_rejects_partial_pair(
    client: TestClient,
    db: Session,
) -> None:
    headers, _ = _auth_headers(db)
    first = _put(
        client,
        headers,
        _valid_update(
            access_client_id=_SECRET_MARKERS[2],
            access_client_secret=_SECRET_MARKERS[3],
        ),
    )
    assert first.status_code == 200
    row = db.get(SystemAISetting, 1)
    assert row is not None
    original_ciphertexts = (
        row.access_client_id_ciphertext,
        row.access_client_secret_ciphertext,
    )
    audit_count = db.query(SystemConfigAudit).count()

    preserved = _put(
        client,
        headers,
        _valid_update(default_model="preserved-model", access_client_id="", access_client_secret=""),
    )
    assert preserved.status_code == 200
    db.expire_all()
    preserved_row = db.get(SystemAISetting, 1)
    assert preserved_row is not None
    assert (
        preserved_row.access_client_id_ciphertext,
        preserved_row.access_client_secret_ciphertext,
    ) == original_ciphertexts

    partial = _put(
        client,
        headers,
        _valid_update(access_client_id="one-sided-secret-marker"),
    )
    assert partial.status_code == 422
    db.expire_all()
    unchanged = db.get(SystemAISetting, 1)
    assert unchanged is not None
    assert unchanged.default_model == "preserved-model"
    assert db.query(SystemConfigAudit).count() == audit_count + 1

    clear_conflict = _put(
        client,
        headers,
        _valid_update(
            clear_access_credentials=True,
            access_client_id="conflicting-client-marker",
            access_client_secret="conflicting-secret-marker",
        ),
    )
    assert clear_conflict.status_code == 422
    assert db.query(SystemConfigAudit).count() == audit_count + 1

    cleared = _put(client, headers, _valid_update(clear_access_credentials=True))
    assert cleared.status_code == 200
    assert cleared.json()["credential_state"]["credentials_usable"] is False


@pytest.mark.filterwarnings("ignore:The HMAC key is.*:jwt.warnings.InsecureKeyLengthWarning")
def test_put_rejects_weak_app_secret_only_when_new_credentials_are_saved(
    client: TestClient,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_SECRET_KEY", "change-this-secret")
    get_settings.cache_clear()
    headers, _ = _auth_headers(db)

    non_sensitive = _put(client, headers, _valid_update(default_model="weak-key-preserve"))
    assert non_sensitive.status_code == 200
    rejected = _put(
        client,
        headers,
        _valid_update(
            default_model="must-not-commit",
            access_client_id="weak-key-client-marker",
            access_client_secret="weak-key-secret-marker",
        ),
    )

    assert rejected.status_code == 400
    assert rejected.json()["error"]["message"] == "服务器密钥强度不足，不能保存凭据"
    db.expire_all()
    row = db.get(SystemAISetting, 1)
    assert row is not None
    assert row.default_model == "weak-key-preserve"
    assert db.query(SystemConfigAudit).count() == 1


def test_delete_requires_explicit_confirmation_and_restores_environment(
    client: TestClient,
    db: Session,
) -> None:
    headers, _ = _auth_headers(db)
    saved = _put(client, headers, _valid_update(default_model="database-model"))
    assert saved.status_code == 200

    missing_confirmation = _delete(
        client,
        headers,
        {
            "admin_password": _ADMIN_PASSWORD,
            "upgrade_password": _UPGRADE_PASSWORD,
        },
    )
    false_confirmation = _delete(
        client,
        headers,
        {
            "admin_password": _ADMIN_PASSWORD,
            "upgrade_password": _UPGRADE_PASSWORD,
            "confirm_reset": False,
        },
    )

    assert missing_confirmation.status_code == 422
    assert false_confirmation.status_code == 422
    assert db.get(SystemAISetting, 1) is not None
    assert db.query(SystemConfigAudit).count() == 1

    restored = _delete(
        client,
        headers,
        {
            "admin_password": _ADMIN_PASSWORD,
            "upgrade_password": _UPGRADE_PASSWORD,
            "confirm_reset": True,
        },
    )

    assert restored.status_code == 200
    assert restored.json()["configuration_source"] == "environment"
    assert restored.json()["default_model"] == "environment-model"
    assert db.get(SystemAISetting, 1) is None
    assert [audit.action for audit in db.query(SystemConfigAudit).order_by(SystemConfigAudit.id)] == [
        "update",
        "reset",
    ]


def test_unconfigured_private_peer_cannot_assert_forwarded_https(
    db: Session,
) -> None:
    headers, _ = _auth_headers(db)

    with _transport_client(db, direct_host="10.0.0.8") as private_peer:
        response = private_peer.put(
            "/api/system/ai-config",
            headers={**headers, "X-Forwarded-Proto": "https"},
            json=_valid_update(),
        )

    assert response.status_code == 400
    assert db.query(SystemAISetting).count() == 0
    assert db.query(SystemConfigAudit).count() == 0


def test_configured_exact_trusted_proxy_can_assert_forwarded_https(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME_LIBRARY_SERVER_CONFIG_TRUSTED_PROXY_IPS", "10.0.0.8")
    get_settings.cache_clear()
    headers, _ = _auth_headers(db)

    with _transport_client(db, direct_host="10.0.0.8") as trusted_proxy:
        response = trusted_proxy.put(
            "/api/system/ai-config",
            headers={**headers, "X-Forwarded-Proto": "https"},
            json=_valid_update(default_model="configured-proxy-model"),
        )

    assert response.status_code == 200
    assert response.json()["default_model"] == "configured-proxy-model"


def test_malformed_or_overbroad_trusted_proxy_config_fails_safely(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "HOME_LIBRARY_SERVER_CONFIG_TRUSTED_PROXY_IPS",
        "10.0.0.0/8,*,not-an-ip,0.0.0.0,::",
    )
    get_settings.cache_clear()
    headers, _ = _auth_headers(db)

    with _transport_client(db, direct_host="10.0.0.8") as private_peer:
        response = private_peer.put(
            "/api/system/ai-config",
            headers={**headers, "X-Forwarded-Proto": "https"},
            json=_valid_update(),
        )

    assert response.status_code == 400
    assert db.query(SystemConfigAudit).count() == 0


def test_public_peer_spoofing_forwarded_headers_remains_rejected(db: Session) -> None:
    headers, _ = _auth_headers(db)

    with _transport_client(db, direct_host="8.8.8.8") as public_peer:
        response = public_peer.put(
            "/api/system/ai-config",
            headers={
                **headers,
                "X-Forwarded-For": "127.0.0.1",
                "X-Forwarded-Proto": "https",
                "Origin": "http://localhost:5173",
            },
            json=_valid_update(),
        )

    assert response.status_code == 400
    assert db.query(SystemConfigAudit).count() == 0


def test_loopback_browser_http_and_direct_https_remain_accepted(db: Session) -> None:
    headers, _ = _auth_headers(db)

    with _transport_client(db, direct_host="127.0.0.1") as loopback:
        local_origin = loopback.put(
            "/api/system/ai-config",
            headers={**headers, "Origin": "http://localhost:5173"},
            json=_valid_update(default_model="loopback-model"),
        )
        local_referer = loopback.put(
            "/api/system/ai-config",
            headers={**headers, "Referer": "http://127.0.0.1:5173/settings"},
            json=_valid_update(default_model="referer-model"),
        )
    assert local_origin.status_code == 200
    assert local_referer.status_code == 200

    with _transport_client(db, direct_host="203.0.113.9", base_url="https://library.test") as https:
        direct_https = https.put(
            "/api/system/ai-config",
            headers=headers,
            json=_valid_update(default_model="https-model"),
        )
    assert direct_https.status_code == 200


def test_api_validation_never_serializes_secret_values(
    client: TestClient,
    db: Session,
    caplog: pytest.LogCaptureFixture,
) -> None:
    headers, _ = _auth_headers(db)
    payload = _valid_update(
        admin_password=_SECRET_MARKERS[0],
        upgrade_password=_SECRET_MARKERS[1],
        access_client_id=_SECRET_MARKERS[2],
        access_client_secret=None,
        default_model="invalid model with spaces",
    )

    response = _put(client, headers, payload)

    assert response.status_code == 422
    serialized = response.text + "\n" + "\n".join(record.getMessage() for record in caplog.records)
    for marker in _SECRET_MARKERS:
        assert marker not in serialized
    assert db.query(SystemAISetting).count() == 0
    assert db.query(SystemConfigAudit).count() == 0


def test_put_requires_explicit_confirmation_before_disabling_tls(
    client: TestClient,
    db: Session,
) -> None:
    headers, _ = _auth_headers(db)

    rejected = _put(client, headers, _valid_update(verify_tls=False))
    accepted = _put(
        client,
        headers,
        _valid_update(verify_tls=False, confirm_insecure_tls=True),
    )

    assert rejected.status_code == 422
    assert accepted.status_code == 200
    assert accepted.json()["verify_tls"] is False
    assert db.query(SystemConfigAudit).count() == 1


def test_test_endpoint_rejects_ad_hoc_config_and_uses_non_generating_probe(
    client: TestClient,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.api.routes import system_ai_settings
    from app.schemas.ai import AIHealthResponse

    headers, admin_id = _auth_headers(db)
    probe_calls: list[tuple[int, bool]] = []

    async def fake_probe(session: Session, user, *, generate: bool) -> AIHealthResponse:
        assert session is db
        probe_calls.append((user.id, generate))
        return AIHealthResponse(status="healthy", message="AI 服务连接正常")

    monkeypatch.setattr(system_ai_settings, "_check_ollama", fake_probe)

    rejected = client.post(
        "/api/system/ai-config/test",
        headers=headers,
        json={
            "base_url": "https://ad-hoc.example.test",
            "access_client_secret": "ad-hoc-secret-marker",
        },
    )
    tested = client.post("/api/system/ai-config/test", headers=headers)

    assert rejected.status_code == 422
    assert tested.status_code == 200
    assert tested.json()["status"] == "healthy"
    assert probe_calls == [(admin_id, False)]


def test_auth_and_transport_failures_do_not_call_mutation_service(
    client: TestClient,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.api.routes import system_ai_settings

    headers, _ = _auth_headers(db)
    calls = 0

    def fail_if_called(*args, **kwargs):
        nonlocal calls
        calls += 1
        raise AssertionError("mutation service must not run")

    monkeypatch.setattr(system_ai_settings, "update_server_ai_config", fail_if_called)

    auth_failure = _put(client, headers, _valid_update(admin_password="wrong-password"))
    with _transport_client(db, direct_host="198.51.100.25") as remote:
        transport_failure = remote.put(
            "/api/system/ai-config",
            headers=headers,
            json=_valid_update(),
        )

    assert auth_failure.status_code == 403
    assert transport_failure.status_code == 400
    assert calls == 0
    assert db.query(SystemAISetting).count() == 0
    assert db.query(SystemConfigAudit).count() == 0


def test_saved_credentials_are_ciphertext_and_never_returned_or_logged(
    client: TestClient,
    db: Session,
    caplog: pytest.LogCaptureFixture,
) -> None:
    headers, _ = _auth_headers(db)

    response = _put(
        client,
        headers,
        _valid_update(
            access_client_id=_SECRET_MARKERS[2],
            access_client_secret=_SECRET_MARKERS[3],
        ),
    )

    assert response.status_code == 200
    row = db.get(SystemAISetting, 1)
    assert row is not None
    assert row.access_client_id_ciphertext not in {None, "", _SECRET_MARKERS[2]}
    assert row.access_client_secret_ciphertext not in {None, "", _SECRET_MARKERS[3]}
    cipher = CredentialCipher.from_secret_key(_STRONG_APP_KEY)
    assert cipher.decrypt(row.access_client_id_ciphertext) == _SECRET_MARKERS[2]
    assert cipher.decrypt(row.access_client_secret_ciphertext) == _SECRET_MARKERS[3]

    public_material = json.dumps(response.json(), ensure_ascii=False) + "\n" + "\n".join(
        record.getMessage() for record in caplog.records
    )
    assert row.access_client_id_ciphertext not in public_material
    assert row.access_client_secret_ciphertext not in public_material
    for marker in _SECRET_MARKERS:
        assert marker not in public_material

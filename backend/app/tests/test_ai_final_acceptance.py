"""Real persisted-account counterexamples from the final branch review."""
from __future__ import annotations

import json
import socket
from datetime import UTC, datetime

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import User, UserAIProviderCredential, UserAISetting
from app.services.ai_health_status_cache import provider_health_cache, provider_model_cache
from app.services.ai_provider_credential_service import set_provider_api_key
from app.services.ai_providers.base import AIProviderHealth, AIProviderModel, AIProviderModelList
from app.services.ai_setting_service import default_provider_configs


@pytest.fixture(autouse=True)
def isolated_runtime(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APP_SECRET_KEY", "final-review-synthetic-application-key-000001")
    for prefix in ("", "HOME_LIBRARY_"):
        for key, value in {
            "OLLAMA_ENABLED": "true", "OLLAMA_BASE_URL": "https://gateway.example.test",
            "OLLAMA_TRUSTED_BASE_URL": "https://gateway.example.test",
            "OLLAMA_DEFAULT_MODEL": "ollama-model", "OLLAMA_CF_ACCESS_CLIENT_ID": "",
            "OLLAMA_CF_ACCESS_CLIENT_SECRET": "",
        }.items():
            monkeypatch.setenv(prefix + key, value)
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: [
        (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("93.184.216.34", 443))
    ])
    get_settings.cache_clear()
    provider_health_cache.invalidate_all()
    provider_model_cache.invalidate_all()
    yield
    get_settings.cache_clear()
    provider_health_cache.invalidate_all()
    provider_model_cache.invalidate_all()


def seed(db: Session, *, role: str = "member", active: str = "ollama", enabled: bool = True):
    user = db.query(User).filter_by(role=role).one()
    configs = default_provider_configs()
    configs["ollama"].update(enabled=True, base_url="https://gateway.example.test", default_model="ollama-model")
    configs["openai"].update(enabled=active == "openai", default_model="cloud-model")
    row = UserAISetting(user_id=user.id, ai_enabled=enabled, active_provider=active,
                        default_model=configs[active]["default_model"], provider_configs=json.dumps(configs))
    db.add(row)
    db.commit()
    return user, row


def recording_factory(monkeypatch: pytest.MonkeyPatch):
    created = []

    class Client:
        def __init__(self, runtime):
            self.runtime = runtime
            created.append(runtime)

        async def test_connection(self):
            return AIProviderHealth(provider=self.runtime.provider, status="available", message="连接正常",
                                    checked_at=datetime.now(UTC), effective_model=self.runtime.default_model,
                                    safe_base_url=self.runtime.base_url, credential_state=self.runtime.credential_state)

        async def list_models(self):
            return AIProviderModelList(capability="supported", models=(
                AIProviderModel(provider=self.runtime.provider, id=self.runtime.default_model, name="模型"),
            ))

        async def generate_text(self, prompt: str, model: str | None = None):
            assert prompt and model == self.runtime.default_model
            return "ok"

    monkeypatch.setattr("app.services.ai_provider_runtime.create_ai_provider_client", Client)
    return created


@pytest.mark.parametrize("operation", ["test", "models", "generate-test"])
def test_final_draft_can_test_nonactive_unsaved_provider_without_persisting(
    client: TestClient, db: Session, member_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch, operation: str,
):
    user, row = seed(db)
    before = row.provider_configs
    created = recording_factory(monkeypatch)
    response = client.post(f"/api/ai/providers/openai/{operation}", headers=member_headers, json={
        "provider": "openai", "base_url": "https://draft.example.test/v1", "model": "draft-model",
        "api_key": "synthetic-draft-key-marker",
    })
    assert response.status_code == 200
    assert response.json()["provider"] == "openai"
    assert len(created) == 1
    assert created[0].get_credential_value() == "synthetic-draft-key-marker"
    assert created[0].default_model == "draft-model"
    db.expire_all()
    assert (row.active_provider, row.default_model, row.provider_configs) == ("ollama", "ollama-model", before)
    assert db.query(UserAIProviderCredential).filter_by(user_id=user.id).count() == 0
    assert "synthetic-draft-key-marker" not in response.text


@pytest.mark.parametrize("operation", ["test", "models", "generate-test"])
def test_final_replacement_draft_repairs_unusable_saved_key_and_url_without_writing(
    client: TestClient, db: Session, member_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch, operation: str,
):
    user, row = seed(db, active="openai")
    configs = json.loads(row.provider_configs)
    configs["openai"]["base_url"] = "http://127.0.0.1/private"
    row.provider_configs = json.dumps(configs)
    set_provider_api_key(db, user.id, "openai", "synthetic-old-key")
    credential = db.query(UserAIProviderCredential).filter_by(user_id=user.id, provider="openai").one()
    credential.api_key_ciphertext = "unusable-synthetic-ciphertext"
    db.commit()
    created = recording_factory(monkeypatch)
    response = client.post(f"/api/ai/providers/openai/{operation}", headers=member_headers, json={
        "base_url": "https://repaired.example.test/v1", "model": "repaired-model",
        "api_key": "synthetic-replacement-key-marker",
    })
    assert response.status_code == 200
    assert len(created) == 1
    assert created[0].get_credential_value() == "synthetic-replacement-key-marker"
    assert created[0].base_url == "https://repaired.example.test/v1"
    db.expire_all()
    assert credential.api_key_ciphertext == "unusable-synthetic-ciphertext"
    assert json.loads(row.provider_configs)["openai"]["base_url"] == "http://127.0.0.1/private"


@pytest.mark.parametrize("operation", ["test", "models", "generate-test"])
def test_final_real_account_off_rejects_even_complete_draft_before_factory(
    client: TestClient, db: Session, member_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch, operation: str,
):
    seed(db, enabled=False)
    created = recording_factory(monkeypatch)
    response = client.post(f"/api/ai/providers/openai/{operation}", headers=member_headers, json={
        "provider": "openai", "base_url": "https://draft.example.test/v1", "model": "draft-model",
        "api_key": "synthetic-draft-key-marker",
    })
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "AI_SERVICE_DISABLED"
    assert created == []


@pytest.mark.parametrize("enabled,active,expected", [(False, "ollama", 503), (True, "openai", 422)])
@pytest.mark.parametrize("generate", [False, True])
def test_final_legacy_diagnostic_respects_account_off_and_cloud_selection(
    client: TestClient, db: Session, admin_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch,
    enabled: bool, active: str, expected: int, generate: bool,
):
    from app.api.routes import ai as routes
    user, _ = seed(db, role="admin", active=active, enabled=enabled)
    if active == "openai":
        set_provider_api_key(db, user.id, active, "synthetic-saved-key")
        db.commit()
    created = []
    calls = []

    def handler(request: httpx.Request):
        calls.append(request.url.path)
        return httpx.Response(200, json={"version": "test", "models": [], "response": "ok"})

    real_client = routes.OllamaClient

    def create(runtime):
        created.append(True)
        return real_client(runtime, transport=httpx.MockTransport(handler))

    monkeypatch.setattr(routes, "OllamaClient", create)
    response = client.post("/api/ai/test-connection", headers=admin_headers, json={"generate": generate})
    assert response.status_code == expected
    assert response.json()["error"]["code"] == ("AI_SERVICE_DISABLED" if not enabled else "AI_CONFIG_INVALID")
    assert calls == created == []


def test_final_partial_config_preserves_selection_but_applies_explicit_values(
    client: TestClient, db: Session, member_headers: dict[str, str],
):
    user, row = seed(db, active="openai")
    set_provider_api_key(db, user.id, "openai", "synthetic-saved-key")
    db.commit()
    for payload, enabled in [({"ai_enabled": False}, False),
                             ({"providers": [{"provider": "openai", "note": "仅更新备注"}]}, False),
                             ({"ai_enabled": True}, True)]:
        response = client.put("/api/ai/config", headers=member_headers, json=payload)
        assert response.status_code == 200
        assert (response.json()["ai_enabled"], response.json()["active_provider"], response.json()["default_model"]) == (
            enabled, "openai", "cloud-model",
        )
        db.expire_all()
        assert (row.ai_enabled, row.active_provider, row.default_model) == (enabled, "openai", "cloud-model")
    response = client.put("/api/ai/config", headers=member_headers, json={
        "ai_enabled": False, "active_provider": "ollama", "default_model": "",
    })
    assert response.status_code == 200
    assert (response.json()["active_provider"], response.json()["default_model"]) == ("ollama", "")

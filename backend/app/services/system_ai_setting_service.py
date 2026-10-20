from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.ollama_url import normalize_ollama_base_url
from app.models.system_ai_setting import SystemAISetting
from app.models.system_config_audit import SystemConfigAudit
from app.services.credential_crypto import (
    CredentialCipher,
    CredentialCryptoError,
    is_production_secret_key,
)


ConfigurationSource = Literal["database", "environment", "default"]
CredentialMode = Literal["preserve", "replace_pair", "clear_pair"]

_AI_SETTING_FIELDS = frozenset(
    {
        "ollama_enabled",
        "ollama_base_url",
        "ollama_trusted_base_url",
        "ollama_default_model",
        "ollama_connect_timeout_seconds",
        "ollama_read_timeout_seconds",
        "ollama_verify_tls",
        "ollama_cf_access_client_id",
        "ollama_cf_access_client_secret",
    }
)
_VALUE_FIELD_NAMES = (
    "enabled",
    "default_base_url",
    "trusted_base_url",
    "default_model",
    "connect_timeout_seconds",
    "read_timeout_seconds",
    "verify_tls",
)


@dataclass(frozen=True)
class ServerAICredentialState:
    configured: bool
    source: ConfigurationSource


@dataclass(frozen=True)
class ServerAIConfig:
    enabled: bool
    default_base_url: str
    trusted_base_url: str
    default_model: str
    connect_timeout_seconds: float
    read_timeout_seconds: float
    verify_tls: bool
    credential_state: ServerAICredentialState
    configuration_source: ConfigurationSource
    config_version: int


@dataclass(frozen=True)
class ServerAIConfigUpdateValues:
    enabled: bool
    default_base_url: str
    trusted_base_url: str
    default_model: str
    connect_timeout_seconds: float
    read_timeout_seconds: float
    verify_tls: bool

    def __post_init__(self) -> None:
        model = self.default_model.strip()
        if not model:
            raise ValueError("默认模型不能为空")
        for value in (self.connect_timeout_seconds, self.read_timeout_seconds):
            if not math.isfinite(value) or value <= 0:
                raise ValueError("超时时间必须为正数")
        object.__setattr__(self, "default_base_url", normalize_ollama_base_url(self.default_base_url))
        object.__setattr__(self, "trusted_base_url", normalize_ollama_base_url(self.trusted_base_url))
        object.__setattr__(self, "default_model", model)


@dataclass(frozen=True)
class CredentialUpdate:
    mode: CredentialMode
    client_id: str = ""
    client_secret: str = ""

    def __post_init__(self) -> None:
        if self.mode not in {"preserve", "replace_pair", "clear_pair"}:
            raise ValueError("不支持的凭据更新模式")
        if self.mode == "replace_pair":
            if not self.client_id or not self.client_secret:
                raise ValueError("必须同时提供完整凭据")
            return
        if self.client_id or self.client_secret:
            raise ValueError("当前模式不接受凭据值")


@dataclass(frozen=True)
class _EffectiveServerAIState:
    config: ServerAIConfig
    client_id: str
    client_secret: str


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _environment_source(settings: Settings) -> ConfigurationSource:
    return "environment" if settings.model_fields_set & _AI_SETTING_FIELDS else "default"


def _validate_credential_pair(client_id: str, client_secret: str) -> tuple[str, str]:
    if bool(client_id) != bool(client_secret):
        raise CredentialCryptoError("凭据配置不完整")
    return client_id, client_secret


def _environment_state(settings: Settings) -> _EffectiveServerAIState:
    source = _environment_source(settings)
    client_id, client_secret = _validate_credential_pair(
        settings.ollama_cf_access_client_id,
        settings.ollama_cf_access_client_secret,
    )
    config = ServerAIConfig(
        enabled=settings.ollama_enabled,
        default_base_url=normalize_ollama_base_url(settings.ollama_base_url),
        trusted_base_url=normalize_ollama_base_url(settings.ollama_trusted_base_url),
        default_model=settings.ollama_default_model.strip(),
        connect_timeout_seconds=settings.ollama_connect_timeout_seconds,
        read_timeout_seconds=settings.ollama_read_timeout_seconds,
        verify_tls=settings.ollama_verify_tls,
        credential_state=ServerAICredentialState(configured=bool(client_id), source=source),
        configuration_source=source,
        config_version=0,
    )
    return _EffectiveServerAIState(config=config, client_id=client_id, client_secret=client_secret)


def _database_state(row: SystemAISetting, settings: Settings) -> _EffectiveServerAIState:
    if not row.default_base_url or not row.trusted_base_url or not row.default_model.strip():
        raise ValueError("服务器 AI 配置无效")
    id_ciphertext = row.access_client_id_ciphertext
    secret_ciphertext = row.access_client_secret_ciphertext
    if bool(id_ciphertext) != bool(secret_ciphertext):
        raise CredentialCryptoError("凭据配置不完整")
    client_id = ""
    client_secret = ""
    if id_ciphertext and secret_ciphertext:
        cipher = CredentialCipher.from_secret_key(settings.secret_key)
        client_id = cipher.decrypt(id_ciphertext)
        client_secret = cipher.decrypt(secret_ciphertext)
        _validate_credential_pair(client_id, client_secret)
    config = ServerAIConfig(
        enabled=row.enabled,
        default_base_url=normalize_ollama_base_url(row.default_base_url),
        trusted_base_url=normalize_ollama_base_url(row.trusted_base_url),
        default_model=row.default_model.strip(),
        connect_timeout_seconds=row.connect_timeout_seconds,
        read_timeout_seconds=row.read_timeout_seconds,
        verify_tls=row.verify_tls,
        credential_state=ServerAICredentialState(configured=bool(client_id), source="database"),
        configuration_source="database",
        config_version=row.config_version,
    )
    return _EffectiveServerAIState(config=config, client_id=client_id, client_secret=client_secret)


def _get_effective_server_ai_state(db: Session) -> _EffectiveServerAIState:
    settings = get_settings()
    row = db.get(SystemAISetting, 1)
    if row is None:
        return _environment_state(settings)
    return _database_state(row, settings)


def get_effective_server_ai_config(db: Session) -> ServerAIConfig:
    return _get_effective_server_ai_state(db).config


def _encrypt_pair(settings: Settings, client_id: str, client_secret: str) -> tuple[str, str]:
    _validate_credential_pair(client_id, client_secret)
    if not is_production_secret_key(settings.secret_key):
        raise CredentialCryptoError("服务器密钥强度不足，不能保存凭据")
    cipher = CredentialCipher.from_secret_key(settings.secret_key)
    return cipher.encrypt(client_id), cipher.encrypt(client_secret)


def update_server_ai_config(
    db: Session,
    *,
    values: ServerAIConfigUpdateValues,
    credentials: CredentialUpdate,
    actor_id: int,
) -> ServerAIConfig:
    try:
        settings = get_settings()
        previous = _get_effective_server_ai_state(db)
        row = db.get(SystemAISetting, 1)
        version = (row.config_version if row is not None else 0) + 1

        if credentials.mode == "replace_pair":
            id_ciphertext, secret_ciphertext = _encrypt_pair(
                settings, credentials.client_id, credentials.client_secret,
            )
        elif credentials.mode == "clear_pair":
            id_ciphertext = None
            secret_ciphertext = None
        elif row is not None:
            id_ciphertext = row.access_client_id_ciphertext
            secret_ciphertext = row.access_client_secret_ciphertext
        elif previous.client_id and previous.client_secret:
            id_ciphertext, secret_ciphertext = _encrypt_pair(
                settings, previous.client_id, previous.client_secret,
            )
        else:
            id_ciphertext = None
            secret_ciphertext = None

        if row is None:
            row = SystemAISetting(id=1)
        row.enabled = values.enabled
        row.default_base_url = values.default_base_url
        row.trusted_base_url = values.trusted_base_url
        row.default_model = values.default_model
        row.connect_timeout_seconds = values.connect_timeout_seconds
        row.read_timeout_seconds = values.read_timeout_seconds
        row.verify_tls = values.verify_tls
        row.access_client_id_ciphertext = id_ciphertext
        row.access_client_secret_ciphertext = secret_ciphertext
        row.config_version = version
        row.updated_by = actor_id
        row.updated_at = _now()
        db.add(row)

        changed_fields = [
            name for name in _VALUE_FIELD_NAMES if getattr(previous.config, name) != getattr(values, name)
        ]
        if credentials.mode != "preserve":
            changed_fields.append("credentials")
        db.add(
            SystemConfigAudit(
                action="update",
                changed_fields=changed_fields,
                config_version=version,
                created_by=actor_id,
            )
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return get_effective_server_ai_config(db)


def reset_server_ai_config(db: Session, *, actor_id: int) -> ServerAIConfig:
    try:
        row = db.get(SystemAISetting, 1)
        version = (row.config_version if row is not None else 0) + 1
        if row is not None:
            db.delete(row)
        db.add(
            SystemConfigAudit(
                action="reset",
                changed_fields=[*_VALUE_FIELD_NAMES, "credentials"],
                config_version=version,
                created_by=actor_id,
            )
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return get_effective_server_ai_config(db)

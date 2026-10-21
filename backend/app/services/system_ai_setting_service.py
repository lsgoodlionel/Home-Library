from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, attributes
from sqlalchemy.orm.exc import StaleDataError

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
    access_client_id_configured: bool
    access_client_secret_configured: bool
    credentials_usable: bool
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


def _environment_credentials(
    settings: Settings,
) -> tuple[ServerAICredentialState, str, str]:
    source = _environment_source(settings)
    client_id = settings.ollama_cf_access_client_id
    client_secret = settings.ollama_cf_access_client_secret
    id_configured = bool(client_id)
    secret_configured = bool(client_secret)
    usable = id_configured and secret_configured
    state = ServerAICredentialState(
        access_client_id_configured=id_configured,
        access_client_secret_configured=secret_configured,
        credentials_usable=usable,
        source=source,
    )
    return state, client_id if usable else "", client_secret if usable else ""


def _environment_state(settings: Settings) -> _EffectiveServerAIState:
    source = _environment_source(settings)
    credential_state, client_id, client_secret = _environment_credentials(settings)
    config = ServerAIConfig(
        enabled=settings.ollama_enabled,
        default_base_url=normalize_ollama_base_url(settings.ollama_base_url),
        trusted_base_url=normalize_ollama_base_url(settings.ollama_trusted_base_url),
        default_model=settings.ollama_default_model.strip(),
        connect_timeout_seconds=settings.ollama_connect_timeout_seconds,
        read_timeout_seconds=settings.ollama_read_timeout_seconds,
        verify_tls=settings.ollama_verify_tls,
        credential_state=credential_state,
        configuration_source=source,
        config_version=0,
    )
    return _EffectiveServerAIState(config=config, client_id=client_id, client_secret=client_secret)


def _database_state(row: SystemAISetting, settings: Settings) -> _EffectiveServerAIState:
    if not row.default_base_url or not row.trusted_base_url or not row.default_model.strip():
        raise ValueError("服务器 AI 配置无效")
    id_ciphertext = row.access_client_id_ciphertext
    secret_ciphertext = row.access_client_secret_ciphertext
    if id_ciphertext is None and secret_ciphertext is None:
        credential_state, client_id, client_secret = _environment_credentials(settings)
    elif id_ciphertext == "" and secret_ciphertext == "":
        credential_state = ServerAICredentialState(
            access_client_id_configured=False,
            access_client_secret_configured=False,
            credentials_usable=False,
            source="database",
        )
        client_id = ""
        client_secret = ""
    else:
        id_configured = bool(id_ciphertext)
        secret_configured = bool(secret_ciphertext)
        client_id = ""
        client_secret = ""
        usable = False
        if id_configured and secret_configured:
            try:
                cipher = CredentialCipher.from_secret_key(settings.secret_key)
                client_id = cipher.decrypt(id_ciphertext)
                client_secret = cipher.decrypt(secret_ciphertext)
                usable = bool(client_id) and bool(client_secret)
            except CredentialCryptoError:
                client_id = ""
                client_secret = ""
        credential_state = ServerAICredentialState(
            access_client_id_configured=id_configured,
            access_client_secret_configured=secret_configured,
            credentials_usable=usable,
            source="database",
        )
        if not usable:
            client_id = ""
            client_secret = ""
    config = ServerAIConfig(
        enabled=row.enabled,
        default_base_url=normalize_ollama_base_url(row.default_base_url),
        trusted_base_url=normalize_ollama_base_url(row.trusted_base_url),
        default_model=row.default_model.strip(),
        connect_timeout_seconds=row.connect_timeout_seconds,
        read_timeout_seconds=row.read_timeout_seconds,
        verify_tls=row.verify_tls,
        credential_state=credential_state,
        configuration_source="database",
        config_version=row.config_version,
    )
    return _EffectiveServerAIState(config=config, client_id=client_id, client_secret=client_secret)


def _get_effective_server_ai_state(db: Session) -> _EffectiveServerAIState:
    settings = get_settings()
    row = db.get(SystemAISetting, 1, populate_existing=True)
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


def _update_server_ai_config_outcome(
    db: Session,
    *,
    values: ServerAIConfigUpdateValues,
    credentials: CredentialUpdate,
    actor_id: int,
) -> ServerAIConfig | Exception:
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
            id_ciphertext = ""
            secret_ciphertext = ""
        elif row is not None:
            id_ciphertext = row.access_client_id_ciphertext
            secret_ciphertext = row.access_client_secret_ciphertext
        else:
            id_ciphertext = None
            secret_ciphertext = None

        existing_row = row is not None
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
        if existing_row:
            # Write the whole validated snapshot, including unchanged fields. The
            # mapper's version predicate rejects a concurrent update or reset.
            for name in (
                *_VALUE_FIELD_NAMES,
                "access_client_id_ciphertext",
                "access_client_secret_ciphertext",
            ):
                attributes.flag_modified(row, name)
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
        return get_effective_server_ai_config(db)
    except Exception as exc:
        return _safe_write_failure(db, exc)


def _reset_server_ai_config_outcome(db: Session, *, actor_id: int) -> ServerAIConfig | Exception:
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
        return get_effective_server_ai_config(db)
    except Exception as exc:
        return _safe_write_failure(db, exc)


class ServerAIConfigConflictError(Exception):
    """A concurrent writer won; the caller must reload before retrying."""


class ServerAIConfigWriteError(Exception):
    """A stable database failure carrying no original exception or parameters."""


def _safe_write_failure(db: Session, error: Exception) -> Exception:
    # The original exception, Session and ORM objects never leave the outcome frame.
    # Constructing a new exception does not link its context; only raising does.
    try:
        db.rollback()
    except Exception:
        try:
            db.invalidate()
        except Exception:
            pass
        return ServerAIConfigWriteError("服务器 AI 配置保存失败，请稍后重试")
    if isinstance(error, StaleDataError) or (
        isinstance(error, IntegrityError)
        and (
            getattr(error.orig, "sqlite_errorcode", None) in {1555, 2067}
            or getattr(error.orig, "pgcode", None) == "23505"
        )
    ):
        return ServerAIConfigConflictError("服务器 AI 配置已被其他请求修改，请刷新后重试")
    if isinstance(error, CredentialCryptoError):
        message = "凭据加密失败"
        if error.args == ("服务器密钥强度不足，不能保存凭据",):
            message = "服务器密钥强度不足，不能保存凭据"
        return CredentialCryptoError(message)
    if isinstance(error, ValueError):
        return ValueError("服务器 AI 配置无效")
    return ServerAIConfigWriteError("服务器 AI 配置保存失败，请稍后重试")


def update_server_ai_config(
    db: Session,
    *,
    values: ServerAIConfigUpdateValues,
    credentials: CredentialUpdate,
    actor_id: int,
) -> ServerAIConfig:
    outcome = _update_server_ai_config_outcome(
        db, values=values, credentials=credentials, actor_id=actor_id,
    )
    del db, values, credentials
    if isinstance(outcome, Exception):
        raise outcome from None
    return outcome


def reset_server_ai_config(db: Session, *, actor_id: int) -> ServerAIConfig:
    outcome = _reset_server_ai_config_outcome(db, actor_id=actor_id)
    del db
    if isinstance(outcome, Exception):
        raise outcome from None
    return outcome

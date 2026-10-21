from __future__ import annotations

import hashlib
import json

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.ollama_url import InvalidOllamaBaseURL, normalize_ollama_base_url
from app.models.user import User
from app.models.user_ai_setting import UserAISetting
from app.services.ai_provider_credential_service import (
    get_provider_api_key,
    get_provider_credential_state,
)
from app.services.ai_provider_url import (
    normalize_cloud_provider_origin,
    validate_cloud_provider_url,
)
from app.services.ai_providers.base import (
    AIProviderClient,
    AIProviderDisabledError,
    AIProviderInvalidConfigurationError,
    AIProviderRuntime,
    OllamaProviderRuntimeOptions,
)
from app.services.ai_providers.gemini import GeminiProviderClient
from app.services.ai_providers.ollama import OllamaProviderClient
from app.services.ai_providers.openai_compatible import (
    OPENAI_COMPATIBLE_DESCRIPTORS,
    OpenAICompatibleProviderClient,
)
from app.services.ai_setting_service import (
    default_provider_configs,
    normalize_access_origin,
)
from app.services.credential_crypto import CredentialCryptoError
from app.services.system_ai_setting_service import _get_effective_server_ai_state


_CLOUD_PROVIDERS = frozenset({*OPENAI_COMPATIBLE_DESCRIPTORS, "gemini"})
_KNOWN_PROVIDERS = frozenset({"ollama", *_CLOUD_PROVIDERS})


def _invalid_configuration() -> AIProviderInvalidConfigurationError:
    return AIProviderInvalidConfigurationError()


def _strict_runtime_provider_config(
    raw: str,
    active_provider: str,
    account_model: str,
) -> dict[str, object]:
    try:
        configs = json.loads(raw)
    except (TypeError, json.JSONDecodeError, RecursionError):
        raise _invalid_configuration() from None
    if not isinstance(configs, dict):
        raise _invalid_configuration() from None
    config = configs.get(active_provider)
    if not isinstance(config, dict) or config.get("provider") != active_provider:
        raise _invalid_configuration() from None
    enabled = config.get("enabled")
    base_url = config.get("base_url")
    provider_model = config.get("default_model")
    if (
        not isinstance(enabled, bool)
        or not isinstance(base_url, str)
        or not base_url
        or base_url != base_url.strip()
        or not isinstance(provider_model, str)
        or not provider_model
        or provider_model != provider_model.strip()
        or not account_model
        or account_model != account_model.strip()
        or account_model != provider_model
    ):
        raise _invalid_configuration() from None
    return config


def _account_selection(
    db: Session,
    user: User,
) -> tuple[str, str, dict[str, object]]:
    setting = db.query(UserAISetting).filter_by(user_id=user.id).first()
    if setting is None:
        configs = default_provider_configs()
        server = _get_effective_server_ai_state(db).config
        configs["ollama"]["base_url"] = server.default_base_url
        configs["ollama"]["default_model"] = server.default_model
        active_provider = "ollama"
        account_model = str(configs[active_provider]["default_model"])
        ai_enabled = True
        config = configs[active_provider]
    else:
        active_provider = setting.active_provider
        account_model = setting.default_model
        ai_enabled = setting.ai_enabled

    if not ai_enabled:
        raise AIProviderDisabledError() from None
    if active_provider not in _KNOWN_PROVIDERS:
        raise _invalid_configuration() from None
    if setting is not None:
        config = _strict_runtime_provider_config(
            setting.provider_configs,
            active_provider,
            account_model,
        )
    if config.get("enabled") is not True:
        raise _invalid_configuration() from None
    provider_model = config.get("default_model")
    if not isinstance(provider_model, str):
        raise _invalid_configuration() from None
    return active_provider, provider_model, config


def _credential_state_from_server(state: object) -> str:
    credentials = state.config.credential_state  # type: ignore[attr-defined]
    if credentials.credentials_usable:
        return "configured"
    if credentials.access_client_id_configured or credentials.access_client_secret_configured:
        return "unusable"
    return "missing"


def _resolve_ollama_runtime(
    db: Session,
    config: dict[str, object],
    model: str,
) -> AIProviderRuntime:
    server_state = _get_effective_server_ai_state(db)
    server = server_state.config
    if not server.enabled:
        raise AIProviderDisabledError() from None
    try:
        base_url = normalize_ollama_base_url(
            str(config.get("base_url") or server.default_base_url)
        )
    except (InvalidOllamaBaseURL, ValueError):
        raise _invalid_configuration() from None

    trusted_origin = normalize_access_origin(server.trusted_base_url)
    uses_access = (
        bool(server_state.client_id and server_state.client_secret)
        and trusted_origin is not None
        and normalize_access_origin(base_url) == trusted_origin
    )
    credential_state = _credential_state_from_server(server_state)
    if credential_state == "unusable" and normalize_access_origin(base_url) == trusted_origin:
        raise _invalid_configuration() from None
    return AIProviderRuntime(
        provider="ollama",
        enabled=True,
        base_url=base_url,
        default_model=model,
        credential_state=credential_state,  # type: ignore[arg-type]
        connect_timeout_seconds=server.connect_timeout_seconds,
        read_timeout_seconds=server.read_timeout_seconds,
        verify_tls=server.verify_tls,
        ollama=OllamaProviderRuntimeOptions(
            trusted_base_url=server.trusted_base_url,
            access_client_id=server_state.client_id or None,
            access_client_secret=server_state.client_secret or None,
            uses_access=uses_access,
            config_version=server.config_version,
        ),
    )


def _resolve_cloud_runtime(
    db: Session,
    user: User,
    provider: str,
    config: dict[str, object],
    model: str,
) -> AIProviderRuntime:
    state = get_provider_credential_state(db, user.id, provider)
    if state != "configured":
        raise _invalid_configuration() from None
    try:
        credential = get_provider_api_key(db, user.id, provider)
    except CredentialCryptoError:
        raise _invalid_configuration() from None
    if not credential:
        raise _invalid_configuration() from None

    settings = get_settings()
    try:
        base_url = validate_cloud_provider_url(
            str(config.get("base_url") or ""),
            allowed_private_origins=settings.ai_provider_allowed_private_origins,
        )
    except AIProviderInvalidConfigurationError:
        credential = ""
        raise _invalid_configuration() from None
    runtime = AIProviderRuntime(
        provider=provider,
        enabled=True,
        base_url=base_url,
        default_model=model,
        credential_state="configured",
        credential=credential,
    )
    credential = ""
    return runtime


def resolve_ai_provider_runtime(db: Session, user: User) -> AIProviderRuntime:
    provider, model, config = _account_selection(db, user)
    if provider == "ollama":
        return _resolve_ollama_runtime(db, config, model)
    return _resolve_cloud_runtime(db, user, provider, config, model)


def _validate_cloud_factory_runtime(runtime: AIProviderRuntime) -> None:
    if (
        runtime.ollama is not None
        or runtime.credential_state != "configured"
        or not runtime.get_credential_value()
    ):
        raise _invalid_configuration() from None
    try:
        validated_url = validate_cloud_provider_url(
            runtime.base_url,
            allowed_private_origins=get_settings().ai_provider_allowed_private_origins,
        )
    except AIProviderInvalidConfigurationError:
        raise _invalid_configuration() from None
    if validated_url != runtime.base_url:
        raise _invalid_configuration() from None


def _validate_ollama_factory_runtime(runtime: AIProviderRuntime) -> None:
    options = runtime.ollama
    if options is None or runtime.credential is not None:
        raise _invalid_configuration() from None
    try:
        normalized_base_url = normalize_ollama_base_url(runtime.base_url)
        normalized_trusted_origin = normalize_cloud_provider_origin(
            options.trusted_base_url
        )
    except (InvalidOllamaBaseURL, AIProviderInvalidConfigurationError, ValueError):
        raise _invalid_configuration() from None
    trusted_origin = normalize_access_origin(options.trusted_base_url)
    if (
        normalized_base_url != runtime.base_url
        or normalized_trusted_origin != options.trusted_base_url
        or trusted_origin is None
    ):
        raise _invalid_configuration() from None

    client_id, client_secret = options.get_access_credentials()
    has_client_id = bool(client_id)
    has_client_secret = bool(client_secret)
    if has_client_id != has_client_secret:
        raise _invalid_configuration() from None
    pair_complete = has_client_id and has_client_secret
    if pair_complete != (runtime.credential_state == "configured"):
        if not (
            not pair_complete
            and runtime.credential_state == "unusable"
        ):
            raise _invalid_configuration() from None
    if runtime.credential_state not in {"missing", "configured", "unusable"}:
        raise _invalid_configuration() from None

    effective_origin = normalize_access_origin(runtime.base_url)
    exact_trusted_origin = effective_origin is not None and effective_origin == trusted_origin
    expected_uses_access = pair_complete and exact_trusted_origin
    if options.uses_access is not expected_uses_access:
        raise _invalid_configuration() from None
    if runtime.credential_state == "unusable" and exact_trusted_origin:
        raise _invalid_configuration() from None


def create_ai_provider_client(runtime: AIProviderRuntime) -> AIProviderClient:
    if not runtime.enabled:
        raise AIProviderDisabledError() from None
    if (
        not runtime.base_url
        or runtime.base_url != runtime.base_url.strip()
        or not runtime.default_model
        or runtime.default_model != runtime.default_model.strip()
    ):
        raise _invalid_configuration() from None
    if runtime.provider == "ollama":
        _validate_ollama_factory_runtime(runtime)
        return OllamaProviderClient(runtime)
    if runtime.provider == "gemini":
        _validate_cloud_factory_runtime(runtime)
        return GeminiProviderClient(runtime)
    if runtime.provider in OPENAI_COMPATIBLE_DESCRIPTORS:
        _validate_cloud_factory_runtime(runtime)
        return OpenAICompatibleProviderClient(runtime)
    raise _invalid_configuration() from None


def provider_runtime_fingerprint(runtime: AIProviderRuntime) -> str:
    safe = runtime.to_safe_dict()
    payload = json.dumps(safe, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


__all__ = [
    "create_ai_provider_client",
    "provider_runtime_fingerprint",
    "resolve_ai_provider_runtime",
]

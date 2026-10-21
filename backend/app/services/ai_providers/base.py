from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Awaitable, Callable, Literal, Protocol, TypeVar, runtime_checkable

import httpx
from pydantic import BaseModel, SecretStr

T = TypeVar("T", bound=BaseModel)
ResultT = TypeVar("ResultT")
CredentialState = Literal["missing", "configured", "unusable"]
ProviderHealthStatus = Literal["available", "unavailable", "unchecked"]


@dataclass(frozen=True, slots=True)
class OllamaProviderRuntimeOptions:
    trusted_base_url: str
    access_client_id: SecretStr | None = field(default=None, repr=False, compare=False)
    access_client_secret: SecretStr | None = field(default=None, repr=False, compare=False)
    uses_access: bool = False
    config_version: int = 0

    def __post_init__(self) -> None:
        if isinstance(self.access_client_id, str):
            object.__setattr__(self, "access_client_id", SecretStr(self.access_client_id))
        if isinstance(self.access_client_secret, str):
            object.__setattr__(self, "access_client_secret", SecretStr(self.access_client_secret))

    def get_access_credentials(self) -> tuple[str, str]:
        client_id = (
            self.access_client_id.get_secret_value()
            if self.access_client_id is not None
            else ""
        )
        client_secret = (
            self.access_client_secret.get_secret_value()
            if self.access_client_secret is not None
            else ""
        )
        return client_id, client_secret

    def to_safe_dict(self) -> dict[str, Any]:
        return {
            "trusted_base_url": self.trusted_base_url,
            "uses_access": self.uses_access,
            "config_version": self.config_version,
        }


@dataclass(frozen=True, slots=True)
class AIProviderRuntime:
    provider: str
    enabled: bool
    base_url: str
    default_model: str
    credential_state: CredentialState
    credential: SecretStr | None = field(default=None, repr=False, compare=False)
    connect_timeout_seconds: float = 20.0
    read_timeout_seconds: float = 180.0
    verify_tls: bool = True
    ollama: OllamaProviderRuntimeOptions | None = field(
        default=None,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        if isinstance(self.credential, str):
            object.__setattr__(self, "credential", SecretStr(self.credential))

    def get_credential_value(self) -> str | None:
        return self.credential.get_secret_value() if self.credential is not None else None

    def to_safe_dict(self) -> dict[str, Any]:
        safe = asdict(self)
        safe.pop("credential", None)
        safe["ollama"] = self.ollama.to_safe_dict() if self.ollama is not None else None
        return safe


@dataclass(frozen=True, slots=True)
class AIProviderModel:
    provider: str
    id: str
    name: str


@dataclass(frozen=True, slots=True)
class AIProviderModelList:
    capability: Literal["supported", "unsupported"]
    models: tuple[AIProviderModel, ...] = ()


@dataclass(frozen=True, slots=True)
class AIProviderHealth:
    provider: str
    status: ProviderHealthStatus
    message: str
    checked_at: datetime
    effective_model: str
    safe_base_url: str
    credential_state: CredentialState
    details: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class AIProviderClient(Protocol):
    async def test_connection(self) -> AIProviderHealth: ...

    async def list_models(self) -> AIProviderModelList: ...

    async def generate_text(self, prompt: str, model: str | None = None) -> str: ...

    async def generate_json(
        self,
        prompt: str,
        response_model: type[T],
        model: str | None = None,
    ) -> T: ...


_SAFE_REASONS = {
    "connection_failed",
    "dns_failure",
    "redirect_not_allowed",
    "request_failed",
    "target_not_allowed",
}


class AIProviderError(Exception):
    category = "provider_error"
    default_message = "AI 服务调用失败"

    def __init__(
        self,
        *,
        status_code: int | None = None,
        reason: str | None = None,
    ) -> None:
        super().__init__(self.default_message)
        self.status_code = status_code if isinstance(status_code, int) else None
        self.reason = reason if reason in _SAFE_REASONS else None


class AIProviderDisabledError(AIProviderError):
    category = "disabled"
    default_message = "AI 服务已停用"


class AIProviderInvalidConfigurationError(AIProviderError):
    category = "invalid_configuration"
    default_message = "AI 服务配置无效"


class AIProviderAuthenticationError(AIProviderError):
    category = "authentication"
    default_message = "AI 服务认证失败"


class AIProviderQuotaError(AIProviderError):
    category = "quota"
    default_message = "AI 服务额度不足"


class AIProviderRateLimitError(AIProviderError):
    category = "rate_limit"
    default_message = "AI 服务请求过于频繁"


class AIProviderModelError(AIProviderError):
    category = "model"
    default_message = "AI 模型不可用"


class AIProviderConnectTimeoutError(AIProviderError):
    category = "connect_timeout"
    default_message = "连接 AI 服务超时"


class AIProviderReadTimeoutError(AIProviderError):
    category = "read_timeout"
    default_message = "等待 AI 服务响应超时"


class AIProviderUpstreamError(AIProviderError):
    category = "upstream"
    default_message = "上游 AI 服务异常"


class AIProviderInvalidResponseError(AIProviderError):
    category = "invalid_response"
    default_message = "AI 服务返回内容无效"


_TRUSTED_PROVIDER_ERROR_TYPES = (
    AIProviderError,
    AIProviderDisabledError,
    AIProviderInvalidConfigurationError,
    AIProviderAuthenticationError,
    AIProviderQuotaError,
    AIProviderRateLimitError,
    AIProviderModelError,
    AIProviderConnectTimeoutError,
    AIProviderReadTimeoutError,
    AIProviderUpstreamError,
    AIProviderInvalidResponseError,
)


def map_provider_exception(exc: Exception) -> AIProviderError:
    if isinstance(exc, AIProviderError):
        # Reusing the source retains context, notes and arbitrary diagnostic state.
        # Choose a trusted constructor even for subclasses, preserving its taxonomy.
        error_type = next(cls for cls in type(exc).__mro__ if cls in _TRUSTED_PROVIDER_ERROR_TYPES)
        status_code = exc.status_code
        if isinstance(status_code, int):
            status_code = status_code if type(status_code) is bool else int.__int__(status_code)
        else:
            status_code = None
        reason = exc.reason
        reason = str.__str__(reason) if isinstance(reason, str) else None
        return error_type(status_code=status_code, reason=reason)
    if isinstance(exc, httpx.ConnectTimeout):
        return AIProviderConnectTimeoutError()
    if isinstance(exc, httpx.ReadTimeout):
        return AIProviderReadTimeoutError()
    if isinstance(exc, httpx.HTTPStatusError):
        status_code = exc.response.status_code
        if status_code in {401, 403}:
            return AIProviderAuthenticationError(status_code=status_code)
        if status_code == 402:
            return AIProviderQuotaError(status_code=status_code)
        if status_code == 429:
            return AIProviderRateLimitError(status_code=status_code)
        if status_code in {400, 404, 422}:
            return AIProviderModelError(status_code=status_code)
        return AIProviderUpstreamError(status_code=status_code)
    if isinstance(exc, (httpx.ConnectError, httpx.RequestError)):
        return AIProviderUpstreamError(reason="request_failed")
    if isinstance(exc, (ValueError, TypeError)):
        return AIProviderInvalidResponseError()
    return AIProviderUpstreamError()


@dataclass(frozen=True, slots=True)
class _ProviderFailureOutcome:
    error: AIProviderError


async def _provider_operation_outcome(
    operation: Callable[[], Awaitable[ResultT]],
) -> ResultT | _ProviderFailureOutcome:
    try:
        return await operation()
    except Exception as source:
        error = map_provider_exception(source)
        source.__traceback__ = None
        del source, operation
        return _ProviderFailureOutcome(error)


async def run_provider_operation(
    operation: Callable[[], Awaitable[ResultT]],
) -> ResultT:
    outcome = await _provider_operation_outcome(operation)
    if isinstance(outcome, _ProviderFailureOutcome):
        error = outcome.error
        del outcome, operation
        raise error from None
    return outcome


__all__ = [
    "AIProviderAuthenticationError",
    "AIProviderClient",
    "AIProviderConnectTimeoutError",
    "AIProviderDisabledError",
    "AIProviderError",
    "AIProviderHealth",
    "AIProviderInvalidConfigurationError",
    "AIProviderInvalidResponseError",
    "AIProviderModel",
    "AIProviderModelList",
    "AIProviderModelError",
    "AIProviderQuotaError",
    "AIProviderRateLimitError",
    "AIProviderReadTimeoutError",
    "AIProviderRuntime",
    "AIProviderUpstreamError",
    "CredentialState",
    "OllamaProviderRuntimeOptions",
    "ProviderHealthStatus",
    "map_provider_exception",
    "run_provider_operation",
]

from __future__ import annotations

from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    StrictBool,
    field_validator,
    model_validator,
)

from app.core.ollama_url import InvalidOllamaBaseURL, normalize_ollama_base_url
from app.services.ai_setting_service import normalize_access_origin
from app.services.system_ai_setting_service import (
    CredentialUpdate,
    ServerAIConfig,
    ServerAIConfigUpdateValues,
)

ConfigurationSource = Literal["database", "environment", "default"]


class SystemAICredentialStateResponse(BaseModel):
    access_client_id_configured: bool
    access_client_secret_configured: bool
    credentials_usable: bool
    source: ConfigurationSource


class SystemAIConfigResponse(BaseModel):
    enabled: bool
    default_base_url: str
    trusted_base_url: str
    default_model: str
    connect_timeout_seconds: float
    read_timeout_seconds: float
    verify_tls: bool
    credential_state: SystemAICredentialStateResponse
    configuration_source: ConfigurationSource
    config_version: int

    @classmethod
    def from_config(cls, config: ServerAIConfig) -> SystemAIConfigResponse:
        return cls.model_validate(config, from_attributes=True)


class SystemAIConfigUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: StrictBool
    default_base_url: str = Field(min_length=1, max_length=2048)
    trusted_base_url: str = Field(min_length=1, max_length=2048)
    default_model: str = Field(
        min_length=1,
        max_length=120,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]*$",
    )
    connect_timeout_seconds: float = Field(gt=0, le=60)
    read_timeout_seconds: float = Field(gt=0, lt=300)
    verify_tls: StrictBool
    admin_password: SecretStr = Field(min_length=1, max_length=1024)
    upgrade_password: SecretStr = Field(min_length=1, max_length=1024)
    access_client_id: SecretStr | None = Field(default=None, max_length=4096)
    access_client_secret: SecretStr | None = Field(default=None, max_length=4096)
    clear_access_credentials: StrictBool = False
    confirm_insecure_tls: StrictBool = False

    @field_validator("default_base_url")
    @classmethod
    def validate_default_base_url(cls, value: str) -> str:
        try:
            return normalize_ollama_base_url(value)
        except InvalidOllamaBaseURL:
            raise ValueError("默认服务地址必须是有效的 HTTP 或 HTTPS URL") from None

    @field_validator("trusted_base_url")
    @classmethod
    def validate_trusted_base_url(cls, value: str) -> str:
        try:
            normalized = normalize_ollama_base_url(value)
        except InvalidOllamaBaseURL:
            raise ValueError("可信服务地址必须是公开域名的 HTTPS URL") from None
        if normalize_access_origin(normalized) is None:
            raise ValueError("可信服务地址必须是公开域名的 HTTPS URL")
        return normalized

    @field_validator("default_model")
    @classmethod
    def normalize_default_model(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def validate_cross_field_rules(self) -> SystemAIConfigUpdateRequest:
        if self.connect_timeout_seconds >= self.read_timeout_seconds:
            raise ValueError("连接超时必须小于读取超时")
        if not self.verify_tls and not self.confirm_insecure_tls:
            raise ValueError("关闭 TLS 验证需要明确风险确认")

        client_id = self._secret_value(self.access_client_id)
        client_secret = self._secret_value(self.access_client_secret)
        if bool(client_id) != bool(client_secret):
            raise ValueError("必须同时提供完整的 Access 凭据")
        if self.clear_access_credentials and (client_id or client_secret):
            raise ValueError("清除凭据时不能同时提交新凭据")
        return self

    def update_values(self) -> ServerAIConfigUpdateValues:
        return ServerAIConfigUpdateValues(
            enabled=self.enabled,
            default_base_url=self.default_base_url,
            trusted_base_url=self.trusted_base_url,
            default_model=self.default_model,
            connect_timeout_seconds=self.connect_timeout_seconds,
            read_timeout_seconds=self.read_timeout_seconds,
            verify_tls=self.verify_tls,
        )

    def credential_update(self) -> CredentialUpdate:
        client_id = self._secret_value(self.access_client_id)
        client_secret = self._secret_value(self.access_client_secret)
        if self.clear_access_credentials:
            return CredentialUpdate(mode="clear_pair")
        if client_id and client_secret:
            return CredentialUpdate(
                mode="replace_pair",
                client_id=client_id,
                client_secret=client_secret,
            )
        return CredentialUpdate(mode="preserve")

    @staticmethod
    def _secret_value(value: SecretStr | None) -> str:
        return value.get_secret_value() if value is not None else ""


class SystemAIConfigResetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    admin_password: SecretStr = Field(min_length=1, max_length=1024)
    upgrade_password: SecretStr = Field(min_length=1, max_length=1024)
    confirm_reset: Literal[True]


class SystemAIConfigTestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

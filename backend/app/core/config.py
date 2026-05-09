from functools import lru_cache
from typing import Annotated

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


def _read_git_version(fallback: str = "0.1.0") -> str:
    """
    从 git commit 数量生成版本号 0.1.<count>。
    优先读取 Docker 挂载的宿主机项目目录 /host-project，
    降级到当前工作目录。服务启动时执行一次，结果由 lru_cache 缓存。
    """
    import subprocess
    candidates = ["/host-project", "."]
    for workdir in candidates:
        try:
            r = subprocess.run(
                ["git", "rev-list", "--count", "HEAD"],
                cwd=workdir,
                capture_output=True,
                text=True,
                timeout=3,
            )
            if r.returncode == 0 and r.stdout.strip().isdigit():
                return f"0.1.{r.stdout.strip()}"
        except Exception:
            continue
    return fallback


_APP_VERSION = _read_git_version()


class Settings(BaseSettings):
    app_name: str = Field(
        default="Home Library",
        validation_alias=AliasChoices("HOME_LIBRARY_APP_NAME", "APP_NAME"),
    )
    app_version: str = Field(
        default=_APP_VERSION,
        validation_alias=AliasChoices("HOME_LIBRARY_APP_VERSION", "APP_VERSION"),
    )
    environment: str = Field(
        default="development",
        validation_alias=AliasChoices("HOME_LIBRARY_ENVIRONMENT", "APP_ENV", "ENVIRONMENT"),
    )
    api_prefix: str = Field(
        default="/api",
        validation_alias=AliasChoices("HOME_LIBRARY_API_PREFIX", "API_PREFIX"),
    )
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:5173"],
        validation_alias=AliasChoices("HOME_LIBRARY_CORS_ORIGINS", "CORS_ORIGINS"),
    )
    database_url: str = Field(
        default="sqlite:///./home_library.db",
        validation_alias=AliasChoices("HOME_LIBRARY_DATABASE_URL", "DATABASE_URL"),
    )
    upload_dir: str = Field(
        default="./uploads",
        validation_alias=AliasChoices("HOME_LIBRARY_UPLOAD_DIR", "UPLOAD_DIR"),
    )
    initial_admin_username: str = Field(
        default="admin",
        validation_alias=AliasChoices("HOME_LIBRARY_INITIAL_ADMIN_USERNAME", "INITIAL_ADMIN_USERNAME"),
    )
    initial_admin_password: str = Field(
        default="change-me",
        validation_alias=AliasChoices("HOME_LIBRARY_INITIAL_ADMIN_PASSWORD", "INITIAL_ADMIN_PASSWORD"),
    )
    secret_key: str = Field(
        default="dev-secret-change-me-in-production",
        validation_alias=AliasChoices("HOME_LIBRARY_SECRET_KEY", "APP_SECRET_KEY"),
    )
    access_token_expire_seconds: int = Field(
        default=86400,
        validation_alias=AliasChoices("HOME_LIBRARY_ACCESS_TOKEN_EXPIRE_SECONDS", "APP_ACCESS_TOKEN_EXPIRE_SECONDS"),
    )
    ollama_base_url: str = Field(
        default="http://127.0.0.1:11434",
        validation_alias=AliasChoices("HOME_LIBRARY_OLLAMA_BASE_URL", "OLLAMA_BASE_URL"),
    )
    ollama_default_model: str = Field(
        default="qwen2.5",
        validation_alias=AliasChoices("HOME_LIBRARY_OLLAMA_DEFAULT_MODEL", "OLLAMA_DEFAULT_MODEL"),
    )
    ollama_timeout_seconds: float = Field(
        default=120.0,
        validation_alias=AliasChoices("HOME_LIBRARY_OLLAMA_TIMEOUT_SECONDS", "OLLAMA_TIMEOUT_SECONDS"),
    )
    ollama_optional: bool = Field(
        default=True,
        validation_alias=AliasChoices("HOME_LIBRARY_OLLAMA_OPTIONAL", "OLLAMA_OPTIONAL"),
    )
    upgrade_password: str = Field(
        default="",
        validation_alias=AliasChoices("HOME_LIBRARY_UPGRADE_PASSWORD", "UPGRADE_PASSWORD"),
    )
    upgrade_command: str = Field(
        default="",
        validation_alias=AliasChoices("HOME_LIBRARY_UPGRADE_COMMAND", "UPGRADE_COMMAND"),
    )
    upgrade_workdir: str = Field(
        default=".",
        validation_alias=AliasChoices("HOME_LIBRARY_UPGRADE_WORKDIR", "UPGRADE_WORKDIR"),
    )
    upgrade_timeout_seconds: int = Field(
        default=900,
        validation_alias=AliasChoices("HOME_LIBRARY_UPGRADE_TIMEOUT_SECONDS", "UPGRADE_TIMEOUT_SECONDS"),
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()

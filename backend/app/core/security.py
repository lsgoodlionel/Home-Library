from __future__ import annotations

import ipaddress
import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated
from urllib.parse import urlsplit

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from passlib.context import CryptContext
from pydantic import SecretStr
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.models.user import User

_pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
_bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return _pwd_ctx.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_ctx.verify(plain, hashed)


def create_access_token(user_id: int) -> str:
    settings = get_settings()
    payload = {
        "sub": str(user_id),
        "exp": datetime.now(tz=timezone.utc) + timedelta(seconds=settings.access_token_expire_seconds),
    }
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def _decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, get_settings().secret_key, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 无效或已过期",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    db: Annotated[Session, Depends(get_db)],
) -> object:
    from app.models.user import User

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供认证凭据",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = _decode_token(credentials.credentials)
    raw_sub = payload.get("sub")
    if raw_sub is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token 无效")

    user = db.get(User, int(raw_sub))
    if user is None or user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在或已禁用",
        )
    return user


def get_optional_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    db: Annotated[Session, Depends(get_db)],
) -> object | None:
    from app.models.user import User

    if credentials is None:
        return None
    payload = _decode_token(credentials.credentials)
    raw_sub = payload.get("sub")
    if raw_sub is None:
        return None

    user = db.get(User, int(raw_sub))
    if user is None or user.status != "active":
        return None
    return user


def require_admin(
    current_user: Annotated[object, Depends(get_current_user)],
) -> object:
    if getattr(current_user, "role", None) != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要管理员权限",
        )
    return current_user


def verify_admin_secondary_auth(
    current_user: User,
    admin_password: SecretStr,
    upgrade_password: SecretStr,
) -> None:
    settings = get_settings()
    if not settings.upgrade_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="服务器二次认证未配置",
        )
    if not verify_password(admin_password.get_secret_value(), current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="管理员密码错误",
        )
    try:
        upgrade_matches = secrets.compare_digest(
            upgrade_password.get_secret_value().encode("utf-8"),
            settings.upgrade_password.encode("utf-8"),
        )
    except UnicodeEncodeError:
        upgrade_matches = False
    if not upgrade_matches:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="服务器升级专用密码错误",
        )


def require_secure_server_config_transport(request: Request) -> None:
    if request.url.scheme.lower() == "https":
        return

    direct_address = _direct_client_address(request)
    if direct_address is not None and _is_configured_trusted_proxy(direct_address):
        forwarded_proto = request.headers.get("x-forwarded-proto", "")
        if forwarded_proto.strip().lower() == "https":
            return

    if direct_address is not None and direct_address.is_loopback:
        browser_source = request.headers.get("origin") or request.headers.get("referer")
        if _is_loopback_browser_source(browser_source):
            return

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="服务器配置必须通过 HTTPS 或本机回环地址提交",
    )


def _direct_client_address(request: Request) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    if request.client is None:
        return None
    try:
        return ipaddress.ip_address(request.client.host)
    except ValueError:
        return None


def _is_configured_trusted_proxy(
    address: ipaddress.IPv4Address | ipaddress.IPv6Address,
) -> bool:
    return str(address) in get_settings().server_config_trusted_proxy_ips


def _is_loopback_browser_source(value: str | None) -> bool:
    if not value:
        return False
    try:
        hostname = urlsplit(value).hostname
    except ValueError:
        return False
    if hostname is None:
        return False
    normalized = hostname.rstrip(".").lower()
    if normalized == "localhost":
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False

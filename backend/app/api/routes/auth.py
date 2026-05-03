from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ApiError
from app.core.security import create_access_token, get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.user import LoginRequest, LoginResponse, UserPublic, UserResponse
from app.services import auth_service

router = APIRouter(prefix="/auth")


@router.post("/login", response_model=LoginResponse)
def login(
    body: LoginRequest,
    db: Annotated[Session, Depends(get_db)],
) -> LoginResponse:
    user = auth_service.authenticate(db, body.username, body.password)
    if user is None:
        raise ApiError("UNAUTHORIZED", "用户名或密码错误", 401)
    auth_service.record_login(db, user)
    settings = get_settings()
    return LoginResponse(
        access_token=create_access_token(user.id),
        token_type="bearer",
        expires_in=settings.access_token_expire_seconds,
        user=UserPublic.model_validate(user),
    )


@router.post("/logout")
def logout() -> dict[str, bool]:
    # JWT 无状态；客户端删除 Token 即完成退出
    return {"ok": True}


@router.get("/me", response_model=UserResponse)
def me(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    return current_user

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.core.security import hash_password
from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def get_user_or_404(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise ApiError("NOT_FOUND", "用户不存在", 404)
    return user


def list_users(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    keyword: str | None = None,
    role: str | None = None,
    status: str | None = None,
) -> tuple[list[User], int]:
    q = db.query(User)
    if keyword:
        like = f"%{keyword}%"
        q = q.filter((User.username.ilike(like)) | (User.display_name.ilike(like)))
    if role:
        q = q.filter(User.role == role)
    if status:
        q = q.filter(User.status == status)
    total: int = q.with_entities(func.count()).scalar()
    users = q.order_by(User.id).offset((page - 1) * page_size).limit(page_size).all()
    return users, total


def create_user(db: Session, data: UserCreate) -> User:
    if db.query(User).filter_by(username=data.username).first():
        raise ApiError("CONFLICT", "用户名已存在", 409)
    now = _now()
    user = User(
        username=data.username,
        password_hash=hash_password(data.password),
        display_name=data.display_name,
        email=data.email,
        role=data.role,
        status=data.status,
        created_at=now,
        updated_at=now,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def update_user(db: Session, user_id: int, data: UserUpdate) -> User:
    user = get_user_or_404(db, user_id)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    user.updated_at = _now()
    db.commit()
    db.refresh(user)
    return user


def disable_user(db: Session, user_id: int) -> User:
    user = get_user_or_404(db, user_id)
    user.status = "disabled"
    user.updated_at = _now()
    db.commit()
    db.refresh(user)
    return user

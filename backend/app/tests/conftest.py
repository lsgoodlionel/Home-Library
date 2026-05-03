"""Shared pytest fixtures for backend API tests."""

from __future__ import annotations

import uuid
from collections.abc import Generator
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.models as _models_module
from app.api.deps import auth_required
from app.core.security import create_access_token, hash_password
from app.db.session import get_db
from app.main import app as fastapi_app
from app.models.base import Base
from app.models.book import Book
from app.models.category import Category
from app.models.location import Location
from app.models.user import User

del _models_module

TEST_DATABASE_URL = "sqlite:///:memory:"


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


@pytest.fixture(scope="function")
def db_engine():
    engine = create_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture(scope="function")
def db_session(db_engine) -> Generator[Session, None, None]:
    test_session = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    session = test_session()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="function")
def db(db_session: Session) -> Session:
    return db_session


@pytest.fixture(scope="function")
def client(db_session: Session) -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    async def override_auth_required() -> None:
        return None

    fastapi_app.dependency_overrides[get_db] = override_get_db
    fastapi_app.dependency_overrides[auth_required] = override_auth_required
    with TestClient(fastapi_app, raise_server_exceptions=False) as test_client:
        yield test_client
    fastapi_app.dependency_overrides.clear()


def make_user(
    db: Session,
    *,
    role: str = "member",
    status: str = "active",
    password: str = "testpass123",
) -> tuple[User, str]:
    username = f"u_{uuid.uuid4().hex[:10]}"
    user = User(
        username=username,
        password_hash=hash_password(password),
        display_name=username,
        role=role,
        status=status,
        created_at=_now(),
        updated_at=_now(),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user, password


def make_category(
    db: Session,
    *,
    code: str = "C91",
    name: str = "社会学",
    parent_id: int | None = None,
    is_system: bool = False,
) -> Category:
    category = Category(
        code=code,
        name=name,
        parent_id=parent_id,
        is_system=is_system,
        created_at=_now(),
        updated_at=_now(),
    )
    db.add(category)
    db.commit()
    db.refresh(category)
    return category


def make_location(
    db: Session,
    *,
    room: str = "书房",
    shelf: str = "A 架",
    layer: str | None = "第 1 层",
    position: str | None = None,
) -> Location:
    parts = [room, shelf, layer, position]
    location = Location(
        room=room,
        shelf=shelf,
        layer=layer,
        position=position,
        full_path=" / ".join(part for part in parts if part),
        created_at=_now(),
        updated_at=_now(),
    )
    db.add(location)
    db.commit()
    db.refresh(location)
    return location


def make_book(
    db: Session,
    *,
    title: str = "乡土中国",
    category_id: int | None = None,
    location_id: int | None = None,
    status: str = "available",
    read_status: str = "unread",
) -> Book:
    book = Book(
        title=title,
        category_id=category_id,
        location_id=location_id,
        status=status,
        read_status=read_status,
        created_at=_now(),
        updated_at=_now(),
    )
    db.add(book)
    db.commit()
    db.refresh(book)
    return book


@pytest.fixture(scope="function")
def admin_headers(db_session: Session) -> dict[str, str]:
    user, _ = make_user(db_session, role="admin")
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


@pytest.fixture(scope="function")
def member_headers(db_session: Session) -> dict[str, str]:
    user, _ = make_user(db_session, role="member")
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}

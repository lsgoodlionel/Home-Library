from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, field_validator


UserRole = Literal["admin", "member", "guest"]
UserStatus = Literal["active", "disabled"]


class UserBase(BaseModel):
    username: str
    display_name: str
    email: Optional[str] = None
    role: UserRole
    status: UserStatus = "active"


class UserCreate(UserBase):
    password: str

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 6:
            raise ValueError("密码至少 6 位")
        return v


class UserUpdate(BaseModel):
    display_name: Optional[str] = None
    email: Optional[str] = None
    role: Optional[UserRole] = None
    status: Optional[UserStatus] = None


class UserResponse(UserBase):
    id: int
    last_login_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class UserPublic(BaseModel):
    id: int
    username: str
    display_name: str
    role: UserRole

    model_config = {"from_attributes": True}


class UserPage(BaseModel):
    items: list[UserResponse]
    total: int
    page: int
    page_size: int


# ---------- Auth schemas ----------

class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserPublic

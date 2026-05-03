"""FastAPI shared dependencies."""

from typing import Annotated

from fastapi import Depends

from app.core.security import require_admin
from app.models.user import User


def auth_required(current_user: Annotated[User, Depends(require_admin)]) -> User:
    return current_user

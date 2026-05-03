from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class TagBase(BaseModel):
    name: str
    color: Optional[str] = None


class TagCreate(TagBase):
    pass


class TagUpdate(BaseModel):
    name: Optional[str] = None
    color: Optional[str] = None


class TagResponse(TagBase):
    id: int
    created_at: datetime

    model_config = {"from_attributes": True}

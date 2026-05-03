from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, model_validator


class LocationBase(BaseModel):
    room: str
    shelf: str
    layer: Optional[str] = None
    position: Optional[str] = None
    description: Optional[str] = None
    sort_order: int = 0


class LocationCreate(LocationBase):
    pass


class LocationUpdate(BaseModel):
    room: Optional[str] = None
    shelf: Optional[str] = None
    layer: Optional[str] = None
    position: Optional[str] = None
    description: Optional[str] = None
    sort_order: Optional[int] = None


class LocationResponse(LocationBase):
    id: int
    full_path: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class LocationBrief(BaseModel):
    id: int
    full_path: str

    model_config = {"from_attributes": True}

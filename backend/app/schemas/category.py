from __future__ import annotations
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel


class CategoryBase(BaseModel):
    code: str
    name: str
    parent_id: Optional[int] = None
    description: Optional[str] = None
    sort_order: int = 0


class CategoryCreate(CategoryBase):
    pass


class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    parent_id: Optional[int] = None
    description: Optional[str] = None
    sort_order: Optional[int] = None


class CategoryResponse(CategoryBase):
    id: int
    is_system: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CategoryTree(CategoryResponse):
    children: List["CategoryTree"] = []

    model_config = {"from_attributes": True}


CategoryTree.model_rebuild()


class CategoryBrief(BaseModel):
    id: int
    code: str
    name: str

    model_config = {"from_attributes": True}

from __future__ import annotations
from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel


class ExternalBookResultResponse(BaseModel):
    id: int
    query: str
    source: str
    source_id: Optional[str] = None
    raw_data: str
    normalized_data: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ExternalBookItem(BaseModel):
    source: str
    source_id: Optional[str] = None
    title: str
    subtitle: Optional[str] = None
    author: Optional[str] = None
    publisher: Optional[str] = None
    publish_year: Optional[int] = None
    isbn: Optional[str] = None
    cover_url: Optional[str] = None
    summary: Optional[str] = None
    raw: Dict[str, Any] = {}

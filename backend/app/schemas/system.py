from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


UpgradeStatus = Literal["pending", "running", "success", "failed"]


class UpgradeRequest(BaseModel):
    upgrade_password: str = Field(min_length=1)


class UpgradeResponse(BaseModel):
    task_id: str
    status: UpgradeStatus
    message: str


class UpgradeStatusResponse(BaseModel):
    task_id: str
    status: UpgradeStatus
    started_at: str
    finished_at: Optional[str] = None
    exit_code: Optional[int] = None
    output: str = ""
    error: str = ""

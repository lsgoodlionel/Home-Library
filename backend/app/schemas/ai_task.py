from __future__ import annotations
from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel


AITaskStatus = Literal["success", "failed"]


class AITaskResponse(BaseModel):
    id: int
    task_type: str
    model: Optional[str] = None
    input_data: str
    output_data: Optional[str] = None
    status: AITaskStatus
    error_message: Optional[str] = None
    created_by: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

import uuid
from datetime import date, datetime

from pydantic import BaseModel

from app.models.enums import LeaveType


class LeaveLogCreate(BaseModel):
    start_date: date
    end_date: date
    leave_type: LeaveType
    reason: str | None = None


class LeaveLogUpdate(BaseModel):
    start_date: date | None = None
    end_date: date | None = None
    leave_type: LeaveType | None = None
    reason: str | None = None


class LeaveLogRead(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    user_id: uuid.UUID
    start_date: date
    end_date: date
    leave_type: LeaveType
    reason: str | None
    created_at: datetime

    model_config = {"from_attributes": True}

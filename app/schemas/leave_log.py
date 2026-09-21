import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field, model_validator

from app.models.enums import LeaveType


class LeaveLogCreate(BaseModel):
    start_date: date
    end_date: date
    leave_type: LeaveType
    reason: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def check_date_order(self) -> "LeaveLogCreate":
        if self.start_date > self.end_date:
            raise ValueError("start_date must be on or before end_date")
        return self


class LeaveLogUpdate(BaseModel):
    start_date: date | None = None
    end_date: date | None = None
    leave_type: LeaveType | None = None
    reason: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_update(self) -> "LeaveLogUpdate":
        for field in ("start_date", "end_date", "leave_type"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        if (
            self.start_date is not None
            and self.end_date is not None
            and self.start_date > self.end_date
        ):
            raise ValueError("start_date must be on or before end_date")
        return self


class LeaveLogRead(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    user_id: uuid.UUID
    start_date: date
    end_date: date
    leave_type: LeaveType
    # Null unless the viewer is the owner, a manager or an admin.
    reason: str | None
    created_at: datetime

    model_config = {"from_attributes": True}

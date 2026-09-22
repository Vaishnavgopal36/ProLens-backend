import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

from app.models.enums import (
    HalfSlot,
    LeavePortion,
    LeaveType,
)


class LeaveLogDayCreate(BaseModel):
    leave_date: date
    portion: LeavePortion
    half_slot: HalfSlot | None = None

    @model_validator(mode="after")
    def validate_day(self) -> "LeaveLogDayCreate":

        if self.portion == LeavePortion.full:
            if self.half_slot is not None:
                raise ValueError("half_slot must be null for full-day leave")

        else:
            if self.half_slot is None:
                raise ValueError("half_slot is required for half-day leave")

        return self


class LeaveLogCreate(BaseModel):
    leave_type: LeaveType
    reason: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def check_date_order(self) -> "LeaveLogCreate":
        if self.start_date > self.end_date:
            raise ValueError("start_date must be on or before end_date")
        return self

    days: list[LeaveLogDayCreate] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_days(self) -> "LeaveLogCreate":

        dates = [day.leave_date for day in self.days]

        if len(set(dates)) != len(dates):
            raise ValueError("Each leave date can appear only once")

        return self


class LeaveLogUpdate(BaseModel):
    leave_type: LeaveType | None = None
    reason: str | None = None


class LeaveLogRead(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    user_id: uuid.UUID
    start_date: date
    end_date: date
    leave_type: LeaveType
    # Null unless the viewer is the owner, a manager or an admin.
    reason: str | None
    total_days: Decimal
    created_at: datetime

    model_config = {
        "from_attributes": True,
    }

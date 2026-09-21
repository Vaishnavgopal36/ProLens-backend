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
    reason: str | None = None

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
    days: list[LeaveLogDayCreate] | None = None

    @model_validator(mode="after")
    def validate_days(self) -> "LeaveLogUpdate":

        if self.days is None:
            return self

        if len(self.days) == 0:
            raise ValueError("At least one leave day is required")

        dates = [day.leave_date for day in self.days]

        if len(set(dates)) != len(dates):
            raise ValueError("Each leave date can appear only once")

        return self


class LeaveLogRead(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    user_id: uuid.UUID
    start_date: date
    end_date: date
    leave_type: LeaveType
    reason: str | None
    total_days: Decimal
    created_at: datetime

    model_config = {
        "from_attributes": True,
    }

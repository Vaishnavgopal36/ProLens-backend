import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.enums import CalendarEventType


def _require_aware(value: datetime | None) -> datetime | None:
    if value is not None and (value.tzinfo is None or value.utcoffset() is None):
        raise ValueError("Datetime must include a timezone offset")
    return value


class CalendarEventCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    event_type: CalendarEventType
    start_time: datetime
    end_time: datetime

    _aware = field_validator("start_time", "end_time")(_require_aware)

    @model_validator(mode="after")
    def check_time_order(self) -> "CalendarEventCreate":
        if self.end_time < self.start_time:
            raise ValueError("end_time must be on or after start_time")
        return self


class CalendarEventUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    event_type: CalendarEventType | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None

    _aware = field_validator("start_time", "end_time")(_require_aware)

    @model_validator(mode="after")
    def validate_update(self) -> "CalendarEventUpdate":
        for field in ("title", "event_type", "start_time", "end_time"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        if (
            self.start_time is not None
            and self.end_time is not None
            and self.end_time < self.start_time
        ):
            raise ValueError("end_time must be on or after start_time")
        return self


class CalendarEventRead(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    source_leave_log_id: uuid.UUID | None
    title: str
    description: str | None
    event_type: CalendarEventType
    start_time: datetime
    end_time: datetime
    created_by: uuid.UUID
    created_at: datetime

    model_config = {"from_attributes": True}

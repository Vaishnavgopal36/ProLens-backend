import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.enums import CalendarEventType


class CalendarEventCreate(BaseModel):
    title: str
    description: str | None = None
    event_type: CalendarEventType
    start_time: datetime
    end_time: datetime


class CalendarEventUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    event_type: CalendarEventType | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None


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

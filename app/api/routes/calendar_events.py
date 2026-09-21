import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.pagination import Pagination, get_pagination
from app.core.database import get_db
from app.models.enums import CalendarEventType
from app.models.user import User
from app.schemas.calendar_event import (
    CalendarEventCreate,
    CalendarEventRead,
    CalendarEventUpdate,
)
from app.schemas.common_response import APIResponse, success_response
from app.services.calendar_event_service import CalendarEventService

router = APIRouter(
    prefix="/calendar-events",
    tags=["calendar-events"],
)


def get_calendar_event_service(db: Session = Depends(get_db)) -> CalendarEventService:
    return CalendarEventService(db)


@router.post(
    "",
    response_model=APIResponse[CalendarEventRead],
    status_code=status.HTTP_201_CREATED,
)
def create_calendar_event(
    payload: CalendarEventCreate,
    db: Session = Depends(get_db),
    caller: User = Depends(get_current_user),
    service: CalendarEventService = Depends(get_calendar_event_service),
) -> APIResponse[CalendarEventRead]:
    event = service.create_event(payload=payload, caller=caller)
    db.commit()

    return success_response(
        status_code=status.HTTP_201_CREATED,
        status_message="Calendar event created successfully",
        response_data=event,
    )


@router.get(
    "",
    response_model=APIResponse[list[CalendarEventRead]],
)
def list_calendar_events(
    id: uuid.UUID | None = None,
    event_type: CalendarEventType | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    pagination: Pagination = Depends(get_pagination),
    _: User = Depends(get_current_user),
    service: CalendarEventService = Depends(get_calendar_event_service),
) -> APIResponse[list[CalendarEventRead]]:
    # start_time / end_time delimit the queried range; events overlapping it
    # (not only those fully inside it) are returned.
    events = service.list_events(
        pagination=pagination,
        event_id=id,
        event_type=event_type,
        range_start=start_time,
        range_end=end_time,
    )

    return success_response(
        status_code=status.HTTP_200_OK,
        status_message="Calendar events retrieved successfully",
        response_data=events,
    )


@router.patch(
    "/{event_id}",
    response_model=APIResponse[CalendarEventRead],
)
def update_calendar_event(
    event_id: uuid.UUID,
    payload: CalendarEventUpdate,
    db: Session = Depends(get_db),
    caller: User = Depends(get_current_user),
    service: CalendarEventService = Depends(get_calendar_event_service),
) -> APIResponse[CalendarEventRead]:
    event = service.update_event(event_id=event_id, payload=payload, caller=caller)
    db.commit()

    return success_response(
        status_code=status.HTTP_200_OK,
        status_message="Calendar event updated successfully",
        response_data=event,
    )


@router.delete(
    "/{event_id}",
    response_model=APIResponse[None],
    status_code=status.HTTP_200_OK,
)
def delete_calendar_event(
    event_id: uuid.UUID,
    db: Session = Depends(get_db),
    caller: User = Depends(get_current_user),
    service: CalendarEventService = Depends(get_calendar_event_service),
) -> APIResponse[None]:
    service.delete_event(event_id=event_id, caller=caller)
    db.commit()

    return success_response(
        status_code=status.HTTP_200_OK,
        status_message="Calendar event deleted successfully",
        response_data=None,
    )

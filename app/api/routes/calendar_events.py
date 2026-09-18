import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.enums import CalendarEventType, UserRole
from app.models.timesheet import CalendarEvent
from app.models.user import User
from app.schemas.calendar_event import (
    CalendarEventCreate,
    CalendarEventRead,
    CalendarEventUpdate,
)
from app.schemas.common_response import APIResponse, success_response, COMMON_RESPONSES

router = APIRouter(
    prefix="/calendar-events",
    tags=["calendar-events"],
    responses=COMMON_RESPONSES,
)


@router.post(
    "",
    response_model=APIResponse[CalendarEventRead],
    status_code=status.HTTP_201_CREATED,
)
def create_calendar_event(
    payload: CalendarEventCreate,
    db: Session = Depends(get_db),
    caller: User = Depends(get_current_user),
) -> APIResponse[CalendarEventRead]:
    if (
        payload.event_type == CalendarEventType.holiday
        and caller.role != UserRole.admin
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only Admin can create holiday events",
        )

    event = CalendarEvent(
        organization_id=caller.organization_id,
        title=payload.title,
        description=payload.description,
        event_type=payload.event_type,
        start_time=payload.start_time,
        end_time=payload.end_time,
        created_by=caller.id,
    )

    db.add(event)
    db.flush()
    db.refresh(event)
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
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> APIResponse[list[CalendarEventRead]]:
    stmt = select(CalendarEvent).where(CalendarEvent.deleted_at.is_(None))

    if id is not None:
        stmt = stmt.where(CalendarEvent.id == id)

    if event_type is not None:
        stmt = stmt.where(CalendarEvent.event_type == event_type)

    if start_time is not None:
        stmt = stmt.where(CalendarEvent.start_time >= start_time)

    if end_time is not None:
        stmt = stmt.where(CalendarEvent.end_time <= end_time)

    events = list(db.scalars(stmt))

    return success_response(
        status_code=status.HTTP_200_OK,
        status_message="Calendar events retrieved successfully",
        response_data=events,
    )


def _can_modify(
    caller: User,
    event: CalendarEvent,
) -> bool:
    return caller.role == UserRole.admin or event.created_by == caller.id


@router.patch(
    "/{event_id}",
    response_model=APIResponse[CalendarEventRead],
)
def update_calendar_event(
    event_id: uuid.UUID,
    payload: CalendarEventUpdate,
    db: Session = Depends(get_db),
    caller: User = Depends(get_current_user),
) -> APIResponse[CalendarEventRead]:
    event = db.get(CalendarEvent, event_id)

    if event is None or event.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Calendar event not found",
        )

    if not _can_modify(caller, event):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )

    new_event_type = (
        payload.event_type if payload.event_type is not None else event.event_type
    )

    if new_event_type == CalendarEventType.holiday and caller.role != UserRole.admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only Admin can set holiday events",
        )

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(event, field, value)

    db.flush()
    db.refresh(event)
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
) -> APIResponse[None]:
    event = db.get(CalendarEvent, event_id)

    if event is None or event.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Calendar event not found",
        )

    if not _can_modify(caller, event):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )

    event.deleted_at = datetime.now(timezone.utc)
    event.deleted_by = caller.id

    db.commit()

    return success_response(
        status_code=status.HTTP_200_OK,
        status_message="Calendar event deleted successfully",
        response_data=None,
    )

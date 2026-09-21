from __future__ import annotations

import uuid
from datetime import date, datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exception import (
    LeaveLogMutationForbiddenError,
    LeaveLogNotFoundError,
    LeavePeriodAlreadyStartedError,
    MustBelongToOrganizationError,
    OverlappingLeaveError,
)
from app.models.enums import (
    HalfSlot,
    LeavePortion,
    LeaveType,
    UserRole,
)
from app.models.timesheet import LeaveLog, LeaveLogDay
from app.models.user import User
from app.repositories.leave_log_day_repository import (
    LeaveLogDayRepository,
)
from app.repositories.leave_log_repository import (
    LeaveLogRepository,
)
from app.schemas.leave_log import (
    LeaveLogCreate,
    LeaveLogDayCreate,
    LeaveLogUpdate,
)

APP_TIMEZONE = ZoneInfo(settings.APP_TIMEZONE)


class LeaveLogService:

    def __init__(self, db: Session):
        self.db = db
        self.leave_logs = LeaveLogRepository(db)
        self.leave_days = LeaveLogDayRepository(db)

    # ---------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------

    def _get_leave_log(
        self,
        leave_log_id: uuid.UUID,
    ) -> LeaveLog:

        leave_log = self.leave_logs.get_active_by_id(leave_log_id)

        if leave_log is None:
            raise LeaveLogNotFoundError()

        return leave_log

    @staticmethod
    def _build_slot(
        day: LeaveLogDayCreate,
    ) -> Range:

        if day.portion == LeavePortion.full:
            return Range(
                0,
                2,
                bounds="[)",
            )

        if day.half_slot == HalfSlot.first:
            return Range(
                0,
                1,
                bounds="[)",
            )

        return Range(
            1,
            2,
            bounds="[)",
        )

    @staticmethod
    def _build_slot_from_day(
        day: LeaveLogDay,
    ) -> Range:

        if day.portion == LeavePortion.full:
            return Range(
                0,
                2,
                bounds="[)",
            )

        if day.half_slot == HalfSlot.first:
            return Range(
                0,
                1,
                bounds="[)",
            )

        return Range(
            1,
            2,
            bounds="[)",
        )

    @staticmethod
    def _get_period_start(
        *,
        leave_date: date,
        portion: LeavePortion,
        half_slot: HalfSlot | None,
    ) -> datetime:

        if portion == LeavePortion.full or half_slot == HalfSlot.first:
            start_time = time.min
        else:
            start_time = time(12, 0)

        return datetime.combine(
            leave_date,
            start_time,
            tzinfo=APP_TIMEZONE,
        )

    @staticmethod
    def _get_first_period_start_from_payload(
        days: list[LeaveLogDayCreate],
    ) -> datetime:

        first_day = min(
            days,
            key=lambda day: day.leave_date,
        )

        return LeaveLogService._get_period_start(
            leave_date=first_day.leave_date,
            portion=first_day.portion,
            half_slot=first_day.half_slot,
        )

    @staticmethod
    def _get_first_period_start_from_rows(
        days: list[LeaveLogDay],
    ) -> datetime:

        first_day = min(
            days,
            key=lambda day: day.leave_date,
        )

        return LeaveLogService._get_period_start(
            leave_date=first_day.leave_date,
            portion=first_day.portion,
            half_slot=first_day.half_slot,
        )

    @staticmethod
    def _calculate_total_days(
        days: list[LeaveLogDayCreate],
    ) -> Decimal:

        total = Decimal("0.0")

        for day in days:
            if day.portion == LeavePortion.full:
                total += Decimal("1.0")
            else:
                total += Decimal("0.5")

        return total

    @staticmethod
    def _ensure_dates_are_valid(
        days: list[LeaveLogDayCreate],
    ) -> tuple[date, date]:

        start_date = min(day.leave_date for day in days)

        end_date = max(day.leave_date for day in days)

        return start_date, end_date

    def _ensure_leave_has_not_started(
        self,
        *,
        days: list[LeaveLogDayCreate],
    ) -> None:

        start_at = self._get_first_period_start_from_payload(days)

        now = datetime.now(APP_TIMEZONE)

        if start_at <= now:
            raise LeavePeriodAlreadyStartedError()

    def _ensure_no_overlap(
        self,
        *,
        user_id: uuid.UUID,
        day: LeaveLogDayCreate,
        exclude_leave_log_id: uuid.UUID | None = None,
    ) -> None:

        slot = self._build_slot(day)

        if self.leave_days.has_overlapping_leave(
            user_id=user_id,
            leave_date=day.leave_date,
            slot=slot,
            exclude_leave_log_id=exclude_leave_log_id,
        ):
            raise OverlappingLeaveError()

    @staticmethod
    def _can_update(
        *,
        caller: User,
        leave_log: LeaveLog,
        current_first_period_start: datetime,
    ) -> bool:

        if caller.role in (
            UserRole.admin,
            UserRole.manager,
        ):
            return True

        return (
            caller.id == leave_log.user_id
            and current_first_period_start > datetime.now(APP_TIMEZONE)
        )

    @staticmethod
    def _can_delete(
        *,
        caller: User,
        leave_log: LeaveLog,
        current_first_period_start: datetime,
    ) -> bool:

        return (
            caller.id == leave_log.user_id
            and current_first_period_start > datetime.now(APP_TIMEZONE)
        )

    # ---------------------------------------------------------
    # Create
    # ---------------------------------------------------------

    def create_leave_log(
        self,
        *,
        caller: User,
        payload: LeaveLogCreate,
    ) -> LeaveLog:

        if caller.organization_id is None:
            raise MustBelongToOrganizationError()

        self._ensure_leave_has_not_started(days=payload.days)

        for day in payload.days:
            self._ensure_no_overlap(
                user_id=caller.id,
                day=day,
            )

        start_date, end_date = self._ensure_dates_are_valid(payload.days)

        total_days = self._calculate_total_days(payload.days)

        leave_log = LeaveLog(
            organization_id=caller.organization_id,
            user_id=caller.id,
            start_date=start_date,
            end_date=end_date,
            leave_type=payload.leave_type,
            reason=payload.reason,
            total_days=total_days,
        )

        try:
            self.db.add(leave_log)
            self.db.flush()

            for day_data in payload.days:
                leave_day = LeaveLogDay(
                    leave_log_id=leave_log.id,
                    user_id=caller.id,
                    organization_id=caller.organization_id,
                    leave_date=day_data.leave_date,
                    portion=day_data.portion,
                    half_slot=day_data.half_slot,
                    slot=self._build_slot(day_data),
                )

                self.db.add(leave_day)

            self.db.flush()
            self.db.refresh(leave_log)

            return leave_log

        except IntegrityError as exc:
            self.db.rollback()
            raise OverlappingLeaveError() from exc

    # ---------------------------------------------------------
    # List
    # ---------------------------------------------------------

    def list_leave_logs(
        self,
        *,
        id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
        leave_type: LeaveType | None = None,
        leave_date: date | None = None,
    ) -> list[LeaveLog]:

        return self.leave_logs.list_filtered(
            id=id,
            user_id=user_id,
            leave_type=leave_type,
            leave_date=leave_date,
        )

    # ---------------------------------------------------------
    # Update
    # ---------------------------------------------------------

    def update_leave_log(
        self,
        *,
        leave_log_id: uuid.UUID,
        payload: LeaveLogUpdate,
        caller: User,
    ) -> LeaveLog:

        leave_log = self._get_leave_log(leave_log_id)

        current_days = self.leave_days.list_active_by_leave_log(leave_log.id)

        if not current_days:
            raise LeaveLogNotFoundError()

        current_first_period_start = self._get_first_period_start_from_rows(
            current_days
        )

        # Permission is based on the CURRENT leave.
        # An employee cannot move an already-started leave
        # into the future to bypass the restriction.
        if not self._can_update(
            caller=caller,
            leave_log=leave_log,
            current_first_period_start=current_first_period_start,
        ):
            raise LeaveLogMutationForbiddenError()

        # -----------------------------------------------------
        # Update schedule
        # -----------------------------------------------------

        if payload.days is not None:

            if caller.role not in (
                UserRole.admin,
                UserRole.manager,
            ):
                self._ensure_leave_has_not_started(days=payload.days)

            for day in payload.days:
                self._ensure_no_overlap(
                    user_id=leave_log.user_id,
                    day=day,
                    exclude_leave_log_id=leave_log.id,
                )

            start_date, end_date = self._ensure_dates_are_valid(payload.days)

            total_days = self._calculate_total_days(payload.days)

            existing_days = self.leave_days.list_active_by_leave_log(leave_log.id)

            existing_by_date = {day.leave_date: day for day in existing_days}

            # Get soft-deleted rows too so a date that was
            # removed earlier can be restored instead of
            # violating UNIQUE(leave_log_id, leave_date).
            for day_data in payload.days:

                existing_day = self.leave_days.get_by_leave_log_and_date(
                    leave_log_id=leave_log.id,
                    leave_date=day_data.leave_date,
                )

                if existing_day is None:

                    new_day = LeaveLogDay(
                        leave_log_id=leave_log.id,
                        user_id=leave_log.user_id,
                        organization_id=leave_log.organization_id,
                        leave_date=day_data.leave_date,
                        portion=day_data.portion,
                        half_slot=day_data.half_slot,
                        slot=self._build_slot(day_data),
                    )

                    self.db.add(new_day)

                else:

                    existing_day.portion = day_data.portion

                    existing_day.half_slot = day_data.half_slot

                    existing_day.slot = self._build_slot(day_data)

                    existing_day.deleted_at = None
                    existing_day.deleted_by = None

            requested_dates = {day.leave_date for day in payload.days}

            now = datetime.now(APP_TIMEZONE)

            for existing_day in existing_days:

                if existing_day.leave_date not in requested_dates:
                    existing_day.deleted_at = now
                    existing_day.deleted_by = caller.id

            leave_log.start_date = start_date
            leave_log.end_date = end_date
            leave_log.total_days = total_days

        # -----------------------------------------------------
        # Update normal parent fields
        # -----------------------------------------------------

        if payload.leave_type is not None:
            leave_log.leave_type = payload.leave_type

        if "reason" in payload.model_fields_set:
            leave_log.reason = payload.reason

        try:
            self.db.flush()
            self.db.refresh(leave_log)

            return leave_log

        except IntegrityError as exc:
            self.db.rollback()
            raise OverlappingLeaveError() from exc

    # ---------------------------------------------------------
    # Delete
    # ---------------------------------------------------------

    def delete_leave_log(
        self,
        *,
        leave_log_id: uuid.UUID,
        caller: User,
    ) -> None:

        leave_log = self._get_leave_log(leave_log_id)

        active_days = self.leave_days.list_active_by_leave_log(leave_log.id)

        if not active_days:
            raise LeaveLogNotFoundError()

        current_first_period_start = self._get_first_period_start_from_rows(active_days)

        if not self._can_delete(
            caller=caller,
            leave_log=leave_log,
            current_first_period_start=current_first_period_start,
        ):
            raise LeaveLogMutationForbiddenError()

        now = datetime.now(APP_TIMEZONE)

        leave_log.deleted_at = now
        leave_log.deleted_by = caller.id

        for day in active_days:
            day.deleted_at = now
            day.deleted_by = caller.id

        self.db.flush()

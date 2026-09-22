from enum import Enum


class UserRole(str, Enum):
    super_admin = "super_admin"
    admin = "admin"
    manager = "manager"
    employee = "employee"


class UserRoleFilter(str, Enum):
    admin = "admin"
    manager = "manager"
    employee = "employee"


class UserStatus(str, Enum):
    invited = "invited"
    active = "active"
    suspended = "suspended"


class OrgStatus(str, Enum):
    active = "active"
    suspended = "suspended"


class ProjectStatus(str, Enum):
    active = "active"
    on_hold = "on_hold"
    completed = "completed"


class EntityStatus(str, Enum):
    to_do = "to_do"
    in_progress = "in_progress"
    in_review = "in_review"
    done = "done"


class PriorityLevel(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    urgent = "urgent"


class LeaveType(str, Enum):
    sick = "sick"
    casual = "casual"
    vacation = "vacation"


class LeavePortion(str, Enum):
    full = "full"
    half = "half"


class HalfSlot(str, Enum):
    first = "first"
    second = "second"


class CalendarEventType(str, Enum):
    holiday = "holiday"
    milestone = "milestone"
    leave = "leave"
    release = "release"
    team_event = "team_event"


class OutboxStatus(str, Enum):
    pending = "pending"
    processing = "processing"
    sent = "sent"
    failed = "failed"


class InvitationStatus(str, Enum):
    pending = "pending"
    processing = "processing"
    sent = "sent"
    failed = "failed"


class ReportJobType(str, Enum):
    report = "report"
    timeline = "timeline"
    summary = "summary"


class ReportJobStatus(str, Enum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class HealthStatus(str, Enum):
    on_track = "on_track"
    at_risk = "at_risk"
    delayed = "delayed"


class AuditAction(str, Enum):
    insert = "insert"
    update = "update"
    delete = "delete"


class SSOProvider(str, Enum):
    azure_ad = "azure_ad"
    google = "google"

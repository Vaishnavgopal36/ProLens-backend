import enum


class UserRole(str, enum.Enum):
    super_admin = "super_admin"
    admin = "admin"
    manager = "manager"
    employee = "employee"

class UserRoleFilter(str, enum.Enum):
    admin = "admin"
    manager = "manager"
    employee = "employee"

class UserStatus(str, enum.Enum):
    invited = "invited"
    active = "active"
    suspended = "suspended"


class OrgStatus(str, enum.Enum):
    active = "active"
    suspended = "suspended"


class ProjectStatus(str, enum.Enum):
    active = "active"
    on_hold = "on_hold"
    completed = "completed"


class EntityStatus(str, enum.Enum):
    to_do = "to_do"
    in_progress = "in_progress"
    in_review = "in_review"
    done = "done"


class PriorityLevel(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"
    urgent = "urgent"


class LeaveType(str, enum.Enum):
    sick = "sick"
    casual = "casual"
    vacation = "vacation"


class CalendarEventType(str, enum.Enum):
    holiday = "holiday"
    milestone = "milestone"
    leave = "leave"
    release = "release"
    team_event = "team_event"


class InvitationStatus(str, enum.Enum):
    pending = "pending"
    accepted = "accepted"
    expired = "expired"
    revoked = "revoked"


class ReportJobType(str, enum.Enum):
    report = "report"
    timeline = "timeline"
    summary = "summary"


class ReportJobStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class HealthStatus(str, enum.Enum):
    on_track = "on_track"
    at_risk = "at_risk"
    delayed = "delayed"


class AuditAction(str, enum.Enum):
    insert = "insert"
    update = "update"
    delete = "delete"


class SSOProvider(str, enum.Enum):
    azure_ad = "azure_ad"
    google="google"

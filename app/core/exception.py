from typing import Any


class AppException(Exception):
    """Base exception for application, domain, and business logic errors."""

    status_code: int = 400
    status_message: str = "Bad Request"
    default_message: str = "An application error occurred."

    def __init__(
        self,
        message: str | None = None,
        status_code: int | None = None,
        status_message: str | None = None,
        details: dict | list[Any] | str | None = None,
    ) -> None:
        self.message = message or self.default_message
        self.status_code = status_code if status_code is not None else self.status_code
        self.status_message = (
            status_message if status_message is not None else self.status_message
        )
        self.details = details

        super().__init__(self.message)


# ---------------------------------------------------------
# Authentication
# ---------------------------------------------------------


class InvalidCredentialsError(AppException):
    status_code = 401
    status_message = "Unauthorized"
    default_message = "Incorrect email or password"


class InactiveAccountError(AppException):
    status_code = 403
    status_message = "Forbidden"
    default_message = "Account is not active"


class InvalidRefreshTokenError(AppException):
    status_code = 401
    status_message = "Unauthorized"
    default_message = "Invalid or expired refresh token"


# ---------------------------------------------------------
# SSO
# ---------------------------------------------------------


class NoSSOConnectionError(AppException):
    status_code = 404
    status_message = "Not Found"
    default_message = "No SSO connection configured for this organization"


class InvalidSSOStateError(AppException):
    status_code = 400
    status_message = "Bad Request"
    default_message = "Invalid or expired SSO state"


class MissingEmailClaimError(AppException):
    status_code = 400
    status_message = "Bad Request"
    default_message = "Identity provider did not return an email claim"


# ---------------------------------------------------------
# User
# ---------------------------------------------------------


class EmailAlreadyInUseError(AppException):
    status_code = 409
    status_message = "Conflict"
    default_message = "Email already in use"


class OrganizationIdRequiredError(AppException):
    status_code = 422
    status_message = "Unprocessable Entity"
    default_message = "organization_id is required"


class CrossOrganizationForbiddenError(AppException):
    status_code = 403
    status_message = "Forbidden"
    default_message = "Cannot create users outside your organization"


class UserNotFoundError(AppException):
    status_code = 404
    status_message = "Not Found"
    default_message = "User not found"


class InvalidRoleAssignmentError(AppException):
    status_code = 403
    status_message = "Forbidden"
    default_message = "You cannot assign this role"


# ---------------------------------------------------------
# Organization
# ---------------------------------------------------------


class OrganizationNotFoundError(AppException):
    status_code = 404
    status_message = "Not Found"
    default_message = "Organization not found"


class DomainAlreadyInUseError(AppException):
    status_code = 409
    status_message = "Conflict"
    default_message = "Domain already in use"


class AdminCredentialsIncompleteError(AppException):
    status_code = 422
    status_message = "Unprocessable Entity"
    default_message = "admin_email and admin_password must be provided together"


class DesignationNotFoundError(AppException):
    status_code = 404
    status_message = "Not Found"
    default_message = "Designation not found"


class CallerHasNoOrganizationError(AppException):
    status_code = 403
    status_message = "Forbidden"
    default_message = "Must belong to an organization"


class FieldNotEditableError(AppException):
    status_code = 403
    status_message = "Forbidden"

    def __init__(self, fields: set[str]):
        super().__init__(f"You are not allowed to edit: {', '.join(fields)}")


class CannotDeleteSelfError(AppException):
    status_code = 403
    status_message = "Forbidden"
    default_message = "You cannot delete your own account"


class CannotDeletePrivilegedUserError(AppException):
    status_code = 403
    status_message = "Forbidden"
    default_message = "You do not have permission to delete this user"


class CannotDeleteLastAdminError(AppException):
    status_code = 409
    status_message = "Conflict"
    default_message = "Cannot delete the last remaining admin of this organization"


class InsufficientPermissionError(AppException):
    status_code = 403
    status_message = "Forbidden"
    default_message = "Insufficient permissions"


class InvalidCredentialsAuthError(AppException):
    status_code = 401
    status_message = "Unauthorized"
    default_message = "Could not validate credentials"


class SSOConnectionAlreadyExistsError(AppException):
    status_code = 409
    default_message = "Organization already has a connection"


class SSOConnectionNotFoundError(AppException):
    status_code = 404
    default_message = "Connection not found"


class UnsupportedSSOProviderError(AppException):
    status_code = 400
    default_message = "Unsupported provider for sync"


class NotProjectMemberError(AppException):
    status_code = 403
    status_message = "Forbidden"
    default_message = "Not a member of this project"


class TaskNotFoundError(AppException):
    status_code = 404
    status_message = "Not Found"
    default_message = "Task not found"


class ProjectNotFoundError(AppException):
    status_code = 404
    status_message = "Not Found"
    default_message = "Project not found"


class MustBelongToOrganizationError(AppException):
    status_code = 403
    status_message = "Forbidden"
    default_message = "Must belong to an organization"


class ProjectMutationForbiddenError(AppException):
    status_code = 403
    status_message = "Forbidden"
    default_message = "Insufficient permissions"


class ProjectHasTasksError(AppException):
    status_code = 409
    status_message = "Conflict"
    default_message = "Project has associated tasks and cannot be deleted"


class ProjectMemberNotFoundError(AppException):
    status_code = 404
    status_message = "Not Found"
    default_message = "Project member not found"


class ProjectMemberAlreadyExistsError(AppException):
    status_code = 409
    status_message = "Conflict"
    default_message = "User is already a project member"


class ProjectMemberMutationForbiddenError(AppException):
    status_code = 403
    status_message = "Forbidden"
    default_message = "Insufficient permissions"


class InvalidProjectMemberRoleError(AppException):
    status_code = 403
    status_message = "Forbidden"
    default_message = (
        "Only managers can be added directly; invite employees via /invitations"
    )


# ---------------------------------------------------------
# Feature
# ---------------------------------------------------------


class FeatureNotFoundError(AppException):
    status_code = 404
    status_message = "Not Found"
    default_message = "Feature not found"


class FeatureMutationForbiddenError(AppException):
    status_code = 403
    status_message = "Forbidden"
    default_message = "Insufficient permissions"


class ProjectMembershipRequiredError(AppException):
    status_code = 403
    status_message = "Forbidden"
    default_message = "User must be a project member before being assigned to a feature"


class FeatureMemberNotFoundError(AppException):
    status_code = 404
    status_message = "Not Found"
    default_message = "Feature member not found"


class FeatureMemberAlreadyExistsError(AppException):
    status_code = 409
    status_message = "Conflict"
    default_message = "User is already an active member"


class FeatureMemberMutationForbiddenError(AppException):
    status_code = 403
    status_message = "Forbidden"
    default_message = "Insufficient permissions"


class EmployeeOnLeaveError(AppException):
    status_code = 409
    status_message = "Conflict"
    default_message = (
        "Employee is on leave and cannot complete this task by its due date"
    )
    
class SSOConnectionNotConfiguredError(AppException):
    status_code = 409
    status_message = "Conflict"
    default_message = "SSO connection has not finished setup — ask your admin to complete tenant discovery"
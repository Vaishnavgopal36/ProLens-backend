from typing import Any

class AppException(Exception):
    """Base exception for all domain and business logic errors."""

    status_code: int = 400
    status_message: str = "Error"
    default_message: str = "An application error occurred."

    def __init__(
        self,
        message: str | None = None,
        status_code: int | None = None,
        status_message: str | None = None,
        details: dict | list[Any] | str | None = None,
    ) -> None:
        self.message = message or self.default_message
        self.status_code = status_code or self.status_code
        self.status_message = status_message or self.status_message
        self.details = details
        super().__init__(self.message)


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

class EmailAlreadyInUseError(AppException):
    status_code = 409
    default_message = "Email already in use"


class OrganizationIdRequiredError(AppException):
    status_code = 422
    default_message = "organization_id is required"


class CrossOrganizationForbiddenError(AppException):
    status_code = 403
    default_message = "Cannot create users outside your organization"


class UserNotFoundError(AppException):
    status_code = 404
    default_message = "User not found"

class InvalidRoleAssignmentError(AppException):
    status_code = 403
    default_message = "You cannot assign this role"

class OrganizationNotFoundError(AppException):
    status_code = 404
    default_message = "Organization not found"

class DomainAlreadyInUseError(AppException):
    status_code = 409
    default_message = "Domain already in use"

class AdminCredentialsIncompleteError(AppException):
    status_code = 422
    default_message = "admin_email and admin_password must be provided together"
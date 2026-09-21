import secrets
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.exception import (
    AppException,
    CannotDeleteLastAdminError,
    CannotDeletePrivilegedUserError,
    CannotDeleteSelfError,
    CrossOrganizationForbiddenError,
    DesignationNotFoundError,
    EmailAlreadyInUseError,
    FieldNotEditableError,
    InsufficientPermissionError,
    InvalidRoleAssignmentError,
    OrganizationIdRequiredError,
    OrganizationNotFoundError,
    UserNotFoundError,
)
from app.core.security import hash_password, verify_password
from app.models.enums import UserRole, UserStatus
from app.models.tenancy import Designation
from app.models.user import User
from app.repositories.designation_repository import DesignationRepository
from app.repositories.organization_repository import OrganizationRepository
from app.repositories.session_repository import SessionRepository
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserCreate, UserUpdate

# Fields any user may change on their own account.
SELF_SERVICE_FIELDS = {"first_name", "last_name", "password", "current_password"}


class UserService:
    def __init__(self, db: Session):
        self.db = db
        self.users = UserRepository(db)
        self.organizations = OrganizationRepository(db)
        self.designations = DesignationRepository(db)
        self.sessions = SessionRepository(db)

    def _validate_role_assignment(self, caller: User, role: UserRole) -> None:
        if caller.role == UserRole.super_admin:
            return
        if role == UserRole.super_admin:
            raise InvalidRoleAssignmentError()

    def _resolve_organization_id(
        self,
        caller: User,
        payload: UserCreate,
    ) -> uuid.UUID:
        if caller.role == UserRole.super_admin:
            organization_id = payload.organization_id or caller.organization_id
            if organization_id is None:
                raise OrganizationIdRequiredError()
            return organization_id

        if payload.organization_id not in (None, caller.organization_id):
            raise CrossOrganizationForbiddenError()

        if caller.organization_id is None:
            raise OrganizationIdRequiredError()

        return caller.organization_id

    def _validate_designation(
        self, designation_id: uuid.UUID, organization_id: uuid.UUID | None
    ) -> None:
        designation = self.designations.get_active_by_id(designation_id)
        if designation is None or designation.organization_id != organization_id:
            raise DesignationNotFoundError()

    @staticmethod
    def _require_designation_for_employee(
        role: UserRole, designation_id: uuid.UUID | None
    ) -> None:
        # Mirrors ck_users_employee_requires_designation with a clean 422.
        if role == UserRole.employee and designation_id is None:
            raise AppException(
                "A designation is required for employees",
                status_code=422,
                status_message="Unprocessable Entity",
            )

    def create_user(self, caller: User, payload: UserCreate) -> User:
        email = payload.email.strip().lower()
        if self.users.get_by_email(email):
            raise EmailAlreadyInUseError()

        self._validate_role_assignment(caller, payload.role)
        organization_id = self._resolve_organization_id(caller, payload)

        if self.organizations.get_active_by_id(organization_id) is None:
            raise OrganizationNotFoundError()

        # Generate secure random password if not provided
        password = payload.password or secrets.token_urlsafe(16)

        # Resolve designation (by ID or by name)
        designation_id = payload.designation_id
        if (
            designation_id is None
            and payload.designation_name
            and payload.designation_name.strip()
        ):
            desig_name = payload.designation_name.strip()
            existing = self.designations.get_active_by_name(organization_id, desig_name)
            if existing:
                designation_id = existing.id
            else:
                new_desig = Designation(
                    organization_id=organization_id, name=desig_name
                )
                self.designations.add(new_desig)
                designation_id = new_desig.id

        if designation_id is not None:
            self._validate_designation(designation_id, organization_id)
        self._require_designation_for_employee(payload.role, designation_id)

        user = User(
            organization_id=organization_id,
            designation_id=designation_id,
            email=email,
            password_hash=hash_password(password),
            first_name=payload.first_name,
            last_name=payload.last_name,
            role=payload.role,
            status=UserStatus.active,
        )

        # A concurrent duplicate email surfaces as IntegrityError -> 409 (main.py).
        return self.users.add(user)

    def list_users(
        self,
        caller: User,
        *,
        id: uuid.UUID | None = None,
        organization_id: uuid.UUID | None = None,
        role: UserRole | None = None,
        status: UserStatus | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[User]:
        if caller.role != UserRole.super_admin:
            organization_id = caller.organization_id

        return self.users.list_filtered(
            id=id,
            organization_id=organization_id,
            role=role,
            status=status,
            limit=limit,
            offset=offset,
        )

    def _authorize_update(
        self, caller: User, user: User, update_data: dict, is_self: bool
    ) -> None:
        if caller.role == UserRole.super_admin:
            return

        if caller.role == UserRole.admin:
            if user.role == UserRole.super_admin:
                raise InsufficientPermissionError()
            if user.organization_id != caller.organization_id:
                raise CrossOrganizationForbiddenError()
            if "role" in update_data:
                self._validate_role_assignment(caller, update_data["role"])
            if is_self:
                # No self-promotion/demotion or self-suspension.
                changed = {
                    f
                    for f in ("role", "status")
                    if f in update_data and update_data[f] != getattr(user, f)
                }
                if changed:
                    raise FieldNotEditableError(fields=changed)
            elif "password" in update_data:
                raise FieldNotEditableError(fields={"password"})
            return

        # manager / employee: self only, and only the self-service fields.
        if not is_self:
            raise InsufficientPermissionError()
        disallowed = set(update_data) - SELF_SERVICE_FIELDS
        if disallowed:
            raise FieldNotEditableError(fields=disallowed)

    def _apply_password_change(self, user: User, update_data: dict) -> bool:
        """Turn password/current_password into password_hash. True if changed."""
        current_password = update_data.pop("current_password", None)
        if "password" not in update_data:
            return False
        if user.password_hash is None:
            raise AppException(
                "This account signs in with SSO and has no password",
                status_code=422,
                status_message="Unprocessable Entity",
            )
        if current_password is None or not verify_password(
            current_password, user.password_hash
        ):
            raise AppException(
                "Current password is incorrect",
                status_code=403,
                status_message="Forbidden",
            )
        update_data["password_hash"] = hash_password(update_data.pop("password"))
        return True

    def _assert_not_last_admin(self, user: User) -> None:
        if (
            user.role != UserRole.admin
            or user.status != UserStatus.active
            or user.organization_id is None
        ):
            return
        remaining = self.users.count_active_admins(
            user.organization_id, exclude_user_id=user.id
        )
        if remaining == 0:
            raise CannotDeleteLastAdminError(
                "Cannot demote, suspend or delete the last active admin "
                "of this organization"
            )

    def update_user(
        self, caller: User, user_id: uuid.UUID, payload: UserUpdate
    ) -> User:
        user = self.users.get_active_by_id(user_id)
        if user is None:
            raise UserNotFoundError()

        update_data = payload.model_dump(exclude_unset=True)
        is_self = caller.id == user.id

        self._authorize_update(caller, user, update_data, is_self)

        new_role = update_data.get("role", user.role)
        new_status = update_data.get("status", user.status)
        new_designation_id = update_data.get("designation_id", user.designation_id)

        if new_role != user.role or new_status != user.status:
            if new_role != UserRole.admin or new_status != UserStatus.active:
                self._assert_not_last_admin(user)

        if update_data.get("designation_id") is not None:
            self._validate_designation(
                update_data["designation_id"], user.organization_id
            )
        self._require_designation_for_employee(new_role, new_designation_id)

        password_changed = self._apply_password_change(user, update_data)

        for field, value in update_data.items():
            setattr(user, field, value)

        self.db.flush()
        if password_changed or new_status != UserStatus.active:
            self.sessions.revoke_all_for_user(user.id)
        self.db.refresh(user)
        return user

    def delete_user(self, caller: User, user_id: uuid.UUID) -> None:
        user = self.users.get_active_by_id(user_id)
        if user is None:
            raise UserNotFoundError()

        if user.id == caller.id:
            raise CannotDeleteSelfError()

        if (
            caller.role != UserRole.super_admin
            and user.organization_id != caller.organization_id
        ):
            raise CannotDeletePrivilegedUserError()

        if caller.role != UserRole.super_admin and user.role == UserRole.super_admin:
            raise CannotDeletePrivilegedUserError()

        self._assert_not_last_admin(user)

        user.deleted_at = datetime.now(timezone.utc)
        user.deleted_by = caller.id
        self.db.flush()
        self.sessions.revoke_all_for_user(user.id)

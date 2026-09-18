# app/services/user_service.py

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.exception import (
    CrossOrganizationForbiddenError,
    EmailAlreadyInUseError,
    InvalidRoleAssignmentError,
    OrganizationIdRequiredError,
    OrganizationNotFoundError,
    UserNotFoundError,
)
from app.core.security import hash_password
from app.models.enums import UserRole, UserStatus
from app.models.user import User
from app.repositories.organization_repository import OrganizationRepository
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserCreate, UserUpdate


class UserService:
    def __init__(self, db: Session):
        self.db = db
        self.users = UserRepository(db)
        self.organizations = OrganizationRepository(db)

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

        return caller.organization_id

    def create_user(self, caller: User, payload: UserCreate) -> User:
        if self.users.get_by_email(payload.email):
            raise EmailAlreadyInUseError()

        self._validate_role_assignment(caller, payload.role)
        organization_id = self._resolve_organization_id(caller, payload)

        if self.organizations.get_by_id(organization_id) is None:
            raise OrganizationNotFoundError()

        user = User(
            organization_id=organization_id,
            designation_id=payload.designation_id,
            email=payload.email,
            password_hash=hash_password(payload.password),
            first_name=payload.first_name,
            last_name=payload.last_name,
            role=payload.role,
            status=UserStatus.invited,
        )

        return self.users.add(user)

    def list_users(
        self,
        *,
        id: uuid.UUID | None = None,
        organization_id: uuid.UUID | None = None,
        role: UserRole | None = None,
        status: UserStatus | None = None,
    ) -> list[User]:
        return self.users.list_filtered(
            id=id,
            organization_id=organization_id,
            role=role,
            status=status,
        )

    def update_user(self, user_id: uuid.UUID, payload: UserUpdate) -> User:
        user = self.users.get_by_id(user_id)
        if user is None or user.deleted_at is not None:
            raise UserNotFoundError()

        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(user, field, value)

        self.db.flush()
        self.db.refresh(user)
        return user

    def delete_user(self, user_id: uuid.UUID, caller: User) -> None:
        user = self.users.get_by_id(user_id)
        if user is None or user.deleted_at is not None:
            raise UserNotFoundError()

        user.deleted_at = datetime.now(timezone.utc)
        user.deleted_by = caller.id
        self.db.flush()
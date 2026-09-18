# app/services/user_service.py

from datetime import datetime, timezone
import uuid

from sqlalchemy.orm import Session

from app.core.exception import (
    CrossOrganizationForbiddenError,
    EmailAlreadyInUseError,
    OrganizationIdRequiredError,
    UserNotFoundError,
)
from app.core.security import hash_password
from app.models.enums import UserRole, UserStatus
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserCreate, UserUpdate


class UserService:
    def __init__(self, db: Session):
        self.db = db
        self.users = UserRepository(db)

    def _resolve_organization_id(self, caller: User, payload: UserCreate) -> uuid.UUID:
        if caller.role == UserRole.super_admin:
            if payload.organization_id is None:
                raise OrganizationIdRequiredError()
            return payload.organization_id

        if payload.organization_id not in (None, caller.organization_id):
            raise CrossOrganizationForbiddenError()

        return caller.organization_id

    def create_user(self, caller: User, payload: UserCreate) -> User:
        if self.users.get_by_email(payload.email):
            raise EmailAlreadyInUseError()

        organization_id = self._resolve_organization_id(caller, payload)

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

        return self.users.create(user) 

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
        user = self.users.get_by_id(user_id)  # assumes BaseRepository.get_by_id()
        if user is None or user.deleted_at is not None:
            raise UserNotFoundError()

        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(user, field, value)

        return self.users.save(user)  # assumes BaseRepository.save() flush+refresh

    def delete_user(self, user_id: uuid.UUID, caller: User) -> None:
        user = self.users.get_by_id(user_id)
        if user is None or user.deleted_at is not None:
            raise UserNotFoundError()

        user.deleted_at = datetime.now(timezone.utc)
        user.deleted_by = caller.id
import uuid

from sqlalchemy import func, select

from app.models.enums import UserRole, UserStatus
from app.models.user import User
from app.repositories.base_repository import BaseRepository


class UserRepository(BaseRepository[User]):
    model = User

    def get_by_email(self, email: str) -> User | None:
        # Case-insensitive so legacy mixed-case rows still match.
        return self.db.scalar(
            select(User).where(func.lower(User.email) == email.strip().lower())
        )

    def get_by_sso_subject_id(self, subject_id: str) -> User | None:
        return self.db.scalar(select(User).where(User.sso_subject_id == subject_id))

    def get_active_by_id(
        self,
        user_id: uuid.UUID,
    ) -> User | None:
        user = self.get_by_id(user_id)

        if user is None or user.deleted_at is not None:
            return None

        return user

    def list_filtered(
        self,
        *,
        id: uuid.UUID | None = None,
        organization_id: uuid.UUID | None = None,
        role: UserRole | None = None,
        status: UserStatus | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[User]:
        stmt = select(User).where(User.deleted_at.is_(None))

        if id is not None:
            stmt = stmt.where(User.id == id)
        if organization_id is not None:
            stmt = stmt.where(User.organization_id == organization_id)
        if role is not None:
            stmt = stmt.where(User.role == role)
        if status is not None:
            stmt = stmt.where(User.status == status)

        stmt = stmt.order_by(User.created_at, User.id).offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)

        return list(self.db.scalars(stmt))

    def count_active_admins(
        self, organization_id: uuid.UUID, exclude_user_id: uuid.UUID | None = None
    ) -> int:
        stmt = (
            select(func.count())
            .select_from(User)
            .where(
                User.organization_id == organization_id,
                User.role == UserRole.admin,
                User.status == UserStatus.active,
                User.deleted_at.is_(None),
            )
        )
        if exclude_user_id is not None:
            stmt = stmt.where(User.id != exclude_user_id)
        return self.db.scalar(stmt) or 0

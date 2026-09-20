import uuid

from sqlalchemy import func, select
from app.models.enums import UserRole, UserStatus
from app.models.user import User
from app.repositories.base_repository import BaseRepository
import uuid
from app.models.enums import UserRole

class UserRepository(BaseRepository[User]):
    model = User

    def get_by_email(self, email: str) -> User | None:
        return self.db.scalar(select(User).where(User.email == email))

    def get_by_sso_subject_id(self, subject_id: str) -> User | None:
        return self.db.scalar(select(User).where(User.sso_subject_id == subject_id))
    
    def list_filtered(
        self,
        *,
        id: uuid.UUID | None = None,
        organization_id: uuid.UUID | None = None,
        role: UserRole | None = None,
        status: UserStatus | None = None,
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

        return list(self.db.scalars(stmt))

    def count_active_admins(self, organization_id: uuid.UUID, exclude_user_id: uuid.UUID | None = None) -> int:
        stmt = select(func.count()).select_from(User).where(
            User.organization_id == organization_id,
            User.role == UserRole.admin,
            User.deleted_at.is_(None),
        )
        if exclude_user_id is not None:
            stmt = stmt.where(User.id != exclude_user_id)
        return self.db.scalar(stmt)
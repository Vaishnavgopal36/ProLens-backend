import uuid

from sqlalchemy import select
from app.models.enums import UserRole, UserStatus
from app.models.user import User
from app.repositories.base_repository import BaseRepository


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



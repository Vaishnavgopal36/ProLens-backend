import uuid

from sqlalchemy import func, select

from app.models.tenancy import Designation
from app.models.user import User
from app.repositories.base_repository import BaseRepository


class DesignationRepository(BaseRepository[Designation]):
    model = Designation

    def get_active_by_id(self, designation_id: uuid.UUID) -> Designation | None:
        designation = self.db.get(Designation, designation_id)
        if designation is None or designation.deleted_at is not None:
            return None
        return designation

    def get_active_by_name(
        self,
        organization_id: uuid.UUID,
        name: str,
        exclude_id: uuid.UUID | None = None,
    ) -> Designation | None:
        stmt = select(Designation).where(
            Designation.organization_id == organization_id,
            func.lower(Designation.name) == name.strip().lower(),
            Designation.deleted_at.is_(None),
        )
        if exclude_id is not None:
            stmt = stmt.where(Designation.id != exclude_id)
        return self.db.scalar(stmt.limit(1))

    def count_assigned_users(self, designation_id: uuid.UUID) -> int:
        """Non-deleted users still pointing at this designation."""
        return (
            self.db.scalar(
                select(func.count())
                .select_from(User)
                .where(
                    User.designation_id == designation_id,
                    User.deleted_at.is_(None),
                )
            )
            or 0
        )

    def list_filtered(
        self,
        *,
        id: uuid.UUID | None = None,
        name: str | None = None,
        organization_id: uuid.UUID | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Designation]:
        stmt = select(Designation).where(Designation.deleted_at.is_(None))

        if id is not None:
            stmt = stmt.where(Designation.id == id)
        if name is not None:
            stmt = stmt.where(Designation.name == name)
        if organization_id is not None:
            stmt = stmt.where(Designation.organization_id == organization_id)

        stmt = stmt.order_by(Designation.created_at, Designation.id).offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)

        return list(self.db.scalars(stmt))

import uuid

from sqlalchemy import select

from app.models.tenancy import Designation
from app.repositories.base_repository import BaseRepository


class DesignationRepository(BaseRepository[Designation]):
    model = Designation

    def get_active_by_id(self, designation_id: uuid.UUID) -> Designation | None:
        designation = self.db.get(Designation, designation_id)
        if designation is None or designation.deleted_at is not None:
            return None
        return designation

    def list_filtered(
        self,
        *,
        id: uuid.UUID | None = None,
        name: str | None = None,
        organization_id: uuid.UUID | None = None,   # ← add this
    ) -> list[Designation]:
        stmt = select(Designation).where(Designation.deleted_at.is_(None))

        if id is not None:
            stmt = stmt.where(Designation.id == id)
        if name is not None:
            stmt = stmt.where(Designation.name == name)
        if organization_id is not None:              # ← and this
            stmt = stmt.where(Designation.organization_id == organization_id)

        return list(self.db.scalars(stmt))
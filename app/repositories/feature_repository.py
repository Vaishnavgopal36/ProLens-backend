import uuid

from sqlalchemy import select

from app.models.enums import EntityStatus
from app.models.project import Feature
from app.repositories.base_repository import BaseRepository


class FeatureRepository(BaseRepository[Feature]):
    model = Feature

    def get_active_by_id(
        self,
        feature_id: uuid.UUID,
    ) -> Feature | None:

        feature = self.get_by_id(feature_id)

        if feature is None or feature.deleted_at is not None:
            return None

        return feature

    def list_filtered(
        self,
        *,
        id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
        status: EntityStatus | None = None,
    ) -> list[Feature]:

        stmt = select(Feature).where(Feature.deleted_at.is_(None))

        if id is not None:
            stmt = stmt.where(Feature.id == id)

        if project_id is not None:
            stmt = stmt.where(Feature.project_id == project_id)

        if status is not None:
            stmt = stmt.where(Feature.status == status)

        return list(self.db.scalars(stmt))

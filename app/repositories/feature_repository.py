import uuid

from sqlalchemy import func, select

from app.models.enums import EntityStatus
from app.models.project import Feature
from app.models.task import Task
from app.models.user import User
from app.repositories.base_repository import BaseRepository
from app.repositories.project_repository import ORG_WIDE_ROLES, member_project_ids


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
        caller: User,
        id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
        status: EntityStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Feature]:

        stmt = select(Feature).where(Feature.deleted_at.is_(None))

        if caller.role not in ORG_WIDE_ROLES:
            stmt = stmt.where(Feature.project_id.in_(member_project_ids(caller.id)))

        if id is not None:
            stmt = stmt.where(Feature.id == id)

        if project_id is not None:
            stmt = stmt.where(Feature.project_id == project_id)

        if status is not None:
            stmt = stmt.where(Feature.status == status)

        stmt = stmt.order_by(Feature.created_at, Feature.id)
        return list(self.db.scalars(stmt.limit(limit).offset(offset)))

    def list_active_by_project(self, project_id: uuid.UUID) -> list[Feature]:
        stmt = select(Feature).where(
            Feature.project_id == project_id,
            Feature.deleted_at.is_(None),
        )
        return list(self.db.scalars(stmt))

    def count_active_tasks(self, feature_id: uuid.UUID) -> int:
        stmt = select(func.count(Task.id)).where(
            Task.feature_id == feature_id,
            Task.deleted_at.is_(None),
        )
        return int(self.db.scalar(stmt) or 0)

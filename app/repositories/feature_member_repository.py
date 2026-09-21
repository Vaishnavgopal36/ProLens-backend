import uuid

from sqlalchemy import select

from app.models.project import FeatureMember
from app.repositories.base_repository import BaseRepository


class FeatureMemberRepository(BaseRepository[FeatureMember]):
    model = FeatureMember

    def get_active_by_id(
        self,
        feature_member_id: uuid.UUID,
    ) -> FeatureMember | None:

        member = self.get_by_id(feature_member_id)

        if member is None or member.removed_at is not None:
            return None

        return member

    def get_active_by_feature_and_user(
        self,
        feature_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> FeatureMember | None:

        stmt = select(FeatureMember).where(
            FeatureMember.feature_id == feature_id,
            FeatureMember.user_id == user_id,
            FeatureMember.removed_at.is_(None),
        )

        return self.db.scalar(stmt)

    def list_filtered(
        self,
        *,
        id: uuid.UUID | None = None,
        feature_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[FeatureMember]:

        stmt = select(FeatureMember).where(FeatureMember.removed_at.is_(None))

        if id is not None:
            stmt = stmt.where(FeatureMember.id == id)

        if feature_id is not None:
            stmt = stmt.where(FeatureMember.feature_id == feature_id)

        if user_id is not None:
            stmt = stmt.where(FeatureMember.user_id == user_id)

        stmt = stmt.order_by(FeatureMember.assigned_at, FeatureMember.id)
        return list(self.db.scalars(stmt.limit(limit).offset(offset)))

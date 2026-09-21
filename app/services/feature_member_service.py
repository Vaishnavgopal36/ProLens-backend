import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.exception import (
    FeatureMemberAlreadyExistsError,
    FeatureMemberMutationForbiddenError,
    FeatureMemberNotFoundError,
    FeatureNotFoundError,
    UserNotFoundError,
    CrossOrganizationForbiddenError,
    MustBelongToOrganizationError,
    ProjectMembershipRequiredError,
    ProjectNotFoundError,
)
from app.models.enums import UserRole, UserStatus
from app.models.project import Feature, FeatureMember
from app.models.user import User

from app.repositories.feature_member_repository import FeatureMemberRepository
from app.repositories.feature_repository import FeatureRepository
from app.repositories.project_repository import ProjectRepository
from app.repositories.user_repository import UserRepository

from app.schemas.feature_member import FeatureMemberCreate


class FeatureMemberService:

    def __init__(self, db: Session):
        self.db = db
        self.feature_members = FeatureMemberRepository(db)
        self.features = FeatureRepository(db)
        self.projects = ProjectRepository(db)
        self.users = UserRepository(db)

    def _get_feature(
        self,
        feature_id: uuid.UUID,
    ) -> Feature:

        feature = self.features.get_active_by_id(feature_id)

        if feature is None:
            raise FeatureNotFoundError()

        project = self.projects.get_active_by_id(feature.project_id)

        if project is None:
            raise ProjectNotFoundError()

        return feature

    def _get_feature_member(
        self,
        feature_member_id: uuid.UUID,
    ) -> FeatureMember:

        member = self.feature_members.get_active_by_id(feature_member_id)

        if member is None:
            raise FeatureMemberNotFoundError()

        return member

    def _authorize_member_management(
        self,
        caller: User,
        feature: Feature,
    ) -> None:

        if caller.role in (UserRole.admin, UserRole.super_admin):
            return

        if caller.role == UserRole.manager:
            if self.projects.is_member(
                project_id=feature.project_id,
                user_id=caller.id,
            ):
                return

        raise FeatureMemberMutationForbiddenError()

    def create_feature_member(
        self,
        caller: User,
        payload: FeatureMemberCreate,
    ) -> FeatureMember:

        if caller.organization_id is None:
            raise MustBelongToOrganizationError()

        feature = self._get_feature(payload.feature_id)

        self._authorize_member_management(
            caller=caller,
            feature=feature,
        )

        user = self.users.get_active_by_id(payload.user_id)

        if user is None or user.status != UserStatus.active:
            raise UserNotFoundError()

        if user.organization_id != caller.organization_id:
            raise CrossOrganizationForbiddenError()

        if not self.projects.is_member(
            project_id=feature.project_id,
            user_id=payload.user_id,
        ):
            raise ProjectMembershipRequiredError()

        existing = self.feature_members.get_active_by_feature_and_user(
            feature_id=payload.feature_id,
            user_id=payload.user_id,
        )

        if existing is not None:
            raise FeatureMemberAlreadyExistsError()

        member = FeatureMember(
            organization_id=caller.organization_id,
            feature_id=payload.feature_id,
            user_id=payload.user_id,
            assigned_by=caller.id,
        )

        return self.feature_members.add(member)

    def list_feature_members(
        self,
        *,
        id: uuid.UUID | None = None,
        feature_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[FeatureMember]:

        return self.feature_members.list_filtered(
            id=id,
            feature_id=feature_id,
            user_id=user_id,
            limit=limit,
            offset=offset,
        )

    def delete_feature_member(
        self,
        feature_member_id: uuid.UUID,
        caller: User,
    ) -> None:

        member = self._get_feature_member(feature_member_id)

        feature = self._get_feature(member.feature_id)

        self._authorize_member_management(
            caller=caller,
            feature=feature,
        )

        member.removed_at = datetime.now(timezone.utc)
        member.removed_by = caller.id

        self.db.flush()

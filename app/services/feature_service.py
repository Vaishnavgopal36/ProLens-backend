import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.exception import (
    AppException,
    FeatureMutationForbiddenError,
    FeatureNotFoundError,
    MustBelongToOrganizationError,
    ProjectNotFoundError,
)
from app.models.enums import EntityStatus, UserRole
from app.models.project import Feature, Project
from app.models.user import User
from app.repositories.feature_repository import FeatureRepository
from app.repositories.project_repository import ProjectRepository
from app.schemas.feature import FeatureCreate, FeatureUpdate


class FeatureService:
    def __init__(self, db: Session):
        self.db = db
        self.features = FeatureRepository(db)
        self.projects = ProjectRepository(db)

    def _get_feature(
        self,
        feature_id: uuid.UUID,
    ) -> Feature:

        feature = self.features.get_active_by_id(feature_id)

        if feature is None:
            raise FeatureNotFoundError()

        return feature

    def _get_project(
        self,
        project_id: uuid.UUID,
    ) -> Project:

        project = self.projects.get_active_by_id(project_id)

        if project is None:
            raise ProjectNotFoundError()

        return project

    def _authorize_feature_management(
        self,
        caller: User,
        project_id: uuid.UUID,
    ) -> None:

        if caller.role in (UserRole.admin, UserRole.super_admin):
            return

        if caller.role == UserRole.manager:
            if self.projects.is_member(
                project_id=project_id,
                user_id=caller.id,
            ):
                return

        raise FeatureMutationForbiddenError()

    def create_feature(
        self,
        caller: User,
        payload: FeatureCreate,
    ) -> Feature:

        if caller.organization_id is None:
            raise MustBelongToOrganizationError()

        project = self._get_project(payload.project_id)

        self._authorize_feature_management(
            caller=caller,
            project_id=project.id,
        )

        feature = Feature(
            organization_id=caller.organization_id,
            project_id=project.id,
            name=payload.name,
            description=payload.description,
            status=EntityStatus.to_do,
            created_by=caller.id,
        )

        return self.features.add(feature)

    def list_features(
        self,
        *,
        caller: User,
        id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
        status: EntityStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Feature]:
        """List visible features.

        Visibility: admins see every feature of the organization; managers and
        employees only features of projects they are an active member of.
        """

        return self.features.list_filtered(
            caller=caller,
            id=id,
            project_id=project_id,
            status=status,
            limit=limit,
            offset=offset,
        )

    def update_feature(
        self,
        feature_id: uuid.UUID,
        payload: FeatureUpdate,
        caller: User,
    ) -> Feature:

        feature = self._get_feature(feature_id)

        self._authorize_feature_management(
            caller=caller,
            project_id=feature.project_id,
        )

        update_data = payload.model_dump(exclude_unset=True)

        for field, value in update_data.items():
            setattr(
                feature,
                field,
                value,
            )

        feature.updated_by = caller.id

        self.db.flush()
        self.db.refresh(feature)

        return feature

    def delete_feature(
        self,
        feature_id: uuid.UUID,
        caller: User,
    ) -> None:

        feature = self._get_feature(feature_id)

        self._authorize_feature_management(
            caller=caller,
            project_id=feature.project_id,
        )

        if self.features.count_active_tasks(feature.id) > 0:
            raise AppException(
                "Feature has active tasks and cannot be deleted",
                status_code=409,
                status_message="Conflict",
            )

        feature.deleted_at = datetime.now(timezone.utc)
        feature.deleted_by = caller.id

        self.db.flush()

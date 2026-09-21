import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.exception import (
    AppException,
    MustBelongToOrganizationError,
    ProjectHasTasksError,
    ProjectMutationForbiddenError,
    ProjectNotFoundError,
)
from app.models.enums import ProjectStatus, UserRole
from app.models.project import Project, ProjectMember
from app.models.user import User
from app.repositories.feature_repository import FeatureRepository
from app.repositories.project_member_repository import ProjectMemberRepository
from app.repositories.project_repository import ProjectRepository
from app.schemas.project import ProjectCreate, ProjectUpdate


class ProjectService:
    def __init__(self, db: Session):
        self.db = db
        self.projects = ProjectRepository(db)
        self.project_members = ProjectMemberRepository(db)
        self.features = FeatureRepository(db)

    def _get_project(
        self,
        project_id: uuid.UUID,
    ) -> Project:

        project = self.projects.get_active_by_id(project_id)

        if project is None:
            raise ProjectNotFoundError()

        return project

    def _authorize_mutation(
        self,
        caller: User,
        project: Project,
    ) -> None:
        """Admins may mutate any project; managers only projects they belong to."""

        if caller.role in (UserRole.admin, UserRole.super_admin):
            return

        if caller.role == UserRole.manager:
            if self.projects.is_member(
                project_id=project.id,
                user_id=caller.id,
            ):
                return

        raise ProjectMutationForbiddenError()

    def create_project(
        self,
        caller: User,
        payload: ProjectCreate,
    ) -> Project:
        """Create the project and enrol its creator as an active member.

        Without the membership a manager who creates a project would be locked
        out of it (managers may only mutate projects they belong to).
        """

        if caller.organization_id is None:
            raise MustBelongToOrganizationError()

        project = Project(
            organization_id=caller.organization_id,
            name=payload.name,
            description=payload.description,
            client_name=payload.client_name,
            client_contact=payload.client_contact,
            start_date=payload.start_date,
            end_date=payload.end_date,
            budget=payload.budget,
            status=ProjectStatus.active,
            created_by=caller.id,
        )

        project = self.projects.add(project)

        self.project_members.add(
            ProjectMember(
                organization_id=caller.organization_id,
                project_id=project.id,
                user_id=caller.id,
                added_by=caller.id,
            )
        )

        return project

    def list_projects(
        self,
        *,
        caller: User,
        id: uuid.UUID | None = None,
        status: ProjectStatus | None = None,
        organization_id: uuid.UUID | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Project]:
        """List visible projects.

        Visibility: admins see every project of the organization; managers and
        employees only projects they are an active member of. The
        ``organization_id`` filter is honored for super_admin only.
        """

        if caller.role != UserRole.super_admin:
            organization_id = None

        return self.projects.list_filtered(
            caller=caller,
            id=id,
            status=status,
            organization_id=organization_id,
            limit=limit,
            offset=offset,
        )

    def update_project(
        self,
        project_id: uuid.UUID,
        payload: ProjectUpdate,
        caller: User,
    ) -> Project:

        project = self._get_project(project_id)

        self._authorize_mutation(
            caller=caller,
            project=project,
        )

        update_data = payload.model_dump(exclude_unset=True)

        start = update_data.get("start_date", project.start_date)
        end = update_data.get("end_date", project.end_date)
        if start is not None and end is not None and start > end:
            raise AppException(
                "start_date must be on or before end_date",
                status_code=422,
                status_message="Unprocessable Entity",
            )

        for field, value in update_data.items():
            setattr(
                project,
                field,
                value,
            )

        project.updated_by = caller.id

        self.db.flush()
        self.db.refresh(project)

        return project

    def delete_project(
        self,
        project_id: uuid.UUID,
        caller: User,
    ) -> None:
        """Soft-delete a project without tasks, together with its (empty) features."""

        project = self._get_project(project_id)

        self._authorize_mutation(
            caller=caller,
            project=project,
        )

        task_count = self.projects.count_active_tasks(project_id)

        if task_count > 0:
            raise ProjectHasTasksError()

        now = datetime.now(timezone.utc)

        for feature in self.features.list_active_by_project(project_id):
            feature.deleted_at = now
            feature.deleted_by = caller.id

        project.deleted_at = now
        project.deleted_by = caller.id

        self.db.flush()

from sqlalchemy.orm import Session
from app.repositories.project_repository import ProjectRepository
from app.models.user import User, UserRole
from app.schemas.project import ProjectCreate, ProjectUpdate
from app.models.project import Project
from app.models.enums import ProjectStatus
from app.core.exception import (
    MustBelongToOrganizationError,
    ProjectHasTasksError,
    ProjectMutationForbiddenError,
    ProjectNotFoundError,
)
import uuid
from datetime import datetime, timezone


class ProjectService:

    def __init__(self, db: Session):
        self.db = db
        self.projects = ProjectRepository(db)

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

        if caller.role == UserRole.admin:
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

        return project

    def list_projects(
        self,
        *,
        id: uuid.UUID | None = None,
        status: ProjectStatus | None = None,
        organization_id: uuid.UUID | None = None,
    ) -> list[Project]:

        return self.projects.list_filtered(
            id=id,
            status=status,
            organization_id=organization_id,
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

        project = self._get_project(project_id)

        self._authorize_mutation(
            caller=caller,
            project=project,
        )

        task_count = self.projects.count_active_tasks(project_id)

        if task_count > 0:
            raise ProjectHasTasksError()

        project.deleted_at = datetime.now(timezone.utc)
        project.deleted_by = caller.id

        self.db.flush()

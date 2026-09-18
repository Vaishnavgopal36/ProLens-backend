from app.repositories.base_repository import BaseRepository
from app.models.project import Project
import uuid
from app.models.enums import ProjectStatus
from sqlalchemy import select, func
from app.models.project import ProjectMember
from app.models.task import Task
from app.models.project import Feature


class ProjectRepository(BaseRepository[Project]):
    model = Project

    def get_active_by_id(
        self,
        project_id: uuid.UUID,
    ) -> Project | None:
        project = self.get_by_id(project_id)

        if project is None or project.deleted_at is not None:
            return None

        return project

    def list_filtered(
        self,
        *,
        id: uuid.UUID | None = None,
        status: ProjectStatus | None = None,
        organization_id: uuid.UUID | None = None,
    ) -> list[Project]:
        stmt = select(Project).where(Project.deleted_at.is_(None))

        if id is not None:
            stmt = stmt.where(Project.id == id)

        if status is not None:
            stmt = stmt.where(Project.status == status)

        if organization_id is not None:
            stmt = stmt.where(Project.organization_id == organization_id)

        return list(self.db.scalars(stmt))

    def is_member(
        self,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> bool:
        stmt = select(ProjectMember.id).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
            ProjectMember.removed_at.is_(None),
        )

        return self.db.scalar(stmt) is not None

    def count_active_tasks(
        self,
        project_id: uuid.UUID,
    ) -> int:
        stmt = (
            select(func.count(Task.id))
            .join(
                Feature,
                Task.feature_id == Feature.id,
            )
            .where(
                Feature.project_id == project_id,
                Task.deleted_at.is_(None),
            )
        )

        return self.db.scalar(stmt)

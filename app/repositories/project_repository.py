import uuid

from sqlalchemy import func, select

from app.models.enums import ProjectStatus, UserRole
from app.models.project import Feature, Project, ProjectMember
from app.models.task import Task
from app.models.user import User
from app.repositories.base_repository import BaseRepository

ORG_WIDE_ROLES = (UserRole.admin, UserRole.super_admin)


def member_project_ids(user_id: uuid.UUID):
    """Subquery of the project ids the user is an active member of."""
    return select(ProjectMember.project_id).where(
        ProjectMember.user_id == user_id,
        ProjectMember.removed_at.is_(None),
    )


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
        caller: User,
        id: uuid.UUID | None = None,
        status: ProjectStatus | None = None,
        organization_id: uuid.UUID | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Project]:
        stmt = select(Project).where(Project.deleted_at.is_(None))

        if caller.role not in ORG_WIDE_ROLES:
            stmt = stmt.where(Project.id.in_(member_project_ids(caller.id)))

        if id is not None:
            stmt = stmt.where(Project.id == id)

        if status is not None:
            stmt = stmt.where(Project.status == status)

        if organization_id is not None:
            stmt = stmt.where(Project.organization_id == organization_id)

        stmt = stmt.order_by(Project.created_at, Project.id)
        return list(self.db.scalars(stmt.limit(limit).offset(offset)))

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
            select(func.coalesce(func.count(Task.id), 0))
            .join(
                Feature,
                Task.feature_id == Feature.id,
            )
            .where(
                Feature.project_id == project_id,
                Feature.deleted_at.is_(None),
                Task.deleted_at.is_(None),
            )
        )

        return int(self.db.scalar(stmt) or 0)

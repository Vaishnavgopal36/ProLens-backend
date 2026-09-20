import uuid

from sqlalchemy import select

from app.models.project import ProjectMember
from app.repositories.base_repository import BaseRepository


class ProjectMemberRepository(BaseRepository[ProjectMember]):
    model = ProjectMember

    def get_active_by_id(
        self,
        member_id: uuid.UUID,
    ) -> ProjectMember | None:

        member = self.get_by_id(member_id)

        if member is None or member.removed_at is not None:
            return None

        return member

    def get_active_by_project_and_user(
        self,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> ProjectMember | None:

        stmt = select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
            ProjectMember.removed_at.is_(None),
        )

        return self.db.scalar(stmt)

    def list_filtered(
        self,
        *,
        id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
    ) -> list[ProjectMember]:

        stmt = select(ProjectMember).where(ProjectMember.removed_at.is_(None))

        if id is not None:
            stmt = stmt.where(ProjectMember.id == id)

        if project_id is not None:
            stmt = stmt.where(ProjectMember.project_id == project_id)

        if user_id is not None:
            stmt = stmt.where(ProjectMember.user_id == user_id)

        return list(self.db.scalars(stmt))

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.exception import (
    InvalidProjectMemberRoleError,
    MustBelongToOrganizationError,
    ProjectMemberAlreadyExistsError,
    ProjectMemberMutationForbiddenError,
    ProjectMemberNotFoundError,
    ProjectNotFoundError,
    UserNotFoundError,
)
from app.models.enums import UserRole
from app.models.project import ProjectMember
from app.models.user import User
from app.repositories.project_member_repository import (
    ProjectMemberRepository,
)
from app.repositories.project_repository import ProjectRepository
from app.repositories.user_repository import UserRepository
from app.schemas.project_member import ProjectMemberCreate


class ProjectMemberService:

    def __init__(self, db: Session):
        self.db = db
        self.project_members = ProjectMemberRepository(db)
        self.projects = ProjectRepository(db)
        self.users = UserRepository(db)

    def _get_project_member(
        self,
        member_id: uuid.UUID,
    ) -> ProjectMember:

        member = self.project_members.get_active_by_id(member_id)

        if member is None:
            raise ProjectMemberNotFoundError()

        return member

    def _get_user(
        self,
        user_id: uuid.UUID,
    ) -> User:

        user = self.users.get_active_by_id(user_id)

        if user is None:
            raise UserNotFoundError()

        return user

    def _ensure_project_exists(
        self,
        project_id: uuid.UUID,
    ) -> None:

        project = self.projects.get_active_by_id(project_id)

        if project is None:
            raise ProjectNotFoundError()

    def _ensure_can_add_member(
        self,
        caller: User,
        target: User,
        project_id: uuid.UUID,
    ) -> None:

        if caller.role == UserRole.admin:
            if target.role in (
                UserRole.manager,
                UserRole.employee,
            ):
                return

        if caller.role == UserRole.manager:
            if target.role == UserRole.employee and self.projects.is_member(
                project_id=project_id,
                user_id=caller.id,
            ):
                return

        raise ProjectMemberMutationForbiddenError()

    def _ensure_can_remove_member(
        self,
        caller: User,
        target: User,
        project_id: uuid.UUID,
    ) -> None:

        if caller.role == UserRole.admin:
            if target.role in (UserRole.manager, UserRole.employee):
                return

        if (
            caller.role == UserRole.manager
            and target.role == UserRole.employee
            and self.projects.is_member(
                project_id=project_id,
                user_id=caller.id,
            )
        ):
            return

        raise ProjectMemberMutationForbiddenError()

    def create_project_member(
        self,
        caller: User,
        payload: ProjectMemberCreate,
    ) -> ProjectMember:

        if caller.organization_id is None:
            raise MustBelongToOrganizationError()

        self._ensure_project_exists(payload.project_id)

        target = self._get_user(payload.user_id)

        if target.organization_id != caller.organization_id:
            raise ProjectMemberMutationForbiddenError()

        existing = self.project_members.get_active_by_project_and_user(
            project_id=payload.project_id,
            user_id=payload.user_id,
        )

        if existing is not None:
            raise ProjectMemberAlreadyExistsError()

        self._ensure_can_add_member(
            caller=caller,
            target=target,
            project_id=payload.project_id,
        )
        member = ProjectMember(
            organization_id=caller.organization_id,
            project_id=payload.project_id,
            user_id=payload.user_id,
            added_by=caller.id,
        )

        return self.project_members.add(member)

    def list_project_members(
        self,
        *,
        id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
    ) -> list[ProjectMember]:

        return self.project_members.list_filtered(
            id=id,
            project_id=project_id,
            user_id=user_id,
        )

    def delete_project_member(
        self,
        member_id: uuid.UUID,
        caller: User,
    ) -> None:

        member = self._get_project_member(member_id)

        target = self._get_user(member.user_id)

        self._ensure_can_remove_member(
            caller=caller,
            target=target,
            project_id=member.project_id,
        )

        member.removed_at = datetime.now(timezone.utc)
        member.removed_by = caller.id

        self.db.flush()

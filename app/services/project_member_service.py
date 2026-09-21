import secrets
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.api.pagination import Pagination
from app.core.exception import (
    AppException,
    MustBelongToOrganizationError,
    ProjectMemberAlreadyExistsError,
    ProjectMemberMutationForbiddenError,
    ProjectMemberNotFoundError,
    ProjectNotFoundError,
    UserNotFoundError,
)
from app.core.security import hash_password
from app.models.enums import UserRole, UserStatus
from app.models.project import Project, ProjectMember
from app.models.user import User
from app.repositories.project_member_repository import (
    ProjectMemberRepository,
)
from app.repositories.project_repository import ProjectRepository
from app.repositories.user_repository import UserRepository
from app.schemas.project_member import ProjectMemberCreate
from app.services.email_templates import build_project_url, project_member_added
from app.services.outbox_service import enqueue_email


def _display_name(user: User) -> str:
    name = " ".join(part for part in (user.first_name, user.last_name) if part)
    return name or user.email


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

    def _get_active_user(
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
        organization_id: uuid.UUID,
    ) -> Project:

        project = self.projects.get_active_by_id(project_id)

        if project is None or project.organization_id != organization_id:
            raise ProjectNotFoundError()

        return project

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
        target: User | None,
        project_id: uuid.UUID,
    ) -> None:

        if caller.role == UserRole.admin:
            # A missing user row is treated as employee-level target.
            if target is None or target.role in (UserRole.manager, UserRole.employee):
                return

        if (
            caller.role == UserRole.manager
            and (target is None or target.role == UserRole.employee)
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

        project = self._ensure_project_exists(
            payload.project_id, caller.organization_id
        )

        if payload.user_id is not None:
            target = self._get_active_user(payload.user_id)
        elif payload.email is not None:
            email_clean = payload.email.strip().lower()
            existing_user = self.users.get_by_email(email_clean)
            if existing_user is not None:
                target = existing_user
            else:
                temp_pass = hash_password(secrets.token_urlsafe(16))
                target = User(
                    organization_id=caller.organization_id,
                    email=email_clean,
                    password_hash=temp_pass,
                    role=UserRole.employee,
                    status=UserStatus.active,
                )
                target = self.users.add(target)
        else:
            raise AppException("Either user_id or email must be provided", status_code=422, status_message="Unprocessable Entity")

        if target.organization_id != caller.organization_id:
            raise UserNotFoundError()

        if target.status != UserStatus.active:
            raise AppException(
                "Only active users can be added to a project",
                status_code=409,
                status_message="Conflict",
            )

        # Permission first so duplicate-membership state is not revealed.
        self._ensure_can_add_member(
            caller=caller,
            target=target,
            project_id=payload.project_id,
        )

        existing = self.project_members.get_active_by_project_and_user(
            project_id=payload.project_id,
            user_id=target.id,
        )

        if existing is not None:
            raise ProjectMemberAlreadyExistsError()

        member = ProjectMember(
            organization_id=caller.organization_id,
            project_id=payload.project_id,
            user_id=target.id,
            added_by=caller.id,
        )
        member = self.project_members.add(member)

        # Same transaction as the member row (route commits once).
        if target.id != caller.id:
            subject, text, html = project_member_added(
                recipient_name=_display_name(target),
                project_name=project.name,
                added_by_name=_display_name(caller),
                project_url=build_project_url(project.id),
            )
            enqueue_email(
                self.db,
                organization_id=caller.organization_id,
                to_email=target.email,
                subject=subject,
                body_text=text,
                body_html=html,
            )

        return member

    def list_project_members(
        self,
        *,
        caller: User,
        pagination: Pagination,
        id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
    ) -> list[ProjectMember]:

        return self.project_members.list_filtered(
            id=id,
            project_id=project_id,
            user_id=user_id,
            visible_to_user_id=None if caller.role == UserRole.admin else caller.id,
            limit=pagination.limit,
            offset=pagination.offset,
        )

    def delete_project_member(
        self,
        member_id: uuid.UUID,
        caller: User,
    ) -> None:

        member = self._get_project_member(member_id)

        # Deleted users must not block removal, so no active-only filter here.
        target = self.users.get_by_id(member.user_id)

        self._ensure_can_remove_member(
            caller=caller,
            target=target,
            project_id=member.project_id,
        )

        member.removed_at = datetime.now(timezone.utc)
        member.removed_by = caller.id

        self.db.flush()

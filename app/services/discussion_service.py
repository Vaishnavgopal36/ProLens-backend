import base64
import binascii
import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.exception import AppException, ProjectNotFoundError
from app.models.collaboration import Comment
from app.models.enums import UserRole
from app.models.project import Project
from app.models.user import User
from app.repositories.discussion_repository import DiscussionRepository
from app.repositories.project_repository import ProjectRepository
from app.schemas.discussion import (
    DiscussionAuthor,
    DiscussionCreate,
    DiscussionMessage,
    DiscussionPage,
    ReadMarker,
    UnreadRead,
)


class InvalidCursorError(AppException):
    status_code = 422
    status_message = "Unprocessable Entity"
    default_message = "Invalid cursor"


def encode_cursor(created_at: datetime, comment_id: uuid.UUID) -> str:
    raw = f"{created_at.isoformat()}|{comment_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        created_at_raw, id_raw = raw.split("|", 1)
        created_at = datetime.fromisoformat(created_at_raw)
        comment_id = uuid.UUID(id_raw)
    except (ValueError, TypeError, binascii.Error, UnicodeError):
        raise InvalidCursorError() from None
    if created_at.tzinfo is None:
        raise InvalidCursorError()
    return created_at, comment_id


def author_display_name(user: User) -> str:
    parts = [p.strip() for p in (user.first_name, user.last_name) if p and p.strip()]
    if parts:
        return " ".join(parts)
    return (user.email or "").split("@", 1)[0]


def author_initials(name: str) -> str:
    letters = [w[0] for w in name.replace(".", " ").replace("_", " ").split() if w]
    return "".join(letters[:2]).upper()


def to_message(comment: Comment) -> DiscussionMessage:
    name = author_display_name(comment.author)
    updated = comment.updated_at
    return DiscussionMessage(
        id=comment.id,
        project_id=comment.project_id,
        author=DiscussionAuthor(
            id=comment.author.id, name=name, initials=author_initials(name)
        ),
        content=comment.content,
        created_at=comment.created_at,
        # updated_at defaults to created_at on insert; only a later value is an edit.
        edited=updated is not None and updated > comment.created_at,
    )


class DiscussionService:
    def __init__(self, db: Session):
        self.db = db
        self.projects = ProjectRepository(db)
        self.discussion = DiscussionRepository(db)

    def _get_accessible_project(self, project_id: uuid.UUID, caller: User) -> Project:
        project = self.projects.get_active_by_id(project_id)
        if project is None or project.organization_id != caller.organization_id:
            raise ProjectNotFoundError()
        if caller.role in (UserRole.admin, UserRole.super_admin):
            return project
        if not self.projects.is_member(project_id=project.id, user_id=caller.id):
            raise ProjectNotFoundError()
        return project

    def list_messages(
        self,
        project_id: uuid.UUID,
        caller: User,
        limit: int,
        before: str | None,
    ) -> DiscussionPage:
        self._get_accessible_project(project_id, caller)
        cursor = decode_cursor(before) if before else None
        rows = self.discussion.list_page(
            project_id=project_id, limit=limit + 1, before=cursor
        )
        has_more = len(rows) > limit
        rows = rows[:limit]
        next_cursor = (
            encode_cursor(rows[-1].created_at, rows[-1].id) if has_more else None
        )
        return DiscussionPage(
            items=[to_message(r) for r in rows],
            next_cursor=next_cursor,
            has_more=has_more,
        )

    def post_message(
        self, project_id: uuid.UUID, payload: DiscussionCreate, caller: User
    ) -> DiscussionMessage:
        self._get_accessible_project(project_id, caller)
        comment = Comment(
            organization_id=caller.organization_id,
            author_id=caller.id,
            parent_comment_id=None,
            project_id=project_id,
            content=payload.content,
        )
        comment = self.discussion.add(comment)
        self._mark_read(project_id, caller)
        comment.author = caller
        return to_message(comment)

    def unread(self, project_id: uuid.UUID, caller: User) -> UnreadRead:
        self._get_accessible_project(project_id, caller)
        last_read_at = self.discussion.get_last_read_at(
            project_id=project_id, user_id=caller.id
        )
        count = self.discussion.count_unread(
            project_id=project_id, user_id=caller.id, last_read_at=last_read_at
        )
        return UnreadRead(unread_count=count, last_read_at=last_read_at)

    def mark_read(self, project_id: uuid.UUID, caller: User) -> ReadMarker:
        self._get_accessible_project(project_id, caller)
        return ReadMarker(last_read_at=self._mark_read(project_id, caller))

    def _mark_read(self, project_id: uuid.UUID, caller: User) -> datetime:
        return self.discussion.upsert_read(
            organization_id=caller.organization_id,
            project_id=project_id,
            user_id=caller.id,
        )

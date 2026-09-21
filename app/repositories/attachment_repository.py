import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.models.collaboration import Attachment
from app.repositories.base_repository import BaseRepository


class AttachmentRepository(BaseRepository[Attachment]):
    model = Attachment

    def get_active_by_id(self, attachment_id: uuid.UUID) -> Attachment | None:
        attachment = self.get_by_id(attachment_id)
        if attachment is None or attachment.deleted_at is not None:
            return None
        return attachment

    def s3_key_exists(self, s3_key: str) -> bool:
        # Includes soft-deleted rows: the stored object key must stay unique.
        return (
            self.db.scalar(select(Attachment.id).where(Attachment.s3_key == s3_key))
            is not None
        )

    def list_filtered(
        self,
        *,
        limit: int,
        offset: int,
        id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
        feature_id: uuid.UUID | None = None,
        task_id: uuid.UUID | None = None,
        activity_id: uuid.UUID | None = None,
        uploaded_by: uuid.UUID | None = None,
    ) -> list[Attachment]:
        stmt = select(Attachment).where(Attachment.deleted_at.is_(None))

        if id is not None:
            stmt = stmt.where(Attachment.id == id)
        if project_id is not None:
            stmt = stmt.where(Attachment.project_id == project_id)
        if feature_id is not None:
            stmt = stmt.where(Attachment.feature_id == feature_id)
        if task_id is not None:
            stmt = stmt.where(Attachment.task_id == task_id)
        if activity_id is not None:
            stmt = stmt.where(Attachment.activity_id == activity_id)
        if uploaded_by is not None:
            stmt = stmt.where(Attachment.uploaded_by == uploaded_by)

        stmt = stmt.order_by(Attachment.created_at, Attachment.id)
        return list(self.db.scalars(stmt.limit(limit).offset(offset)))

    def soft_delete(self, attachment: Attachment, deleted_by: uuid.UUID) -> None:
        attachment.deleted_at = datetime.now(timezone.utc)
        attachment.deleted_by = deleted_by
        self.db.flush()

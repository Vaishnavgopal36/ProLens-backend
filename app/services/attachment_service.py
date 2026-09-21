import uuid

from sqlalchemy.orm import Session

from app.api.pagination import Pagination
from app.core import storage
from app.core.config import settings
from app.core.exception import (
    AppException,
    InsufficientPermissionError,
)
from app.models.collaboration import Attachment
from app.models.enums import UserRole
from app.models.user import User
from app.repositories.attachment_repository import AttachmentRepository
from app.repositories.comment_repository import load_target
from app.schemas.attachment import (
    AttachmentCreate,
    AttachmentDownloadUrl,
    AttachmentUploadRequest,
    AttachmentUploadUrl,
)

DELETE_ROLES = (UserRole.admin, UserRole.super_admin, UserRole.manager)


def _bad_request(message: str) -> AppException:
    return AppException(message, status_code=400, status_message="Bad Request")


class AttachmentNotFoundError(AppException):
    status_code = 404
    status_message = "Not Found"
    default_message = "Attachment not found"


class AttachmentService:

    def __init__(self, db: Session):
        self.db = db
        self.attachments = AttachmentRepository(db)

    def create_upload_url(
        self, payload: AttachmentUploadRequest, caller: User
    ) -> AttachmentUploadUrl:
        """Step 1: presigned PUT URL. The client uploads with the same
        Content-Type, then registers the key via create_attachment."""
        if caller.organization_id is None:
            raise _bad_request("User does not belong to an organization")
        if payload.size_bytes > settings.ATTACHMENT_MAX_SIZE_BYTES:
            raise AppException(
                f"File exceeds {settings.ATTACHMENT_MAX_SIZE_BYTES} bytes",
                status_code=413,
                status_message="Payload Too Large",
            )

        key = storage.build_object_key(caller.organization_id, payload.file_name)
        return AttachmentUploadUrl(
            upload_url=storage.create_upload_url(key, payload.mime_type),
            s3_key=key,
            expires_in=settings.ATTACHMENT_URL_EXPIRE_SECONDS,
        )

    def create_attachment(self, payload: AttachmentCreate, caller: User) -> Attachment:
        # Step 2: the file must already be in storage, under the caller's org
        # prefix, and match the declared size.
        if caller.organization_id is None or not storage.key_belongs_to_org(
            payload.s3_key, caller.organization_id
        ):
            raise _bad_request("Invalid s3_key")
        if self.attachments.s3_key_exists(payload.s3_key):
            raise AppException(
                "This file is already registered as an attachment",
                status_code=409,
                status_message="Conflict",
            )

        target = load_target(
            self.db,
            project_id=payload.project_id,
            feature_id=payload.feature_id,
            task_id=payload.task_id,
            activity_id=payload.activity_id,
        )
        if target is None or target.organization_id != caller.organization_id:
            raise AppException(
                "Attachment target not found",
                status_code=404,
                status_message="Not Found",
            )

        stored_size = storage.get_object_size(payload.s3_key)
        if stored_size is None:
            raise _bad_request("File has not been uploaded")
        if (
            stored_size != payload.size_bytes
            or stored_size > settings.ATTACHMENT_MAX_SIZE_BYTES
        ):
            storage.delete_object(payload.s3_key)
            raise _bad_request("Uploaded file size does not match or exceeds the limit")

        attachment = Attachment(
            organization_id=caller.organization_id,
            uploaded_by=caller.id,
            project_id=payload.project_id,
            feature_id=payload.feature_id,
            task_id=payload.task_id,
            activity_id=payload.activity_id,
            file_name=payload.file_name,
            s3_key=payload.s3_key,
            size_bytes=payload.size_bytes,
            mime_type=payload.mime_type,
        )
        return self.attachments.add(attachment)

    def list_attachments(
        self,
        pagination: Pagination,
        attachment_id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
        feature_id: uuid.UUID | None = None,
        task_id: uuid.UUID | None = None,
        activity_id: uuid.UUID | None = None,
        uploaded_by: uuid.UUID | None = None,
    ) -> list[Attachment]:
        return self.attachments.list_filtered(
            limit=pagination.limit,
            offset=pagination.offset,
            id=attachment_id,
            project_id=project_id,
            feature_id=feature_id,
            task_id=task_id,
            activity_id=activity_id,
            uploaded_by=uploaded_by,
        )

    def _get_attachment(self, attachment_id: uuid.UUID, caller: User) -> Attachment:
        attachment = self.attachments.get_active_by_id(attachment_id)
        if attachment is None or (
            caller.role != UserRole.super_admin
            and attachment.organization_id != caller.organization_id
        ):
            raise AttachmentNotFoundError()
        return attachment

    def get_download_url(
        self, attachment_id: uuid.UUID, caller: User
    ) -> AttachmentDownloadUrl:
        attachment = self._get_attachment(attachment_id, caller)
        return AttachmentDownloadUrl(
            download_url=storage.create_download_url(
                attachment.s3_key, attachment.file_name
            ),
            expires_in=settings.ATTACHMENT_URL_EXPIRE_SECONDS,
        )

    def delete_attachment(self, attachment_id: uuid.UUID, caller: User) -> None:
        attachment = self._get_attachment(attachment_id, caller)

        if attachment.uploaded_by != caller.id and caller.role not in DELETE_ROLES:
            raise InsufficientPermissionError()

        self.attachments.soft_delete(attachment, deleted_by=caller.id)

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core import storage
from app.core.config import settings
from app.core.database import get_db
from app.models.collaboration import Attachment
from app.models.project import Feature, Project
from app.models.task import Activity, Task
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.attachment import (
    AttachmentCreate,
    AttachmentDownloadUrl,
    AttachmentRead,
    AttachmentUploadRequest,
    AttachmentUploadUrl,
)
from app.schemas.common_response import APIResponse, success_response

router = APIRouter(
    prefix="/attachments",
    tags=["attachments"],
)


@router.post(
    "/upload-url",
    response_model=APIResponse[AttachmentUploadUrl],
)
def create_upload_url(
    payload: AttachmentUploadRequest,
    caller: User = Depends(get_current_user),
) -> APIResponse[AttachmentUploadUrl]:
    """Step 1: get a presigned URL. The client PUTs the file to it with the
    same Content-Type, then calls POST /attachments with the returned key."""
    if caller.organization_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User does not belong to an organization",
        )
    if payload.size_bytes > settings.ATTACHMENT_MAX_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds {settings.ATTACHMENT_MAX_SIZE_BYTES} bytes",
        )

    key = storage.build_object_key(caller.organization_id, payload.file_name)
    return success_response(
        status_code=status.HTTP_200_OK,
        status_message="Upload URL generated successfully",
        response_data=AttachmentUploadUrl(
            upload_url=storage.create_upload_url(key, payload.mime_type),
            s3_key=key,
            expires_in=settings.ATTACHMENT_URL_EXPIRE_SECONDS,
        ),
    )


@router.post(
    "",
    response_model=APIResponse[AttachmentRead],
    status_code=status.HTTP_201_CREATED,
)
def create_attachment(
    payload: AttachmentCreate,
    db: Session = Depends(get_db),
    caller: User = Depends(get_current_user),
) -> APIResponse[AttachmentRead]:
    # Step 2: the file must already be in storage, under the caller's org
    # prefix, and match the declared size.
    if caller.organization_id is None or not storage.key_belongs_to_org(
        payload.s3_key, caller.organization_id
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid s3_key"
        )
    if db.scalar(select(Attachment.id).where(Attachment.s3_key == payload.s3_key)):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This file is already registered as an attachment",
        )
    # RLS-scoped lookup: the target must exist inside the caller's org.
    for model, target_id in (
        (Project, payload.project_id),
        (Feature, payload.feature_id),
        (Task, payload.task_id),
        (Activity, payload.activity_id),
    ):
        if target_id is not None and db.get(model, target_id) is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Attachment target not found",
            )
    stored_size = storage.get_object_size(payload.s3_key)
    if stored_size is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File has not been uploaded",
        )
    if stored_size != payload.size_bytes or stored_size > (
        settings.ATTACHMENT_MAX_SIZE_BYTES
    ):
        storage.delete_object(payload.s3_key)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file size does not match or exceeds the limit",
        )

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

    db.add(attachment)
    db.flush()
    db.refresh(attachment)
    db.commit()

    return success_response(
        status_code=status.HTTP_201_CREATED,
        status_message="Attachment created successfully",
        response_data=attachment,
    )


@router.get(
    "",
    response_model=APIResponse[list[AttachmentRead]],
)
def list_attachments(
    id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    feature_id: uuid.UUID | None = None,
    task_id: uuid.UUID | None = None,
    activity_id: uuid.UUID | None = None,
    uploaded_by: uuid.UUID | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> APIResponse[list[AttachmentRead]]:
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

    attachments = list(db.scalars(stmt))

    return success_response(
        status_code=status.HTTP_200_OK,
        status_message="Attachments retrieved successfully",
        response_data=attachments,
    )


@router.get(
    "/{attachment_id}/download-url",
    response_model=APIResponse[AttachmentDownloadUrl],
)
def get_download_url(
    attachment_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> APIResponse[AttachmentDownloadUrl]:
    attachment = db.get(Attachment, attachment_id)

    if attachment is None or attachment.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Attachment not found",
        )

    return success_response(
        status_code=status.HTTP_200_OK,
        status_message="Download URL generated successfully",
        response_data=AttachmentDownloadUrl(
            download_url=storage.create_download_url(
                attachment.s3_key, attachment.file_name
            ),
            expires_in=settings.ATTACHMENT_URL_EXPIRE_SECONDS,
        ),
    )


@router.delete(
    "/{attachment_id}",
    response_model=APIResponse[None],
    status_code=status.HTTP_200_OK,
)
def delete_attachment(
    attachment_id: uuid.UUID,
    db: Session = Depends(get_db),
    caller: User = Depends(get_current_user),
) -> APIResponse[None]:
    attachment = db.get(Attachment, attachment_id)

    if attachment is None or attachment.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Attachment not found",
        )

    if caller.id != attachment.uploaded_by and caller.role != UserRole.admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )

    attachment.deleted_at = datetime.now(timezone.utc)
    attachment.deleted_by = caller.id

    db.commit()

    return success_response(
        status_code=status.HTTP_200_OK,
        status_message="Attachment deleted successfully",
        response_data=None,
    )

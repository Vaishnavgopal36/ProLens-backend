import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.collaboration import Attachment
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.attachment import AttachmentCreate, AttachmentRead
from app.schemas.common_response import APIResponse, success_response, COMMON_RESPONSES

router = APIRouter(
    prefix="/attachments",
    tags=["attachments"],
    responses=COMMON_RESPONSES,
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

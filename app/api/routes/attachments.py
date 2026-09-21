import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.pagination import Pagination, get_pagination
from app.core.database import get_db
from app.models.user import User
from app.schemas.attachment import (
    AttachmentCreate,
    AttachmentDownloadUrl,
    AttachmentRead,
    AttachmentUploadRequest,
    AttachmentUploadUrl,
)
from app.schemas.common_response import APIResponse, success_response
from app.services.attachment_service import AttachmentService

router = APIRouter(
    prefix="/attachments",
    tags=["attachments"],
)


def get_attachment_service(db: Session = Depends(get_db)) -> AttachmentService:
    return AttachmentService(db)


@router.post(
    "/upload-url",
    response_model=APIResponse[AttachmentUploadUrl],
)
def create_upload_url(
    payload: AttachmentUploadRequest,
    caller: User = Depends(get_current_user),
    service: AttachmentService = Depends(get_attachment_service),
) -> APIResponse[AttachmentUploadUrl]:
    upload = service.create_upload_url(payload=payload, caller=caller)

    return success_response(
        status_code=status.HTTP_200_OK,
        status_message="Upload URL generated successfully",
        response_data=upload,
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
    service: AttachmentService = Depends(get_attachment_service),
) -> APIResponse[AttachmentRead]:
    attachment = service.create_attachment(payload=payload, caller=caller)
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
    pagination: Pagination = Depends(get_pagination),
    _: User = Depends(get_current_user),
    service: AttachmentService = Depends(get_attachment_service),
) -> APIResponse[list[AttachmentRead]]:
    attachments = service.list_attachments(
        pagination=pagination,
        attachment_id=id,
        project_id=project_id,
        feature_id=feature_id,
        task_id=task_id,
        activity_id=activity_id,
        uploaded_by=uploaded_by,
    )

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
    caller: User = Depends(get_current_user),
    service: AttachmentService = Depends(get_attachment_service),
) -> APIResponse[AttachmentDownloadUrl]:
    download = service.get_download_url(attachment_id=attachment_id, caller=caller)

    return success_response(
        status_code=status.HTTP_200_OK,
        status_message="Download URL generated successfully",
        response_data=download,
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
    service: AttachmentService = Depends(get_attachment_service),
) -> APIResponse[None]:
    service.delete_attachment(attachment_id=attachment_id, caller=caller)
    db.commit()

    return success_response(
        status_code=status.HTTP_200_OK,
        status_message="Attachment deleted successfully",
        response_data=None,
    )

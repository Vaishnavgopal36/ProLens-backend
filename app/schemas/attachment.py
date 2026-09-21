import uuid
from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class _AttachmentTarget(BaseModel):
    project_id: uuid.UUID | None = None
    feature_id: uuid.UUID | None = None
    task_id: uuid.UUID | None = None
    activity_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def check_exclusive_arc(self):
        targets = [self.project_id, self.feature_id, self.task_id, self.activity_id]
        if sum(target is not None for target in targets) != 1:
            raise ValueError(
                "Exactly one of project_id, feature_id, task_id, activity_id must be set"
            )
        return self


class AttachmentUploadRequest(BaseModel):
    file_name: str = Field(min_length=1, max_length=255)
    mime_type: str = Field(min_length=1, max_length=100)
    size_bytes: int = Field(gt=0)


class AttachmentUploadUrl(BaseModel):
    upload_url: str
    s3_key: str
    expires_in: int


class AttachmentDownloadUrl(BaseModel):
    download_url: str
    expires_in: int


class AttachmentCreate(_AttachmentTarget):
    file_name: str = Field(min_length=1, max_length=255)
    s3_key: str = Field(min_length=1, max_length=500)
    size_bytes: int = Field(gt=0)
    mime_type: str = Field(min_length=1, max_length=100)


class AttachmentRead(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    uploaded_by: uuid.UUID
    project_id: uuid.UUID | None
    feature_id: uuid.UUID | None
    task_id: uuid.UUID | None
    activity_id: uuid.UUID | None
    file_name: str
    s3_key: str
    size_bytes: int
    mime_type: str
    created_at: datetime

    model_config = {"from_attributes": True}

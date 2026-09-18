import uuid
from datetime import datetime

from pydantic import BaseModel, model_validator


class CommentCreate(BaseModel):
    project_id: uuid.UUID | None = None
    feature_id: uuid.UUID | None = None
    task_id: uuid.UUID | None = None
    activity_id: uuid.UUID | None = None
    parent_comment_id: uuid.UUID | None = None
    content: str

    @model_validator(mode="after")
    def check_exclusive_arc(self) -> "CommentCreate":
        targets = [self.project_id, self.feature_id, self.task_id, self.activity_id]
        if sum(target is not None for target in targets) != 1:
            raise ValueError(
                "Exactly one of project_id, feature_id, task_id, activity_id must be set"
            )
        return self


class CommentUpdate(BaseModel):
    content: str


class CommentRead(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    author_id: uuid.UUID
    parent_comment_id: uuid.UUID | None
    project_id: uuid.UUID | None
    feature_id: uuid.UUID | None
    task_id: uuid.UUID | None
    activity_id: uuid.UUID | None
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}

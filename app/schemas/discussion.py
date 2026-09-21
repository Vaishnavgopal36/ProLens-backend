import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DiscussionAuthor(BaseModel):
    id: uuid.UUID
    name: str
    initials: str


class DiscussionMessage(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    author: DiscussionAuthor
    content: str
    created_at: datetime
    edited: bool


class DiscussionPage(BaseModel):
    items: list[DiscussionMessage]
    next_cursor: str | None
    has_more: bool


class DiscussionCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    content: str = Field(min_length=1, max_length=10_000)


class UnreadRead(BaseModel):
    unread_count: int
    last_read_at: datetime | None


class ReadMarker(BaseModel):
    last_read_at: datetime

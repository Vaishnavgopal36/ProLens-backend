"""Build and publish discussion real-time events. Never raises."""

import logging
import uuid

from app.core import realtime
from app.models.collaboration import Comment
from app.schemas.discussion import DiscussionMessage
from app.services.discussion_service import to_message

logger = logging.getLogger(__name__)


def message_event(event_type: str, message: DiscussionMessage) -> dict:
    return {"type": event_type, "data": message.model_dump(mode="json")}


def deleted_event(comment_id: uuid.UUID, project_id: uuid.UUID) -> dict:
    return {
        "type": "message.deleted",
        "data": {"id": str(comment_id), "project_id": str(project_id)},
    }


def build_comment_event(event_type: str, comment: Comment) -> dict | None:
    """Event for a project comment; None for task/feature/activity comments."""
    try:
        if comment.project_id is None:
            return None
        if event_type == "message.deleted":
            return deleted_event(comment.id, comment.project_id)
        return message_event(event_type, to_message(comment))
    except Exception:  # noqa: BLE001
        logger.exception("Failed to build discussion event")
        return None


def publish_event(project_id: uuid.UUID | None, event: dict | None) -> None:
    """Call only AFTER the DB commit succeeded."""
    if project_id is None or event is None:
        return
    try:
        realtime.manager.publish_threadsafe(project_id, event)
    except Exception:  # noqa: BLE001
        logger.exception("Failed to publish discussion event")

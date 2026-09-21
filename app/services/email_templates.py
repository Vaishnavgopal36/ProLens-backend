import uuid
from html import escape

from app.core.config import settings


def project_member_added(
    recipient_name: str,
    project_name: str,
    added_by_name: str,
    project_url: str,
) -> tuple[str, str, str]:
    """Return (subject, text_body, html_body)."""
    subject = f"You were added to {project_name}"[:255]
    text = (
        f"Hi {recipient_name},\n\n"
        f'{added_by_name} added you to the project "{project_name}".\n\n'
        f"Open the project: {project_url}\n"
    )
    html = (
        f"<p>Hi {escape(recipient_name)},</p>"
        f"<p>{escape(added_by_name)} added you to the project "
        f"<strong>{escape(project_name)}</strong>.</p>"
        f'<p><a href="{escape(project_url, quote=True)}">Open the project</a></p>'
    )
    return subject, text, html


def build_project_url(project_id: uuid.UUID) -> str:
    return f"{settings.FRONTEND_BASE_URL.rstrip('/')}/projects/{project_id}"

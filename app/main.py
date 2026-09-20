from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError

from app.api.routes import (
    activities,
    activity_assignees,
    attachments,
    auth,
    calendar_events,
    comments,
    designations,
    feature_members,
    features,
    invitations,
    leave_logs,
    organizations,
    project_members,
    projects,
    sso,
    task_assignees,
    tasks,
    time_logs,
    users,
)
from app.core.exception import AppException
from app.core.exception_handlers import (
    app_exception_handler,
    generic_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)

app = FastAPI(title="ProLens API")

app.add_exception_handler(AppException, app_exception_handler)
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, generic_exception_handler)

app.include_router(auth.router)
app.include_router(organizations.router)
app.include_router(users.router)
app.include_router(sso.router)
app.include_router(designations.router)
app.include_router(projects.router)
app.include_router(feature_members.router)
app.include_router(features.router)
app.include_router(invitations.router)
app.include_router(leave_logs.router)
app.include_router(project_members.router)
app.include_router(task_assignees.router)
app.include_router(tasks.router)
app.include_router(time_logs.router)
app.include_router(calendar_events.router)
app.include_router(comments.router)
app.include_router(attachments.router)
app.include_router(activities.router)
app.include_router(activity_assignees.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
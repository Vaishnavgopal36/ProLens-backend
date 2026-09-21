from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import DataError, IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes import (
    activities,
    activity_assignees,
    attachments,
    auth,
    calendar_events,
    comments,
    designations,
    discussion,
    feature_members,
    features,
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
from app.core.config import settings
from app.core.exception import AppException
from app.core.exception_handlers import (
    app_exception_handler,
    data_error_handler,
    generic_exception_handler,
    http_exception_handler,
    integrity_error_handler,
    storage_exception_handler,
    validation_exception_handler,
)
from app.core.storage import StorageError

app = FastAPI(title="ProLens API")

app.add_exception_handler(AppException, app_exception_handler)
app.add_exception_handler(StorageError, storage_exception_handler)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(IntegrityError, integrity_error_handler)
app.add_exception_handler(DataError, data_error_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, generic_exception_handler)

# Explicit lists: "*" is not allowed together with credentials (cookie auth).
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Accept", "Authorization"],
)

app.include_router(auth.router)
app.include_router(organizations.router)
app.include_router(users.router)
app.include_router(sso.router)
app.include_router(designations.router)
app.include_router(projects.router)
app.include_router(feature_members.router)
app.include_router(features.router)
app.include_router(leave_logs.router)
app.include_router(project_members.router)
app.include_router(task_assignees.router)
app.include_router(tasks.router)
app.include_router(time_logs.router)
app.include_router(calendar_events.router)
app.include_router(comments.router)
app.include_router(discussion.router)
app.include_router(attachments.router)
app.include_router(activities.router)
app.include_router(activity_assignees.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}

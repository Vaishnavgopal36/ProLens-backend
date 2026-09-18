from app.models.user import User
from sqlalchemy.orm import Session
from app.schemas.project import ProjectCreate, ProjectRead
from fastapi import Depends, APIRouter, status as http_status
from app.api.deps import require_roles
from app.models.enums import UserRole
from app.schemas.common_response import success_response, APIResponse
from app.core.database import get_db
from app.models.enums import ProjectStatus, UserRole
from app.models.project import Feature, Project, ProjectMember
from app.models.task import Task
from app.models.user import User
from app.schemas.project import ProjectCreate, ProjectRead, ProjectUpdate
from app.schemas.common_response import APIResponse, success_response

router = APIRouter(
    prefix="/projects",
    tags=["projects"],
)
from app.services.project_service import ProjectService

router = APIRouter(prefix="/projects", tags=["projects"])

require_creator = require_roles(UserRole.admin, UserRole.manager)


@router.post(
    "",
    response_model=APIResponse[ProjectRead],
    status_code=http_status.HTTP_201_CREATED,
)
def create_project(
    payload: ProjectCreate,
    db: Session = Depends(get_db),
    caller: User = Depends(require_creator),
) -> APIResponse[ProjectRead]:
    service = ProjectService(db)

    project = service.create_project(
        caller=caller,
        payload=payload,
    )

    db.commit()

    return success_response(
        status_code=http_status.HTTP_201_CREATED,
        status_message="Project created successfully",
        response_data=project,
    )

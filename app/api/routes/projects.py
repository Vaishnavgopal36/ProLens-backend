import uuid

from fastapi import APIRouter, Depends
from fastapi import status as http_status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.api.pagination import Pagination, get_pagination
from app.core.database import get_db
from app.models.enums import ProjectStatus, UserRole
from app.models.user import User
from app.schemas.common_response import APIResponse, success_response
from app.schemas.project import ProjectCreate, ProjectRead, ProjectUpdate
from app.services.project_service import ProjectService

router = APIRouter(prefix="/projects", tags=["projects"])

# Creating a project is portfolio ownership, so it is admin-only. Managers run
# delivery on projects they belong to and can staff them with employees.
require_creator = require_roles(UserRole.admin)


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


@router.get(
    "",
    response_model=APIResponse[list[ProjectRead]],
    status_code=http_status.HTTP_200_OK,
)
def list_projects(
    id: uuid.UUID | None = None,
    status: ProjectStatus | None = None,
    organization_id: uuid.UUID | None = None,
    include_insights: bool = False,
    pagination: Pagination = Depends(get_pagination),
    db: Session = Depends(get_db),
    caller: User = Depends(get_current_user),
) -> APIResponse[list[ProjectRead]]:

    service = ProjectService(db)

    projects = service.list_projects(
        caller=caller,
        id=id,
        status=status,
        organization_id=organization_id,
        include_insights=include_insights,
        limit=pagination.limit,
        offset=pagination.offset,
    )

    return success_response(
        status_code=http_status.HTTP_200_OK,
        status_message="Projects retrieved successfully",
        response_data=projects,
    )


@router.patch(
    "/{project_id}",
    response_model=APIResponse[ProjectRead],
    status_code=http_status.HTTP_200_OK,
)
def update_project(
    project_id: uuid.UUID,
    payload: ProjectUpdate,
    db: Session = Depends(get_db),
    caller: User = Depends(get_current_user),
) -> APIResponse[ProjectRead]:

    service = ProjectService(db)

    project = service.update_project(
        project_id=project_id,
        payload=payload,
        caller=caller,
    )

    db.commit()

    return success_response(
        status_code=http_status.HTTP_200_OK,
        status_message="Project updated successfully",
        response_data=project,
    )


@router.delete(
    "/{project_id}",
    response_model=APIResponse[None],
    status_code=http_status.HTTP_200_OK,
)
def delete_project(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    caller: User = Depends(get_current_user),
) -> APIResponse[None]:

    service = ProjectService(db)

    service.delete_project(
        project_id=project_id,
        caller=caller,
    )

    db.commit()

    return success_response(
        status_code=http_status.HTTP_200_OK,
        status_message="Project deleted successfully",
        response_data=None,
    )

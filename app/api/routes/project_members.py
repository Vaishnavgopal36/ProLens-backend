import uuid

from fastapi import APIRouter, Depends
from fastapi import status as http_status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.common_response import APIResponse, success_response
from app.schemas.project_member import (
    ProjectMemberCreate,
    ProjectMemberRead,
)
from app.services.project_member_service import ProjectMemberService

router = APIRouter(
    prefix="/project-members",
    tags=["project-members"],
)


@router.post(
    "",
    response_model=APIResponse[ProjectMemberRead],
    status_code=http_status.HTTP_201_CREATED,
)
def create_project_member(
    payload: ProjectMemberCreate,
    db: Session = Depends(get_db),
    caller: User = Depends(get_current_user),
) -> APIResponse[ProjectMemberRead]:

    service = ProjectMemberService(db)

    member = service.create_project_member(
        caller=caller,
        payload=payload,
    )

    db.commit()

    return success_response(
        status_code=http_status.HTTP_201_CREATED,
        status_message="Project member created successfully",
        response_data=member,
    )


@router.get(
    "",
    response_model=APIResponse[list[ProjectMemberRead]],
    status_code=http_status.HTTP_200_OK,
)
def list_project_members(
    id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> APIResponse[list[ProjectMemberRead]]:

    service = ProjectMemberService(db)

    members = service.list_project_members(
        id=id,
        project_id=project_id,
        user_id=user_id,
    )

    return success_response(
        status_code=http_status.HTTP_200_OK,
        status_message="Project members retrieved successfully",
        response_data=members,
    )


@router.delete(
    "/{member_id}",
    response_model=APIResponse[None],
    status_code=http_status.HTTP_200_OK,
)
def delete_project_member(
    member_id: uuid.UUID,
    db: Session = Depends(get_db),
    caller: User = Depends(get_current_user),
) -> APIResponse[None]:

    service = ProjectMemberService(db)

    service.delete_project_member(
        member_id=member_id,
        caller=caller,
    )

    db.commit()

    return success_response(
        status_code=http_status.HTTP_200_OK,
        status_message="Project member deleted successfully",
        response_data=None,
    )

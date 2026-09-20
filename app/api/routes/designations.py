import uuid
from fastapi import APIRouter, Depends
from fastapi import status as http_status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.core.database import get_db
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.common_response import APIResponse, success_response
from app.schemas.designation import (
    DesignationCreate,
    DesignationRead,
    DesignationUpdate,
)
from app.services.designation_service import DesignationService

router = APIRouter(
    prefix="/designations",
    tags=["designations"],
)

require_admin = require_roles(UserRole.admin, UserRole.super_admin)


@router.post(
    "",
    response_model=APIResponse[DesignationRead],
    status_code=http_status.HTTP_201_CREATED,
)
def create_designation(
    payload: DesignationCreate,
    db: Session = Depends(get_db),
    caller: User = Depends(require_admin),
) -> APIResponse[DesignationRead]:
    designation = DesignationService(db).create_designation(caller, payload)
    db.commit()

    return success_response(
        status_code=http_status.HTTP_201_CREATED,
        status_message="Designation created successfully",
        response_data=designation,
    )


@router.get("", response_model=APIResponse[list[DesignationRead]])
def list_designations(
    id: uuid.UUID | None = None,
    name: str | None = None,
    db: Session = Depends(get_db),
    caller: User = Depends(get_current_user),   
) -> APIResponse[list[DesignationRead]]:
    designations = DesignationService(db).list_designations(caller, id=id, name=name)  

    return success_response(
        status_code=http_status.HTTP_200_OK,
        status_message="Designations retrieved successfully",
        response_data=designations,
    )


@router.patch("/{designation_id}", response_model=APIResponse[DesignationRead])
def update_designation(
    designation_id: uuid.UUID,
    payload: DesignationUpdate,
    db: Session = Depends(get_db),
    caller: User = Depends(require_admin),   
) -> APIResponse[DesignationRead]:
    designation = DesignationService(db).update_designation(caller, designation_id, payload)
    db.commit()

    return success_response(
        status_code=http_status.HTTP_200_OK,
        status_message="Designation updated successfully",
        response_data=designation,
    )


@router.delete(
    "/{designation_id}",
    response_model=APIResponse[None],
    status_code=http_status.HTTP_200_OK,
)
def delete_designation(
    designation_id: uuid.UUID,
    db: Session = Depends(get_db),
    caller: User = Depends(require_admin),
) -> APIResponse[None]:
    DesignationService(db).delete_designation(caller, designation_id)  
    db.commit()

    return success_response(
        status_code=http_status.HTTP_200_OK,
        status_message="Designation deleted successfully",
        response_data=None,
    )
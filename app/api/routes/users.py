# app/api/routes/users.py

import uuid

from fastapi import APIRouter, Depends
from fastapi import status as http_status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.api.pagination import Pagination, get_pagination
from app.core.database import get_db
from app.models.enums import UserRole, UserStatus
from app.models.user import User
from app.schemas.common_response import APIResponse, success_response
from app.schemas.user import UserCreate, UserRead, UserUpdate
from app.services.user_service import UserService

router = APIRouter(
    prefix="/users",
    tags=["users"],
)

require_admin = require_roles(UserRole.admin, UserRole.super_admin)


@router.post(
    "",
    response_model=APIResponse[UserRead],
    status_code=http_status.HTTP_201_CREATED,
)
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    caller: User = Depends(require_admin),
) -> APIResponse[UserRead]:
    user = UserService(db).create_user(caller, payload)
    db.commit()

    return success_response(
        status_code=http_status.HTTP_201_CREATED,
        status_message="User created successfully",
        response_data=user,
    )


@router.get("", response_model=APIResponse[list[UserRead]])
def list_users(
    id: uuid.UUID | None = None,
    organization_id: uuid.UUID | None = None,
    role: UserRole | None = None,
    status: UserStatus | None = None,
    pagination: Pagination = Depends(get_pagination),
    db: Session = Depends(get_db),
    caller: User = Depends(require_admin),
) -> APIResponse[list[UserRead]]:
    users = UserService(db).list_users(
        caller,
        id=id,
        organization_id=organization_id,
        role=role,
        status=status,
        limit=pagination.limit,
        offset=pagination.offset,
    )

    return success_response(
        status_code=http_status.HTTP_200_OK,
        status_message="Users retrieved successfully",
        response_data=users,
    )


@router.patch("/{user_id}", response_model=APIResponse[UserRead])
def update_user(
    user_id: uuid.UUID,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    # Any authenticated user; UserService decides what each role may edit.
    caller: User = Depends(get_current_user),
) -> APIResponse[UserRead]:
    user = UserService(db).update_user(caller, user_id, payload)
    db.commit()

    return success_response(
        status_code=http_status.HTTP_200_OK,
        status_message="User updated successfully",
        response_data=user,
    )


@router.delete(
    "/{user_id}",
    response_model=APIResponse[None],
    status_code=http_status.HTTP_200_OK,
)
def delete_user(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    caller: User = Depends(require_admin),
) -> APIResponse[None]:
    UserService(db).delete_user(caller, user_id)
    db.commit()

    return success_response(
        status_code=http_status.HTTP_200_OK,
        status_message="User deleted successfully",
        response_data=None,
    )

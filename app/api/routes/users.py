import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.core.database import get_db
from app.core.security import hash_password
from app.models.enums import UserRole, UserStatus
from app.models.user import User
from app.schemas.common_response import APIResponse, success_response, COMMON_RESPONSES
from app.schemas.user import UserCreate, UserRead, UserUpdate

router = APIRouter(
    prefix="/users",
    tags=["users"],
    responses=COMMON_RESPONSES,
)

require_admin = require_roles(
    UserRole.admin,
    UserRole.super_admin,
)


def build_user(
    db: Session,
    organization_id: uuid.UUID | None,
    payload: UserCreate,
) -> User:
    if db.scalar(select(User).where(User.email == payload.email)):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already in use",
        )

    return User(
        organization_id=organization_id,
        designation_id=payload.designation_id,
        email=payload.email,
        password_hash=hash_password(payload.password),
        first_name=payload.first_name,
        last_name=payload.last_name,
        role=payload.role,
        status=UserStatus.invited,
    )


def _resolve_organization_id(
    caller: User,
    payload: UserCreate,
) -> uuid.UUID:
    if caller.role == UserRole.super_admin:
        if payload.organization_id is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="organization_id is required",
            )

        return payload.organization_id

    if payload.organization_id not in (
        None,
        caller.organization_id,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot create users outside your organization",
        )

    return caller.organization_id


@router.post(
    "",
    response_model=APIResponse[UserRead],
    status_code=status.HTTP_201_CREATED,
)
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    caller: User = Depends(require_admin),
) -> APIResponse[UserRead]:
    organization_id = _resolve_organization_id(
        caller,
        payload,
    )

    user = build_user(
        db,
        organization_id,
        payload,
    )

    db.add(user)
    db.flush()
    db.refresh(user)
    db.commit()

    return success_response(
        status_code=status.HTTP_201_CREATED,
        status_message="User created successfully",
        response_data=user,
    )


@router.get(
    "",
    response_model=APIResponse[list[UserRead]],
)
def list_users(
    id: uuid.UUID | None = None,
    organization_id: uuid.UUID | None = None,
    role: UserRole | None = None,
    status: UserStatus | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> APIResponse[list[UserRead]]:
    stmt = select(User).where(User.deleted_at.is_(None))

    if id is not None:
        stmt = stmt.where(User.id == id)

    if organization_id is not None:
        stmt = stmt.where(User.organization_id == organization_id)

    if role is not None:
        stmt = stmt.where(User.role == role)

    if status is not None:
        stmt = stmt.where(User.status == status)

    users = list(db.scalars(stmt))

    return success_response(
        status_code=status.HTTP_200_OK,
        status_message="Users retrieved successfully",
        response_data=users,
    )


@router.patch(
    "/{user_id}",
    response_model=APIResponse[UserRead],
)
def update_user(
    user_id: uuid.UUID,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> APIResponse[UserRead]:
    user = db.get(User, user_id)

  
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(user, field, value)

    db.flush()
    db.refresh(user)
    db.commit()

    return success_response(
        status_code=status.HTTP_200_OK,
        status_message="User updated successfully",
        response_data=user,
    )


@router.delete(
    "/{user_id}",
    response_model=APIResponse[None],
    status_code=status.HTTP_200_OK,
)
def delete_user(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    caller: User = Depends(require_admin),
) -> APIResponse[None]:
    user = db.get(User, user_id)

    if user is None or user.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    user.deleted_at = datetime.now(timezone.utc)
    user.deleted_by = caller.id

    db.commit()

    return success_response(
        status_code=status.HTTP_200_OK,
        status_message="User deleted successfully",
        response_data=None,
    )

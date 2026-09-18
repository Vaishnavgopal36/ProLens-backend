import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.enums import EntityStatus, UserRole
from app.models.project import Feature, ProjectMember
from app.models.user import User
from app.schemas.feature import FeatureCreate, FeatureRead, FeatureUpdate
from app.schemas.common_response import APIResponse, success_response

router = APIRouter(
    prefix="/features",
    tags=["features"],
)


def _is_active_project_member(
    db: Session,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
) -> bool:
    return (
        db.scalar(
            select(ProjectMember).where(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == user_id,
                ProjectMember.removed_at.is_(None),
            )
        )
        is not None
    )


def _ensure_can_manage_feature(
    db: Session,
    caller: User,
    project_id: uuid.UUID,
) -> None:
    if caller.role == UserRole.admin:
        return

    if caller.role == UserRole.manager and _is_active_project_member(
        db,
        project_id,
        caller.id,
    ):
        return

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Insufficient permissions",
    )


@router.post(
    "",
    response_model=APIResponse[FeatureRead],
    status_code=status.HTTP_201_CREATED,
)
def create_feature(
    payload: FeatureCreate,
    db: Session = Depends(get_db),
    caller: User = Depends(get_current_user),
) -> APIResponse[FeatureRead]:
    if caller.organization_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )

    _ensure_can_manage_feature(
        db,
        caller,
        payload.project_id,
    )

    feature = Feature(
        organization_id=caller.organization_id,
        project_id=payload.project_id,
        name=payload.name,
        description=payload.description,
        status=EntityStatus.to_do,
        created_by=caller.id,
    )

    db.add(feature)
    db.flush()
    db.refresh(feature)
    db.commit()

    return success_response(
        status_code=status.HTTP_201_CREATED,
        status_message="Feature created successfully",
        response_data=feature,
    )


@router.get(
    "",
    response_model=APIResponse[list[FeatureRead]],
)
def list_features(
    id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    status: EntityStatus | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> APIResponse[list[FeatureRead]]:
    stmt = select(Feature).where(Feature.deleted_at.is_(None))

    if id is not None:
        stmt = stmt.where(Feature.id == id)

    if project_id is not None:
        stmt = stmt.where(Feature.project_id == project_id)

    if status is not None:
        stmt = stmt.where(Feature.status == status)

    features = list(db.scalars(stmt))

    return success_response(
        status_code=status.HTTP_200_OK,
        status_message="Features retrieved successfully",
        response_data=features,
    )


@router.patch(
    "/{feature_id}",
    response_model=APIResponse[FeatureRead],
)
def update_feature(
    feature_id: uuid.UUID,
    payload: FeatureUpdate,
    db: Session = Depends(get_db),
    caller: User = Depends(get_current_user),
) -> APIResponse[FeatureRead]:
    feature = db.get(
        Feature,
        feature_id,
    )

    if feature is None or feature.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Feature not found",
        )

    _ensure_can_manage_feature(
        db,
        caller,
        feature.project_id,
    )

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(feature, field, value)

    feature.updated_by = caller.id

    db.flush()
    db.refresh(feature)
    db.commit()

    return success_response(
        status_code=status.HTTP_200_OK,
        status_message="Feature updated successfully",
        response_data=feature,
    )


@router.delete(
    "/{feature_id}",
    response_model=APIResponse[None],
    status_code=status.HTTP_200_OK,
)
def delete_feature(
    feature_id: uuid.UUID,
    db: Session = Depends(get_db),
    caller: User = Depends(get_current_user),
) -> APIResponse[None]:
    feature = db.get(
        Feature,
        feature_id,
    )

    if feature is None or feature.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Feature not found",
        )

    _ensure_can_manage_feature(
        db,
        caller,
        feature.project_id,
    )

    feature.deleted_at = datetime.now(timezone.utc)
    feature.deleted_by = caller.id

    db.commit()

    return success_response(
        status_code=status.HTTP_200_OK,
        status_message="Feature deleted successfully",
        response_data=None,
    )

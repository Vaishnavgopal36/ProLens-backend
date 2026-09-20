import uuid

from fastapi import APIRouter, Depends
from fastapi import status as http_status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.enums import EntityStatus
from app.models.user import User
from app.schemas.common_response import APIResponse, success_response
from app.schemas.feature import (
    FeatureCreate,
    FeatureRead,
    FeatureUpdate,
)
from app.services.feature_service import FeatureService

router = APIRouter(
    prefix="/features",
    tags=["features"],
)


@router.post(
    "",
    response_model=APIResponse[FeatureRead],
    status_code=http_status.HTTP_201_CREATED,
)
def create_feature(
    payload: FeatureCreate,
    db: Session = Depends(get_db),
    caller: User = Depends(get_current_user),
) -> APIResponse[FeatureRead]:

    service = FeatureService(db)

    feature = service.create_feature(
        caller=caller,
        payload=payload,
    )

    db.commit()

    return success_response(
        status_code=http_status.HTTP_201_CREATED,
        status_message="Feature created successfully",
        response_data=feature,
    )


@router.get(
    "",
    response_model=APIResponse[list[FeatureRead]],
    status_code=http_status.HTTP_200_OK,
)
def list_features(
    id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    status: EntityStatus | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> APIResponse[list[FeatureRead]]:

    service = FeatureService(db)

    features = service.list_features(
        id=id,
        project_id=project_id,
        status=status,
    )

    return success_response(
        status_code=http_status.HTTP_200_OK,
        status_message="Features retrieved successfully",
        response_data=features,
    )


@router.patch(
    "/{feature_id}",
    response_model=APIResponse[FeatureRead],
    status_code=http_status.HTTP_200_OK,
)
def update_feature(
    feature_id: uuid.UUID,
    payload: FeatureUpdate,
    db: Session = Depends(get_db),
    caller: User = Depends(get_current_user),
) -> APIResponse[FeatureRead]:

    service = FeatureService(db)

    feature = service.update_feature(
        feature_id=feature_id,
        payload=payload,
        caller=caller,
    )

    db.commit()

    return success_response(
        status_code=http_status.HTTP_200_OK,
        status_message="Feature updated successfully",
        response_data=feature,
    )


@router.delete(
    "/{feature_id}",
    response_model=APIResponse[None],
    status_code=http_status.HTTP_200_OK,
)
def delete_feature(
    feature_id: uuid.UUID,
    db: Session = Depends(get_db),
    caller: User = Depends(get_current_user),
) -> APIResponse[None]:

    service = FeatureService(db)

    service.delete_feature(
        feature_id=feature_id,
        caller=caller,
    )

    db.commit()

    return success_response(
        status_code=http_status.HTTP_200_OK,
        status_message="Feature deleted successfully",
        response_data=None,
    )

import uuid

from fastapi import APIRouter, Depends
from fastapi import status as http_status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.common_response import APIResponse, success_response
from app.schemas.feature_member import (
    FeatureMemberCreate,
    FeatureMemberRead,
)
from app.services.feature_member_service import FeatureMemberService

router = APIRouter(
    prefix="/feature-members",
    tags=["feature-members"],
)


@router.post(
    "",
    response_model=APIResponse[FeatureMemberRead],
    status_code=http_status.HTTP_201_CREATED,
)
def create_feature_member(
    payload: FeatureMemberCreate,
    db: Session = Depends(get_db),
    caller: User = Depends(get_current_user),
) -> APIResponse[FeatureMemberRead]:

    service = FeatureMemberService(db)

    member = service.create_feature_member(
        caller=caller,
        payload=payload,
    )

    db.commit()

    return success_response(
        status_code=http_status.HTTP_201_CREATED,
        status_message="Feature member created successfully",
        response_data=member,
    )


@router.get(
    "",
    response_model=APIResponse[list[FeatureMemberRead]],
    status_code=http_status.HTTP_200_OK,
)
def list_feature_members(
    id: uuid.UUID | None = None,
    feature_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> APIResponse[list[FeatureMemberRead]]:

    service = FeatureMemberService(db)

    members = service.list_feature_members(
        id=id,
        feature_id=feature_id,
        user_id=user_id,
    )

    return success_response(
        status_code=http_status.HTTP_200_OK,
        status_message="Feature members retrieved successfully",
        response_data=members,
    )


@router.delete(
    "/{feature_member_id}",
    response_model=APIResponse[None],
    status_code=http_status.HTTP_200_OK,
)
def delete_feature_member(
    feature_member_id: uuid.UUID,
    db: Session = Depends(get_db),
    caller: User = Depends(get_current_user),
) -> APIResponse[None]:

    service = FeatureMemberService(db)

    service.delete_feature_member(
        feature_member_id=feature_member_id,
        caller=caller,
    )

    db.commit()

    return success_response(
        status_code=http_status.HTTP_200_OK,
        status_message="Feature member deleted successfully",
        response_data=None,
    )

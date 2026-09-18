import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
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

require_creator = require_roles(
    UserRole.admin,
    UserRole.manager,
)


def _is_member(
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


def _authorize_mutation(
    db: Session,
    caller: User,
    project: Project,
) -> None:
    if caller.role == UserRole.admin:
        return

    if caller.role == UserRole.manager and _is_member(db, project.id, caller.id):
        return

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Insufficient permissions",
    )


@router.post(
    "",
    response_model=APIResponse[ProjectRead],
    status_code=status.HTTP_201_CREATED,
)
def create_project(
    payload: ProjectCreate,
    db: Session = Depends(get_db),
    caller: User = Depends(require_creator),
) -> APIResponse[ProjectRead]:
    if caller.organization_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Must belong to an organization",
        )

    project = Project(
        organization_id=caller.organization_id,
        name=payload.name,
        description=payload.description,
        client_name=payload.client_name,
        client_contact=payload.client_contact,
        start_date=payload.start_date,
        end_date=payload.end_date,
        budget=payload.budget,
        status=ProjectStatus.active,
        created_by=caller.id,
    )

    db.add(project)
    db.flush()
    db.refresh(project)
    db.commit()

    return success_response(
        status_code=status.HTTP_201_CREATED,
        status_message="Project created successfully",
        response_data=project,
    )


@router.get(
    "",
    response_model=APIResponse[list[ProjectRead]],
)
def list_projects(
    id: uuid.UUID | None = None,
    status: ProjectStatus | None = None,
    organization_id: uuid.UUID | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> APIResponse[list[ProjectRead]]:
    stmt = select(Project).where(Project.deleted_at.is_(None))

    if id is not None:
        stmt = stmt.where(Project.id == id)

    if status is not None:
        stmt = stmt.where(Project.status == status)

    if organization_id is not None:
        stmt = stmt.where(Project.organization_id == organization_id)

    projects = list(db.scalars(stmt))

    return success_response(
        status_code=status.HTTP_200_OK,
        status_message="Projects retrieved successfully",
        response_data=projects,
    )


@router.patch(
    "/{project_id}",
    response_model=APIResponse[ProjectRead],
)
def update_project(
    project_id: uuid.UUID,
    payload: ProjectUpdate,
    db: Session = Depends(get_db),
    caller: User = Depends(get_current_user),
) -> APIResponse[ProjectRead]:
    project = db.get(
        Project,
        project_id,
    )

    if project is None or project.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    _authorize_mutation(
        db,
        caller,
        project,
    )

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(project, field, value)

    project.updated_by = caller.id

    db.flush()
    db.refresh(project)
    db.commit()

    return success_response(
        status_code=status.HTTP_200_OK,
        status_message="Project updated successfully",
        response_data=project,
    )


@router.delete(
    "/{project_id}",
    response_model=APIResponse[None],
    status_code=status.HTTP_200_OK,
)
def delete_project(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    caller: User = Depends(get_current_user),
) -> APIResponse[None]:
    project = db.get(
        Project,
        project_id,
    )

    if project is None or project.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    _authorize_mutation(
        db,
        caller,
        project,
    )

    task_count = db.scalar(
        select(func.count(Task.id))
        .join(
            Feature,
            Task.feature_id == Feature.id,
        )
        .where(
            Feature.project_id == project_id,
            Task.deleted_at.is_(None),
        )
    )

    if task_count and task_count > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project has associated tasks and cannot be deleted.",
        )

    project.deleted_at = datetime.now(timezone.utc)
    project.deleted_by = caller.id

    db.commit()

    return success_response(
        status_code=status.HTTP_200_OK,
        status_message="Project deleted successfully",
        response_data=None,
    )

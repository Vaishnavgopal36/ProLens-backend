import uuid

from sqlalchemy import and_, exists, or_, select

from app.models.enums import EntityStatus, PriorityLevel
from app.models.project import Feature
from app.models.task import Task, TaskAssignee
from app.models.user import User
from app.repositories.base_repository import BaseRepository
from app.repositories.project_repository import ORG_WIDE_ROLES, member_project_ids


class TaskRepository(BaseRepository[Task]):
    model = Task

    def get_active_by_id(self, task_id: uuid.UUID) -> Task | None:
        task = self.get_by_id(task_id)
        if task is None or task.deleted_at is not None:
            return None
        return task

    def list_filtered(
        self,
        *,
        caller: User,
        id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
        feature_id: uuid.UUID | None = None,
        status: EntityStatus | None = None,
        priority: PriorityLevel | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Task]:
        stmt = select(Task).where(Task.deleted_at.is_(None))

        if caller.role not in ORG_WIDE_ROLES:
            in_member_project = Task.feature_id.in_(
                select(Feature.id).where(
                    Feature.project_id.in_(member_project_ids(caller.id))
                )
            )
            assigned_to_caller = exists().where(
                TaskAssignee.task_id == Task.id,
                TaskAssignee.user_id == caller.id,
                TaskAssignee.removed_at.is_(None),
            )
            own_standalone = and_(
                Task.feature_id.is_(None), Task.created_by == caller.id
            )
            stmt = stmt.where(
                or_(in_member_project, assigned_to_caller, own_standalone)
            )

        if id is not None:
            stmt = stmt.where(Task.id == id)
        if project_id is not None:
            in_project_feature = Task.feature_id.in_(
                select(Feature.id).where(Feature.project_id == project_id)
            )
            stmt = stmt.where(or_(Task.project_id == project_id, in_project_feature))
        if feature_id is not None:
            stmt = stmt.where(Task.feature_id == feature_id)
        if status is not None:
            stmt = stmt.where(Task.status == status)
        if priority is not None:
            stmt = stmt.where(Task.priority == priority)

        stmt = stmt.order_by(Task.created_at, Task.id)
        return list(self.db.scalars(stmt.limit(limit).offset(offset)))

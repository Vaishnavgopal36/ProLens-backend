import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from app.core.exception import (
    AppException,
    FeatureMutationForbiddenError,
    FeatureNotFoundError,
    ProjectNotFoundError,
)
from app.models.enums import UserRole
from app.repositories.feature_repository import FeatureRepository
from app.schemas.feature import FeatureCreate, FeatureUpdate
from app.services.feature_member_service import FeatureMemberService
from app.services.feature_service import FeatureService
from tests.conftest import make_user

PROJECT_ID = uuid.uuid4()


def make_service(feature=None, member=True, active_tasks=0, project=True):
    svc = FeatureService(MagicMock())
    svc.features = MagicMock()
    svc.features.get_active_by_id.return_value = feature
    svc.features.count_active_tasks.return_value = active_tasks
    svc.features.add.side_effect = lambda f: f
    svc.projects = MagicMock()
    svc.projects.is_member.return_value = member
    svc.projects.get_active_by_id.return_value = (
        SimpleNamespace(id=PROJECT_ID) if project else None
    )
    return svc


def feature():
    return SimpleNamespace(
        id=uuid.uuid4(), project_id=PROJECT_ID, deleted_at=None, deleted_by=None
    )


def test_manager_needs_project_membership():
    manager = make_user(UserRole.manager)
    f = feature()
    svc = make_service(f, member=False)
    with pytest.raises(FeatureMutationForbiddenError):
        svc.create_feature(manager, FeatureCreate(project_id=PROJECT_ID, name="f"))
    with pytest.raises(FeatureMutationForbiddenError):
        svc.update_feature(f.id, FeatureUpdate(name="x"), manager)
    with pytest.raises(FeatureMutationForbiddenError):
        svc.delete_feature(f.id, manager)
    svc.projects.is_member.return_value = True
    assert svc.create_feature(manager, FeatureCreate(project_id=PROJECT_ID, name="f"))


def test_employee_forbidden_admin_allowed():
    f = feature()
    with pytest.raises(FeatureMutationForbiddenError):
        make_service(f).update_feature(
            f.id, FeatureUpdate(name="x"), make_user(UserRole.employee)
        )
    make_service(f, member=False).update_feature(
        f.id, FeatureUpdate(name="x"), make_user(UserRole.admin)
    )


def test_missing_feature_or_project():
    admin = make_user(UserRole.admin)
    with pytest.raises(FeatureNotFoundError):
        make_service(None).delete_feature(uuid.uuid4(), admin)
    with pytest.raises(ProjectNotFoundError):
        make_service(project=False).create_feature(
            admin, FeatureCreate(project_id=PROJECT_ID, name="f")
        )


def test_delete_rejected_with_active_tasks():
    f = feature()
    with pytest.raises(AppException) as e:
        make_service(f, active_tasks=2).delete_feature(f.id, make_user(UserRole.admin))
    assert e.value.status_code == 409
    assert f.deleted_at is None


def test_delete_ok_without_tasks():
    f = feature()
    admin = make_user(UserRole.admin)
    make_service(f).delete_feature(f.id, admin)
    assert f.deleted_at is not None and f.deleted_by == admin.id


def test_active_task_count_only_counts_live_tasks_and_is_int():
    db = MagicMock()
    db.scalar.return_value = None
    assert FeatureRepository(db).count_active_tasks(uuid.uuid4()) == 0
    assert "tasks.deleted_at IS NULL" in str(db.scalar.call_args[0][0].compile())


def _sql(role):
    db = MagicMock()
    FeatureRepository(db).list_filtered(caller=make_user(role))
    return str(db.scalars.call_args[0][0].compile())


def test_list_visibility_scoping():
    assert "project_members" not in _sql(UserRole.admin)
    assert "project_members" in _sql(UserRole.manager)
    assert "project_members" in _sql(UserRole.employee)
    assert "ORDER BY features.created_at, features.id" in _sql(UserRole.admin)


def test_feature_schema_validation():
    pid = uuid.uuid4()
    with pytest.raises(ValidationError):
        FeatureCreate(project_id=pid, name="")
    with pytest.raises(ValidationError):
        FeatureCreate(project_id=pid, name="x" * 256)
    with pytest.raises(ValidationError):
        FeatureCreate(project_id=pid, name="x", description="d" * 10_001)
    for field in ("name", "status"):
        with pytest.raises(ValidationError):
            FeatureUpdate(**{field: None})
    assert FeatureUpdate(description=None).model_dump(exclude_unset=True) == {
        "description": None
    }


def test_feature_http_validation_and_pagination(make_client):
    client = make_client(UserRole.admin)
    assert (
        client.patch(f"/features/{uuid.uuid4()}", json={"name": None}).status_code
        == 422
    )
    assert client.get("/features?limit=0").status_code == 422
    assert client.get("/features?limit=10").status_code == 200
    assert client.get("/feature-members?offset=-1").status_code == 422
    assert client.get("/feature-members?limit=10").status_code == 200
    assert client.get("/task-assignees?limit=0").status_code == 422
    assert client.get("/task-assignees?limit=10").status_code == 200


def test_feature_member_rejects_inactive_user():
    from app.core.exception import UserNotFoundError
    from app.models.enums import UserStatus
    from app.schemas.feature_member import FeatureMemberCreate

    svc = FeatureMemberService(MagicMock())
    svc.features = MagicMock()
    svc.features.get_active_by_id.return_value = feature()
    svc.projects = MagicMock()
    svc.users = MagicMock()
    svc.users.get_active_by_id.return_value = SimpleNamespace(
        status=UserStatus.suspended, organization_id=None
    )
    admin = make_user(UserRole.admin)
    with pytest.raises(UserNotFoundError):
        svc.create_feature_member(
            admin, FeatureMemberCreate(feature_id=uuid.uuid4(), user_id=uuid.uuid4())
        )

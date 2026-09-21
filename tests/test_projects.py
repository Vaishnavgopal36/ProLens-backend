import datetime as dt
import uuid
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from app.core.exception import (
    AppException,
    ProjectHasTasksError,
    ProjectMutationForbiddenError,
    ProjectNotFoundError,
)
from app.models.enums import ProjectStatus, UserRole
from app.models.project import ProjectMember
from app.repositories.project_repository import ProjectRepository
from app.schemas.project import ProjectCreate, ProjectUpdate
from app.services.project_service import ProjectService
from tests.conftest import make_user


def make_service(project=None, member=True, task_count=0, features=()):
    svc = ProjectService(MagicMock())
    svc.projects = MagicMock()
    svc.projects.get_active_by_id.return_value = project
    svc.projects.is_member.return_value = member
    svc.projects.count_active_tasks.return_value = task_count
    svc.projects.add.side_effect = lambda p: setattr(p, "id", uuid.uuid4()) or p
    svc.project_members = MagicMock()
    svc.features = MagicMock()
    svc.features.list_active_by_project.return_value = list(features)
    return svc


def project():
    return SimpleNamespace(
        id=uuid.uuid4(),
        start_date=None,
        end_date=None,
        deleted_at=None,
        deleted_by=None,
        updated_by=None,
    )


# ---- 2. creator becomes a member ----


@pytest.mark.parametrize("role", [UserRole.manager, UserRole.admin])
def test_create_project_adds_creator_as_member(role):
    caller = make_user(role)
    svc = make_service()
    created = svc.create_project(caller, ProjectCreate(name="P"))
    member = svc.project_members.add.call_args[0][0]
    assert isinstance(member, ProjectMember)
    assert (
        member.organization_id,
        member.project_id,
        member.user_id,
        member.added_by,
    ) == (
        caller.organization_id,
        created.id,
        caller.id,
        caller.id,
    )
    svc.db.commit.assert_not_called()


def test_create_project_requires_organization():
    with pytest.raises(AppException):
        make_service().create_project(
            make_user(UserRole.admin, organization_id=None), ProjectCreate(name="P")
        )


def test_create_project_route_rejects_employee(make_client):
    client = make_client(UserRole.employee)
    assert client.post("/projects", json={"name": "P"}).status_code == 403


# ---- mutation authorization ----


def test_manager_mutation_requires_membership():
    p = project()
    manager = make_user(UserRole.manager)
    svc = make_service(p, member=False)
    with pytest.raises(ProjectMutationForbiddenError):
        svc.update_project(p.id, ProjectUpdate(name="x"), manager)
    with pytest.raises(ProjectMutationForbiddenError):
        svc.delete_project(p.id, manager)
    svc.projects.is_member.return_value = True
    svc.update_project(p.id, ProjectUpdate(name="x"), manager)
    assert p.updated_by == manager.id


def test_employee_cannot_mutate_and_admin_always_can():
    p = project()
    with pytest.raises(ProjectMutationForbiddenError):
        make_service(p).update_project(
            p.id, ProjectUpdate(name="x"), make_user(UserRole.employee)
        )
    make_service(p, member=False).update_project(
        p.id, ProjectUpdate(name="x"), make_user(UserRole.admin)
    )


def test_missing_project_404():
    with pytest.raises(ProjectNotFoundError):
        make_service(None).delete_project(uuid.uuid4(), make_user(UserRole.admin))


def test_update_date_ordering_against_stored_values():
    p = project()
    p.end_date = dt.date(2026, 1, 1)
    with pytest.raises(AppException) as e:
        make_service(p).update_project(
            p.id,
            ProjectUpdate(start_date=dt.date(2026, 2, 1)),
            make_user(UserRole.admin),
        )
    assert e.value.status_code == 422


# ---- 8. deletion ----


def test_delete_blocked_by_tasks():
    p = project()
    with pytest.raises(ProjectHasTasksError):
        make_service(p, task_count=1).delete_project(p.id, make_user(UserRole.admin))
    assert p.deleted_at is None


def test_delete_soft_deletes_empty_features():
    p = project()
    f = SimpleNamespace(deleted_at=None, deleted_by=None)
    admin = make_user(UserRole.admin)
    make_service(p, features=[f]).delete_project(p.id, admin)
    assert (
        p.deleted_at is not None
        and f.deleted_at is not None
        and f.deleted_by == admin.id
    )


def test_count_active_tasks_returns_int_and_ignores_deleted_features():
    db = MagicMock()
    db.scalar.return_value = None
    assert ProjectRepository(db).count_active_tasks(uuid.uuid4()) == 0
    sql = str(db.scalar.call_args[0][0].compile())
    assert "features.deleted_at IS NULL" in sql and "tasks.deleted_at IS NULL" in sql
    assert "coalesce" in sql.lower()


# ---- 9. visibility ----


def _list_sql(role):
    db = MagicMock()
    ProjectRepository(db).list_filtered(caller=make_user(role))
    return str(db.scalars.call_args[0][0].compile())


def test_list_scoping():
    assert "project_members" not in _list_sql(UserRole.admin)
    for role in (UserRole.manager, UserRole.employee):
        sql = _list_sql(role)
        assert "project_members" in sql and "removed_at IS NULL" in sql
    assert "ORDER BY projects.created_at, projects.id" in _list_sql(UserRole.admin)


def test_organization_filter_only_for_super_admin():
    org = uuid.uuid4()
    for role, expected in [
        (UserRole.admin, None),
        (UserRole.manager, None),
        (UserRole.super_admin, org),
    ]:
        svc = make_service()
        svc.list_projects(caller=make_user(role), organization_id=org)
        assert (
            svc.projects.list_filtered.call_args.kwargs["organization_id"] == expected
        )


# ---- 7/10. schema + http ----


def test_project_schema_validation():
    with pytest.raises(ValidationError):
        ProjectCreate(name="")
    with pytest.raises(ValidationError):
        ProjectCreate(name="x" * 256)
    with pytest.raises(ValidationError):
        ProjectCreate(name="x", description="d" * 10_001)
    with pytest.raises(ValidationError):
        ProjectCreate(name="x", client_name="c" * 256)
    with pytest.raises(ValidationError):
        ProjectCreate(name="x", client_contact="c" * 256)
    with pytest.raises(ValidationError):
        ProjectCreate(name="x", budget=Decimal("-1"))
    with pytest.raises(ValidationError):
        ProjectCreate(
            name="x", start_date=dt.date(2026, 2, 1), end_date=dt.date(2026, 1, 1)
        )
    ProjectCreate(
        name="x",
        budget=Decimal("0"),
        start_date=dt.date(2026, 1, 1),
        end_date=dt.date(2026, 1, 1),
    )
    for field in ("name", "status"):
        with pytest.raises(ValidationError):
            ProjectUpdate(**{field: None})
    with pytest.raises(ValidationError):
        ProjectUpdate(budget=Decimal("-0.01"))
    assert ProjectUpdate(budget=None, description=None).model_dump(exclude_unset=True)


def test_project_http_validation_and_pagination(make_client):
    client = make_client(UserRole.admin)
    assert (
        client.patch(f"/projects/{uuid.uuid4()}", json={"status": None}).status_code
        == 422
    )
    assert client.post("/projects", json={"name": ""}).status_code == 422
    assert client.get("/projects?limit=501").status_code == 422
    assert client.get("/projects?limit=10&offset=0").status_code == 200


def test_status_enum_default():
    assert ProjectStatus.active

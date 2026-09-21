import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from app.api.pagination import Pagination
from app.core import storage
from app.core.exception import AppException, InsufficientPermissionError
from app.models.enums import UserRole
from app.repositories import comment_repository
from app.schemas.attachment import AttachmentCreate
from app.schemas.comment import CommentCreate, CommentUpdate
from app.services import attachment_service as att_mod
from app.services.attachment_service import (
    AttachmentNotFoundError,
    AttachmentService,
)
from app.services.comment_service import (
    CommentNotFoundError,
    CommentService,
    CommentTargetNotFoundError,
)
from tests.conftest import ORG_ID, make_user

PAGE = Pagination(limit=20, offset=0)


def target(**kw):
    fields = dict(id=uuid.uuid4(), organization_id=ORG_ID, deleted_at=None)
    fields.update(kw)
    return SimpleNamespace(**fields)


# ---- comments -------------------------------------------------------------


def make_comment(**kw):
    fields = dict(
        id=uuid.uuid4(),
        organization_id=ORG_ID,
        author_id=uuid.uuid4(),
        parent_comment_id=None,
        project_id=None,
        feature_id=None,
        task_id=uuid.uuid4(),
        activity_id=None,
        content="hi",
        deleted_at=None,
        updated_at=None,
    )
    fields.update(kw)
    return SimpleNamespace(**fields)


def make_comment_service(target_row=None, comment=None, monkeypatch=None):
    svc = CommentService(MagicMock())
    svc.comments = MagicMock()
    svc.comments.get_active_by_id.return_value = comment
    svc.comments.add.side_effect = lambda c: c
    return svc


def patch_target(monkeypatch, module, row):
    monkeypatch.setattr(module, "load_target", lambda db, **kw: row)


def test_comment_schema_content_rules():
    task = str(uuid.uuid4())
    with pytest.raises(ValidationError):
        CommentCreate(task_id=task, content="   ")
    with pytest.raises(ValidationError):
        CommentCreate(task_id=task, content="x" * 10_001)
    with pytest.raises(ValidationError):
        CommentUpdate(content="  ")
    assert CommentCreate(task_id=task, content="  hi ").content == "hi"


def test_comment_target_must_exist_in_org(monkeypatch):
    from app.services import comment_service

    payload = CommentCreate(task_id=uuid.uuid4(), content="hi")
    caller = make_user()
    svc = make_comment_service()
    for row in (None, target(organization_id=uuid.uuid4())):
        patch_target(monkeypatch, comment_service, row)
        with pytest.raises(CommentTargetNotFoundError):
            svc.create_comment(payload, caller)
    patch_target(monkeypatch, comment_service, target())
    comment = svc.create_comment(payload, caller)
    assert comment.author_id == caller.id
    svc.db.commit.assert_not_called()


def test_load_target_rejects_soft_deleted_rows():
    db = MagicMock()
    db.get.return_value = target(deleted_at=datetime.now(timezone.utc))
    assert comment_repository.load_target(db, task_id=uuid.uuid4()) is None
    db.get.return_value = target()
    assert comment_repository.load_target(db, task_id=uuid.uuid4()) is not None
    assert comment_repository.load_target(db) is None


def test_parent_comment_validation(monkeypatch):
    from app.services import comment_service

    task_id = uuid.uuid4()
    caller = make_user()
    payload = CommentCreate(
        task_id=task_id, parent_comment_id=uuid.uuid4(), content="reply"
    )
    patch_target(monkeypatch, comment_service, target())

    svc = make_comment_service(comment=None)
    with pytest.raises(CommentNotFoundError):
        svc.create_comment(payload, caller)

    svc = make_comment_service(comment=make_comment(organization_id=uuid.uuid4()))
    with pytest.raises(CommentNotFoundError):
        svc.create_comment(payload, caller)

    svc = make_comment_service(comment=make_comment(task_id=uuid.uuid4()))
    with pytest.raises(AppException) as exc:
        svc.create_comment(payload, caller)
    assert exc.value.status_code == 422

    svc = make_comment_service(comment=make_comment(task_id=task_id))
    assert svc.create_comment(payload, caller).parent_comment_id == (
        payload.parent_comment_id
    )


def test_only_author_can_edit_admin_can_delete():
    author = make_user(UserRole.employee)
    comment = make_comment(author_id=author.id)
    svc = make_comment_service(comment=comment)

    svc.update_comment(comment.id, CommentUpdate(content="edited"), author)
    assert comment.content == "edited"

    admin = make_user(UserRole.admin)
    with pytest.raises(InsufficientPermissionError):
        svc.update_comment(comment.id, CommentUpdate(content="hax"), admin)
    with pytest.raises(InsufficientPermissionError):
        svc.delete_comment(comment.id, make_user(UserRole.manager))
    with pytest.raises(InsufficientPermissionError):
        svc.delete_comment(comment.id, make_user(UserRole.employee))
    svc.delete_comment(comment.id, admin)
    svc.comments.soft_delete.assert_called_once()
    svc.db.commit.assert_not_called()


def test_comment_list_route_and_validation(make_client):
    client = make_client()
    assert client.get("/comments?limit=5&offset=0").status_code == 200
    assert client.get("/comments?limit=0").status_code == 422
    bad = client.post(
        "/comments", json={"task_id": str(uuid.uuid4()), "content": "   "}
    )
    assert bad.status_code == 422


# ---- attachments ----------------------------------------------------------


def make_attachment_service(attachment=None, key_exists=False):
    svc = AttachmentService(MagicMock())
    svc.attachments = MagicMock()
    svc.attachments.get_active_by_id.return_value = attachment
    svc.attachments.s3_key_exists.return_value = key_exists
    svc.attachments.add.side_effect = lambda a: a
    return svc


def attachment_payload(caller, **kw):
    fields = dict(
        task_id=uuid.uuid4(),
        file_name="a.pdf",
        s3_key=f"{caller.organization_id}/{uuid.uuid4()}/a.pdf",
        size_bytes=10,
        mime_type="application/pdf",
    )
    fields.update(kw)
    return AttachmentCreate(**fields)


def test_attachment_register_happy_path(monkeypatch):
    caller = make_user()
    monkeypatch.setattr(att_mod, "load_target", lambda db, **kw: target())
    monkeypatch.setattr(storage, "get_object_size", lambda key: 10)
    svc = make_attachment_service()
    attachment = svc.create_attachment(attachment_payload(caller), caller)
    assert attachment.uploaded_by == caller.id
    svc.db.commit.assert_not_called()


def test_attachment_register_rejections(monkeypatch):
    caller = make_user()
    monkeypatch.setattr(att_mod, "load_target", lambda db, **kw: target())
    monkeypatch.setattr(storage, "get_object_size", lambda key: 10)
    deleted = []
    monkeypatch.setattr(storage, "delete_object", deleted.append)

    with pytest.raises(AppException) as exc:
        make_attachment_service().create_attachment(
            attachment_payload(caller, s3_key=f"{uuid.uuid4()}/x/a.pdf"), caller
        )
    assert exc.value.status_code == 400

    with pytest.raises(AppException) as exc:
        make_attachment_service(key_exists=True).create_attachment(
            attachment_payload(caller), caller
        )
    assert exc.value.status_code == 409

    monkeypatch.setattr(att_mod, "load_target", lambda db, **kw: None)
    with pytest.raises(AppException) as exc:
        make_attachment_service().create_attachment(attachment_payload(caller), caller)
    assert exc.value.status_code == 404

    monkeypatch.setattr(
        att_mod, "load_target", lambda db, **kw: target(organization_id=uuid.uuid4())
    )
    with pytest.raises(AppException) as exc:
        make_attachment_service().create_attachment(attachment_payload(caller), caller)
    assert exc.value.status_code == 404

    monkeypatch.setattr(att_mod, "load_target", lambda db, **kw: target())
    monkeypatch.setattr(storage, "get_object_size", lambda key: 99)
    with pytest.raises(AppException) as exc:
        make_attachment_service().create_attachment(attachment_payload(caller), caller)
    assert exc.value.status_code == 400 and len(deleted) == 1

    monkeypatch.setattr(storage, "get_object_size", lambda key: None)
    with pytest.raises(AppException):
        make_attachment_service().create_attachment(attachment_payload(caller), caller)


def test_storage_error_propagates(monkeypatch):
    caller = make_user()
    monkeypatch.setattr(att_mod, "load_target", lambda db, **kw: target())

    def boom(key):
        raise storage.StorageError("down")

    monkeypatch.setattr(storage, "get_object_size", boom)
    with pytest.raises(storage.StorageError):
        make_attachment_service().create_attachment(attachment_payload(caller), caller)


def test_download_url_404_for_deleted_or_foreign(monkeypatch):
    monkeypatch.setattr(storage, "create_download_url", lambda key, name: "https://u")
    caller = make_user()
    with pytest.raises(AttachmentNotFoundError):
        make_attachment_service(attachment=None).get_download_url(uuid.uuid4(), caller)
    foreign = SimpleNamespace(
        id=uuid.uuid4(), organization_id=uuid.uuid4(), s3_key="k", file_name="f"
    )
    with pytest.raises(AttachmentNotFoundError):
        make_attachment_service(attachment=foreign).get_download_url(foreign.id, caller)
    own = SimpleNamespace(
        id=uuid.uuid4(), organization_id=ORG_ID, s3_key="k", file_name="f"
    )
    result = make_attachment_service(attachment=own).get_download_url(own.id, caller)
    assert result.download_url == "https://u"


def test_attachment_delete_permissions():
    uploader = make_user(UserRole.employee)
    attachment = SimpleNamespace(
        id=uuid.uuid4(), organization_id=ORG_ID, uploaded_by=uploader.id
    )
    svc = make_attachment_service(attachment=attachment)
    svc.delete_attachment(attachment.id, uploader)
    svc.delete_attachment(attachment.id, make_user(UserRole.admin))
    svc.delete_attachment(attachment.id, make_user(UserRole.manager))
    with pytest.raises(InsufficientPermissionError):
        svc.delete_attachment(attachment.id, make_user(UserRole.employee))
    svc.db.commit.assert_not_called()


def test_attachment_upload_url_size_limit(monkeypatch):
    from app.core.config import settings
    from app.schemas.attachment import AttachmentUploadRequest

    caller = make_user()
    monkeypatch.setattr(storage, "create_upload_url", lambda key, mime: "https://put")
    svc = make_attachment_service()
    with pytest.raises(AppException) as exc:
        svc.create_upload_url(
            AttachmentUploadRequest(
                file_name="a",
                mime_type="text/plain",
                size_bytes=settings.ATTACHMENT_MAX_SIZE_BYTES + 1,
            ),
            caller,
        )
    assert exc.value.status_code == 413
    result = svc.create_upload_url(
        AttachmentUploadRequest(file_name="a", mime_type="text/plain", size_bytes=1),
        caller,
    )
    assert result.s3_key.startswith(f"{caller.organization_id}/")


def test_storage_wraps_botocore_errors(monkeypatch):
    from botocore.exceptions import EndpointConnectionError

    client = MagicMock()
    client.head_object.side_effect = EndpointConnectionError(endpoint_url="x")
    client.generate_presigned_url.side_effect = EndpointConnectionError(
        endpoint_url="x"
    )
    monkeypatch.setattr(storage, "_client", lambda: client)
    with pytest.raises(storage.StorageError):
        storage.get_object_size("k")
    with pytest.raises(storage.StorageError):
        storage.create_download_url("k", "f")
    with pytest.raises(storage.StorageError):
        storage.create_upload_url("k", "text/plain")


def test_attachment_routes_pagination(make_client):
    client = make_client()
    assert client.get("/attachments").status_code == 200
    assert client.get(f"/attachments/{uuid.uuid4()}/download-url").status_code == 404

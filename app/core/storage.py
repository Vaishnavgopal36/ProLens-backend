import re
import uuid
from urllib.parse import quote
from functools import lru_cache

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from app.core.config import settings


class StorageError(Exception):
    """The storage backend rejected or failed a request."""


@lru_cache
def _client():
    # Supabase's S3 endpoint requires SigV4 and path-style addressing.
    return boto3.client(
        "s3",
        endpoint_url=settings.SUPABASE_S3_ENDPOINT,
        region_name=settings.SUPABASE_S3_REGION,
        aws_access_key_id=settings.SUPABASE_S3_ACCESS_KEY_ID,
        aws_secret_access_key=settings.SUPABASE_S3_SECRET_ACCESS_KEY,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def build_object_key(organization_id: uuid.UUID, file_name: str) -> str:
    """Server-generated key, namespaced by organization."""
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", file_name)[-120:] or "file"
    return f"{organization_id}/{uuid.uuid4()}/{safe_name}"


def key_belongs_to_org(key: str, organization_id: uuid.UUID) -> bool:
    return key.startswith(f"{organization_id}/")


def create_upload_url(key: str, mime_type: str) -> str:
    return _client().generate_presigned_url(
        "put_object",
        Params={
            "Bucket": settings.SUPABASE_S3_BUCKET,
            "Key": key,
            "ContentType": mime_type,
        },
        ExpiresIn=settings.ATTACHMENT_URL_EXPIRE_SECONDS,
    )


def create_download_url(key: str, file_name: str) -> str:
    # RFC 5987 encoding keeps CR/LF, quotes and non-ASCII out of the header.
    encoded = quote(file_name, safe="")
    return _client().generate_presigned_url(
        "get_object",
        Params={
            "Bucket": settings.SUPABASE_S3_BUCKET,
            "Key": key,
            "ResponseContentDisposition": f"attachment; filename*=UTF-8''{encoded}",
        },
        ExpiresIn=settings.ATTACHMENT_URL_EXPIRE_SECONDS,
    )


def get_object_size(key: str) -> int | None:
    """Size of the stored object, or None if it does not exist."""
    try:
        head = _client().head_object(Bucket=settings.SUPABASE_S3_BUCKET, Key=key)
    except ClientError as exc:
        if exc.response["Error"]["Code"] in ("404", "NoSuchKey", "NotFound"):
            return None
        raise StorageError(str(exc)) from exc
    return head["ContentLength"]


def delete_object(key: str) -> None:
    try:
        _client().delete_object(Bucket=settings.SUPABASE_S3_BUCKET, Key=key)
    except ClientError as exc:
        raise StorageError(str(exc)) from exc

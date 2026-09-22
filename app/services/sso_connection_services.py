import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.sso_clients import get_sso_client

from app.api.deps import assert_same_organization
from app.core.exception import (
    OrganizationIdRequiredError,
    CrossOrganizationForbiddenError,
    SSOConnectionAlreadyExistsError,
    SSOConnectionNotFoundError,
    UnsupportedSSOProviderError,
)
from app.models.enums import SSOProvider, UserRole, UserStatus
from app.models.sso import SSOConnection
from app.models.user import User
from app.repositories.sso_repository import SSORepository
from app.schemas.sso import SSOConnectionCreate, SSOSyncResult


class SSOConnectionService:
    def __init__(self, db: Session):
        self.db = db
        self.connections = SSORepository(db)

    def _resolve_organization_id(
        self, caller: User, organization_id: uuid.UUID | None
    ) -> uuid.UUID:
        if caller.role == UserRole.super_admin:
            if organization_id is None:
                raise OrganizationIdRequiredError()
            return organization_id

        if organization_id not in (None, caller.organization_id):
            raise CrossOrganizationForbiddenError()

        if caller.organization_id is None:
            raise OrganizationIdRequiredError()

        return caller.organization_id

    @staticmethod
    def _vendor_credentials(provider: SSOProvider) -> tuple[str, str]:
        if provider == SSOProvider.azure_ad:
            return settings.AZURE_CLIENT_ID, settings.AZURE_CLIENT_SECRET
        return settings.GOOGLE_CLIENT_ID, settings.GOOGLE_CLIENT_SECRET

    def create_connection(self, caller: User, payload: SSOConnectionCreate) -> SSOConnection:
        organization_id = self._resolve_organization_id(caller, payload.organization_id)

        if self.connections.get_connection_by_org_id(organization_id):
            raise SSOConnectionAlreadyExistsError()

        client_id, client_secret = self._vendor_credentials(payload.provider)

        connection = SSOConnection(
            organization_id=organization_id,
            provider=payload.provider,
            tenant_id=None,
            client_id=client_id,
            client_secret=client_secret,
        )

        return self.connections.add(connection)

    def list_connections(
        self,
        caller: User,
        *,
        id: uuid.UUID | None = None,
        organization_id: uuid.UUID | None = None,
        provider: SSOProvider | None = None,
    ) -> list[SSOConnection]:
        if caller.role != UserRole.super_admin:
            organization_id = caller.organization_id

        return self.connections.list_filtered(
            id=id, organization_id=organization_id, provider=provider
        )

    def delete_connection(self, caller: User, connection_id: uuid.UUID) -> None:
        connection = self.connections.get_by_id(connection_id)
        if connection is None:
            raise SSOConnectionNotFoundError()

        assert_same_organization(caller, connection.organization_id)

        self.connections.delete(connection)

    def _upsert_users_from_directory(
        self, organization_id: uuid.UUID, directory_users: list[dict]
    ) -> SSOSyncResult:
        created = 0
        updated = 0

        for entry in directory_users:
            subject_id = entry.get("id")
            email = entry.get("mail") or entry.get("userPrincipalName")

            if not subject_id or not email:
                continue

            user = self.db.scalar(select(User).where(User.sso_subject_id == subject_id))

            if user is None:
                email_match = self.db.scalar(select(User).where(User.email == email))
                if email_match is not None and email_match.organization_id not in (
                    None,
                    organization_id,
                ):
                    continue
                user = email_match

            if user is None:
                self.db.add(
                    User(
                        organization_id=organization_id,
                        email=email,
                        sso_subject_id=subject_id,
                        first_name=entry.get("givenName"),
                        last_name=entry.get("surname"),
                        role=UserRole.employee,
                        status=UserStatus.active,
                    )
                )
                created += 1
            else:
                user.sso_subject_id = subject_id
                user.first_name = entry.get("givenName") or user.first_name
                user.last_name = entry.get("surname") or user.last_name
                updated += 1

        return SSOSyncResult(
            total_fetched=len(directory_users),
            created=created,
            updated=updated,
        )

    def sync_users(self, caller: User, connection_id: uuid.UUID) -> SSOSyncResult:
        connection = self.connections.get_by_id(connection_id)
        if connection is None:
            raise SSOConnectionNotFoundError()

        assert_same_organization(caller, connection.organization_id)

        client = get_sso_client(connection)
        try:
            directory_users = client.list_users()
        except NotImplementedError:
            raise UnsupportedSSOProviderError()

        return self._upsert_users_from_directory(connection.organization_id, directory_users)
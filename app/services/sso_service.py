from typing import Any
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from sqlalchemy.orm import Session

from app.core.azure_ad import AzureADClient, generate_pkce_pair
from app.core.config import settings
from app.core.exception import (
    InvalidSSOStateError,
    NoSSOConnectionError,
    MissingEmailClaimError,
    InactiveAccountError,
    SSOConnectionNotFoundError,
    SSOConnectionNotConfiguredError,
)
from app.core.sso_clients import get_sso_client
from app.models.enums import SSOProvider, UserRole, UserStatus
from app.models.user import User
from app.repositories.sso_repository import SSORepository
from app.repositories.user_repository import UserRepository
from app.schemas.auth import TokenResponse
from app.schemas.sso import SSOAuthorizeResponse
from app.services.auth_service import AuthService

DISCOVERY_STATE_EXPIRE_MINUTES = 10
LOGIN_STATE_EXPIRE_MINUTES = 10


class SSOService:
    def __init__(self, db: Session):
        self.db = db
        self.sso = SSORepository(db)
        self.users = UserRepository(db)
        self.auth = AuthService(db)

    def _redirect_uri(self) -> str:
        return f"{settings.PUBLIC_BASE_URL}/auth/sso/callback"

    def authorize(self, host: str | None = None) -> SSOAuthorizeResponse:
        code_verifier, code_challenge = generate_pkce_pair()
        nonce = secrets.token_urlsafe(16)
        state_data: dict[str, Any] = {
            "purpose": "login",
            "provider": SSOProvider.azure_ad.value,
            "nonce": nonce,
            "code_verifier": code_verifier,
            "exp": datetime.now(timezone.utc) + timedelta(minutes=LOGIN_STATE_EXPIRE_MINUTES),
        }

        if host:
            clean_host = host.split("@")[-1].split(":")[0].strip().lower()
            connection = self.sso.get_connection_by_domain(clean_host)
            if connection:
                state_data["org_id"] = str(connection.organization_id)

        state = jwt.encode(
            state_data,
            settings.JWT_SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM,
        )

        client = AzureADClient(
            client_id=settings.AZURE_CLIENT_ID,
            client_secret=settings.AZURE_CLIENT_SECRET,
            tenant_id="organizations",
        )
        url = client.build_authorize_url(self._redirect_uri(), state, nonce, code_challenge)
        return SSOAuthorizeResponse(authorize_url=url)

    def authorize_discovery(self, connection_id: uuid.UUID, caller: User) -> SSOAuthorizeResponse:
        connection = self.sso.get_by_id(connection_id)
        if connection is None:
            raise SSOConnectionNotFoundError()

        from app.api.deps import assert_same_organization
        assert_same_organization(caller, connection.organization_id)

        if connection.provider != SSOProvider.azure_ad:
            raise ValueError("Tenant discovery only applies to Azure AD connections.")

        code_verifier, code_challenge = generate_pkce_pair()
        nonce = secrets.token_urlsafe(16)
        state = jwt.encode(
            {
                "purpose": "discover",
                "connection_id": str(connection.id),
                "nonce": nonce,
                "code_verifier": code_verifier,
                "exp": datetime.now(timezone.utc) + timedelta(minutes=DISCOVERY_STATE_EXPIRE_MINUTES),
            },
            settings.JWT_SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM,
        )

        client = get_sso_client(connection)  # tenant_id is None -> falls back to "organizations"
        url = client.build_authorize_url(self._redirect_uri(), state, nonce, code_challenge)
        return SSOAuthorizeResponse(authorize_url=url)

    def callback(self, code: str, state: str) -> TokenResponse | None:
        try:
            state_payload = jwt.decode(
                state, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
            )
        except jwt.PyJWTError:
            raise InvalidSSOStateError()

        if state_payload.get("purpose") == "discover":
            self._complete_discovery(code, state_payload)
            return None

        return self._complete_login(code, state_payload)

    def _complete_login(self, code: str, state_payload: dict) -> TokenResponse:
        client = AzureADClient(
            client_id=settings.AZURE_CLIENT_ID,
            client_secret=settings.AZURE_CLIENT_SECRET,
            tenant_id="organizations",
        )
        tokens = client.exchange_code(
            code, self._redirect_uri(), state_payload["code_verifier"]
        )
        claims = client.decode_id_token(
            tokens["id_token"], expected_nonce=state_payload["nonce"]
        )

        subject_id = claims.get("oid") or claims.get("sub")
        email = (claims.get("email") or claims.get("preferred_username") or "").strip().lower()
        if not email:
            raise MissingEmailClaimError()

        tenant_id = claims.get("tid")

        # 1. Resolve organization by tenant_id
        connection = None
        if tenant_id:
            connection = self.sso.get_connection_by_tenant_id(tenant_id)

        # 2. If not found by tenant_id, resolve by email domain
        if connection is None and "@" in email:
            domain = email.split("@")[-1].lower()
            connection = self.sso.get_connection_by_domain(domain)
            # Auto-pin tenant_id if connection exists without tenant_id
            if connection and connection.tenant_id is None and tenant_id:
                connection.tenant_id = tenant_id
                self.db.flush()

        # 3. Fallback to org_id from state if present
        if connection is None and state_payload.get("org_id"):
            connection = self.sso.get_connection_by_org_id(uuid.UUID(state_payload["org_id"]))

        if connection is None:
            raise NoSSOConnectionError()

        org_id = connection.organization_id

        user = self.users.get_by_sso_subject_id(subject_id)

        if user is None:
            email_match = self.users.get_by_email(email)
            if email_match is not None and email_match.organization_id not in (
                None,
                org_id,
            ):
                email_match = None
            user = email_match

        if user is None:
            user = self.users.add(
                User(
                    organization_id=org_id,
                    email=email,
                    sso_subject_id=subject_id,
                    first_name=claims.get("given_name"),
                    last_name=claims.get("family_name"),
                    role=UserRole.employee,
                    status=UserStatus.active,
                )
            )
        else:
            user.sso_subject_id = subject_id
            if user.organization_id is None:
                user.organization_id = org_id
            if user.status == UserStatus.invited:
                user.status = UserStatus.active
            self.db.flush()
            self.db.refresh(user)

        if user.status != UserStatus.active:
            raise InactiveAccountError()

        return self.auth.issue_tokens(user)

    def _complete_discovery(self, code: str, state_payload: dict) -> None:
        connection = self.sso.get_by_id(uuid.UUID(state_payload["connection_id"]))
        if connection is None:
            raise SSOConnectionNotFoundError()

        client = get_sso_client(connection)  # still tenant_id=None -> "organizations"
        tokens = client.exchange_code(
            code, self._redirect_uri(), state_payload["code_verifier"]
        )
        claims = client.decode_id_token(
            tokens["id_token"], expected_nonce=state_payload["nonce"]
        )

        connection.tenant_id = claims["tid"]
        self.db.flush()

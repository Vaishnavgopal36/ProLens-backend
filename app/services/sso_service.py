# app/services/sso_service.py

import secrets
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from sqlalchemy.orm import Session

from app.core.azure_ad import generate_pkce_pair
from app.core.config import settings
from app.core.exception import (
    InactiveAccountError,
    InvalidSSOStateError,
    MissingEmailClaimError,
    NoSSOConnectionError,
)
from app.core.sso_clients import get_sso_client
from app.models.enums import SSOProvider, UserRole, UserStatus
from app.models.user import User
from app.repositories.sso_repository import SSORepository
from app.repositories.user_repository import UserRepository
from app.schemas.auth import SSOAuthorizeResponse, TokenResponse
from app.services.auth_service import AuthService

SSO_STATE_EXPIRE_MINUTES = 10


class SSOService:
    def __init__(self, db: Session):
        self.db = db
        self.sso = SSORepository(db)
        self.users = UserRepository(db)
        self.auth = AuthService(db)

    @staticmethod
    def _redirect_uri() -> str:
        return f"{settings.PUBLIC_BASE_URL}/auth/sso/callback"

    def authorize(self, host: str) -> SSOAuthorizeResponse:
        connection = self.sso.get_connection_by_domain(host)
        if connection is None:
            raise NoSSOConnectionError()

        code_verifier, code_challenge = generate_pkce_pair()
        nonce = secrets.token_urlsafe(16)
        state = jwt.encode(
            {
                "org_id": str(connection.organization_id),
                "nonce": nonce,
                "code_verifier": code_verifier,
                "exp": datetime.now(timezone.utc)
                + timedelta(minutes=SSO_STATE_EXPIRE_MINUTES),
            },
            settings.JWT_SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM,
        )

        client = get_sso_client(connection)
        url = client.build_authorize_url(
            self._redirect_uri(), state, nonce, code_challenge
        )
        return SSOAuthorizeResponse(authorize_url=url)

    def callback(self, code: str, state: str) -> TokenResponse:
        try:
            state_payload = jwt.decode(
                state, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
            )
        except jwt.PyJWTError:
            raise InvalidSSOStateError()

        org_id = uuid.UUID(state_payload["org_id"])
        connection = self.sso.get_connection_by_org_id(org_id)
        if connection is None:
            raise NoSSOConnectionError()

        client = get_sso_client(connection)
        tokens = client.exchange_code(
            code, self._redirect_uri(), state_payload["code_verifier"]
        )
        claims = client.decode_id_token(tokens["id_token"])

        if claims.get("nonce") != state_payload["nonce"]:
            raise InvalidSSOStateError()

        subject_id = claims["oid"] if connection.provider == SSOProvider.azure_ad else claims["sub"]
        email = claims.get("email") or claims.get("preferred_username")
        if not email:
            raise MissingEmailClaimError()

        user = self.users.get_by_sso_subject_id(subject_id)

        if user is None:
            email_match = self.users.get_by_email(email)
            if email_match is not None and email_match.organization_id not in (None, org_id):
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
            if user.status == UserStatus.invited:
                user.status = UserStatus.active
            self.db.flush()
            self.db.refresh(user)

        if user.status != UserStatus.active:
            raise InactiveAccountError()

        return self.auth.issue_tokens(user)
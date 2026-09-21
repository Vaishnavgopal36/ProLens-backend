import base64
import hashlib
import secrets
from typing import Any, Optional
from urllib.parse import urlencode

import httpx
import jwt

GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"


def generate_pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return verifier, challenge


class AzureADClient:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        tenant_id: str = "organizations",
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.tenant_id = tenant_id if tenant_id else "organizations"

    def _get_token(self, target_tenant_id: Optional[str] = None) -> str:
        """Acquires an app-only access token via client credentials grant.

        Note: Client credentials flow requires a specific tenant ID or domain
        and cannot run against the generic 'organizations' endpoint.
        """
        tenant = target_tenant_id or self.tenant_id
        if tenant == "organizations":
            raise ValueError(
                "Client credentials grant requires a specific tenant ID or domain, "
                "not the 'organizations' wildcard."
            )

        resp = httpx.post(
            f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "scope": "https://graph.microsoft.com/.default",
                "grant_type": "client_credentials",
            },
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()["access_token"]

    def list_users(
        self, target_tenant_id: Optional[str] = None
    ) -> list[dict[str, Any]]:
        """Lists users in a specific tenant directory using app-only permissions."""
        token = self._get_token(target_tenant_id=target_tenant_id)
        headers = {"Authorization": f"Bearer {token}"}
        url = f"{GRAPH_BASE_URL}/users?$select=id,mail,userPrincipalName,givenName,surname"
        users: list[dict[str, Any]] = []
        while url:
            resp = httpx.get(url, headers=headers, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            users.extend(data.get("value", []))
            url = data.get("@odata.nextLink")
        return users

    def build_authorize_url(
        self, redirect_uri: str, state: str, nonce: str, code_challenge: str
    ) -> str:
        """Generates authorization URL directing users to the organizations endpoint."""
        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "response_mode": "query",
            "scope": "openid profile email",
            "state": state,
            "nonce": nonce,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        return (
            f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/authorize"
            f"?{urlencode(params)}"
        )

    def exchange_code(
        self, code: str, redirect_uri: str, code_verifier: str
    ) -> dict[str, Any]:
        """Exchanges authorization code for tokens."""
        resp = httpx.post(
            f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token",
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "code_verifier": code_verifier,
            },
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

    def decode_id_token(
        self, id_token: str, expected_nonce: Optional[str] = None
    ) -> dict[str, Any]:
        """Decodes, verifies keys via JWKS, dynamically matches issuer, and checks nonce."""
        # 1. Fetch public keys from Microsoft's JWKS endpoint
        jwks_client = jwt.PyJWKClient(
            f"https://login.microsoftonline.com/{self.tenant_id}/discovery/v2.0/keys"
        )
        signing_key = jwks_client.get_signing_key_from_jwt(id_token)

        # 2. Extract tenant ID ('tid') from unverified token to validate dynamic issuer
        unverified_claims = jwt.decode(id_token, options={"verify_signature": False})
        token_tenant_id = unverified_claims.get("tid")
        if not token_tenant_id:
            raise ValueError("ID token missing 'tid' (tenant ID) claim.")

        # 3. Accept both v2.0 and v1.0 issuer formats for the authenticated tenant
        valid_issuers = [
            f"https://login.microsoftonline.com/{token_tenant_id}/v2.0",
            f"https://sts.windows.net/{token_tenant_id}/",
        ]

        # 4. Decode and verify signature, audience, and issuer
        claims = jwt.decode(
            id_token,
            signing_key.key,
            algorithms=["RS256"],
            audience=self.client_id,
            issuer=valid_issuers,
        )

        # 5. Prevent replay attacks by checking nonce
        if expected_nonce and claims.get("nonce") != expected_nonce:
            raise ValueError("ID token nonce does not match expected session nonce.")

        return claims

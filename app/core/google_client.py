from urllib.parse import urlencode

import httpx
import jwt

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
GOOGLE_ISSUER = "https://accounts.google.com"


ADMIN_DIRECTORY_URL = "https://admin.googleapis.com/admin/directory/v1/users"


class GoogleClient:
    def __init__(self, client_id: str, client_secret: str) -> None:
        self.client_id = client_id
        self.client_secret = client_secret

    def build_authorize_url(
        self, redirect_uri: str, state: str, nonce: str, code_challenge: str
    ) -> str:
        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "scope": "openid profile email",
            "state": state,
            "nonce": nonce,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "access_type": "offline",
        }
        return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"

    def exchange_code(self, code: str, redirect_uri: str, code_verifier: str) -> dict:
        resp = httpx.post(
            GOOGLE_TOKEN_URL,
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

    def decode_id_token(self, id_token: str) -> dict:
        jwks_client = jwt.PyJWKClient(GOOGLE_JWKS_URL)
        signing_key = jwks_client.get_signing_key_from_jwt(id_token)
        return jwt.decode(
            id_token,
            signing_key.key,
            algorithms=["RS256"],
            audience=self.client_id,
            issuer=GOOGLE_ISSUER,
        )

    def list_users(self) -> list[dict]:
        raise NotImplementedError(
            "Directory sync is not supported for Google SSO connections"
        )

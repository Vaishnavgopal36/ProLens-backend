from sqlalchemy.exc import DataError, IntegrityError

from app.core.config import settings
from app.main import app


class _PgError(Exception):
    def __init__(self, pgcode: str) -> None:
        super().__init__("db detail that must not leak")
        self.pgcode = pgcode


@app.get("/__test/integrity/{code}")
def _raise_integrity(code: str) -> None:
    raise IntegrityError("INSERT ...", {}, _PgError(code))


@app.get("/__test/data")
def _raise_data() -> None:
    raise DataError("INSERT ...", {}, _PgError("22001"))


def test_unknown_route_and_wrong_method_use_envelope(make_client):
    client = make_client()
    body = client.get("/definitely-not-a-route").json()
    assert body["status_code"] == 404 and body["response_data"] is None
    assert client.delete("/health").json()["status_code"] == 405


def test_integrity_error_unique_is_409_without_leaking(make_client):
    response = make_client().get("/__test/integrity/23505")
    body = response.json()
    assert response.status_code == 409
    assert "already exists" in body["error_message"]
    assert "leak" not in response.text


def test_integrity_error_check_violation_is_422_and_fk_is_409(make_client):
    client = make_client()
    assert client.get("/__test/integrity/23514").status_code == 422
    assert client.get("/__test/integrity/23503").status_code == 409


def test_data_error_is_422(make_client):
    assert make_client().get("/__test/data").status_code == 422


def test_cors_preflight_allows_configured_origin_with_credentials(make_client):
    origin = settings.CORS_ALLOWED_ORIGINS[0]
    response = make_client().options(
        "/users",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    assert response.headers["access-control-allow-credentials"] == "true"


def test_cors_preflight_rejects_unknown_origin(make_client):
    response = make_client().options(
        "/users",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert "access-control-allow-origin" not in response.headers

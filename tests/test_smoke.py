from app.models.enums import UserRole


def test_health(make_client):
    assert make_client(UserRole.admin).get("/health").status_code == 200


def test_unknown_route_uses_app_error_envelope(make_client):
    body = make_client().get("/definitely-not-a-route").json()
    assert body["status_code"] == 404 and "response_data" in body

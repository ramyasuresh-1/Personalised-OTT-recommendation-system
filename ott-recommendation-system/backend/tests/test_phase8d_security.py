import uuid

from fastapi.testclient import TestClient

from app import main


def test_admin_mutations_require_token(monkeypatch):
    monkeypatch.setattr(main, "ADMIN_API_TOKEN", "test-admin-token")
    client = TestClient(main.app)

    assert client.post("/api/retrain").status_code == 403
    assert client.post("/api/simulate-drift", json={"skew_type": "negative"}).status_code == 403
    assert client.post(
        "/api/simulate-drift",
        json={"skew_type": "invalid"},
        headers={"X-Admin-Token": "test-admin-token"},
    ).status_code == 422


def test_logout_invalidates_session_and_headers_are_present():
    client = TestClient(main.app)
    suffix = uuid.uuid4().hex[:10]
    payload = {
        "username": f"security_{suffix}",
        "email": f"security_{suffix}@example.test",
        "password": "correct horse battery staple",
    }
    response = client.post("/api/auth/register", json=payload)
    assert response.status_code == 201
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"

    assert client.post("/api/auth/logout").status_code == 200
    assert client.get("/api/auth/me").status_code == 401


def test_invalid_rating_and_origin_are_rejected():
    client = TestClient(main.app)
    invalid_rating = client.post(
        "/api/rate",
        json={"user_id": 999, "movie_id": 1, "rating": 9},
    )
    assert invalid_rating.status_code == 400

    blocked = client.get("/api/health", headers={"Origin": "https://evil.example"})
    assert blocked.status_code == 403

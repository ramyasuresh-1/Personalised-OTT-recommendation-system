import uuid

from fastapi.testclient import TestClient

from app.main import app


def make_user(prefix: str):
    suffix = uuid.uuid4().hex[:10]
    return {
        "username": f"{prefix}_{suffix}",
        "email": f"{prefix}_{suffix}@example.test",
        "password": "correct horse battery staple",
    }


def register(client: TestClient, prefix: str):
    payload = make_user(prefix)
    response = client.post("/api/auth/register", json=payload)
    assert response.status_code == 201
    return payload, response.json()["user"]


def test_auth_registration_duplicate_login_and_logout():
    client = TestClient(app)
    payload, user = register(client, "auth")

    duplicate = client.post("/api/auth/register", json=payload)
    assert duplicate.status_code == 409
    assert client.get("/api/auth/me").json()["user"]["id"] == user["id"]

    invalid = TestClient(app).post(
        "/api/auth/login",
        json={"identifier": payload["email"], "password": "wrong password"},
    )
    assert invalid.status_code == 401

    logged_out = client.post("/api/auth/logout")
    assert logged_out.status_code == 200
    assert client.get("/api/auth/me").status_code == 401


def test_protected_routes_require_authentication():
    client = TestClient(app)
    for path in ("/api/watchlist", "/api/history/ratings", "/api/analytics/me"):
        assert client.get(path).status_code == 401


def test_watchlist_is_persistent_and_isolated_between_users():
    client_a = TestClient(app)
    client_b = TestClient(app)
    _, user_a = register(client_a, "watch_a")
    register(client_b, "watch_b")

    assert client_a.post("/api/watchlist/1").status_code == 201
    assert client_a.post("/api/watchlist/1").status_code == 409
    assert client_b.get("/api/watchlist").json()["items"] == []
    assert client_a.get("/api/watchlist").json()["items"][0]["id"] == 1

    assert client_a.delete("/api/watchlist/1").status_code == 204
    assert client_a.get("/api/watchlist").json()["items"] == []
    assert user_a["id"] != 1


def test_ratings_history_and_analytics_are_user_scoped():
    client_a = TestClient(app)
    client_b = TestClient(app)
    _, user_a = register(client_a, "data_a")
    register(client_b, "data_b")

    first = client_a.post(
        "/api/rate", json={"user_id": user_a["id"], "movie_id": 1, "rating": 4.0}
    )
    assert first.status_code == 200
    updated = client_a.post(
        "/api/rate", json={"user_id": user_a["id"], "movie_id": 1, "rating": 5.0}
    )
    assert updated.status_code == 200

    history_a = client_a.get("/api/history/ratings").json()["items"]
    assert len(history_a) == 1
    assert history_a[0]["rating"] == 5.0
    assert client_b.get("/api/history/ratings").json()["items"] == []

    analytics_a = client_a.get("/api/analytics/me").json()
    analytics_b = client_b.get("/api/analytics/me").json()
    assert analytics_a["total_ratings"] == 1
    assert analytics_a["average_rating"] == 5.0
    assert analytics_b["total_ratings"] == 0
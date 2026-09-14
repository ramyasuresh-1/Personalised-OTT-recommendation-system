import os
import sys
import uuid
import pytest
from fastapi.testclient import TestClient

# Add parent directory to sys.path so app can be imported
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import app

client = TestClient(app)

def test_read_root():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["status"] == "online"
    assert "model_version" in response.json()

def test_get_movies():
    response = client.get("/api/movies")
    assert response.status_code == 200
    movies = response.json()
    assert len(movies) > 0
    assert "title" in movies[0]
    assert "genre" in movies[0]

def test_get_recommendations():
    suffix = uuid.uuid4().hex[:10]
    registered = client.post("/api/auth/register", json={
        "username": f"recommend_{suffix}",
        "email": f"recommend_{suffix}@example.test",
        "password": "correct horse battery staple",
    })
    assert registered.status_code == 201
    response = client.get("/api/recommend")
    assert response.status_code == 200
    data = response.json()
    assert "user_id" in data
    assert "recommendations" in data
    assert len(data["recommendations"]) > 0

def test_rate_movie():
    suffix = uuid.uuid4().hex[:10]
    registered = client.post("/api/auth/register", json={
        "username": f"rate_{suffix}",
        "email": f"rate_{suffix}@example.test",
        "password": "correct horse battery staple",
    })
    assert registered.status_code == 201
    user_id = registered.json()["user"]["id"]
    rate_payload = {"user_id": user_id, "movie_id": 1, "rating": 5.0}
    response = client.post("/api/rate", json=rate_payload)
    assert response.status_code == 200
    assert response.json()["status"] == "success"

def test_get_metrics():
    response = client.get("/api/monitoring/metrics")
    assert response.status_code == 200
    data = response.json()
    assert "drift_score" in data
    assert "drift_status" in data
    assert "telemetry" in data


def test_health_check():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "online"
    assert "model_version" in data


def test_prometheus_metrics():
    response = client.get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "# HELP" in response.text

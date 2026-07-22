import os
import sys
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
    # User 1 is seeded in initial DB seed
    response = client.get("/api/recommend?user_id=1")
    assert response.status_code == 200
    data = response.json()
    assert "user_id" in data
    assert "recommendations" in data
    assert len(data["recommendations"]) > 0

def test_rate_movie():
    rate_payload = {"user_id": 999, "movie_id": 1, "rating": 5.0}
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

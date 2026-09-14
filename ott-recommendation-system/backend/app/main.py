import os
import time
import random
import re
import secrets
import sqlite3
import logging
from fastapi import FastAPI, HTTPException, BackgroundTasks, Request, Depends, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

from .database import (
    init_db,
    get_all_movies,
    insert_rating,
    log_inference,
    get_metrics_telemetry,
    get_ratings_data,
    create_user,
    get_user_for_login,
    get_user_by_session,
    create_session,
    delete_session,
    get_watchlist,
    add_to_watchlist,
    remove_from_watchlist,
    get_user_ratings,
    get_user_analytics,
    verify_password,
)
from .recommender import OTTRecommender
from .monitoring import (
    detect_drift,
    evaluate_data_drift,
    evaluate_data_quality,
    generate_latest_metrics,
    get_metrics_content_type,
    refresh_dataset_metrics,
    record_recommendation_success,
    record_recommendation_error,
    record_retraining_start,
    record_retraining_end,
    record_model_promotion,
    record_model_rejection,
    update_candidate_champion_metrics,
    update_drift_metric,
)
from .retraining import trigger_retraining, RetrainingConfig

# Initialize FastAPI
app = FastAPI(
    title="Personalized OTT Recommendation & Monitoring API",
    description="Backend service supplying recommendation inference, feedback gathering, drift monitoring and automated retraining.",
    version="1.0.0"
)

def get_cors_origins() -> List[str]:
    raw_value = os.getenv(
        "CORS_ORIGINS",
        os.getenv("FRONTEND_URL", "http://localhost"),
    )
    if not raw_value:
        return ["http://localhost", "http://localhost:80", "http://localhost:3000", "http://127.0.0.1", "http://127.0.0.1:80", "http://127.0.0.1:3000"]
    origins = [origin.strip() for origin in raw_value.split(",") if origin.strip()]
    if "*" in origins:
        raise RuntimeError("CORS_ORIGINS cannot contain '*' when credentials are enabled")
    return origins or ["http://localhost"]

# CORS configurations
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    origin = request.headers.get("origin")
    if origin and origin not in get_cors_origins():
        return Response(status_code=status.HTTP_403_FORBIDDEN, content="Origin not allowed")
    if origin and request.method in {"POST", "PUT", "PATCH", "DELETE"} and request.cookies.get(SESSION_COOKIE_NAME):
        if request.url.path.startswith("/api/") and request.url.path not in {"/api/auth/login", "/api/auth/register"}:
            if request.headers.get("sec-fetch-site") == "cross-site":
                return Response(status_code=status.HTTP_403_FORBIDDEN, content="Cross-site request blocked")
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if request.url.scheme == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response

# Global model state
recommender = OTTRecommender()
is_currently_retraining = False

# Seed/Init DB on startup
@app.on_event("startup")
def startup_event():
    init_db()
    recommender.load_model()
    refresh_dataset_metrics()

class RatingRequest(BaseModel):
    user_id: int
    movie_id: int
    rating: float


class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str


class LoginRequest(BaseModel):
    identifier: str
    password: str

class DriftSimulationRequest(BaseModel):
    skew_type: str  # "negative" (lots of 1s), "positive" (lots of 5s), "genre_shift"


SESSION_COOKIE_NAME = "aura_session"
SESSION_MAX_AGE = 60 * 60 * 24 * 30
ADMIN_API_TOKEN = os.getenv("ADMIN_API_TOKEN", "")


def get_optional_user(request: Request) -> Dict[str, Any] | None:
    return get_user_by_session(request.cookies.get(SESSION_COOKIE_NAME, ""))


def get_current_user(request: Request) -> Dict[str, Any]:
    user = get_optional_user(request)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    return user


def require_admin_token(request: Request) -> None:
    if not ADMIN_API_TOKEN:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Administrative API is not configured")
    if not secrets.compare_digest(request.headers.get("X-Admin-Token", ""), ADMIN_API_TOKEN):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Administrative access required")


def set_session_cookie(response: Response, user_id: int) -> None:
    token = create_session(user_id)
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        secure=os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true",
        samesite=os.getenv("SESSION_COOKIE_SAMESITE", "lax"),
    )


def public_user(user: Dict[str, Any]) -> Dict[str, Any]:
    return {key: user[key] for key in ("id", "username", "email", "created_at") if key in user}


def validate_registration(request: RegisterRequest) -> tuple[str, str, str]:
    username = request.username.strip()
    email = request.email.strip().lower()
    if not re.fullmatch(r"[A-Za-z0-9_]{3,32}", username):
        raise HTTPException(status_code=422, detail="Username must be 3-32 letters, numbers, or underscores")
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise HTTPException(status_code=422, detail="Enter a valid email address")
    if len(request.password) < 8:
        raise HTTPException(status_code=422, detail="Password must be at least 8 characters")
    return username, email, request.password

def bg_retrain_task():
    """Background task for Phase 6 automated retraining pipeline."""
    global is_currently_retraining
    start_time = time.time()
    try:
        record_retraining_start()
        
        # Execute Phase 6 retraining pipeline with quality gate
        result = trigger_retraining(recommender)
        
        # Record metrics
        duration = time.time() - start_time
        record_retraining_end(success=result.get("success", False), duration_seconds=duration)
        
        # Update model metrics if available
        if result.get("metrics_comparison"):
            candidate_rmse = result["metrics_comparison"].get("candidate_rmse", 0)
            champion_rmse = result["metrics_comparison"].get("champion_rmse", 0)
            update_candidate_champion_metrics(candidate_rmse, champion_rmse)
        
        # Record promotion/rejection
        if result.get("promotion_status") == "accepted":
            record_model_promotion(
                result.get("candidate_version", "unknown"),
                result.get("champion_version", "unknown")
            )
        else:
            record_model_rejection()
        
        print(f"Retraining completed: {result.get('message', 'Unknown result')}")
        
    except Exception as e:
        print(f"Retraining task error: {e}")
        duration = time.time() - start_time
        record_retraining_end(success=False, duration_seconds=duration)
        record_model_rejection()
    finally:
        is_currently_retraining = False

@app.get("/")
def read_root():
    return {
        "status": "online",
        "service": "ott-recommendation-api",
        "model_version": recommender.model_version
    }


@app.post("/api/auth/register", status_code=status.HTTP_201_CREATED)
def register(request: RegisterRequest, response: Response):
    username, email, password = validate_registration(request)
    try:
        user = create_user(username, email, password)
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username or email is already registered")
    set_session_cookie(response, user["id"])
    return {"user": public_user(user)}


@app.post("/api/auth/login")
def login(request: LoginRequest, response: Response):
    user = get_user_for_login(request.identifier.strip().lower())
    if not user or not verify_password(request.password, user["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    set_session_cookie(response, user["id"])
    return {"user": public_user(user)}


@app.post("/api/auth/logout")
def logout(request: Request, response: Response):
    token = request.cookies.get(SESSION_COOKIE_NAME, "")
    if token:
        delete_session(token)
    response.delete_cookie(SESSION_COOKIE_NAME)
    return {"status": "success"}


@app.get("/api/auth/me")
def auth_me(user: Dict[str, Any] = Depends(get_current_user)):
    return {"user": public_user(user)}

@app.get("/api/movies")
def get_movies():
    try:
        return get_all_movies()
    except Exception as e:
        logger.exception("Movie catalog request failed")
        raise HTTPException(status_code=500, detail="Movie catalog is temporarily unavailable")

@app.get("/api/recommend")
def get_recommendations(
    request: Request,
    user: Dict[str, Any] = Depends(get_current_user),
):
    user_id = int(user["id"])
    start_time = time.time()
    
    # Add minor random network/processing jitter
    time.sleep(random.uniform(0.01, 0.05))
    
    try:
        recs = recommender.recommend(user_id=user_id, top_n=6)
        
        latency_ms = (time.time() - start_time) * 1000
        
        # Log telemetry async to DB
        log_inference(user_id, latency_ms, recommender.model_version)
        
        cold_start = not (
            recommender.reconstructed_matrix_df is not None and
            user_id in recommender.reconstructed_matrix_df.index
        )
        record_recommendation_success(latency_ms / 1000.0, len(recs), cold_start)
        
        return {
            "user_id": user_id,
            "recommendations": recs,
            "latency_ms": round(latency_ms, 2),
            "model_version": recommender.model_version
        }
    except Exception as e:
        latency_ms = (time.time() - start_time) * 1000
        log_inference(user_id, latency_ms, recommender.model_version)
        record_recommendation_error()
        logger.exception("Recommendation request failed")
        raise HTTPException(status_code=500, detail="Recommendations are temporarily unavailable")

@app.post("/api/rate")
def rate_movie(req: RatingRequest, request: Request):
    try:
        if not (1.0 <= req.rating <= 5.0):
            raise HTTPException(status_code=400, detail="Rating must be between 1.0 and 5.0")
        authenticated_user = get_current_user(request)
        user_id = int(authenticated_user["id"])
        if req.user_id != user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot rate for another user")
        insert_rating(user_id, req.movie_id, req.rating)
        return {"status": "success", "message": f"Rating of {req.rating} submitted for user {user_id}.", "user_id": user_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Rating request failed")
        raise HTTPException(status_code=500, detail="Rating could not be saved")


@app.get("/api/watchlist")
def list_watchlist(user: Dict[str, Any] = Depends(get_current_user)):
    return {"items": get_watchlist(int(user["id"]))}


@app.post("/api/watchlist/{movie_id}", status_code=status.HTTP_201_CREATED)
def add_watchlist(movie_id: int, user: Dict[str, Any] = Depends(get_current_user)):
    if not any(int(movie["id"]) == movie_id for movie in get_all_movies()):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Movie not found")
    if not add_to_watchlist(int(user["id"]), movie_id):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Movie is already in your watchlist")
    return {"status": "success", "movie_id": movie_id}


@app.delete("/api/watchlist/{movie_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_watchlist(movie_id: int, user: Dict[str, Any] = Depends(get_current_user)):
    if not remove_from_watchlist(int(user["id"]), movie_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Movie is not in your watchlist")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/api/history/ratings")
def rating_history(user: Dict[str, Any] = Depends(get_current_user)):
    return {"items": get_user_ratings(int(user["id"]))}


@app.get("/api/analytics/me")
def personal_analytics(user: Dict[str, Any] = Depends(get_current_user)):
    return get_user_analytics(int(user["id"]))

@app.get("/api/monitoring/metrics")
def get_metrics():
    try:
        refresh_dataset_metrics()
        telemetry = get_metrics_telemetry()
        drift_results = detect_drift()
        quality_report = evaluate_data_quality()
        drift_report = evaluate_data_drift()
        
        # Update drift metric
        update_drift_metric(drift_results.get("status", "Healthy"))
        
        return {
            "status": "online",
            "model_version": recommender.model_version,
            "is_retraining": is_currently_retraining,
            # Phase 4 fields (PSI-based drift)
            "drift_score": drift_results["psi"],
            "drift_status": drift_results["status"],
            "drift_message": drift_results["message"],
            # Phase 5 fields (Evidently)
            "data_quality_status": quality_report["status"],
            "data_quality_score": quality_report["quality_score"],
            "data_quality_summary": quality_report["summary"],
            "evidently_drift": drift_report,
            "phase5_drift": drift_report,
            # Phase 6 fields (Retraining status)
            "retraining_status": "in_progress" if is_currently_retraining else "idle",
            "ratings_distribution": {
                "baseline": drift_results.get("baseline_dist", []),
                "recent": drift_results.get("recent_dist", [])
            },
            "telemetry": telemetry
        }
    except Exception as e:
        logger.exception("Monitoring request failed")
        raise HTTPException(status_code=500, detail="Monitoring data is temporarily unavailable")

@app.get("/metrics")
def prometheus_metrics():
    return Response(content=generate_latest_metrics(), media_type=get_metrics_content_type())

@app.get("/api/health")
def health_check():
    return {
        "status": "online",
        "model_version": recommender.model_version,
        "is_retraining": is_currently_retraining
    }

@app.post("/api/retrain")
def trigger_retrain(background_tasks: BackgroundTasks, request: Request):
    """
    Trigger Phase 6 automated retraining pipeline.
    
    The pipeline will:
    1. Check for drift signals from Phase 5
    2. Train a candidate model if drift detected
    3. Evaluate candidate vs current champion
    4. Apply quality gate
    5. Promote candidate to champion if it passes
    6. Reject candidate and keep champion if quality gate fails
    
    Returns immediately with status; actual retraining happens in background.
    """
    global is_currently_retraining
    require_admin_token(request)
    
    if is_currently_retraining:
        return {
            "status": "running",
            "message": "Retraining already in progress. Please wait for completion.",
            "model_version": recommender.model_version
        }
    
    # Check drift condition first (quick check)
    try:
        drift_result = detect_drift()
        drift_status = drift_result.get("status", "Healthy")
        quality_result = evaluate_data_quality()
        quality_status = quality_result.get("status", "FAIL")
        
        if drift_status != "Drifted":
            return {
                "status": "skipped",
                "message": f"Retraining not triggered. Drift status: {drift_status} (expected: Drifted)",
                "model_version": recommender.model_version,
                "drift_info": drift_result
            }
        
        if quality_status == "FAIL":
            return {
                "status": "skipped",
                "message": "Retraining not triggered. Data quality is FAIL - fix data pipeline first",
                "model_version": recommender.model_version,
                "data_quality": quality_status
            }
        
        # Conditions met, trigger retraining in background
        is_currently_retraining = True
        background_tasks.add_task(bg_retrain_task)
        
        return {
            "status": "initiated",
            "message": "Phase 6 retraining pipeline initiated. Processing in background.",
            "model_version": recommender.model_version,
            "drift_status": drift_status,
            "data_quality_status": quality_status
        }
        
    except Exception:
        logger.exception("Retraining condition check failed")
        return {
            "status": "error",
            "message": "Unable to check retraining conditions",
            "model_version": recommender.model_version
        }

@app.post("/api/simulate-drift")
def simulate_drift(req: DriftSimulationRequest, request: Request):
    """
    Simulates model drift by injecting skewed user feedback into the ratings database.
    """
    try:
        require_admin_token(request)
        if req.skew_type not in {"negative", "positive", "genre_shift"}:
            raise HTTPException(status_code=422, detail="Unsupported drift simulation type")
        movies = get_all_movies()
        if not movies:
            raise HTTPException(status_code=500, detail="No movies seeded.")
            
        # We inject ratings for newly created user sessions (e.g. users 100 to 125)
        # to distort the recent ratings distribution
        if req.skew_type == "negative":
            # Inject ratings mostly of 1.0 or 2.0 stars
            for user_id in range(100, 125):
                rated_movies = random.sample(movies, random.randint(3, 6))
                for movie in rated_movies:
                    rating = random.choice([1.0, 1.5, 2.0])
                    insert_rating(user_id, movie["id"], rating)
            msg = "Injected 100+ low user ratings (1.0-2.0 stars), skewing ratings downward."
            
        elif req.skew_type == "genre_shift":
            # Users suddenly hate Action/Sci-fi (rate 1.0) and love Comedy (rate 5.0)
            for user_id in range(100, 125):
                rated_movies = random.sample(movies, random.randint(4, 7))
                for movie in rated_movies:
                    if movie["genre"] in ["Action", "Sci-Fi"]:
                        rating = random.choice([1.0, 1.5])
                    elif movie["genre"] == "Comedy":
                        rating = 5.0
                    else:
                        rating = random.choice([3.0, 4.0])
                    insert_rating(user_id, movie["id"], rating)
            msg = "Injected skewed genre ratings (hating action/sci-fi, loving comedy)."
            
        else:
            # Positive skew: inject ratings mostly of 5.0 stars
            for user_id in range(100, 125):
                rated_movies = random.sample(movies, random.randint(3, 6))
                for movie in rated_movies:
                    insert_rating(user_id, movie["id"], 5.0)
            msg = "Injected 100+ high user ratings (5.0 stars), skewing ratings upward."
            
        return {
            "status": "success",
            "message": f"Drift simulation injected successfully. {msg}"
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Drift simulation failed")
        raise HTTPException(status_code=500, detail="Drift simulation failed")

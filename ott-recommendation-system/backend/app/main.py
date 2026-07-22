import time
import random
from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Any

from .database import (
    init_db, 
    get_all_movies, 
    insert_rating, 
    log_inference, 
    get_metrics_telemetry,
    get_ratings_data
)
from .recommender import OTTRecommender
from .monitoring import detect_drift

# Initialize FastAPI
app = FastAPI(
    title="Personalized OTT Recommendation & Monitoring API",
    description="Backend service supplying recommendation inference, feedback gathering, drift monitoring and automated retraining.",
    version="1.0.0"
)

# CORS configurations
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global model state
recommender = OTTRecommender()
is_currently_retraining = False

# Seed/Init DB on startup
@app.on_event("startup")
def startup_event():
    init_db()
    recommender.load_model()

class RatingRequest(BaseModel):
    user_id: int
    movie_id: int
    rating: float

class DriftSimulationRequest(BaseModel):
    skew_type: str  # "negative" (lots of 1s), "positive" (lots of 5s), "genre_shift"

def bg_retrain_task():
    global is_currently_retraining
    try:
        # Simulate training delay
        time.sleep(4)
        recommender.train_model()
    finally:
        is_currently_retraining = False

@app.get("/")
def read_root():
    return {
        "status": "online",
        "service": "ott-recommendation-api",
        "model_version": recommender.model_version
    }

@app.get("/api/movies")
def get_movies():
    try:
        return get_all_movies()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/recommend")
def get_recommendations(user_id: int = Query(..., description="The ID of the user requesting recommendations")):
    start_time = time.time()
    
    # Add minor random network/processing jitter
    time.sleep(random.uniform(0.01, 0.05))
    
    try:
        recs = recommender.recommend(user_id=user_id, top_n=6)
        
        latency_ms = (time.time() - start_time) * 1000
        
        # Log telemetry async to DB
        log_inference(user_id, latency_ms, recommender.model_version)
        
        return {
            "user_id": user_id,
            "recommendations": recs,
            "latency_ms": round(latency_ms, 2),
            "model_version": recommender.model_version
        }
    except Exception as e:
        latency_ms = (time.time() - start_time) * 1000
        log_inference(user_id, latency_ms, recommender.model_version)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/rate")
def rate_movie(req: RatingRequest):
    try:
        if not (1.0 <= req.rating <= 5.0):
            raise HTTPException(status_code=400, detail="Rating must be between 1.0 and 5.0")
            
        insert_rating(req.user_id, req.movie_id, req.rating)
        return {"status": "success", "message": f"Rating of {req.rating} submitted for user {req.user_id}."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/monitoring/metrics")
def get_metrics():
    try:
        telemetry = get_metrics_telemetry()
        drift_results = detect_drift()
        
        return {
            "status": "online",
            "model_version": recommender.model_version,
            "is_retraining": is_currently_retraining,
            "drift_score": drift_results["psi"],
            "drift_status": drift_results["status"],
            "drift_message": drift_results["message"],
            "ratings_distribution": {
                "baseline": drift_results.get("baseline_dist", []),
                "recent": drift_results.get("recent_dist", [])
            },
            "telemetry": telemetry
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/retrain")
def trigger_retrain(background_tasks: BackgroundTasks):
    global is_currently_retraining
    if is_currently_retraining:
        return {"status": "running", "message": "Model retraining already in progress."}
        
    is_currently_retraining = True
    background_tasks.add_task(bg_retrain_task)
    return {"status": "initiated", "message": "Asynchronous model retraining triggered."}

@app.post("/api/simulate-drift")
def simulate_drift(req: DriftSimulationRequest):
    """
    Simulates model drift by injecting skewed user feedback into the ratings database.
    """
    try:
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

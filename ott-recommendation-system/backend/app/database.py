import os
import sqlite3
import random
from typing import List, Dict, Any

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "ott_recommendation.db")

MOVIES_SEED = [
    {"id": 1, "title": "Cosmic Odyssey", "genre": "Sci-Fi", "year": 2024, "rating": 4.5, "poster": "cosmic_odyssey"},
    {"id": 2, "title": "Shadow Protocol", "genre": "Action", "year": 2023, "rating": 4.2, "poster": "shadow_protocol"},
    {"id": 3, "title": "Love in Kyoto", "genre": "Drama", "year": 2022, "rating": 4.7, "poster": "love_in_kyoto"},
    {"id": 4, "title": "Midnight Laughs", "genre": "Comedy", "year": 2024, "rating": 3.9, "poster": "midnight_laughs"},
    {"id": 5, "title": "Spectral Whispers", "genre": "Horror", "year": 2023, "rating": 4.1, "poster": "spectral_whispers"},
    {"id": 6, "title": "Cyberpunk 2099", "genre": "Sci-Fi", "year": 2024, "rating": 4.6, "poster": "cyberpunk_2099"},
    {"id": 7, "title": "Apex Hunt", "genre": "Action", "year": 2024, "rating": 4.3, "poster": "apex_hunt"},
    {"id": 8, "title": "The Last Symphony", "genre": "Drama", "year": 2021, "rating": 4.8, "poster": "the_last_symphony"},
    {"id": 9, "title": "Stand-up Society", "genre": "Comedy", "year": 2023, "rating": 4.0, "poster": "stand_up_society"},
    {"id": 10, "title": "Abyss of Terror", "genre": "Horror", "year": 2022, "rating": 4.4, "poster": "abyss_of_terror"},
    {"id": 11, "title": "Nebula Explorer", "genre": "Sci-Fi", "year": 2023, "rating": 4.2, "poster": "nebula_explorer"},
    {"id": 12, "title": "Velocity Chase", "genre": "Action", "year": 2024, "rating": 4.5, "poster": "velocity_chase"},
    {"id": 13, "title": "Silent Tears", "genre": "Drama", "year": 2020, "rating": 4.3, "poster": "silent_tears"},
    {"id": 14, "title": "Office Jokes", "genre": "Comedy", "year": 2021, "rating": 3.8, "poster": "office_jokes"},
    {"id": 15, "title": "Haunted Manor", "genre": "Horror", "year": 2024, "rating": 4.0, "poster": "haunted_manor"},
    {"id": 16, "title": "Time Loop", "genre": "Sci-Fi", "year": 2024, "rating": 4.7, "poster": "time_loop"},
    {"id": 17, "title": "Rogue Agent", "genre": "Action", "year": 2023, "rating": 4.1, "poster": "rogue_agent"},
    {"id": 18, "title": "Summer Nostalgia", "genre": "Drama", "year": 2022, "rating": 4.6, "poster": "summer_nostalgia"},
    {"id": 19, "title": "Prank Wars", "genre": "Comedy", "year": 2023, "rating": 4.2, "poster": "prank_wars"},
    {"id": 20, "title": "The Conjuring Realm", "genre": "Horror", "year": 2024, "rating": 4.5, "poster": "conjuring_realm"}
]

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    data_dir = os.path.dirname(DB_PATH)
    os.makedirs(data_dir, exist_ok=True)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Create tables
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS movies (
            id INTEGER PRIMARY KEY,
            title TEXT NOT NULL,
            genre TEXT NOT NULL,
            year INTEGER,
            rating REAL,
            poster TEXT
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ratings (
            user_id INTEGER,
            movie_id INTEGER,
            rating REAL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, movie_id)
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS inference_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            user_id INTEGER,
            latency_ms REAL,
            model_version TEXT
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS retraining_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            data_points INTEGER,
            mse REAL,
            model_version TEXT
        )
    """)
    
    # Check if movies are empty
    cursor.execute("SELECT COUNT(*) FROM movies")
    if cursor.fetchone()[0] == 0:
        for movie in MOVIES_SEED:
            cursor.execute(
                "INSERT INTO movies (id, title, genre, year, rating, poster) VALUES (?, ?, ?, ?, ?, ?)",
                (movie["id"], movie["title"], movie["genre"], movie["year"], movie["rating"], movie["poster"])
            )
            
    # Check if ratings are empty, seed initial user interactions (collaborative filtering requires data!)
    cursor.execute("SELECT COUNT(*) FROM ratings")
    if cursor.fetchone()[0] == 0:
        # Let's seed ratings for users 1 to 50
        # Seed user preferences so the collaborative filtering has signal
        # For instance: 
        # - Users 1-15 like Sci-Fi and Action (rate high)
        # - Users 16-30 like Drama and Romance/Comedy (rate high)
        # - Users 31-50 like Horror and Action (rate high)
        for user_id in range(1, 51):
            num_ratings = random.randint(5, 12)
            rated_movies = random.sample(MOVIES_SEED, num_ratings)
            for movie in rated_movies:
                # Base rating
                r = random.randint(3, 5)
                
                # Apply bias based on user group preferences to seed patterns
                if user_id <= 15:
                    if movie["genre"] in ["Sci-Fi", "Action"]:
                        r = random.choice([4.5, 5.0])
                    elif movie["genre"] == "Comedy":
                        r = random.choice([2.0, 3.0])
                elif user_id <= 30:
                    if movie["genre"] in ["Drama", "Comedy"]:
                        r = random.choice([4.5, 5.0])
                    elif movie["genre"] == "Horror":
                        r = random.choice([1.0, 2.0])
                else:
                    if movie["genre"] in ["Horror", "Action"]:
                        r = random.choice([4.5, 5.0])
                    elif movie["genre"] == "Drama":
                        r = random.choice([2.0, 3.0])
                        
                cursor.execute(
                    "INSERT INTO ratings (user_id, movie_id, rating) VALUES (?, ?, ?)",
                    (user_id, movie["id"], float(r))
                )
    
    conn.commit()
    conn.close()

def get_all_movies() -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM movies")
    movies = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return movies

def get_ratings_data() -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, movie_id, rating FROM ratings")
    ratings = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return ratings

def insert_rating(user_id: int, movie_id: int, rating: float):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO ratings (user_id, movie_id, rating) VALUES (?, ?, ?)",
        (user_id, movie_id, rating)
    )
    conn.commit()
    conn.close()

def log_inference(user_id: int, latency_ms: float, model_version: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO inference_logs (user_id, latency_ms, model_version) VALUES (?, ?, ?)",
        (user_id, latency_ms, model_version)
    )
    conn.commit()
    conn.close()

def log_retraining(data_points: int, mse: float, model_version: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO retraining_history (data_points, mse, model_version) VALUES (?, ?, ?)",
        (data_points, mse, model_version)
    )
    conn.commit()
    conn.close()

def get_metrics_telemetry() -> Dict[str, Any]:
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Total recommendations served
    cursor.execute("SELECT COUNT(*) FROM inference_logs")
    total_inferences = cursor.fetchone()[0]
    
    # 2. Avg latency (last 100 queries)
    cursor.execute("SELECT AVG(latency_ms) FROM (SELECT latency_ms FROM inference_logs ORDER BY id DESC LIMIT 100)")
    avg_latency = cursor.fetchone()[0] or 0.0
    
    # 3. Active ratings count
    cursor.execute("SELECT COUNT(*) FROM ratings")
    total_ratings = cursor.fetchone()[0]
    
    # 4. Retraining runs
    cursor.execute("SELECT * FROM retraining_history ORDER BY id DESC")
    history = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    
    return {
        "total_inferences": total_inferences,
        "avg_latency_ms": round(avg_latency, 2),
        "total_ratings": total_ratings,
        "retraining_history": history
    }

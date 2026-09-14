import os
import sqlite3
import random
import hashlib
import secrets
from datetime import datetime, timezone
from typing import List, Dict, Any

DB_PATH = os.environ.get(
    "DATABASE_PATH",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "ott_recommendation.db")
)

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


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 310000)
    return f"pbkdf2_sha256$310000${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt_hex, digest_hex = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        candidate = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations)
        )
        return secrets.compare_digest(candidate.hex(), digest_hex)
    except (TypeError, ValueError):
        return False


def create_session(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    conn = get_db_connection()
    conn.execute(
        "INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
        (token_hash, user_id, datetime.fromtimestamp(datetime.now().timestamp() + 60 * 60 * 24 * 30, timezone.utc).isoformat()),
    )
    conn.commit()
    conn.close()
    return token


def get_user_by_session(token: str) -> Dict[str, Any] | None:
    if not token:
        return None
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    conn = get_db_connection()
    row = conn.execute(
        """SELECT users.id, users.username, users.email, users.created_at
           FROM sessions JOIN users ON users.id = sessions.user_id
           WHERE sessions.token_hash = ? AND sessions.expires_at > ?""",
        (token_hash, utc_now()),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def delete_session(token: str) -> None:
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    conn = get_db_connection()
    conn.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))
    conn.commit()
    conn.close()


def create_user(username: str, email: str, password: str) -> Dict[str, Any]:
    conn = get_db_connection()
    try:
        cursor = conn.execute(
            "INSERT INTO users (username, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
            (username, email, hash_password(password), utc_now()),
        )
        conn.commit()
        return {
            "id": cursor.lastrowid,
            "username": username,
            "email": email,
            "created_at": utc_now(),
        }
    finally:
        conn.close()


def get_user_for_login(identifier: str) -> Dict[str, Any] | None:
    conn = get_db_connection()
    row = conn.execute(
        "SELECT id, username, email, password_hash, created_at FROM users WHERE email = ? OR username = ?",
        (identifier, identifier),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_by_id(user_id: int) -> Dict[str, Any] | None:
    conn = get_db_connection()
    row = conn.execute(
        "SELECT id, username, email, created_at FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None

def _deduplicate_ratings(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    deduped: Dict[tuple, float] = {}
    for row in rows:
        user_id = int(row["user_id"])
        movie_id = int(row["movie_id"])
        pair = (user_id, movie_id)
        deduped[pair] = float(row["rating"])
    return [
        {"user_id": user_id, "movie_id": movie_id, "rating": rating}
        for (user_id, movie_id), rating in sorted(deduped.items(), key=lambda item: (item[0][0], item[0][1]))
    ]


def init_db():
    data_dir = os.path.dirname(DB_PATH)
    os.makedirs(data_dir, exist_ok=True)

    if os.path.exists(DB_PATH):
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.execute("PRAGMA quick_check")
            conn.close()
        except sqlite3.DatabaseError:
            os.remove(DB_PATH)
    
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

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            token_hash TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            expires_at TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS watchlist (
            user_id INTEGER NOT NULL,
            movie_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (user_id, movie_id),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (movie_id) REFERENCES movies(id) ON DELETE CASCADE
        )
    """)

    # Keep new account IDs separate from the seeded anonymous recommender IDs.
    cursor.execute(
        "INSERT OR REPLACE INTO sqlite_sequence (name, seq) VALUES ('users', MAX(10000, COALESCE((SELECT seq FROM sqlite_sequence WHERE name = 'users'), 0)))"
    )
    
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
                    "INSERT OR IGNORE INTO ratings (user_id, movie_id, rating) VALUES (?, ?, ?)",
                    (user_id, movie["id"], float(r))
                )

    cursor.execute("DELETE FROM ratings WHERE rowid NOT IN (SELECT MIN(rowid) FROM ratings GROUP BY user_id, movie_id)")
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
    cursor.execute("SELECT user_id, movie_id, rating FROM ratings ORDER BY user_id, movie_id")
    ratings = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return _deduplicate_ratings(ratings)

def insert_rating(user_id: int, movie_id: int, rating: float):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO ratings (user_id, movie_id, rating, timestamp) VALUES (?, ?, ?, ?)
           ON CONFLICT(user_id, movie_id) DO UPDATE SET rating = excluded.rating, timestamp = excluded.timestamp""",
        (user_id, movie_id, rating, utc_now())
    )
    conn.commit()
    conn.close()


def get_watchlist(user_id: int) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    rows = conn.execute(
        """SELECT movies.*, watchlist.created_at AS added_at
           FROM watchlist JOIN movies ON movies.id = watchlist.movie_id
           WHERE watchlist.user_id = ? ORDER BY watchlist.created_at DESC""",
        (user_id,),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def add_to_watchlist(user_id: int, movie_id: int) -> bool:
    conn = get_db_connection()
    cursor = conn.execute(
        "INSERT OR IGNORE INTO watchlist (user_id, movie_id, created_at) VALUES (?, ?, ?)",
        (user_id, movie_id, utc_now()),
    )
    conn.commit()
    conn.close()
    return cursor.rowcount > 0


def remove_from_watchlist(user_id: int, movie_id: int) -> bool:
    conn = get_db_connection()
    cursor = conn.execute(
        "DELETE FROM watchlist WHERE user_id = ? AND movie_id = ?", (user_id, movie_id)
    )
    conn.commit()
    conn.close()
    return cursor.rowcount > 0


def get_user_ratings(user_id: int) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    rows = conn.execute(
        """SELECT ratings.movie_id, ratings.rating, ratings.timestamp,
                  movies.title, movies.genre, movies.year, movies.poster
           FROM ratings JOIN movies ON movies.id = ratings.movie_id
           WHERE ratings.user_id = ? ORDER BY ratings.timestamp DESC""",
        (user_id,),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_user_analytics(user_id: int) -> Dict[str, Any]:
    ratings = get_user_ratings(user_id)
    distribution = {str(value): 0 for value in range(1, 6)}
    genres: Dict[str, int] = {}
    for item in ratings:
        rounded = str(max(1, min(5, round(float(item["rating"])))))
        distribution[rounded] += 1
        genre = item.get("genre") or "General"
        genres[genre] = genres.get(genre, 0) + 1
    conn = get_db_connection()
    watchlist_count = conn.execute(
        "SELECT COUNT(*) FROM watchlist WHERE user_id = ?", (user_id,)
    ).fetchone()[0]
    conn.close()
    return {
        "total_ratings": len(ratings),
        "average_rating": round(sum(float(item["rating"]) for item in ratings) / len(ratings), 2) if ratings else None,
        "rating_distribution": distribution,
        "favorite_genres": sorted(
            [{"genre": genre, "count": count} for genre, count in genres.items()],
            key=lambda item: item["count"], reverse=True,
        ),
        "watchlist_count": watchlist_count,
    }

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

import mlflow
import os
import pickle
import time
from pathlib import Path

import pandas as pd
import numpy as np
from mlflow.tracking import MlflowClient

ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_MLFLOW_DB = ROOT_DIR / "mlflow.db"
DEFAULT_MLFLOW_ARTIFACT_ROOT = ROOT_DIR / "mlruns"
EXPERIMENT_NAME = os.environ.get("MLFLOW_EXPERIMENT_NAME", "OTT Recommendation System")
MLFLOW_TRACKING_URI = os.environ.get("MLFLOW_TRACKING_URI", f"sqlite:///{DEFAULT_MLFLOW_DB.as_posix()}")
raw_artifact_root = os.environ.get("MLFLOW_ARTIFACT_ROOT", str(DEFAULT_MLFLOW_ARTIFACT_ROOT))

if raw_artifact_root.startswith("file://"):
    artifact_path = Path(raw_artifact_root[7:])
else:
    artifact_path = Path(raw_artifact_root)

MLFLOW_ARTIFACT_ROOT = artifact_path
os.makedirs(MLFLOW_ARTIFACT_ROOT, exist_ok=True)
mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
client = MlflowClient(MLFLOW_TRACKING_URI)
experiment = client.get_experiment_by_name(EXPERIMENT_NAME)
artifact_uri = MLFLOW_ARTIFACT_ROOT.as_uri()

if experiment is None:
    client.create_experiment(EXPERIMENT_NAME, artifact_location=artifact_uri)
else:
    current_artifact_location = experiment.artifact_location or ""
    if not current_artifact_location.startswith("file://"):
        import sqlite3

        conn = sqlite3.connect(DEFAULT_MLFLOW_DB)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE experiments SET artifact_location = ? WHERE experiment_id = ?",
            (artifact_uri, experiment.experiment_id)
        )
        conn.commit()
        conn.close()

mlflow.set_experiment(EXPERIMENT_NAME)

from typing import List, Dict, Any
from .database import get_ratings_data, get_all_movies, log_retraining


MODEL_DIR = os.environ.get(
    "MODEL_DIR",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models")
)
MODEL_PATH = os.path.join(MODEL_DIR, "recommender.pkl")

class OTTRecommender:
    def __init__(self):
        self.model_version = "v1.0.0"
        self.user_movie_matrix = None
        self.reconstructed_matrix_df = None
        self.movie_popularity = None
        self.all_movies_dict = {}
        self.is_trained = False
        
    def load_model(self) -> bool:
        if os.path.exists(MODEL_PATH):
            try:
                with open(MODEL_PATH, "rb") as f:
                    state = pickle.load(f)
                    self.__dict__.update(state)
                self.is_trained = True
                print(f"Loaded recommendation model {self.model_version}")
                return True
            except Exception as e:
                print(f"Error loading model: {e}")
        return False

    def save_model(self):
        os.makedirs(MODEL_DIR, exist_ok=True)
        with open(MODEL_PATH, "wb") as f:
            pickle.dump(self.__dict__, f)
        print(f"Saved recommendation model to {MODEL_PATH}")

    def train_model(self) -> Dict[str, Any]:
        ratings = get_ratings_data()
        movies = get_all_movies()
        mlflow.set_experiment(EXPERIMENT_NAME)
        run = mlflow.start_run(run_name=f"Training_{self.model_version}_{int(time.time())}")
        start_time = time.perf_counter()

        self.all_movies_dict = {m["id"]: m for m in movies}

        try:
            if not ratings:
                print("No rating data available for training.")
                return {
                    "status": "error",
                    "message": "No rating data available"
                }

            df = pd.DataFrame(ratings)
            movies_df = pd.DataFrame(movies)
            
            # Calculate backup popular movies (cold-start fallback)
            popularity = df.groupby('movie_id').agg(
                avg_rating=('rating', 'mean'),
                count=('rating', 'count')
            ).reset_index()
            
            # Merge popularity with all movies
            popularity = pd.merge(movies_df[['id']], popularity, left_on='id', right_on='movie_id', how='left').fillna(0)
            popularity['score'] = (popularity['avg_rating'] * 0.7) + (popularity['count'] * 0.3)
            self.movie_popularity = popularity.sort_values(by='score', ascending=False)['id'].tolist()
            
            # Pivot table
            pivot = df.pivot(index='user_id', columns='movie_id', values='rating')
            self.user_movie_matrix = pivot
            
            num_users, num_items = pivot.shape
            
            # Implement a Pure NumPy Funk SVD (Matrix Factorization) 
            # to bypass the sandboxed Application Control policies on sklearn's DLLs
            K = 6  # Latent factors
            np.random.seed(42)
            
            # Random initialization of User and Movie latent factors
            P = np.random.normal(0, 0.1, (num_users, K))
            Q = np.random.normal(0, 0.1, (num_items, K))
            
            users_idx_map = {uid: idx for idx, uid in enumerate(pivot.index)}
            movies_idx_map = {mid: idx for idx, mid in enumerate(pivot.columns)}
            
            # Extract ratings coordinates for training
            ratings_list = []
            for _, row in df.iterrows():
                uid = int(row['user_id'])
                mid = int(row['movie_id'])
                r = float(row['rating'])
                if uid in users_idx_map and mid in movies_idx_map:
                    ratings_list.append((users_idx_map[uid], movies_idx_map[mid], r))
                    
            # Stochastic Gradient Descent (SGD) for matrix factorization
            epochs = 35
            lr = 0.05      # Learning rate
            reg = 0.02   
            mlflow.log_param("Algorithm", "Funk SVD")
            mlflow.log_param("Latent Factors", K)
            mlflow.log_param("Epochs", epochs)
            mlflow.log_param("Learning Rate", lr)
            mlflow.log_param("Regularization", reg)
            mlflow.log_param("Dataset", "MovieLens Latest Small")
            
            for epoch in range(epochs):
                np.random.shuffle(ratings_list)
                for u, i, r in ratings_list:
                    pred = np.dot(P[u, :], Q[i, :])
                    err = r - pred
                    
                    # Update factors
                    p_old = P[u, :].copy()
                    P[u, :] += lr * (err * Q[i, :] - reg * P[u, :])
                    Q[i, :] += lr * (err * p_old - reg * Q[i, :])
                    
            # Reconstruct the rating predictions
            reconstructed = np.dot(P, Q.T)
            
            # Compute Training Mean Squared Error
            mask = pivot.notna().to_numpy()
            pivot_filled = pivot.fillna(0).to_numpy()
            diff = (pivot_filled - reconstructed) * mask
            mse = float(np.sum(diff ** 2) / np.sum(mask)) if np.sum(mask) > 0 else 0.0
            
            # Write reconstructed ratings back to DataFrame
            self.reconstructed_matrix_df = pd.DataFrame(
                reconstructed,
                index=pivot.index,
                columns=pivot.columns
            )
            
            print(f"Custom Funk SVD Model trained successfully. MSE: {mse:.4f}")
            training_time = time.perf_counter() - start_time

            mlflow.log_metric("Training_MSE", mse)
            mlflow.log_metric("Training_Samples", len(ratings))
            mlflow.log_metric("Number_of_Users", num_users)
            mlflow.log_metric("Number_of_Movies", num_items)
            mlflow.log_metric("Training_Time_Seconds", training_time)

            # Increment version
            try:
                ver_num = float(self.model_version.replace("v", ""))
                self.model_version = f"v{ver_num + 0.1:.1f}"
                mlflow.log_metric("Model_Version_Number", ver_num + 0.1)
            except Exception:
                self.model_version = "v1.1.0"

            self.is_trained = True
            self.save_model()
            mlflow.log_param("Model Version", self.model_version)
            mlflow.set_tag("model_version", self.model_version)

            if os.path.exists(MODEL_PATH):
                mlflow.log_artifacts(MODEL_DIR, artifact_path="models")

            # Log retraining event
            log_retraining(len(ratings), mse, self.model_version)
            return {
                "status": "success",
                "model_version": self.model_version,
                "data_points": len(ratings),
                "mse": mse
            }
        finally:
            if mlflow.active_run() is not None:
                mlflow.end_run()

    def recommend(self, user_id: int, top_n: int = 6) -> List[Dict[str, Any]]:
        if not self.is_trained:
            if not self.load_model():
                print("No model found. Training initial model...")
                self.train_model()
                
        if (self.reconstructed_matrix_df is not None and 
            user_id in self.reconstructed_matrix_df.index):
            
            user_predictions = self.reconstructed_matrix_df.loc[user_id]
            
            already_rated = []
            if self.user_movie_matrix is not None and user_id in self.user_movie_matrix.index:
                user_row = self.user_movie_matrix.loc[user_id]
                already_rated = user_row[user_row.notna()].index.tolist()
            
            predictions_filtered = user_predictions.drop(already_rated, errors='ignore')
            top_movie_ids = predictions_filtered.sort_values(ascending=False).index.tolist()[:top_n]
            
            if len(top_movie_ids) < top_n:
                for movie_id in self.movie_popularity:
                    if movie_id not in top_movie_ids and movie_id not in already_rated:
                        top_movie_ids.append(movie_id)
                        if len(top_movie_ids) == top_n:
                            break
        else:
            print(f"Cold start recommendations for user_id={user_id}")
            top_movie_ids = self.movie_popularity[:top_n] if self.movie_popularity else []
            
        recommendations = []
        for mid in top_movie_ids:
            if mid in self.all_movies_dict:
                recommendations.append(self.all_movies_dict[mid])
                
        return recommendations

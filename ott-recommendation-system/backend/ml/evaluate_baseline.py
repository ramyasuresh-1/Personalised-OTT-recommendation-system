"""
Baseline model evaluation module for OTT recommendation system.

Phase 1: Evaluates the current Funk SVD implementation using proper train/test splits.
"""

import json
import os
import sys
import csv
import time
from typing import List, Dict, Any, Tuple, Set
from pathlib import Path
import math

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from ml.split_data import create_splits, load_processed_ratings
from app.database import get_all_movies
import numpy as np
import pandas as pd


class BaselineEvaluator:
    """Evaluates Funk SVD baseline model."""
    
    def __init__(self):
        self.start_time = None
        self.end_time = None
    
    def train_funk_svd_from_ratings(
        self,
        train_ratings: List[Dict[str, Any]],
        k: int = 6,
        epochs: int = 35,
        lr: float = 0.05,
        reg: float = 0.02,
        random_state: int = 42
    ) -> Tuple[np.ndarray, np.ndarray, pd.DataFrame, Dict[str, Any]]:
        """
        Train Funk SVD model using training ratings only.
        
        Args:
            train_ratings: Training set ratings
            k: Number of latent factors
            epochs: Number of training epochs
            lr: Learning rate
            reg: Regularization parameter
            random_state: Random seed
        
        Returns:
            Tuple of (P matrix, Q matrix, pivot dataframe, movie popularity list)
        """
        
        # Create pivot table from training data only
        df = pd.DataFrame(train_ratings)
        pivot = df.pivot(index='user_id', columns='movie_id', values='rating')
        
        num_users, num_items = pivot.shape
        
        # Initialize latent factor matrices
        np.random.seed(random_state)
        P = np.random.normal(0, 0.1, (num_users, k))
        Q = np.random.normal(0, 0.1, (num_items, k))
        
        # Create index mappings
        users_idx_map = {uid: idx for idx, uid in enumerate(pivot.index)}
        movies_idx_map = {mid: idx for idx, mid in enumerate(pivot.columns)}
        
        # Extract training ratings as list of tuples
        ratings_list = []
        for _, row in df.iterrows():
            uid = int(row['user_id'])
            mid = int(row['movie_id'])
            r = float(row['rating'])
            if uid in users_idx_map and mid in movies_idx_map:
                ratings_list.append((users_idx_map[uid], movies_idx_map[mid], r))
        
        # SGD training
        for epoch in range(epochs):
            np.random.shuffle(ratings_list)
            for u, i, r in ratings_list:
                pred = np.dot(P[u, :], Q[i, :])
                err = r - pred
                
                # Update factors
                p_old = P[u, :].copy()
                P[u, :] += lr * (err * Q[i, :] - reg * P[u, :])
                Q[i, :] += lr * (err * p_old - reg * Q[i, :])
        
        # Calculate training MSE
        reconstructed = np.dot(P, Q.T)
        mask = pivot.notna().to_numpy()
        pivot_filled = pivot.fillna(0).to_numpy()
        diff = (pivot_filled - reconstructed) * mask
        mse = float(np.sum(diff ** 2) / np.sum(mask)) if np.sum(mask) > 0 else 0.0
        
        # Reconstruct DataFrame
        reconstructed_df = pd.DataFrame(
            reconstructed,
            index=pivot.index,
            columns=pivot.columns
        )
        
        # Calculate movie popularity from training data
        popularity = df.groupby('movie_id').agg(
            avg_rating=('rating', 'mean'),
            count=('rating', 'count')
        ).reset_index()
        
        movies = get_all_movies()
        movies_df = pd.DataFrame(movies)[['id']]
        popularity = pd.merge(movies_df, popularity, left_on='id', right_on='movie_id', how='left').fillna(0)
        popularity['score'] = (popularity['avg_rating'] * 0.7) + (popularity['count'] * 0.3)
        movie_popularity_list = popularity.sort_values(by='score', ascending=False)['id'].tolist()
        
        return P, Q, reconstructed_df, {
            'training_mse': mse,
            'pivot': pivot,
            'movies_idx_map': movies_idx_map,
            'users_idx_map': users_idx_map,
            'movie_popularity': movie_popularity_list
        }
    
    def predict_ratings(
        self,
        user_id: int,
        reconstructed_df: pd.DataFrame,
        user_movie_matrix: pd.DataFrame,
        movie_popularity: List[int],
        top_n: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get top-N recommendations for a user.
        
        Args:
            user_id: User ID
            reconstructed_df: Reconstructed rating matrix
            user_movie_matrix: Original user-movie matrix
            movie_popularity: Popularity-ranked movies
            top_n: Number of recommendations
        
        Returns:
            List of recommended movie IDs
        """
        
        recommendations = []
        
        # If user exists in training data
        if user_id in reconstructed_df.index:
            user_predictions = reconstructed_df.loc[user_id]
            
            # Get already-rated movies
            already_rated = []
            if user_id in user_movie_matrix.index:
                user_row = user_movie_matrix.loc[user_id]
                already_rated = user_row[user_row.notna()].index.tolist()
            
            # Get unrated predictions
            predictions_filtered = user_predictions.drop(already_rated, errors='ignore')
            top_movie_ids = predictions_filtered.sort_values(ascending=False).index.tolist()[:top_n]
            
            # Fill with popularity if needed
            if len(top_movie_ids) < top_n:
                for mid in movie_popularity:
                    if mid not in top_movie_ids and mid not in already_rated:
                        top_movie_ids.append(mid)
                        if len(top_movie_ids) == top_n:
                            break
        else:
            # Cold-start: use popularity
            top_movie_ids = movie_popularity[:top_n]
        
        return top_movie_ids
    
    def evaluate_model(
        self,
        reconstructed_df: pd.DataFrame,
        user_movie_matrix: pd.DataFrame,
        movie_popularity: List[int],
        ratings: List[Dict[str, Any]],
        k_values: List[int] = [5, 10],
        model_params: Dict[str, Any] | None = None
    ) -> Dict[str, Any]:
        """Evaluate an already-trained Funk SVD state without retraining it."""
        if not ratings:
            return {
                "rmse": 0.0, "mae": 0.0,
                "precision": {f"@{k}": 0.0 for k in k_values},
                "recall": {f"@{k}": 0.0 for k in k_values},
                "hit_rate": {f"@{k}": 0.0 for k in k_values},
                "ndcg": {f"@{k}": 0.0 for k in k_values},
                "catalog_coverage": 0.0, "recommendation_diversity": 0.0,
            }

        ratings_by_user: Dict[int, List[tuple[int, float]]] = {}
        for rating in ratings:
            ratings_by_user.setdefault(int(rating["user_id"]), []).append(
                (int(rating["movie_id"]), float(rating["rating"]))
            )

        squared_errors = []
        absolute_errors = []
        precisions = {k: [] for k in k_values}
        recalls = {k: [] for k in k_values}
        hit_rates = {k: [] for k in k_values}
        ndcgs = {k: [] for k in k_values}
        all_recommendations = []

        for user_id, interactions in ratings_by_user.items():
            recommendations = self.predict_ratings(
                user_id, reconstructed_df, user_movie_matrix, movie_popularity, max(k_values)
            )
            all_recommendations.extend(recommendations)
            relevant = {movie_id for movie_id, _ in interactions}
            for movie_id, actual in interactions:
                if user_id in reconstructed_df.index and movie_id in reconstructed_df.columns:
                    predicted = float(reconstructed_df.loc[user_id, movie_id])
                    squared_errors.append((actual - predicted) ** 2)
                    absolute_errors.append(abs(actual - predicted))
            for k in k_values:
                top_k = recommendations[:k]
                hits = len(set(top_k) & relevant)
                precisions[k].append(hits / k if k else 0.0)
                recalls[k].append(hits / len(relevant) if relevant else 0.0)
                hit_rates[k].append(1.0 if hits else 0.0)
                ndcgs[k].append(self._calculate_ndcg(set(top_k), relevant, k))

        movies = get_all_movies()
        return {
            "rmse": round(math.sqrt(sum(squared_errors) / len(squared_errors)), 4) if squared_errors else 0.0,
            "mae": round(sum(absolute_errors) / len(absolute_errors), 4) if absolute_errors else 0.0,
            "precision": {f"@{k}": round(sum(precisions[k]) / len(precisions[k]), 4) if precisions[k] else 0.0 for k in k_values},
            "recall": {f"@{k}": round(sum(recalls[k]) / len(recalls[k]), 4) if recalls[k] else 0.0 for k in k_values},
            "hit_rate": {f"@{k}": round(sum(hit_rates[k]) / len(hit_rates[k]), 4) if hit_rates[k] else 0.0 for k in k_values},
            "ndcg": {f"@{k}": round(sum(ndcgs[k]) / len(ndcgs[k]), 4) if ndcgs[k] else 0.0 for k in k_values},
            "catalog_coverage": round(len(set(all_recommendations)) / len(movies), 4) if movies else 0.0,
            "recommendation_diversity": round(len(set(all_recommendations)) / len(all_recommendations), 4) if all_recommendations else 0.0,
        }

    def evaluate_on_testset(
        self,
        train_ratings: List[Dict[str, Any]],
        test_ratings: List[Dict[str, Any]],
        k_values: List[int] = [5, 10]
    ) -> Dict[str, Any]:
        """
        Evaluate baseline model on test set.
        
        Args:
            train_ratings: Training ratings
            test_ratings: Test ratings
            k_values: K values for Precision@K, Recall@K, etc.
        
        Returns:
            Evaluation metrics dictionary
        """
        
        self.start_time = time.time()
        
        print("Training Funk SVD model on training data...")
        P, Q, reconstructed_df, model_data = self.train_funk_svd_from_ratings(
            train_ratings, k=6, epochs=35, lr=0.05, reg=0.02, random_state=42
        )
        
        print(f"Model trained. Training MSE: {model_data['training_mse']:.4f}")
        
        # Create user-movie matrix from training
        train_df = pd.DataFrame(train_ratings)
        user_movie_matrix = train_df.pivot(index='user_id', columns='movie_id', values='rating')
        
        movies = get_all_movies()
        movie_popularity = model_data['movie_popularity']
        
        # Prepare test set for evaluation
        test_df = pd.DataFrame(test_ratings)
        test_by_user = test_df.groupby('user_id').apply(
            lambda x: list(zip(x['movie_id'], x['rating']))
        ).to_dict()
        
        # Evaluation metrics
        rmse_values = []
        mae_values = []
        
        # Recommendation metrics
        precisions = {k: [] for k in k_values}
        recalls = {k: [] for k in k_values}
        ndcgs = {k: [] for k in k_values}
        hit_rates = {k: [] for k in k_values}
        
        all_recs = []  # For coverage/diversity
        all_relevant = set()
        
        # Evaluate per user in test set
        num_evaluated_users = 0
        num_cold_start_users = 0
        
        for user_id, test_interactions in test_by_user.items():
            if not test_interactions:
                continue
            
            # Get recommendations
            recs = self.predict_ratings(
                user_id, reconstructed_df, user_movie_matrix,
                movie_popularity, top_n=max(k_values)
            )
            all_recs.extend(recs)
            
            # Separate recommendations and ratings
            test_movies = [m for m, r in test_interactions]
            test_ratings_vals = [r for m, r in test_interactions]
            all_relevant.update(test_movies)
            
            # Check if cold-start
            if user_id not in user_movie_matrix.index:
                num_cold_start_users += 1
            
            # Rating prediction metrics
            for test_movie, test_rating in test_interactions:
                if test_movie in reconstructed_df.columns and user_id in reconstructed_df.index:
                    pred_rating = reconstructed_df.loc[user_id, test_movie]
                    rmse_values.append((test_rating - pred_rating) ** 2)
                    mae_values.append(abs(test_rating - pred_rating))
            
            # Recommendation metrics
            relevant_movies = set(test_movies)
            
            for k in k_values:
                top_k_recs = set(recs[:k])
                
                # Precision@K
                hits = len(top_k_recs & relevant_movies)
                precision_k = hits / k if k > 0 else 0
                precisions[k].append(precision_k)
                
                # Recall@K
                recall_k = hits / len(relevant_movies) if len(relevant_movies) > 0 else 0
                recalls[k].append(recall_k)
                
                # Hit Rate@K
                hit_rate_k = 1.0 if hits > 0 else 0.0
                hit_rates[k].append(hit_rate_k)
                
                # NDCG@K
                ndcg_k = self._calculate_ndcg(top_k_recs, relevant_movies, k)
                ndcgs[k].append(ndcg_k)
            
            num_evaluated_users += 1
        
        # Calculate averages
        avg_rmse = math.sqrt(sum(rmse_values) / len(rmse_values)) if rmse_values else 0.0
        avg_mae = sum(mae_values) / len(mae_values) if mae_values else 0.0
        
        avg_precisions = {k: sum(precisions[k]) / len(precisions[k]) if precisions[k] else 0.0 for k in k_values}
        avg_recalls = {k: sum(recalls[k]) / len(recalls[k]) if recalls[k] else 0.0 for k in k_values}
        avg_hit_rates = {k: sum(hit_rates[k]) / len(hit_rates[k]) if hit_rates[k] else 0.0 for k in k_values}
        avg_ndcgs = {k: sum(ndcgs[k]) / len(ndcgs[k]) if ndcgs[k] else 0.0 for k in k_values}
        
        # Coverage: unique movies recommended / total movies
        unique_recs = len(set(all_recs))
        total_movies = len(movies)
        coverage = unique_recs / total_movies if total_movies > 0 else 0.0
        
        # Diversity: average distance between recommendations (simplified)
        diversity = len(set(all_recs)) / len(all_recs) if all_recs else 0.0
        
        self.end_time = time.time()
        eval_time = self.end_time - self.start_time
        
        # Compile results
        results = {
            "evaluation_timestamp": "2026-08-11",
            "evaluation_time_seconds": round(eval_time, 2),
            
            # Rating prediction
            "rmse": round(avg_rmse, 4),
            "mae": round(avg_mae, 4),
            
            # Recommendation
            "precision": {f"@{k}": round(avg_precisions[k], 4) for k in k_values},
            "recall": {f"@{k}": round(avg_recalls[k], 4) for k in k_values},
            "hit_rate": {f"@{k}": round(avg_hit_rates[k], 4) for k in k_values},
            "ndcg": {f"@{k}": round(avg_ndcgs[k], 4) for k in k_values},
            
            # Coverage & Diversity
            "catalog_coverage": round(coverage, 4),
            "recommendation_diversity": round(diversity, 4),
            
            # Evaluation setup
            "evaluation_setup": {
                "num_test_users": num_evaluated_users,
                "num_cold_start_users": num_cold_start_users,
                "num_test_ratings": len(test_ratings),
                "k_values": k_values,
                "model_params": {
                    "algorithm": "Funk SVD",
                    "latent_factors": 6,
                    "epochs": 35,
                    "learning_rate": 0.05,
                    "regularization": 0.02
                }
            }
        }
        
        return results
    
    def _calculate_ndcg(self, recommendations: Set, relevant: Set, k: int) -> float:
        """Calculate NDCG@K."""
        if not relevant or not recommendations:
            return 0.0
        
        # Simple NDCG: hits at positions
        hits = recommendations & relevant
        if not hits:
            return 0.0
        
        # DCG: sum of 1/log(position+1) for hits
        dcg = 0.0
        position = 1
        for item in recommendations:
            if item in relevant:
                dcg += 1.0 / math.log(position + 1, 2)
            position += 1
        
        # IDCG: ideal DCG
        idcg = sum(1.0 / math.log(i + 2, 2) for i in range(min(k, len(relevant))))
        
        ndcg = dcg / idcg if idcg > 0 else 0.0
        return ndcg


def evaluate_baseline(
    train_file: str = "backend/data/splits/train.csv",
    test_file: str = "backend/data/splits/test.csv"
) -> Dict[str, Any]:
    """
    Run baseline evaluation.
    
    Args:
        train_file: Path to training ratings
        test_file: Path to test ratings
    
    Returns:
        Evaluation results dictionary
    """
    
    # Load splits
    print(f"Loading training set from {train_file}...")
    train_ratings = load_processed_ratings(train_file)
    
    print(f"Loading test set from {test_file}...")
    test_ratings = load_processed_ratings(test_file)
    
    # Evaluate
    evaluator = BaselineEvaluator()
    results = evaluator.evaluate_on_testset(train_ratings, test_ratings, k_values=[5, 10])
    
    return results


def save_evaluation_results(results: Dict[str, Any], output_dir: str = "docs") -> str:
    """
    Save evaluation results to JSON.
    
    Args:
        results: Evaluation results dictionary
        output_dir: Output directory
    
    Returns:
        Path to saved file
    """
    
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, "baseline_evaluation.json")
    
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"Saved evaluation results to {output_file}")
    
    # Print summary
    print("\n" + "="*60)
    print("BASELINE EVALUATION RESULTS")
    print("="*60)
    print(f"RMSE: {results.get('rmse', 'N/A')}")
    print(f"MAE:  {results.get('mae', 'N/A')}")
    print(f"\nPrecision: {results.get('precision', {})}")
    print(f"Recall:    {results.get('recall', {})}")
    print(f"Hit Rate:  {results.get('hit_rate', {})}")
    print(f"NDCG:      {results.get('ndcg', {})}")
    print(f"\nCoverage:  {results.get('catalog_coverage', 'N/A')}")
    print(f"Diversity: {results.get('recommendation_diversity', 'N/A')}")
    print("="*60)
    
    return output_file


if __name__ == "__main__":
    print("Running baseline evaluation...")
    results = evaluate_baseline()
    save_evaluation_results(results)
    print("Baseline evaluation complete!")

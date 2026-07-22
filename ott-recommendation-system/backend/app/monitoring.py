import numpy as np
import pandas as pd
from typing import Dict, Any
from .database import get_ratings_data

def calculate_psi(expected: np.ndarray, actual: np.ndarray, num_buckets: int = 5) -> float:
    """
    Computes Population Stability Index (PSI) between two distributions.
    expected: baseline rating counts
    actual: production/recent rating counts
    """
    # Normalize to probabilities
    exp_pct = expected / np.sum(expected) if np.sum(expected) > 0 else np.ones(num_buckets) / num_buckets
    act_pct = actual / np.sum(actual) if np.sum(actual) > 0 else np.ones(num_buckets) / num_buckets
    
    # Avoid zero division/log errors by adding a small constant epsilon
    eps = 1e-4
    exp_pct = np.clip(exp_pct, eps, 1 - eps)
    act_pct = np.clip(act_pct, eps, 1 - eps)
    
    # Re-normalize
    exp_pct /= np.sum(exp_pct)
    act_pct /= np.sum(act_pct)
    
    # Calculate PSI
    psi_value = np.sum((act_pct - exp_pct) * np.log(act_pct / exp_pct))
    return float(psi_value)

def detect_drift() -> Dict[str, Any]:
    """
    Compares recent ratings (last 100) vs baseline ratings (all ratings) to determine drift.
    """
    ratings = get_ratings_data()
    
    if len(ratings) < 10:
        return {
            "psi": 0.0,
            "status": "Healthy",
            "message": "Insufficient rating logs to compute drift."
        }
        
    df = pd.DataFrame(ratings)
    
    # Baseline: all ratings except the last 30%
    split_idx = int(len(df) * 0.7)
    if split_idx < 5:
        split_idx = len(df)
        
    baseline_ratings = df.iloc[:split_idx]['rating']
    # Recent: last 30 ratings or 30% of ratings
    recent_count = max(15, int(len(df) * 0.3))
    recent_ratings = df.iloc[-recent_count:]['rating']
    
    # Rating values from 1.0 to 5.0 in 0.5 increments or 1.0 increments.
    # To keep simple, let's bucket them into standard ranges:
    # Bucket 1: <=2.0 (Low)
    # Bucket 2: 2.5 - 3.0 (Mediocre)
    # Bucket 3: 3.5 - 4.0 (Good)
    # Bucket 4: 4.5 (Very Good)
    # Bucket 5: 5.0 (Excellent)
    def bucket_ratings(series: pd.Series) -> np.ndarray:
        counts = [0] * 5
        for val in series:
            if val <= 2.0:
                counts[0] += 1
            elif val <= 3.0:
                counts[1] += 1
            elif val <= 4.0:
                counts[2] += 1
            elif val < 5.0:
                counts[3] += 1
            else:
                counts[4] += 1
        return np.array(counts, dtype=float)
        
    expected_counts = bucket_ratings(baseline_ratings)
    actual_counts = bucket_ratings(recent_ratings)
    
    psi = calculate_psi(expected_counts, actual_counts)
    
    # Classify status
    if psi < 0.1:
        status = "Healthy"
        message = "Model performance is stable. Ratings distribution matches training baseline."
    elif psi < 0.25:
        status = "Warning"
        message = "Moderate rating distribution shift detected. Monitoring recommended."
    else:
        status = "Drifted"
        message = "Significant data drift detected! Retraining recommended to realign recommendations."
        
    return {
        "psi": round(psi, 4),
        "status": status,
        "message": message,
        "baseline_dist": expected_counts.tolist(),
        "recent_dist": actual_counts.tolist()
    }
